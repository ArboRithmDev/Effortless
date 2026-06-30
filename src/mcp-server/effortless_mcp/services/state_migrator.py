import os
import json
import shutil


def _move_registry(src_dir: str, dst_dir: str) -> int:
    """Déplace tous les fichiers *.json de src_dir vers dst_dir.

    Retourne le nombre de fichiers déplacés. Source absente/vide -> 0 (silencieux).
    Ignore sous-dossiers et fichiers non-json. En cas de collision, le fichier
    cible est écrasé (idempotence). stdlib pure (os, shutil).
    """
    if not os.path.isdir(src_dir):
        return 0
    os.makedirs(dst_dir, exist_ok=True)
    moved = 0
    for name in os.listdir(src_dir):
        src = os.path.join(src_dir, name)
        if not os.path.isfile(src) or not name.endswith(".json"):
            continue
        dst = os.path.join(dst_dir, name)
        if os.path.exists(dst):
            os.remove(dst)
        shutil.move(src, dst)
        moved += 1
    return moved


def migrate_state_to_fractal(root: str, dry_run: bool = True) -> str:
    """Auto-migration d'un projet Effortless du modèle global plat (state.current_phase)
    vers le modèle fractal (DEC-22).

    SCAFFOLD UNIQUEMENT : crée l'Epic + la Story par défaut et positionne les pointeurs
    d'état (active_epic_id / active_story_id). Ne déplace AUCUN registre (tasks / decisions /
    questions) ni les documents de cadrage — c'est l'affaire de tâches séparées.

    stdlib pure (os, json). N'importe RIEN depuis effortless_mcp.server (import circulaire) :
    tous les chemins sont construits inline avec os.path.join.
    """
    state_path = os.path.join(root, ".effortless", "state.json")
    epic_dir = os.path.join(root, ".effortless", "epics", "EPIC-PROJET")
    story_dir = os.path.join(epic_dir, "stories", "STO-PROJET-01")

    # 1. state.json absent -> erreur, aucune écriture.
    if not os.path.exists(state_path):
        return f"Error: {state_path} not initialized"

    # 2. Charger state.json.
    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    # 3. Idempotence : déjà migré -> no-op, aucune écriture (dry_run comme réel).
    if state.get("active_epic_id") and state.get("active_story_id"):
        return "Already migrated to fractal model (EPIC-PROJET / STO-PROJET-01)."

    current_phase = state.get("current_phase")

    # 4. Dicts cibles.
    epic = {
        "id": "EPIC-PROJET",
        "zone": "PROJET",
        "title": "Cadrage & pilotage du projet",
        "description": "Epic racine absorbant le cadrage et la progression globale du projet (modèle fractal).",
        "status": "Open",
        "stories": ["STO-PROJET-01"],
    }
    story = {
        "id": "STO-PROJET-01",
        "epic_id": "EPIC-PROJET",
        "zone": "PROJET",
        "title": "Story par défaut — progression du projet",
        "opale_phase": current_phase,
        "status": "Doing",
    }

    # 5. Dry-run (défaut) : aperçu non destructif, rien n'est écrit.
    if dry_run:
        lines = ["🔬 FRACTAL MIGRATION PREVIEW (dry-run — nothing was written)\n"]
        lines.append("Would create Epic:  EPIC-PROJET (Cadrage & pilotage du projet)")
        lines.append("Would create Story: STO-PROJET-01 (Story par défaut — progression du projet)")
        lines.append(f"Would set story.opale_phase = {current_phase!r} (from state.current_phase)")
        lines.append("Would set state.active_epic_id = EPIC-PROJET, state.active_story_id = STO-PROJET-01")
        return "\n".join(lines)

    # 6. Réel : scaffolder l'arborescence et écrire les fichiers.
    os.makedirs(story_dir, exist_ok=True)
    os.makedirs(os.path.join(story_dir, "tasks"), exist_ok=True)
    os.makedirs(os.path.join(story_dir, "decisions"), exist_ok=True)
    os.makedirs(os.path.join(story_dir, "questions"), exist_ok=True)
    os.makedirs(epic_dir, exist_ok=True)

    with open(os.path.join(epic_dir, "epic.json"), "w", encoding="utf-8") as f:
        json.dump(epic, f, indent=2, ensure_ascii=False)
    with open(os.path.join(story_dir, "story.json"), "w", encoding="utf-8") as f:
        json.dump(story, f, indent=2, ensure_ascii=False)

    # Pointeurs d'état. current_phase est CONSERVÉ (fallback transitoire, retiré plus tard).
    state["active_epic_id"] = "EPIC-PROJET"
    state["active_story_id"] = "STO-PROJET-01"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    # 7. Déplacer les registres globaux plats vers les sous-registres de la Story.
    eff_dir = os.path.join(root, ".effortless")
    n_tasks = _move_registry(
        os.path.join(eff_dir, "tasks"), os.path.join(story_dir, "tasks")
    )
    n_decisions = _move_registry(
        os.path.join(eff_dir, "decisions"), os.path.join(story_dir, "decisions")
    )
    n_questions = _move_registry(
        os.path.join(eff_dir, "questions"), os.path.join(story_dir, "questions")
    )

    return (
        "Migrated to fractal model: created Epic EPIC-PROJET and Story STO-PROJET-01 "
        f"(opale_phase={current_phase!r}). State pointers set; current_phase kept as transitional fallback. "
        f"Relocated registries into STO-PROJET-01: {n_tasks} task(s), {n_decisions} decision(s), {n_questions} question(s)."
    )
