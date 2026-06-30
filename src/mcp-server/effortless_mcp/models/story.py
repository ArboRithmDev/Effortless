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
