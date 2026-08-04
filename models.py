from pydantic import BaseModel
from typing import Optional, List

class JobRequest(BaseModel):
    youtube_url: str
    project_id: str
    user_id: str

class JobResponse(BaseModel):
    job_id: str
    status: str

class ClipSegment(BaseModel):
    start: float
    end: float
    title: str
    topic: str
    viral_score: int
    caption_text: str
