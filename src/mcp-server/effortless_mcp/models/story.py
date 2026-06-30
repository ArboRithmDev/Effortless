from pydantic import BaseModel, Field
from typing import List, Optional

class Story(BaseModel):
    id: str
    epic_id: str
    zone: Optional[str] = None
    title: str
    opale_phase: str = "O-analyse"
    status: str = "Todo"
    depends_on: List[str] = Field(default_factory=list)
    # Identité tracker (DEC-02) — champs canoniques, vides tant que non couplé.
    tracker_id: str = ""
    tracker_url: str = ""
