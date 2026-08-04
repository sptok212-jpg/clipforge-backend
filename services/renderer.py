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
def render_clip(
    source_video_path: str,
    start: float,
    end: float,
    caption_text: str,
) -> str:
    os.makedirs(TMP_DIR, exist_ok=True)  # jaga-jaga folder belum ada
    duration = max(1.0, end - start)
    output_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}.mp4")
    target_w, target_h = 1080, 1920
    caption_filter = _build_caption_filter(caption_text, target_w, target_h)
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},"
        f"{caption_filter}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", source_video_path,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-threads", "2",              # <-- batasi thread per proses, jangan auto
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        full_stderr = result.stderr.strip()
        print(f"FFMPEG FULL STDERR (exit code {result.returncode}):\n{full_stderr}")
        lines = [l for l in full_stderr.splitlines() if l.strip()]
        tail = "\n".join(lines[-15:]) if lines else "(stderr kosong — kemungkinan proses dibunuh sinyal)"
        raise RuntimeError(
            f"ffmpeg render failed (exit code {result.returncode}):\n{tail}"
        )
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
