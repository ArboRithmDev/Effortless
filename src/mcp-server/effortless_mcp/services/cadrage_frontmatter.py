"""Frontmatter Obsidian des documents de cadrage Story (004-Story-Cadrage).

Symétrie avec le cadrage projet (docs 0-4) et le cadrage Epic (0-Epic / 1-Stories) :
tout document de cadrage scaffoldé doit être *Obsidian-ready*, c.-à-d. porter un
frontmatter YAML riche (``type``/``projet``/``epic``/``story``/``code``/``tags``).

Ce module NE réécrit jamais un document existant : il ne fait que déposer un stub
(frontmatter + titre + « à rédiger ») pour les documents encore absents. Le contenu
est ensuite rédigé par l'auteur / l'agent au fil des phases.

Convention de nom : ``NN-<CODE>-<slug>.md`` où ``NN`` = ordre de phase et ``CODE``
est un ou plusieurs jetons majuscules (``BQO``, ``FNC-GLO``, ``MET-DEC``…). Le code
est la suite de jetons majuscules qui précède le premier jeton en minuscules (slug).
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Tuple

PROJET = "Effortless"


def parse_doc_code(basename: str) -> str:
    """Extrait le CODE d'un nom de doc ``NN-<CODE>-<slug>``.

    ``05-FNC-SPE-specifications`` → ``FNC-SPE`` ; ``02-BQO-questions`` → ``BQO``.
    Règle : après le préfixe numérique, on prend la suite de jetons entièrement
    majuscules jusqu'au premier jeton contenant une minuscule (le slug).
    """
    stem = os.path.splitext(basename)[0]
    parts = stem.split("-")
    # Saute un éventuel préfixe purement numérique (l'ordre de phase).
    idx = 1 if parts and parts[0].isdigit() else 0
    code_tokens: List[str] = []
    for tok in parts[idx:]:
        if tok and tok.isupper():
            code_tokens.append(tok)
        else:
            break
    return "-".join(code_tokens)


def _title_from_basename(basename: str) -> str:
    """Titre humain lisible dérivé du slug (jetons en minuscules), sinon du code."""
    stem = os.path.splitext(basename)[0]
    parts = stem.split("-")
    idx = 1 if parts and parts[0].isdigit() else 0
    slug = [t for t in parts[idx:] if not (t and t.isupper())]
    if slug:
        return " ".join(slug).replace("_", " ").capitalize()
    return parse_doc_code(basename) or stem


def story_doc_frontmatter(
    epic_id: str,
    story_id: str,
    basename: str,
    phase: str,
    statut: str = "À rédiger",
) -> str:
    """Bloc frontmatter YAML (avec délimiteurs) pour un doc de cadrage Story."""
    code = parse_doc_code(basename)
    document = os.path.splitext(basename)[0]
    lines = [
        "---",
        f"titre: {_title_from_basename(basename)}",
        f"phase: {phase}",
        f"statut: {statut}",
        "type: cadrage-story",
        f"projet: {PROJET}",
        f"epic: {epic_id}",
        f"story: {story_id}",
    ]
    if code:
        lines.append(f"code: {code}")
    lines.append(f"document: {document}")
    lines.append("tags:")
    lines.append("  - cadrage/story")
    lines.append(f"  - cadrage/{epic_id.lower()}")
    if code:
        lines.append(f"  - cadrage/{code.lower()}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _stub_body(basename: str) -> str:
    return f"\n# {_title_from_basename(basename)}\n\n_À rédiger._\n"


def scaffold_story_docs(
    root: str,
    epic_id: str,
    story_id: str,
    phase_docs: Iterable[Tuple[str, str]],
    documents_root: str = "cadrage",
) -> List[str]:
    """Dépose les stubs *manquants* des docs de cadrage d'une Story. Idempotent.

    ``phase_docs`` = itérable de ``(phase_id, basename)``. Un doc déjà présent
    n'est JAMAIS écrasé. Retourne la liste des chemins relatifs créés.
    """
    docs_dir = os.path.join(root, documents_root, epic_id, story_id)
    os.makedirs(docs_dir, exist_ok=True)
    created: List[str] = []
    for phase, basename in phase_docs:
        path = os.path.join(docs_dir, basename)
        if os.path.exists(path):
            continue
        text = story_doc_frontmatter(epic_id, story_id, basename, phase) + _stub_body(basename)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        created.append(os.path.relpath(path, root))
    return created


def backfill_titre(root: str, documents_root: str = "cadrage") -> List[str]:
    """Ajoute ``titre`` au frontmatter des docs de cadrage story existants qui n'en ont
    pas (EVO-014, noms de nœuds lisibles). Idempotent : un doc ayant déjà ``titre`` est
    ignoré ; les non-story et la config ``.obsidian`` sont ignorés. Retourne les chemins
    relatifs modifiés.
    """
    import re
    changed: List[str] = []
    base = os.path.join(root, documents_root)
    for dirpath, _dirs, files in os.walk(base):
        if ".obsidian" in dirpath.split(os.sep):
            continue
        for fn in files:
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
            if not m:
                continue
            fm = m.group(1)
            if "type: cadrage-story" not in fm or re.search(r"^titre:", fm, re.M):
                continue
            new_fm = f"titre: {_title_from_basename(fn)}\n" + fm
            text = text.replace(m.group(1), new_fm, 1)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            changed.append(os.path.relpath(path, root))
    return changed


def phase_docs_from_workflow(config_data: dict) -> List[Tuple[str, str]]:
    """Aplati les required_documents du workflow en ``(phase_id, basename)``.

    Les chemins déclarés dans effortless.json sont figés sur la Story d'init ; on
    n'en garde que le *nom de fichier* (convention de phase) — le dossier est
    rebasculé sur la Story cible par ``scaffold_story_docs``.
    """
    out: List[Tuple[str, str]] = []
    for phase in config_data.get("workflow", {}).get("phases", []):
        pid = phase.get("id", "")
        for doc in phase.get("required_documents", []):
            out.append((pid, os.path.basename(doc)))
    return out
