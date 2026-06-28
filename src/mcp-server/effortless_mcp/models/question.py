from pydantic import BaseModel
from typing import Optional

class Question(BaseModel):
    id: str
    phase: str
    question: str
    status: str = "Pending"
    impact: str = "Structuring"
    context: str
    suggestion: Optional[str] = None
    answer: Optional[str] = None
    date_resolved: Optional[str] = None
