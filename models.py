from pydantic import BaseModel

class JobRequest(BaseModel):
    youtube_url: str | None = None
    project_id: str
    user_id: str

class JobResponse(BaseModel):
    job_id: str
    status: str
