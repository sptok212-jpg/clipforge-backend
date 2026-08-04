import os
import uuid
import yt_dlp

TMP_DIR = "/tmp/clipforge"
os.makedirs(TMP_DIR, exist_ok=True)


def download_video(youtube_url: str) -> str:
    """
    Downloads a YouTube video and returns the local file path.
    """
    job_id = str(uuid.uuid4())
    output_path = os.path.join(TMP_DIR, f"{job_id}.mp4")

    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": output_path,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])

    if not os.path.exists(output_path):
        # yt-dlp sometimes appends extension differently
        for f in os.listdir(TMP_DIR):
            if f.startswith(job_id):
                return os.path.join(TMP_DIR, f)
        raise FileNotFoundError("Download failed: no output file found")

    return output_path


def get_video_info(youtube_url: str) -> dict:
    """
    Fetches metadata (title, duration, thumbnail) without downloading.
    """
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
    return {
        "title": info.get("title"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
    }
