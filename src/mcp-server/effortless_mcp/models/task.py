from pydantic import BaseModel, Field
from typing import List, Optional

class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str = "Todo"
    phase: str
    story_id: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)
    complexity: Optional[str] = None
    # Identité tracker (DEC-02) — champs canoniques, vides tant que non couplé.
    tracker_id: str = ""
    tracker_url: str = ""
