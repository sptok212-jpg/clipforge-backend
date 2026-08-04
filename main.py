import os
import shutil
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

from models import JobRequest, JobResponse
from services.downloader import get_local_duration
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
        
        # STREAM ke disk, JANGAN muat seluruh file ke RAM (mencegah error di Railway)
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # Baca 1 MB per chunk
                f.write(chunk)
                
        req = JobRequest(youtube_url=None, project_id=project_id, user_id=user_id)
        background_tasks.add_task(process_job, req)
        return {"status": "uploaded", "file_path": file_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def process_job(req: JobRequest):
    """Process uploaded video file"""
    video_path = None
    audio_path = None
    try:
        supabase.table("projects").update({"status": "processing"}).eq(
            "id", req.project_id
        ).execute()

        # Ambil video dari upload folder
        video_path = os.path.join(UPLOAD_DIR, f"{req.project_id}.mp4")
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        video_duration = get_local_duration(video_path)
        print(f"DEBUG: Video duration: {video_duration}s")

        audio_path = extract_audio(video_path)
        transcript = transcribe_audio(audio_path)

        clip_segments = analyze_transcript(transcript["segments"])
        print(f"DEBUG: Total segments from AI: {len(clip_segments)}")

        rendered_count = 0
        MIN_CLIP_DURATION = 20.0  # Minimal durasi 20 detik sesuai prompt AI
        
        for idx, seg in enumerate(clip_segments):
            raw_start = float(seg.get("start", 0))
            raw_end = float(seg.get("end", 0))
            
            # Skip jika segment tidak valid
            if raw_end <= raw_start:
                print(f"DEBUG: SKIPPED seg {idx+1} end<=start")
                continue

            seg_start = max(0.0, min(raw_start, video_duration - 1))
            seg_end = min(raw_end, video_duration)
            
            # PAKSA minimal durasi 20 detik (sebelumnya hanya 5 detik)
            seg_end = max(seg_end, seg_start + MIN_CLIP_DURATION)
            seg_end = min(seg_end, video_duration) # Pastikan tidak melebihi durasi video
            
            # Skip jika setelah dipaksa 20 detik, durasinya terlalu mepet
            if seg_end - seg_start < 15:
                print(f"DEBUG: SKIPPED seg {idx+1} too short after clamp ({seg_start:.1f}-{seg_end:.1f}s)")
                continue

            print(f"DEBUG: Segment {idx+1} '{seg['title']}' - {seg_start:.1f}-{seg_end:.1f}s (dur={seg_end-seg_start:.1f}s)")

            if seg_start >= video_duration - 2:
                print(f"DEBUG: SKIPPED segment {idx+1} (start too close to end)")
                continue

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
                print(f"DEBUG: Rendered segment {idx+1}")
            except Exception as render_err:
                print(f"DEBUG: Error rendering segment {idx+1}: {str(render_err)[:200]}")
                continue

        print(f"DEBUG: Total rendered: {rendered_count}/{len(clip_segments)}")

        supabase.table("projects").update({
            "status": "completed",
            "title": "Uploaded Video",
            "source_duration": int(video_duration),
        }).eq("id", req.project_id).execute()

    except Exception as e:
        print(f"DEBUG: Error: {str(e)[:300]}")
        supabase.table("projects").update({
            "status": "failed",
            "error_message": str(e)[:500],
        }).eq("id", req.project_id).execute()

    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
