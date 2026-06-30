"""Templates de scaffolding externalisés (STO-TRACKER-02, DEC-04).

Le template `[PROJET]` (arbre Epic / Stories / sous-tâches) est décrit en JSON,
initialisé depuis l'observation d'IFX-1, versionné ici et surchargeable.
"""

import json
import os

_DIR = os.path.dirname(__file__)


def load_scaffold_template(name: str = "jira_project_scaffold") -> dict:
    """Charge un template de scaffold par nom (sans extension). Retourne l'arbre
    `{zone_prefix, root:{level,title,children:[...]}}`."""
    path = os.path.join(_DIR, f"{name}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
