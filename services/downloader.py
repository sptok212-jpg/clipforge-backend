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


def download_video(youtube_url: str) -> str:
    job_id = str(uuid.uuid4())
    # Gunakan %(ext)s agar yt-dlp menulis ekstensi asli (misal .webm atau .mp4)
    output_tmpl = os.path.join(TMP_DIR, f"{job_id}.%(ext)s")
    cookies_file = _write_cookies_file()
    
    # Paksa cari MP4, kalau tidak ada baru ambil best
    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
        "outtmpl": output_tmpl,
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        "merge_output_format": "mp4", # Wajib merge ke mp4 kalau video & audio terpisah
    }
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])
        
    # Cari file yang sebenarnya diunduh
    downloaded_file = None
    for f in os.listdir(TMP_DIR):
        if f.startswith(job_id):
            downloaded_file = os.path.join(TMP_DIR, f)
            break
            
    if not downloaded_file:
        raise FileNotFoundError("Download failed")
        
    # Jika ternyata bukan mp4 (misal webm), kita rename path-nya agar ffmpeg tahu
    if not downloaded_file.endswith(".mp4"):
        new_path = downloaded_file.rsplit(".", 1)[0] + ".mp4"
        os.rename(downloaded_file, new_path)
        return new_path
        
    return downloaded_file


def get_video_info(youtube_url: str) -> dict:
    cookies_file = _write_cookies_file()
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
    }
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        return {
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
        }


def get_local_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
