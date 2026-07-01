from pydantic import BaseModel, Field
from typing import List, Optional

class ProjectMeta(BaseModel):
    name: str
    description: Optional[str] = None
    version: str = "0.1.0"

class PhaseConfig(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    required_documents: List[str] = Field(default_factory=list)

class WorkflowConfig(BaseModel):
    phases: List[PhaseConfig]

class SettingsConfig(BaseModel):
    storage_dir: str = ".effortless"
    documents_dir: str = "cadrage/Phase-001"
    # Mode d'initialisation (005-Story-Cadrage) : "agile" (greenfield OPALE) ou
    # "v-cycle" (repris de Jira, cycle en V). Détermine le workflow de phases.
    init_mode: str = "agile"

class EffortlessConfig(BaseModel):
    project: ProjectMeta
    workflow: WorkflowConfig
    settings: SettingsConfig
