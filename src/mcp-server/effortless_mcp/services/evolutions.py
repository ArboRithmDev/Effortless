"""Registre des évolutions projet + rendu dérivé (004-Story-Process / EVO-010).

Symétrie avec les questions projet (``services/bqo.py``) : une source JSON maître
``.effortless/evolutions.json`` et un rendu dérivé ``cadrage/4-Evolutions.md``
régénéré à chaque mutation — jamais édité à la main (fin du drift constaté où
EVO-007 vivait dans le JSON sans apparaître dans le ``.md``).

Cycle de vie d'une évolution : ``Planifié`` → ``En cours`` (graduée vers un Epic)
→ ``Résolu`` (avec résolution). ``type`` ∈ {finding, besoin}. La graduation copie
le lien Epic dans l'évolution et matérialise le scaffold anticipé (P4).
"""

from __future__ import annotations

import datetime
import json
import os
from typing import List, Optional

PROJET = "Effortless"
VALID_TYPES = ("finding", "besoin")
VALID_STATUSES = ("Planifié", "En cours", "Résolu")


def _evolutions_path(root: str) -> str:
    return os.path.join(root, ".effortless", "evolutions.json")


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


def load_evolutions(root: str) -> dict:
    return _read_json(
        _evolutions_path(root),
        {"version": 1, "updated_at": _today(),
         "doc": "Registre des évolutions (document 4). Découvertes et besoins issus "
                "des échanges utilisateur/agent. Vivant : addition, modification, "
                "suivi d'état.",
         "evolutions": []},
    )


def _next_evo_id(evolutions: List[dict]) -> str:
    mx = 0
    for e in evolutions:
        eid = e.get("id", "")
        if eid.startswith("EVO-"):
            try:
                mx = max(mx, int(eid.split("-")[1]))
            except (ValueError, IndexError):
                pass
    return f"EVO-{mx + 1:03d}"


def add_evolution(
    root: str,
    type_: str,
    title: str,
    detail: str = "",
    status: str = "Planifié",
    date: Optional[str] = None,
) -> dict:
    """Ajoute une évolution (finding/besoin). Retourne l'évolution créée."""
    if type_ not in VALID_TYPES:
        raise ValueError(f"type invalide '{type_}' (attendu: {', '.join(VALID_TYPES)})")
    if status not in VALID_STATUSES:
        raise ValueError(f"status invalide '{status}' (attendu: {', '.join(VALID_STATUSES)})")
    data = load_evolutions(root)
    evo = {
        "id": _next_evo_id(data["evolutions"]),
        "date": date or _today(),
        "type": type_,
        "title": title,
        "detail": detail,
        "status": status,
        "epic": None,
    }
    data["evolutions"].append(evo)
    data["updated_at"] = _today()
    _write_json(_evolutions_path(root), data)
    render_evolutions(root, data)
    return evo


def set_evolution(
    root: str,
    evo_id: str,
    status: Optional[str] = None,
    resolution: Optional[str] = None,
) -> Optional[dict]:
    """Met à jour le statut et/ou la résolution d'une évolution. Régénère le rendu."""
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(f"status invalide '{status}' (attendu: {', '.join(VALID_STATUSES)})")
    data = load_evolutions(root)
    target = next((e for e in data["evolutions"] if e.get("id") == evo_id), None)
    if target is None:
        return None
    if status is not None:
        target["status"] = status
    if resolution is not None:
        target["resolution"] = resolution
    data["updated_at"] = _today()
    _write_json(_evolutions_path(root), data)
    render_evolutions(root, data)
    return target


def graduate_evolution(root: str, evo_id: str, epic_id: str) -> Optional[dict]:
    """Rattache une évolution à un Epic (graduation).

    Lie ``evolution.epic = epic_id`` et bascule le statut ``Planifié`` → ``En cours``
    (une évolution déjà Résolue n'est pas rétrogradée). Régénère le rendu. Retourne
    l'évolution, ou None si introuvable. La création/résolution de l'Epic est faite
    par l'appelant (outil serveur) ; ici on ne fait que le lien + le suivi d'état.
    """
    data = load_evolutions(root)
    target = next((e for e in data["evolutions"] if e.get("id") == evo_id), None)
    if target is None:
        return None
    target["epic"] = epic_id
    if target.get("status") == "Planifié":
        target["status"] = "En cours"
    data["updated_at"] = _today()
    _write_json(_evolutions_path(root), data)
    render_evolutions(root, data)
    return target


def render_evolutions(root: str, data: Optional[dict] = None) -> str:
    """(Ré)génère ``cadrage/4-Evolutions.md`` depuis le JSON maître. Rendu dérivé."""
    data = data if data is not None else load_evolutions(root)
    maj = data.get("updated_at", _today())
    fm = (
        "---\n"
        "type: cadrage-projet\n"
        "document: 4-evolutions\n"
        "titre: Effortless — Registre des évolutions\n"
        f"projet: {PROJET}\n"
        "statut: vivant\n"
        "source: .effortless/evolutions.json\n"
        f"maj: {maj}\n"
        "tags:\n"
        "  - cadrage/projet\n"
        "  - cadrage/evolutions\n"
        "---\n\n"
    )
    evos = data.get("evolutions", [])
    lines = [
        "# Effortless — Registre des évolutions (document 4)\n",
        "> Rendu dérivé de `.effortless/evolutions.json` (source de vérité) — ne pas "
        "éditer à la main. Découvertes (finding) et besoins issus des échanges.\n",
        "| Id | Type | Titre | État | Epic | Résolution |",
        "|---|---|---|---|---|---|",
    ]
    for e in evos:
        lines.append(
            f"| {e.get('id','?')} | {_esc(e.get('type',''))} | {_esc(e.get('title',''))} | "
            f"{_esc(e.get('status',''))} | {e.get('epic') or '—'} | "
            f"{_esc(e.get('resolution','') or '—')} |"
        )
    if not evos:
        lines.append("| — | — | _(aucune évolution)_ | — | — | — |")
    # Détails (detail long, hors tableau).
    detailed = [e for e in evos if (e.get("detail") or "").strip()]
    if detailed:
        lines.append("\n## Détails\n")
        for e in detailed:
            lines.append(f"- **{e.get('id','?')}** — {e.get('detail','').strip()}")
    text = fm + "\n".join(lines) + "\n"
    _write_text(os.path.join(root, "cadrage", "4-Evolutions.md"), text)
    return text
