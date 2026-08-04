import os
import uuid
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
                "player_client": ["android"],
            }
        },
    }
    cookies_file = _write_cookies_file()
    if cookies_file:
        opts["cookiefile"] = cookies_file
    return opts


def _pick_best_format_id(formats: list[dict]) -> str:
    """
    Inspects the actual formats YouTube returned for this video and
    picks the best usable one ourselves, instead of guessing a format
    selector string that may not match what's actually available.
    """
    # Prefer a combined (video+audio) mp4 format, highest resolution first
    combined = [
        f for f in formats
        if f.get("vcodec") != "none" and f.get("acodec") != "none"
    ]
    if combined:
        combined.sort(key=lambda f: f.get("height") or 0, reverse=True)
        return combined[0]["format_id"]

    # Fall back to the highest-resolution video-only format
    video_only = [f for f in formats if f.get("vcodec") != "none"]
    if video_only:
        video_only.sort(key=lambda f: f.get("height") or 0, reverse=True)
        return video_only[0]["format_id"]

    raise RuntimeError("No downloadable formats found for this video.")


def download_video(youtube_url: str) -> str:
    job_id = str(uuid.uuid4())
    output_path = os.path.join(TMP_DIR, f"{job_id}.mp4")

    # Step 1: extract info (no download) to see what formats truly exist
    info_opts = {**_base_ydl_opts(), "skip_download": True}
    with yt_dlp.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)

    formats = info.get("formats") or []
    if not formats:
        raise RuntimeError(
            "YouTube returned no available formats for this video "
            "(it may be blocked, private, or region-restricted)."
        )

    format_id = _pick_best_format_id(formats)

    # Step 2: download using the exact format_id we confirmed exists
    ydl_opts = {
        **_base_ydl_opts(),
        "format": format_id,
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
