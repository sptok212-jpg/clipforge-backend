import os
import uuid
import json
import subprocess
import yt_dlp

TMP_DIR = "/tmp/clipforge"
os.makedirs(TMP_DIR, exist_ok=True)

COOKIES_PATH = "/tmp/clipforge/cookies.txt"
CLIENTS_TO_TRY = ["ios", "android", "web"]


def _write_cookies_file() -> str | None:
    cookies_content = os.environ.get("YOUTUBE_COOKIES")
    if not cookies_content:
        return None
    with open(COOKIES_PATH, "w") as f:
        f.write(cookies_content)
    return COOKIES_PATH


def _opts_for_client(client: str) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": [client]}},
    }
    cookies_file = _write_cookies_file()
    if cookies_file:
        opts["cookiefile"] = cookies_file
    return opts


def _extract_info_with_fallback(youtube_url: str) -> dict:
    """
    Tries each YouTube player client in turn until one returns
    actual downloadable formats. Used for metadata-only lookups
    (get_video_info) where there's no download-time mismatch risk.
    """
    last_error = None
    for client in CLIENTS_TO_TRY:
        try:
            opts = {**_opts_for_client(client), "skip_download": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
            if info.get("formats"):
                info["_client_used"] = client
                return info
        except Exception as e:
            last_error = e
            continue
    if last_error:
        raise last_error
    raise RuntimeError("No client returned usable formats for this video.")


def download_video(youtube_url: str) -> str:
    """
    Downloads the video in a single extract+download pass per client,
    using a flexible format selector so yt-dlp validates format
    availability at download time instead of relying on a format_id
    pinned from a separate, earlier extraction (which can go stale).
    """
    job_id = str(uuid.uuid4())
    output_path = os.path.join(TMP_DIR, f"{job_id}.mp4")

    last_error = None
    for client in CLIENTS_TO_TRY:
        ydl_opts = {
            **_opts_for_client(client),
            "format": "bv*+ba/b/best",
            "outtmpl": output_path,
            "merge_output_format": "mp4",
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
        except Exception as e:
            last_error = e
            continue  # try the next client

        if os.path.exists(output_path):
            return output_path
        for f in os.listdir(TMP_DIR):
            if f.startswith(job_id):
                return os.path.join(TMP_DIR, f)

    raise RuntimeError(f"Download gagal di semua client. Error terakhir: {last_error}")


def get_video_info(youtube_url: str) -> dict:
    info = _extract_info_with_fallback(youtube_url)
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
