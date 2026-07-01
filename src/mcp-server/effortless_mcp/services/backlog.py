"""Backlog projet : réconciliation depuis les Epics réels + rendu dérivé.

004-Story-Process / EVO-010. ``backlog.json`` est la vérité *éditoriale* (périmètre,
intention, notes) ; mais son état structurel (existence des Epics, statut, compteurs
de stories) doit refléter les ``epic.json`` réels — sinon il dérive (constat :
``004-Epic-Process`` créé par ``epic_start`` n'y figurait pas).

``reconcile_backlog`` upsert chaque Epic réel dans ``backlog.json`` en **préservant
les champs éditoriaux** (``intent``, ``note``, sous-liste ``stories``) et en
**dérivant** ``status`` + ``stories_done`` / ``stories_total`` des fichiers d'état.
``render_backlog`` régénère ``cadrage/3-Backlog.md`` — jamais édité à la main.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import List, Optional

PROJET = "Effortless"


def _backlog_path(root: str) -> str:
    return os.path.join(root, ".effortless", "backlog.json")


def _epics_dir(root: str) -> str:
    return os.path.join(root, ".effortless", "epics")


def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def _today() -> str:
    return datetime.date.today().isoformat()


def _perimetre_from_id(epic_id: str) -> str:
    if "-Epic-" in epic_id:
        return epic_id.split("-Epic-", 1)[1]
    return epic_id.replace("EPIC-", "").title()


def load_backlog(root: str) -> dict:
    return _read_json(
        _backlog_path(root),
        {"version": 1, "updated_at": _today(),
         "doc": "Backlog global projet (document 3). Vivant : addition, modification, "
                "suivi d'état. Vérité maître ; les Epics en sont des projections.",
         "epics": []},
    )


def _story_done_counts(root: str, epic_id: str, story_ids: List[str]) -> tuple:
    """Retourne (done, total) en lisant le statut réel de chaque story.json."""
    total = len(story_ids)
    done = 0
    for sid in story_ids:
        sjson = os.path.join(_epics_dir(root), epic_id, "stories", sid, "story.json")
        st = _read_json(sjson, {})
        if (st or {}).get("status") == "Done":
            done += 1
    return done, total


def _real_epics(root: str) -> List[dict]:
    """Epics réels (epic.json), triés par séquence de création."""
    d = _epics_dir(root)
    epics: List[dict] = []
    if os.path.isdir(d):
        for name in os.listdir(d):
            ej = os.path.join(d, name, "epic.json")
            e = _read_json(ej, None)
            if e is not None:
                epics.append(e)
    epics.sort(key=lambda e: e.get("seq") if isinstance(e.get("seq"), int) else 0)
    return epics


def reconcile_backlog(root: str) -> dict:
    """Upsert les Epics réels dans backlog.json (préserve l'éditorial, dérive l'état)."""
    data = load_backlog(root)
    by_id = {e.get("id"): e for e in data.get("epics", [])}
    for epic in _real_epics(root):
        eid = epic.get("id")
        if not eid:
            continue
        done, total = _story_done_counts(root, eid, epic.get("stories", []) or [])
        status = epic.get("status", "Open")
        if eid in by_id:
            ent = by_id[eid]
            ent.setdefault("perimetre", _perimetre_from_id(eid))
            ent["status"] = status
            ent["stories_done"] = done
            ent["stories_total"] = total
        else:
            ent = {
                "id": eid,
                "perimetre": _perimetre_from_id(eid),
                "intent": epic.get("title", ""),
                "status": status,
                "stories_done": done,
                "stories_total": total,
            }
            data["epics"].append(ent)
            by_id[eid] = ent
    data["updated_at"] = _today()
    _write_json(_backlog_path(root), data)
    render_backlog(root, data)
    return data


def render_backlog(root: str, data: Optional[dict] = None) -> str:
    """(Ré)génère ``cadrage/3-Backlog.md`` depuis backlog.json. Rendu dérivé."""
    data = data if data is not None else load_backlog(root)
    maj = data.get("updated_at", _today())
    fm = (
        "---\n"
        "type: cadrage-projet\n"
        "document: 3-backlog\n"
        "titre: Effortless — Backlog global\n"
        f"projet: {PROJET}\n"
        "statut: vivant\n"
        "source: .effortless/backlog.json\n"
        f"maj: {maj}\n"
        "tags:\n"
        "  - cadrage/projet\n"
        "  - cadrage/backlog\n"
        "---\n\n"
    )
    epics = data.get("epics", [])
    lines = [
        "# Effortless — Backlog global (document 3)\n",
        "> Rendu dérivé de `.effortless/backlog.json` (source de vérité) — ne pas "
        "éditer à la main. Vérité maître ; les Epics en sont des projections.\n",
        "| Epic | Périmètre | État | Avancement | Intention |",
        "|---|---|---|---|---|",
    ]
    for e in epics:
        total = e.get("stories_total")
        done = e.get("stories_done")
        av = f"{done}/{total}" if isinstance(total, int) and total else "—"
        lines.append(
            f"| {e.get('id','?')} | {_esc(e.get('perimetre',''))} | "
            f"{_esc(e.get('status',''))} | {av} | {_esc(e.get('intent',''))} |"
        )
    if not epics:
        lines.append("| — | — | — | — | _(aucun Epic)_ |")
    text = fm + "\n".join(lines) + "\n"
    _write_text(os.path.join(root, "cadrage", "3-Backlog.md"), text)
    return text
