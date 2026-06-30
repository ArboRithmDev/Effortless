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

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
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


class JiraClient:
    """Client REST Jira Cloud v3 (auth Basic email:api_token).

    Même interface que FakeJiraClient. Implémenté en stdlib (urllib) — aucune
    nouvelle dépendance. Exercé en réel uniquement en validation EFL (TSK-13) ;
    la suite pytest reste hermétique via FakeJiraClient.
    """

    def __init__(self, base_url: str, email: str, api_token: str):
        self._base = base_url.rstrip("/")
        token = base64.b64encode(f"{email}:{api_token}".encode("utf-8")).decode("ascii")
        self._auth = f"Basic {token}"

    def _req(self, method: str, path: str, params: Optional[dict] = None,
             body: Optional[dict] = None) -> dict:
        url = self._base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._auth)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}

    def get_issue_types(self, project_key: str) -> List[Dict]:
        data = self._req("GET", f"/rest/api/3/project/{project_key}")
        return [
            {"id": t["id"], "name": t.get("name"),
             "hierarchyLevel": t.get("hierarchyLevel"), "subtask": t.get("subtask", False)}
            for t in data.get("issueTypes", [])
        ]

    def get_transitions(self, issue_key: str) -> List[Dict]:
        data = self._req("GET", f"/rest/api/3/issue/{issue_key}/transitions")
        out = []
        for t in data.get("transitions", []):
            to = t.get("to", {})
            out.append({"id": t["id"], "to_status_id": to.get("id"),
                        "to_status_name": to.get("name")})
        return out

    def create_issue(self, *, project_key: str, issue_type_id: str, summary: str,
                     parent_key: Optional[str] = None, assignee: Optional[str] = None,
                     description: Optional[str] = None,
                     labels: Optional[List[str]] = None) -> Dict:
        fields: Dict = {
            "project": {"key": project_key},
            "issuetype": {"id": issue_type_id},
            "summary": summary,
        }
        if parent_key:
            fields["parent"] = {"key": parent_key}
        if assignee:
            fields["assignee"] = {"accountId": assignee}
        if labels:
            fields["labels"] = labels
        if description:
            fields["description"] = {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph",
                             "content": [{"type": "text", "text": description}]}],
            }
        data = self._req("POST", "/rest/api/3/issue", body={"fields": fields})
        key = data.get("key")
        return {"key": key, "id": data.get("id"), "url": f"{self._base}/browse/{key}"}

    def search(self, jql: str, fields: Optional[List[str]] = None) -> List[Dict]:
        params = {"jql": jql}
        if fields:
            params["fields"] = ",".join(fields)
        data = self._req("GET", "/rest/api/3/search/jql", params=params)
        return [{"key": i.get("key")} for i in data.get("issues", [])]

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        self._req("POST", f"/rest/api/3/issue/{issue_key}/transitions",
                  body={"transition": {"id": transition_id}})

    def add_worklog(self, issue_key: str, seconds: int, comment: str) -> None:
        self._req("POST", f"/rest/api/3/issue/{issue_key}/worklog",
                  body={"timeSpentSeconds": seconds, "comment": comment})
