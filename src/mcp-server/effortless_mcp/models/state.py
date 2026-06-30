from pydantic import BaseModel
from typing import List, Optional

class CompletedPhase(BaseModel):
    id: str
    completed_at: str

class ProjectState(BaseModel):
    project_name: str
    current_phase: str
    active_story_id: Optional[str] = None
    active_epic_id: Optional[str] = None
    started_at: str
    completed_phases: List[CompletedPhase] = []
