"""Questions de cadrage projet → BQO d'Epic (006-Story-Cadrage).

Trois niveaux de questions dans le modèle fractal :
  - **Story** : questions opérationnelles (Q-NN, ``effortless_question_ask``, doc 02-BQO).
  - **Epic (BQO)** : « Big Questions Ouvertes » qui orientent un Epic. Rendu dérivé
    ``cadrage/<epic>/2-BQO.md`` depuis ``epic.json["bqo"]``.
  - **Projet** : questions transverses pas encore rattachées à un Epic. Source unique
    ``.effortless/questions_projet.json`` ; rendu ``cadrage/5-Questions.md``.

Cycle de vie d'une question projet : ``open`` → *graduation* vers un Epic
(``graduated``, copiée dans le BQO de l'Epic) ou ``resolved``. Vérité maître = le
JSON projet + ``epic.json["bqo"]`` ; les ``.md`` sont des rendus régénérés (pas de
2e source de vérité — même doctrine que le registre des stories).
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

PROJET = "Effortless"


def _proj_questions_path(root: str) -> str:
    return os.path.join(root, ".effortless", "questions_projet.json")


def _epic_dir(root: str, epic_id: str) -> str:
    return os.path.join(root, ".effortless", "epics", epic_id)


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
    return (s or "").replace("|", "\\|")


def load_project_questions(root: str) -> dict:
    return _read_json(_proj_questions_path(root), {"version": 1, "questions": []})


def _next_pq_id(questions: List[dict]) -> str:
    mx = 0
    for q in questions:
        qid = q.get("id", "")
        if qid.startswith("PQ-"):
            try:
                mx = max(mx, int(qid.split("-")[1]))
            except (ValueError, IndexError):
                pass
    return f"PQ-{mx + 1:03d}"


def add_project_question(root: str, text: str) -> dict:
    """Ajoute une question projet (statut open). Retourne la question créée."""
    data = load_project_questions(root)
    q = {"id": _next_pq_id(data["questions"]), "text": text, "status": "open", "epic": None}
    data["questions"].append(q)
    _write_json(_proj_questions_path(root), data)
    render_project_questions(root, data)
    return q


def resolve_project_question(root: str, pq_id: str, answer: Optional[str] = None) -> Optional[dict]:
    """Passe une question projet à ``resolved`` (avec réponse optionnelle)."""
    data = load_project_questions(root)
    for q in data["questions"]:
        if q.get("id") == pq_id:
            q["status"] = "resolved"
            if answer is not None:
                q["answer"] = answer
            _write_json(_proj_questions_path(root), data)
            render_project_questions(root, data)
            return q
    return None


def graduate_question(root: str, pq_id: str, epic_id: str) -> Optional[dict]:
    """Gradue une question projet en BQO d'un Epic.

    Marque la question ``graduated`` (rattachée à l'Epic) et la copie dans
    ``epic.json["bqo"]`` (dédup par id). Régénère les deux rendus. Retourne la
    question, ou None si question/epic introuvable.
    """
    epic_file = os.path.join(_epic_dir(root, epic_id), "epic.json")
    epic = _read_json(epic_file, None)
    if epic is None:
        return None
    data = load_project_questions(root)
    target = next((q for q in data["questions"] if q.get("id") == pq_id), None)
    if target is None:
        return None
    target["status"] = "graduated"
    target["epic"] = epic_id
    bqo = epic.setdefault("bqo", [])
    if not any(b.get("id") == pq_id for b in bqo):
        bqo.append({"id": pq_id, "text": target.get("text", ""), "status": "open"})
    _write_json(_proj_questions_path(root), data)
    _write_json(epic_file, epic)
    render_project_questions(root, data)
    render_epic_bqo(root, epic_id, epic)
    return target


def render_project_questions(root: str, data: Optional[dict] = None) -> str:
    """(Ré)génère ``cadrage/5-Questions.md`` depuis le JSON projet. Rendu dérivé."""
    data = data if data is not None else load_project_questions(root)
    fm = (
        "---\n"
        "type: cadrage-projet\n"
        "document: 5-questions\n"
        "titre: Questions projet\n"
        f"projet: {PROJET}\n"
        "statut: vivant\n"
        "tags:\n"
        "  - cadrage/projet\n"
        "  - cadrage/questions\n"
        "---\n\n"
    )
    lines = [
        "# Questions projet\n",
        "> Questions transverses (pas encore rattachées à un Epic). Rendu dérivé de "
        "`.effortless/questions_projet.json` — ne pas éditer à la main. Une question "
        "mûre *gradue* en BQO d'Epic.\n",
        "| Id | Question | Statut | Epic |", "|---|---|---|---|",
    ]
    qs = data.get("questions", [])
    for q in qs:
        lines.append(
            f"| {q.get('id','?')} | {_esc(q.get('text',''))} | "
            f"{q.get('status','?')} | {q.get('epic') or '—'} |"
        )
    if not qs:
        lines.append("| — | _(aucune question)_ | — | — |")
    text = fm + "\n".join(lines) + "\n"
    _write_text(os.path.join(root, "cadrage", "5-Questions.md"), text)
    return text


def render_epic_bqo(root: str, epic_id: str, epic: Optional[dict] = None) -> str:
    """(Ré)génère ``cadrage/<epic>/2-BQO.md`` depuis ``epic.json["bqo"]``. Dérivé."""
    if epic is None:
        epic = _read_json(os.path.join(_epic_dir(root, epic_id), "epic.json"), {}) or {}
    titre = epic.get("title", epic_id)
    fm = (
        "---\n"
        "type: cadrage-epic-bqo\n"
        "document: 2-bqo\n"
        f"projet: {PROJET}\n"
        f"epic: {epic_id}\n"
        "statut: vivant\n"
        "tags:\n"
        "  - cadrage/epic\n"
        "  - cadrage/bqo\n"
        "---\n\n"
    )
    lines = [
        f"# {titre} — BQO (questions ouvertes de l'Epic)\n",
        "> Big Questions Ouvertes qui orientent l'Epic, graduées depuis les questions "
        "projet. Rendu dérivé de `epic.json[\"bqo\"]` — ne pas éditer à la main.\n",
        "| Id | Question | Statut |", "|---|---|---|",
    ]
    bqo = epic.get("bqo", [])
    for b in bqo:
        lines.append(f"| {b.get('id','?')} | {_esc(b.get('text',''))} | {b.get('status','?')} |")
    if not bqo:
        lines.append("| — | _(aucune question graduée)_ | — |")
    text = fm + "\n".join(lines) + "\n"
    _write_text(os.path.join(root, "cadrage", epic_id, "2-BQO.md"), text)
    return text
