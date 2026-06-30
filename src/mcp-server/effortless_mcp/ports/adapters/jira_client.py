"""Frontière I/O Jira (STO-TRACKER-02, DEC-03).

Tout accès réseau à Jira est confiné ici. `JiraTracker` ne dépend QUE de cette
interface, ce qui rend l'adapter testable hors-ligne via `FakeJiraClient`.

Interface attendue d'un client Jira (MVP) :
    get_issue_types(project_key) -> list[{"id","name","hierarchyLevel","subtask"}]
    get_transitions(issue_key)   -> list[{"id","to_status_id","to_status_name"}]
    create_issue(*, project_key, issue_type_id, summary, parent_key=None,
                 assignee=None, description=None, labels=None) -> {"key","id","url"}
    search(jql, fields=None)      -> list[{"key", ...}]

`JiraClient` (REST Jira Cloud v3) est ajouté en TSK-10 ; il respecte la même
interface que `FakeJiraClient`.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


# Taxonomie de référence observée sur IFX/EFL (catégorie « Projet cycle en V »).
# Sert de seed par défaut au FakeJiraClient et de fixture aux tests. Les ids réels
# sont identiques sur EFL (vérifié au cadrage, Q-02).
DEFAULT_ISSUE_TYPES: List[Dict] = [
    {"id": "10000", "name": "Epic", "hierarchyLevel": 1, "subtask": False},
    {"id": "10007", "name": "Story", "hierarchyLevel": 0, "subtask": False},
    {"id": "10002", "name": "Tâche", "hierarchyLevel": 0, "subtask": False},
    {"id": "10095", "name": "Sous-tâche", "hierarchyLevel": -1, "subtask": True},
]

# Transitions du workflow cycle en V (statut cible -> transitionId), observées sur IFX-1.
DEFAULT_TRANSITIONS: List[Dict] = [
    {"id": "2", "to_status_id": "10079", "to_status_name": "A faire"},
    {"id": "5", "to_status_id": "10066", "to_status_name": "En cours"},
    {"id": "9", "to_status_id": "10063", "to_status_name": "Terminé"},
    {"id": "12", "to_status_id": "10312", "to_status_name": "Annulé(e)"},
]


class FakeJiraClient:
    """Double de test en mémoire — zéro réseau (DEC-03).

    Seedé avec une taxonomie (types + transitions). Enregistre les issues créées
    (parent, labels, type) et permet la recherche par label, suffisant pour
    exercer l'adapter et le composer de scaffold de façon déterministe.
    """

    def __init__(
        self,
        issue_types: Optional[List[Dict]] = None,
        transitions: Optional[List[Dict]] = None,
        base_url: str = "https://jira.test",
    ):
        self._issue_types = list(issue_types if issue_types is not None else DEFAULT_ISSUE_TYPES)
        self._transitions = list(transitions if transitions is not None else DEFAULT_TRANSITIONS)
        self._base_url = base_url.rstrip("/")
        self.issues: Dict[str, Dict] = {}   # key -> issue dict
        self._seq = 0

    # --- Lecture taxonomie ---
    def get_issue_types(self, project_key: str) -> List[Dict]:
        return list(self._issue_types)

    def get_transitions(self, issue_key: str) -> List[Dict]:
        return list(self._transitions)

    # --- Écriture ---
    def create_issue(
        self,
        *,
        project_key: str,
        issue_type_id: str,
        summary: str,
        parent_key: Optional[str] = None,
        assignee: Optional[str] = None,
        description: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> Dict:
        self._seq += 1
        key = f"{project_key}-{self._seq}"
        issue = {
            "key": key,
            "id": str(10000 + self._seq),
            "url": f"{self._base_url}/browse/{key}",
            "project_key": project_key,
            "issue_type_id": issue_type_id,
            "summary": summary,
            "parent_key": parent_key,
            "assignee": assignee,
            "description": description,
            "labels": list(labels or []),
        }
        self.issues[key] = issue
        return {"key": key, "id": issue["id"], "url": issue["url"]}

    def search(self, jql: str, fields: Optional[List[str]] = None) -> List[Dict]:
        """Recherche minimale : supporte `labels = "X"` et `project = KEY`.

        Suffit à la garde d'idempotence du scaffold (recherche du label
        `effortless-scaffold:<zone>`)."""
        label_m = re.search(r'labels\s*=\s*"([^"]+)"', jql)
        project_m = re.search(r'project\s*=\s*"?([A-Za-z0-9_]+)"?', jql)
        results = []
        for issue in self.issues.values():
            if label_m and label_m.group(1) not in issue["labels"]:
                continue
            if project_m and issue["project_key"] != project_m.group(1):
                continue
            results.append({"key": issue["key"], "url": issue["url"], "labels": issue["labels"]})
        return results

    # --- Post-MVP (stubs enregistreurs) ---
    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        self.issues.setdefault(issue_key, {}).setdefault("transitions", []).append(transition_id)

    def add_worklog(self, issue_key: str, seconds: int, comment: str) -> None:
        self.issues.setdefault(issue_key, {}).setdefault("worklogs", []).append((seconds, comment))
