import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SYSTEM_PROMPT = """You are a viral short-form video editor. Given a podcast
transcript with timestamps, identify the best segments to turn into
short vertical clips (like TikTok/Reels).

Rules:
- Each clip must be between 20 and 60 seconds long.
- Pick segments that are self-contained, emotionally engaging, or
  contain a strong hook, story, or insight.
- Write the title and caption_text in the SAME language as the
  transcript. Do not translate to English or any other language.
- Return between 3 and 8 clips, ranked by viral_score (0-100).

Respond ONLY with a JSON array, no other text, matching this schema:
[
  {
    "start": float,
    "end": float,
    "title": string,
    "topic": string,
    "viral_score": int,
    "caption_text": string
  }
]
"""


def analyze_transcript(segments: list[dict]) -> list[dict]:
    transcript_text = "\n".join(
        f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript_text},
        ],
        temperature=0.7,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if the model added them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    clips = json.loads(raw)
    return clips
