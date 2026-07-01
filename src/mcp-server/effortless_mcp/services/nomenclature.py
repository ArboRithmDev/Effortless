"""Nomenclature des identifiants fractals (EVO-005, STO-CADRAGE-02).

L'identifiant logique DEVIENT la forme lisible (dir == id) :
  - Epic  : ``<NNN>-Epic-<Périmètre>``   (NNN = séquence de création, globale)
  - Story : ``<NNN>-Story-<Sujet>``      (NNN = séquence de création, par Epic)

``<Périmètre>`` (Epic) = zone en Titlecase (TRACKER -> Tracker). ``<Sujet>`` (Story) =
slug Title-hyphen dérivé du *titre* de la Story (EVO-011), lisible dans Obsidian.
La migration renomme les
répertoires (``.effortless/epics`` + ``cadrage``) et réécrit toutes les références
(epic.json id/stories[], story.json id/epic_id, state.active_*, backlog.json,
frontmatter des docs de cadrage). Idempotente : un arbre déjà migré donne un plan
vide.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import unicodedata
from typing import Dict, List, Optional


def _robust_move(src: str, dst: str, attempts: int = 5) -> None:
    """Renomme src→dst en tolérant les locks transitoires Windows (indexeur, AV) :
    retries espacés, puis repli sur shutil.move. Lève si tout échoue."""
    last = None
    for i in range(attempts):
        try:
            os.rename(src, dst)
            return
        except OSError as e:
            last = e
            time.sleep(0.15 * (i + 1))
    shutil.move(src, dst)  # dernier recours ; lève si toujours bloqué
    _ = last

_EPIC_RE = re.compile(r"^\d{3}-Epic-.+$")
_STORY_RE = re.compile(r"^\d{3}-Story-.+$")


def perimetre_of(zone: Optional[str], fallback_id: str) -> str:
    """Périmètre Titlecase depuis la zone, sinon dérivé de l'id (EPIC-<ZONE>)."""
    z = zone or fallback_id.replace("EPIC-", "").replace("STO-", "")
    return z.strip().title()


def format_epic_id(seq: int, perimetre: str) -> str:
    return f"{seq:03d}-Epic-{perimetre}"


def format_story_id(seq: int, subject: str) -> str:
    return f"{seq:03d}-Story-{subject}"


# Mots vides (fr/en) écartés du slug de sujet — ne portent pas de sens distinctif.
_STORY_STOPWORDS = {
    "de", "du", "des", "le", "la", "les", "un", "une", "au", "aux", "a",
    "en", "et", "ou", "sur", "pour", "dans", "par", "avec", "vers", "est",
    "the", "of", "to", "for", "and", "or", "l", "d", "in", "on", "with",
    "via", "as", "vs", "plus",
}


def slugify_subject(title: str, max_words: int = 4) -> str:
    """Slug Title-hyphen ASCII dérivé du *titre* d'une Story (sujet lisible).

    Ex : « Anti-dérive étendu au travail cadrage (gate) » → « Anti-Derive-Etendu-Travail ».
    Retire parenthèses et entités HTML (``&lt;``…), translittère les accents (é→e, ç→c),
    écarte les mots vides et les jetons d'une lettre, garde les ``max_words`` premiers
    mots significatifs. Repli « Story » si le titre ne donne aucun mot exploitable.
    """
    t = re.sub(r"\([^)]*\)", " ", title or "")
    t = re.sub(r"&[a-zA-Z]+;|&#\d+;", " ", t)  # entités HTML (&lt; &gt; &amp;…)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    tokens = re.findall(r"[A-Za-z0-9]+", t)
    words = [w for w in tokens if len(w) > 1 and w.lower() not in _STORY_STOPWORDS] or tokens
    slug = "-".join(w.capitalize() for w in words[:max_words])
    return slug or "Story"


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def next_epic_seq(root: str) -> int:
    """Prochaine séquence de création d'Epic : max(seq existants) + 1."""
    epics_dir = os.path.join(root, ".effortless", "epics")
    seqs = []
    if os.path.isdir(epics_dir):
        for name in os.listdir(epics_dir):
            ejson = os.path.join(epics_dir, name, "epic.json")
            if os.path.isfile(ejson):
                s = _read_json(ejson).get("seq")
                seqs.append(s if isinstance(s, int) else 0)
    return (max(seqs) if seqs else 0) + 1


def next_story_seq(root: str, epic_id: str) -> int:
    """Prochaine séquence de création de Story au sein d'un Epic : max(seq) + 1."""
    stories_dir = os.path.join(root, ".effortless", "epics", epic_id, "stories")
    seqs = []
    if os.path.isdir(stories_dir):
        for name in os.listdir(stories_dir):
            sjson = os.path.join(stories_dir, name, "story.json")
            if os.path.isfile(sjson):
                s = _read_json(sjson).get("seq")
                seqs.append(s if isinstance(s, int) else 0)
    return (max(seqs) if seqs else 0) + 1


def epic_with_perimetre_exists(root: str, perimetre: str) -> Optional[str]:
    """Retourne l'id de l'Epic ayant déjà ce périmètre, sinon None (garde anti-doublon)."""
    epics_dir = os.path.join(root, ".effortless", "epics")
    if os.path.isdir(epics_dir):
        for name in os.listdir(epics_dir):
            ejson = os.path.join(epics_dir, name, "epic.json")
            if os.path.isfile(ejson):
                e = _read_json(ejson)
                if perimetre_of(e.get("zone"), e.get("id", name)) == perimetre:
                    return e.get("id", name)
    return None


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _story_sort_key(old_id: str, dirpath: str):
    """Ordonne les stories : numéro de l'id (STO-X-05 -> 5 ; 005-Story-X -> 5)
    sinon date de création du répertoire."""
    m = re.search(r"(\d+)", old_id)
    if m:
        return (0, int(m.group(1)))
    try:
        return (1, os.path.getctime(dirpath))
    except OSError:
        return (1, 0.0)


def plan_nomenclature(root: str) -> dict:
    """Calcule le plan de renommage (dry-run), sans rien modifier.

    Retourne ``{"epics": [...], "changed": bool}``. Les Epics sont ordonnés par date
    de création (getctime) pour attribuer la séquence globale ; les Stories par
    numéro d'id au sein de chaque Epic."""
    epics_dir = os.path.join(root, ".effortless", "epics")
    if not os.path.isdir(epics_dir):
        return {"epics": [], "changed": False}

    entries = []
    for name in os.listdir(epics_dir):
        epic_path = os.path.join(epics_dir, name)
        epic_json = os.path.join(epic_path, "epic.json")
        if not os.path.isfile(epic_json):
            continue
        try:
            ctime = os.path.getctime(epic_path)
        except OSError:
            ctime = 0.0
        epic = _read_json(epic_json)
        # seq explicite prioritaire (déterministe) sinon date de création.
        seq = epic.get("seq")
        sort_key = (0, seq) if isinstance(seq, int) else (1, ctime)
        entries.append((sort_key, name, epic_path, epic))
    entries.sort(key=lambda e: e[0])

    plan_epics = []
    changed = False
    for i, (_ct, dirname, epic_path, epic) in enumerate(entries, start=1):
        old_epic_id = epic.get("id", dirname)
        perimetre = perimetre_of(epic.get("zone"), old_epic_id)
        new_epic_id = format_epic_id(i, perimetre)

        stories_dir = os.path.join(epic_path, "stories")
        story_dirs = []
        if os.path.isdir(stories_dir):
            for sname in os.listdir(stories_dir):
                sp = os.path.join(stories_dir, sname)
                if os.path.isfile(os.path.join(sp, "story.json")):
                    story_dirs.append(sname)
        story_dirs.sort(key=lambda s: _story_sort_key(s, os.path.join(stories_dir, s)))

        story_plan = []
        for j, sname in enumerate(story_dirs, start=1):
            story = _read_json(os.path.join(stories_dir, sname, "story.json"))
            old_sid = story.get("id", sname)
            # Sujet de la Story dérivé de son titre (pas du périmètre de l'Epic) :
            # <NNN>-Story-<Sujet> lisible dans Obsidian (EVO-011).
            subject = slugify_subject(story.get("title", "") or old_sid)
            new_sid = format_story_id(j, subject)
            story_plan.append({"old_id": old_sid, "new_id": new_sid, "seq": j})
            if old_sid != new_sid:
                changed = True

        if old_epic_id != new_epic_id:
            changed = True
        plan_epics.append({
            "old_id": old_epic_id,
            "new_id": new_epic_id,
            "seq": i,
            "perimetre": perimetre,
            "old_dir": dirname,
            "stories": story_plan,
        })
    return {"epics": plan_epics, "changed": changed}


def _rewrite_frontmatter(md_path: str, repl: Dict[str, str]) -> None:
    """Remplace les valeurs epic/story et le tag cadrage/<epic> dans le frontmatter."""
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    if not text.startswith("---\n"):
        return
    end = text.find("\n---\n", 4)
    if end == -1:
        return
    fm, body = text[4:end], text[end + 5:]
    for old, new in repl.items():
        fm = fm.replace(old, new)
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("---\n" + fm + "\n---\n" + body)


def _replace_in_file(path: str, repl: Dict[str, str]) -> None:
    """Remplace des ids en respectant les bordières (un id n'est jamais réécrit
    comme préfixe d'un id plus long : STO-X-1 ne touche pas STO-X-10)."""
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # Clés les plus longues d'abord (stabilité), remplacement borné par (?<![\w-])/(?![\w-]).
    for old in sorted(repl, key=len, reverse=True):
        text = re.sub(r"(?<![\w-])" + re.escape(old) + r"(?![\w-])", repl[old], text)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def apply_nomenclature(root: str, plan: Optional[dict] = None) -> dict:
    """Applique le plan : renomme les répertoires et réécrit toutes les références.

    Idempotent (un plan sans changement ne touche rien). Retourne un rapport
    ``{"epics_renamed", "stories_renamed", "epic_map", "story_map"}``."""
    plan = plan or plan_nomenclature(root)
    epics_dir = os.path.join(root, ".effortless", "epics")
    cadrage_dir = os.path.join(root, "cadrage")

    epic_map: Dict[str, str] = {}
    story_map: Dict[str, str] = {}
    warnings: List[str] = []
    epics_renamed = 0
    stories_renamed = 0

    # === Phase 1 : MODÈLE (.effortless) — critique, doit aboutir. ===
    for ep in plan["epics"]:
        old_epic, new_epic = ep["old_id"], ep["new_id"]
        epic_map[old_epic] = new_epic
        old_epic_path = os.path.join(epics_dir, ep["old_dir"])
        stories_dir = os.path.join(old_epic_path, "stories")

        for st in ep["stories"]:
            old_sid, new_sid = st["old_id"], st["new_id"]
            story_map[old_sid] = new_sid
            old_sp = os.path.join(stories_dir, old_sid)
            sjson = os.path.join(old_sp, "story.json")
            if os.path.isfile(sjson):
                s = _read_json(sjson)
                s["id"] = new_sid
                s["epic_id"] = new_epic
                s["seq"] = st["seq"]
                _write_json(sjson, s)
            if old_sid != new_sid and os.path.isdir(old_sp):
                _robust_move(old_sp, os.path.join(stories_dir, new_sid))
                stories_renamed += 1

        ejson = os.path.join(old_epic_path, "epic.json")
        if os.path.isfile(ejson):
            e = _read_json(ejson)
            e["id"] = new_epic
            e["seq"] = ep["seq"]
            e["stories"] = [st["new_id"] for st in ep["stories"]]
            _write_json(ejson, e)

        if old_epic != new_epic:
            _robust_move(old_epic_path, os.path.join(epics_dir, new_epic))
            epics_renamed += 1

    # === Phase 2 : références globales du modèle (state, backlog). ===
    all_repl = {**epic_map, **story_map}
    _replace_in_file(os.path.join(root, ".effortless", "state.json"), all_repl)
    _replace_in_file(os.path.join(root, ".effortless", "backlog.json"), epic_map)

    # === Phase 3 : CADRAGE — documentation, best-effort (un lock ne corrompt pas le modèle). ===
    for ep in plan["epics"]:
        old_epic, new_epic = ep["old_id"], ep["new_id"]
        try:
            old_cad_epic = os.path.join(cadrage_dir, old_epic)
            new_cad_epic = os.path.join(cadrage_dir, new_epic)
            if os.path.isdir(old_cad_epic) and old_epic != new_epic:
                _robust_move(old_cad_epic, new_cad_epic)
            cad_epic = new_cad_epic if os.path.isdir(new_cad_epic) else old_cad_epic
            if os.path.isdir(cad_epic):
                for st in ep["stories"]:
                    old_cs = os.path.join(cad_epic, st["old_id"])
                    new_cs = os.path.join(cad_epic, st["new_id"])
                    if os.path.isdir(old_cs) and st["old_id"] != st["new_id"]:
                        _robust_move(old_cs, new_cs)
                    cs = new_cs if os.path.isdir(new_cs) else old_cs
                    if os.path.isdir(cs):
                        fm_repl = {
                            f"epic: {old_epic}": f"epic: {new_epic}",
                            f"story: {st['old_id']}": f"story: {st['new_id']}",
                            f"cadrage/{old_epic.lower()}": f"cadrage/{new_epic.lower()}",
                        }
                        for fn in os.listdir(cs):
                            if fn.endswith(".md"):
                                _rewrite_frontmatter(os.path.join(cs, fn), fm_repl)
        except OSError as e:
            warnings.append(f"cadrage {old_epic}: {e} (re-lance après avoir libéré le lock)")

    for fn in ("3-Backlog.md", "4-Evolutions.md"):
        try:
            _replace_in_file(os.path.join(cadrage_dir, fn), all_repl)
        except OSError as e:
            warnings.append(f"cadrage {fn}: {e}")

    return {
        "epics_renamed": epics_renamed,
        "stories_renamed": stories_renamed,
        "epic_map": epic_map,
        "story_map": story_map,
        "warnings": warnings,
    }
