"""Modes d'initialisation Effortless (005-Story-Cadrage).

Deux manières d'amorcer un projet, chacune avec son workflow de phases :

- ``agile`` (défaut) — projet *greenfield*. Cycle OPALE (Observer / Positionner /
  Articuler / Lancer). On part d'une page blanche, le backlog se construit.

- ``v-cycle`` — projet *repris de Jira* (read-mostly). Cycle en V : Besoins →
  Spécifications → Conception → Réalisation → Vérification/recette. Le backlog est
  la projection du tracker (couple + import médié), pas un greenfield.

Chaque phase déclare ses documents de cadrage selon la convention
``NN-<CODE>-<slug>.md`` — les stubs Obsidian-ready sont ensuite déposés par
``cadrage_frontmatter.scaffold_story_docs`` (004-Story-Cadrage).
"""

from __future__ import annotations

from typing import List

from effortless_mcp.models.config import PhaseConfig, WorkflowConfig

AGILE = "agile"
VCYCLE = "v-cycle"
MODES = (AGILE, VCYCLE)


def normalize_mode(mode: str) -> str:
    """Tolère quelques alias ; défaut agile. Lève ValueError si inconnu."""
    m = (mode or AGILE).strip().lower()
    aliases = {
        "agile": AGILE, "opale": AGILE, "greenfield": AGILE,
        "v-cycle": VCYCLE, "vcycle": VCYCLE, "cycle-v": VCYCLE,
        "cycle-en-v": VCYCLE, "v": VCYCLE, "jira": VCYCLE,
    }
    if m not in aliases:
        raise ValueError(f"mode inconnu '{mode}' (attendu: {', '.join(MODES)})")
    return aliases[m]


# (phase_id, phase_name, description, [basenames]) par mode.
_AGILE_PHASES = [
    ("O-analyse", "Observer", "Analyse de l'existant, glossaire métier et cartographie technique",
     ["00-FNC-GLO-glossaire.md", "01-TEC-ANA-analyse.md", "02-BQO-questions.md"]),
    ("P-cadrage", "Positionner", "Cadrage décisionnel et architecture cible",
     ["03-TEC-ARC-architecture-cible.md", "04-MET-DEC-registre-decisions.md"]),
    ("A-specs", "Articuler", "Spécifications fonctionnelles et techniques détaillées",
     ["05-FNC-SPE-specifications.md", "06-TEC-API-contrat-api.md"]),
    ("L-plan", "Lancer", "Plan d'implémentation et découpage en tâches",
     ["07-MET-PLN-plan-action.md"]),
]

_VCYCLE_PHASES = [
    ("B-besoins", "Besoins", "Expression du besoin repris de Jira (exigences, périmètre)",
     ["00-FNC-BES-besoins.md", "01-BQO-questions.md"]),
    ("S-specifications", "Spécifications", "Spécifications fonctionnelles et techniques",
     ["02-FNC-SPE-specifications.md", "03-TEC-SPE-specifications-techniques.md"]),
    ("C-conception", "Conception", "Architecture et conception détaillée",
     ["04-TEC-ARC-architecture.md", "05-MET-DEC-registre-decisions.md"]),
    ("R-realisation", "Réalisation", "Implémentation et découpage en tâches",
     ["06-MET-PLN-plan-action.md"]),
    ("V-verification", "Vérification", "Plan de tests, validation et recette (branche montante du V)",
     ["07-TEC-TST-plan-tests.md", "08-FNC-VAL-recette.md"]),
]


def build_workflow(mode: str, docs_root: str) -> WorkflowConfig:
    """Construit le WorkflowConfig du mode, docs préfixés par ``docs_root``."""
    mode = normalize_mode(mode)
    spec = _AGILE_PHASES if mode == AGILE else _VCYCLE_PHASES
    phases: List[PhaseConfig] = []
    for pid, name, desc, docs in spec:
        phases.append(PhaseConfig(
            id=pid, name=name, description=desc,
            required_documents=[f"{docs_root}/{d}" for d in docs],
        ))
    return WorkflowConfig(phases=phases)
