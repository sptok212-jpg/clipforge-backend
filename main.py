import os
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from models import JobRequest, JobResponse
from services.downloader import download_video, get_video_info
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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", response_model=JobResponse)
def create_job(req: JobRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_job, req)
    return JobResponse(job_id=req.project_id, status="processing")


def process_job(req: JobRequest):
    video_path = None
    audio_path = None
    try:
        supabase.table("projects").update({"status": "processing"}).eq(
            "id", req.project_id
        ).execute()

        video_path = download_video(req.youtube_url)
        info = get_video_info(req.youtube_url)
        video_duration = info.get("duration") or 0

        audio_path = extract_audio(video_path)
        transcript = transcribe_audio(audio_path)

        clip_segments = analyze_transcript(transcript["segments"])

        for seg in clip_segments:
            seg_start = max(0, min(seg["start"], video_duration - 1)) if video_duration else seg["start"]
            seg_end = max(seg_start + 5, min(seg["end"], video_duration)) if video_duration else seg["end"]

            if video_duration and seg_start >= video_duration - 2:
                # This segment is essentially out of range, skip it
                continue

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
                "start_time": seg_start,
                "end_time": seg_end,
                "video_url": public_url,
                "status": "completed",
            }).execute()

            os.remove(local_clip_path)

        supabase.table("projects").update({
            "status": "completed",
            "title": info.get("title"),
            "thumbnail_url": info.get("thumbnail"),
            "source_duration": video_duration,
        }).eq("id", req.project_id).execute()

    except Exception as e:
        supabase.table("projects").update({
            "status": "failed",
            "error_message": str(e)[:500],
        }).eq("id", req.project_id).execute()

    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
