"""Intégration du Port Tracker au cœur — couplage + projection best-effort.

- Couplage projet (TSK-06) : lecture/écriture de `settings.tracker` dans
  `effortless.json`, identité d'espace (DEC-02), propagation SecondBrain.
- Projection (TSK-08) : projette les mutations locales (create / transition) via
  l'adapter résolu. Garde NullTracker : sans couplage, no-op sans I/O. Tracker
  injoignable → l'opération locale n'échoue jamais, la projection est consignée
  dans le SyncJournal (DEC-05).
"""

from __future__ import annotations

import json
import os
from typing import Optional

from effortless_mcp.ports.tracker import (
    NullTracker,
    ObjectPayload,
    ProjectRef,
    TrackerRef,
    resolve_tracker,
)
from effortless_mcp.ports.sync_journal import SyncJournal


def _config_path(root: str) -> str:
    return os.path.join(root, "effortless.json")


def _read_settings(root: str) -> dict:
    try:
        with open(_config_path(root), "r", encoding="utf-8") as f:
            return json.load(f).get("settings", {}) or {}
    except (OSError, json.JSONDecodeError):
        return {}


# --- couplage projet (TSK-06) --------------------------------------------

def tracker_project_ref(root: str) -> Optional[ProjectRef]:
    """ProjectRef de l'espace couplé, ou None si non couplé."""
    tcfg = _read_settings(root).get("tracker") or {}
    if tcfg.get("project_id"):
        return ProjectRef(project_id=tcfg["project_id"], project_url=tcfg.get("project_url", ""))
    return None


def is_coupled(root: str) -> bool:
    """Vrai si un adapter concret est résolu (≠ NullTracker)."""
    return not isinstance(resolve_tracker(_read_settings(root), root), NullTracker)


def couple_project(
    root: str,
    type: str,
    project_id: str,
    project_url: str,
    *,
    slug: Optional[str] = None,
    phase: Optional[str] = None,
) -> ProjectRef:
    """Écrit `settings.tracker` dans `effortless.json` (couplage, DEC-02).

    Si `slug` et `phase` sont fournis, propage l'identité d'espace à SecondBrain
    (best-effort, non bloquant)."""
    with open(_config_path(root), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    tracker = {"type": type, "project_id": project_id, "project_url": project_url}
    cfg.setdefault("settings", {})["tracker"] = tracker
    with open(_config_path(root), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    if slug and phase:
        try:
            from effortless_mcp.services.secondbrain import sync_phase_to_secondbrain
            sync_phase_to_secondbrain(slug, phase, tracker=tracker)
        except Exception:
            pass

    return ProjectRef(project_id=project_id, project_url=project_url)


# --- projection des mutations (TSK-08) -----------------------------------

def project_task_created(root: str, task: dict) -> dict:
    """Projette la création d'une Task. Persiste tracker_id/url sur l'objet, ou
    consigne une migration si le tracker est injoignable. Best-effort : n'échoue
    jamais l'opération locale. Retourne le task (éventuellement enrichi)."""
    tracker = resolve_tracker(_read_settings(root), root)
    if isinstance(tracker, NullTracker):
        return task  # non couplé : no-op, zéro I/O
    payload = ObjectPayload(
        level="task",
        title=task.get("title", ""),
        description=task.get("description"),
    )
    try:
        ref = tracker.create(payload)
        task["tracker_id"] = ref.tracker_id
        task["tracker_url"] = ref.tracker_url
    except Exception:
        SyncJournal(root).enqueue(
            "create",
            {"level": "task", "id": task.get("id"), "title": task.get("title", "")},
        )
    return task


def project_task_transitioned(root: str, task: dict, status: str) -> None:
    """Projette un changement de statut. Tracker injoignable → migration outbox."""
    tracker = resolve_tracker(_read_settings(root), root)
    if isinstance(tracker, NullTracker):
        return  # non couplé : no-op, zéro I/O
    ref = TrackerRef(task.get("tracker_id", ""), task.get("tracker_url", ""))
    try:
        tracker.transition(ref, status)
    except Exception:
        SyncJournal(root).enqueue(
            "transition",
            {"id": task.get("id"), "status": status},
        )


def project_task_log_work(root: str, task: dict, minutes: int, comment: str = "") -> None:
    """Projette du temps passé sur une Task. Tracker injoignable → migration outbox.

    Best-effort : n'échoue jamais l'opération locale. Le rollup temps est natif Jira."""
    tracker = resolve_tracker(_read_settings(root), root)
    if isinstance(tracker, NullTracker):
        return  # non couplé : no-op, zéro I/O
    ref = TrackerRef(task.get("tracker_id", ""), task.get("tracker_url", ""))
    try:
        tracker.log_work(ref, minutes, comment)
    except Exception:
        SyncJournal(root).enqueue(
            "log_work",
            {"id": task.get("id"), "minutes": minutes, "comment": comment},
        )
