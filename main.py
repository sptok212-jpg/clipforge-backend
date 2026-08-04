import os
import shutil
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

from models import JobRequest, JobResponse
from services.downloader import get_local_duration, download_video
from services.transcriber import extract_audio, transcribe_audio
from services.analyzer import analyze_transcript
from services.renderer import render_clip, upload_clip_to_storage
from supabase_client import supabase

app = FastAPI(title="ClipForge Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://clipper.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/tmp/clipforge_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/jobs", response_model=JobResponse)
def create_job(req: JobRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_job, req)
    return JobResponse(job_id=req.project_id, status="processing")

@app.post("/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: str = Form(""),
    user_id: str = Form(""),
):
    """Upload video file dan trigger processing"""
    try:
        file_path = os.path.join(UPLOAD_DIR, f"{project_id}.mp4")
        # STREAM ke disk, JANGAN muat seluruh file ke RAM
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1 MB per chunk
                f.write(chunk)
        req = JobRequest(youtube_url=None, project_id=project_id, user_id=user_id)
        background_tasks.add_task(process_job, req)
        return {"status": "uploaded", "file_path": file_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def process_job(req: JobRequest):
    """Process uploaded video file or YouTube URL"""
    video_path = None
    audio_path = None
    try:
        supabase.table("projects").update({"status": "processing"}).eq(
            "id", req.project_id
        ).execute()

        # CEK APAKAH YOUTUBE URL ATAU UPLOAD FILE
        if req.youtube_url:
            print(f"DEBUG: Mode YouTube, mulai download...")
            video_path = download_video(req.youtube_url)
        else:
            print(f"DEBUG: Mode Upload File, mencari file...")
            video_path = os.path.join(UPLOAD_DIR, f"{req.project_id}.mp4")
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")

        video_duration = get_local_duration(video_path)
        print(f"DEBUG: Video duration: {video_duration}s")

        audio_path = extract_audio(video_path)
        transcript = transcribe_audio(audio_path)
        print(f"DEBUG: Transkripsi selesai. Total segmen: {len(transcript['segments'])}")

        clip_segments = analyze_transcript(transcript["segments"])
        print(f"DEBUG: Total segments from AI: {len(clip_segments)}")

        if len(clip_segments) == 0:
            print("DEBUG: AI tidak menemukan clip, kemungkinan transkrip kosong/gagal.")

        rendered_count = 0
        MIN_CLIP_DURATION = 20.0
        
        for idx, seg in enumerate(clip_segments):
            raw_start = float(seg.get("start", 0))
            raw_end = float(seg.get("end", 0))
            
            if raw_end <= raw_start:
                continue

            seg_start = max(0.0, min(raw_start, video_duration - 1))
            seg_end = min(raw_end, video_duration)
            seg_end = max(seg_end, seg_start + MIN_CLIP_DURATION)
            seg_end = min(seg_end, video_duration)
            
            if seg_end - seg_start < 15:
                continue

            print(f"DEBUG: Render seg {idx+1} - {seg_start:.1f}-{seg_end:.1f}s")

            try:
                local_clip_path = render_clip(
                    video_path,
                    seg_start,
                    seg_end,
                    seg["caption_text"],
                )
                storage_path = f"{req.user_id}/{req.project_id}/{seg['title'][:30]}.mp4"
                public_url = upload_clip_to_storage(supabase, local_clip_path, storage_path)

                supabase.table("clips").insert({
                    "project_id": req.project_id,
                    "user_id": req.user_id,
                    "title": seg["title"],
                    "topic": seg["topic"],
                    "viral_score": seg["viral_score"],
                    "transcript": seg["caption_text"],
                    "start_time": int(seg_start),
                    "end_time": int(seg_end),
                    "video_url": public_url,
                    "status": "completed",
                }).execute()

                os.remove(local_clip_path)
                rendered_count += 1
                print(f"DEBUG: Rendered segment {idx+1} SUKSES")
            except Exception as render_err:
                print(f"DEBUG: Error rendering segment {idx+1}: {str(render_err)[:300]}")
                continue

        print(f"DEBUG: Total rendered: {rendered_count}/{len(clip_segments)}")

        supabase.table("projects").update({
            "status": "completed",
            "title": "Uploaded Video",
            "source_duration": int(video_duration),
        }).eq("id", req.project_id).execute()

    except Exception as e:
        print(f"DEBUG: UTAMA ERROR: {str(e)[:500]}")
        supabase.table("projects").update({
            "status": "failed",
            "error_message": str(e)[:500],
        }).eq("id", req.project_id).execute()

    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
