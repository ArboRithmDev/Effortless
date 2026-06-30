from pydantic import BaseModel, Field
from typing import List, Optional

class Epic(BaseModel):
    id: str
    zone: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: str = "Open"
    # Identité tracker (DEC-02) — champs canoniques, vides tant que non couplé.
    tracker_id: str = ""
    tracker_url: str = ""
