import os
import uuid
import json
import subprocess
import yt_dlp

TMP_DIR = "/tmp/clipforge"
os.makedirs(TMP_DIR, exist_ok=True)

COOKIES_PATH = "/tmp/clipforge/cookies.txt"


def _write_cookies_file() -> str | None:
    cookies_content = os.environ.get("YOUTUBE_COOKIES")
    if not cookies_content:
        return None
    with open(COOKIES_PATH, "w") as f:
        f.write(cookies_content)
    return COOKIES_PATH


def _base_ydl_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["ios"],
            }
        },
    }
    cookies_file = _write_cookies_file()
    if cookies_file:
        opts["cookiefile"] = cookies_file
    return opts


def download_video(youtube_url: str) -> str:
    job_id = str(uuid.uuid4())
    output_path = os.path.join(TMP_DIR, f"{job_id}.mp4")

    ydl_opts = {
        **_base_ydl_opts(),
        "format": "best",
        "outtmpl": output_path,
        "merge_output_format": "mp4",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])

    if not os.path.exists(output_path):
        for f in os.listdir(TMP_DIR):
            if f.startswith(job_id):
                return os.path.join(TMP_DIR, f)
        raise FileNotFoundError("Download failed: no output file found")

    return output_path


def get_video_info(youtube_url: str) -> dict:
    ydl_opts = {
        **_base_ydl_opts(),
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
    return {
        "title": info.get("title"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
    }


def get_local_duration(video_path: str) -> float:
    """
    Reads the actual duration of a downloaded video file using ffprobe.
    More reliable than YouTube's reported duration.
    """
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", video_path,
        ],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
