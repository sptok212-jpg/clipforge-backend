import os
import subprocess
import uuid
import textwrap

TMP_DIR = "/tmp/clipforge"


def _build_caption_filter(caption_text: str, video_w: int, video_h: int) -> str:
    wrapped = textwrap.fill(caption_text, width=28)
    escaped = (
        wrapped.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("\n", "\\n")
    )

    font_size = int(video_w * 0.045)
    box_y = int(video_h * 0.72)

    return (
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"text='{escaped}':fontcolor=white:fontsize={font_size}:"
        f"box=1:boxcolor=black@0.55:boxborderw=14:"
        f"x=(w-text_w)/2:y={box_y}:line_spacing=8"
    )


def render_clip(source_video_path: str, start: float, end: float, caption_text: str) -> str:
    os.makedirs(TMP_DIR, exist_ok=True)
    duration = max(1.0, end - start)
    output_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}.mp4")
    target_w, target_h = 1080, 1920
    caption_filter = _build_caption_filter(caption_text, target_w, target_h)
    
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},"
        f"{caption_filter}"
    )
    
    # PERBAIKAN OOM (Out of Memory):
    # 1. -preset ultrafast (paling hemat RAM)
    # 2. -threads 1 (tidak multi-threading, jadi RAM tidak kebablasan)
    # 3. -tune zerolatency (mengurangi penggunaan buffer memori)
    cmd = [
        "ffmpeg", "-y",
        "-i", source_video_path,
        "-ss", str(start),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-threads", "1",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart",
        output_path,
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"ffmpeg render failed (exit {result.returncode}):\n{tail}")
        
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 10_000:
        size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        raise RuntimeError(f"Output render tidak valid (size={size} bytes).")
    return output_path


def upload_clip_to_storage(supabase_client, local_path: str, storage_path: str) -> str:
    with open(local_path, "rb") as f:
        supabase_client.storage.from_("clips").upload(
            storage_path,
            f,
            {"content-type": "video/mp4", "upsert": "true"},
        )

    public_url = supabase_client.storage.from_("clips").get_public_url(storage_path)
    return public_url
