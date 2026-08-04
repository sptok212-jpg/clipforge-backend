import os
import subprocess
import uuid
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

TMP_DIR = "/tmp/clipforge"


def extract_audio(video_path: str) -> str:
    """
    Extracts audio track from video as mp3 using ffmpeg.
    """
    audio_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}.mp3")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "2",
            audio_path,
        ],
        check=True,
        capture_output=True,
    )
    return audio_path


def transcribe_audio(audio_path: str) -> dict:
    """
    Transcribes audio using Whisper, preserving original spoken language.
    IMPORTANT: uses the transcriptions endpoint (not translations),
    and does NOT force a `language` param, so Whisper auto-detects
    and keeps the output in whatever language is spoken in the audio
    (e.g. Indonesian stays Indonesian, not auto-translated to English).
    """
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment", "word"],
        )

    return {
        "text": result.text,
        "language": result.language,
        "segments": [
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
            }
            for seg in result.segments
        ],
    }
