"""Cadrage niveau Epic (003-Story-Cadrage) — symétrie avec le cadrage projet.

Chaque Epic possède, sous ``cadrage/<epic_id>/`` :
  - ``0-Epic.md``    : charte (intention, périmètre, objectifs, critères de Done).
                        Scaffoldée si absente, JAMAIS écrasée (document vivant, édité
                        par l'auteur).
  - ``1-Stories.md`` : registre des stories, RENDU DÉRIVÉ (régénéré à chaque mutation)
                        depuis ``epic.json`` + chaque ``story.json``. Pas de 2e source
                        de vérité.
"""

from __future__ import annotations

import json
import os
from typing import Optional


def _epic_dir(root: str, epic_id: str) -> str:
    return os.path.join(root, ".effortless", "epics", epic_id)


def _cadrage_dir(root: str, epic_id: str) -> str:
    return os.path.join(root, "cadrage", epic_id)


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_epic_charter(root: str, epic_id: str, epic: Optional[dict] = None) -> bool:
    """Scaffolde ``0-Epic.md`` si absent. Ne l'écrase jamais. Retourne True si créé."""
    epic = epic or _read_json(os.path.join(_epic_dir(root, epic_id), "epic.json")) or {}
    path = os.path.join(_cadrage_dir(root, epic_id), "0-Epic.md")
    if os.path.exists(path):
        return False
    perimetre = (epic.get("zone") or "").title()
    titre = epic.get("title", epic_id)
    desc = epic.get("description") or "_à compléter_"
    fm = (
        "---\n"
        "type: cadrage-epic\n"
        "document: 0-epic\n"
        f"titre: {titre}\n"
        "projet: Effortless\n"
        f"epic: {epic_id}\n"
        f"perimetre: {perimetre}\n"
        "statut: vivant\n"
        "tags:\n"
        "  - cadrage/epic\n"
        f"  - cadrage/{epic_id.lower()}\n"
        "---\n\n"
    )
    body = (
        f"# {titre} — Charte d'Epic\n\n"
        "> Direction de l'Epic. Document vivant, enrichi par l'auteur. Le détail\n"
        "> fonctionnel/technique vit au niveau des Stories.\n\n"
        "## Intention\n\n"
        f"{desc}\n\n"
        "## Périmètre\n\n"
        f"Périmètre **{perimetre}** — délimité par le document 1 projet (fonctionnel global).\n\n"
        "## Objectifs\n\n"
        "- _à compléter_\n\n"
        "## Critères de Done\n\n"
        "- Toutes les Stories de l'Epic sont Done.\n\n"
        "## Registre\n\n"
        "Voir [1-Stories](1-Stories.md).\n"
    )
    _write(path, fm + body)
    return True


def render_story_registry(root: str, epic_id: str, epic: Optional[dict] = None) -> str:
    """(Ré)génère ``1-Stories.md`` depuis epic.json + chaque story.json. Rendu dérivé."""
    epic = epic or _read_json(os.path.join(_epic_dir(root, epic_id), "epic.json")) or {}
    stories_dir = os.path.join(_epic_dir(root, epic_id), "stories")
    rows = []
    for sid in epic.get("stories", []):
        s = _read_json(os.path.join(stories_dir, sid, "story.json")) or {}
        rows.append((
            s.get("seq") if isinstance(s.get("seq"), int) else 0,
            sid,
            (s.get("title") or "").replace("|", "\\|"),
            s.get("status", "?"),
        ))
    rows.sort(key=lambda r: r[0])
    titre = epic.get("title", epic_id)
    fm = (
        "---\n"
        "type: cadrage-epic-registre\n"
        "document: 1-stories\n"
        "projet: Effortless\n"
        f"epic: {epic_id}\n"
        "statut: vivant\n"
        "tags:\n"
        "  - cadrage/epic\n"
        "  - cadrage/registre\n"
        "---\n\n"
    )
    lines = [f"# {titre} — Registre des stories\n",
             "> Rendu dérivé (régénéré) depuis `epic.json` + chaque `story.json`. Ne pas éditer à la main.\n",
             "| Seq | Id | Titre | Statut |", "|---|---|---|---|"]
    for seq, sid, title, status in rows:
        lines.append(f"| {seq} | {sid} | {title} | {status} |")
    if not rows:
        lines.append("| — | — | _(aucune story)_ | — |")
    text = fm + "\n".join(lines) + "\n"
    _write(os.path.join(_cadrage_dir(root, epic_id), "1-Stories.md"), text)
    return text


def refresh_epic_cadrage(root: str, epic_id: str, epic: Optional[dict] = None) -> None:
    """Scaffolde la charte (si absente) + régénère le registre. Best-effort."""
    try:
        epic = epic or _read_json(os.path.join(_epic_dir(root, epic_id), "epic.json")) or {}
        write_epic_charter(root, epic_id, epic)
        render_story_registry(root, epic_id, epic)
        # BQO d'Epic (006-Story-Cadrage) : rendu dérivé de epic.json["bqo"].
        from effortless_mcp.services.bqo import render_epic_bqo
        render_epic_bqo(root, epic_id, epic)
    except OSError:
        pass
