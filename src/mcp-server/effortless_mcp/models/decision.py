from pydantic import BaseModel, Field
from typing import List, Optional

class Decision(BaseModel):
    id: str
    title: str
    status: str = "Accepted"
    phase: str
    date: str
    context: str
    decision: str
    consequences: List[str] = Field(default_factory=list)
    rejected_alternatives: List[str] = Field(default_factory=list)
