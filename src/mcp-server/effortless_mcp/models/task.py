from pydantic import BaseModel, Field
from typing import List, Optional

class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str = "Todo"
    phase: str
    depends_on: List[str] = Field(default_factory=list)
    complexity: Optional[str] = None
