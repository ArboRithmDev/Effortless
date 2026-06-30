import os
import json
import shutil
from typing import Dict, Any, List

def _backup_existing(repo_path: str) -> List[str]:
    """Sauvegarde non destructive d'une init Effortless préexistante avant overwrite (force=True).
    effortless.json -> effortless.json.bak ; .effortless/ -> .effortless.bak/ (remplace l'ancien .bak)."""
    backed = []
    cfg = os.path.join(repo_path, "effortless.json")
    if os.path.exists(cfg):
        shutil.copy2(cfg, cfg + ".bak")
        backed.append("effortless.json.bak")
    edir = os.path.join(repo_path, ".effortless")
    if os.path.isdir(edir):
        bak = edir + ".bak"
        if os.path.exists(bak):
            shutil.rmtree(bak)
        shutil.copytree(edir, bak)
        backed.append(".effortless.bak/")
    return backed


def _render_migration_preview(config: Dict[str, Any], tasks: List[Dict[str, Any]],
                              analysis: Dict[str, Any]) -> str:
    """Aperçu non destructif : décrit ce que migrate_init écrirait, sans rien toucher au disque."""
    relocations = analysis.get("proposed_relocations", [])
    lines = ["🔬 MIGRATION PREVIEW (dry-run — nothing was written)\n"]
    lines.append(f"Target project: {config['project']['name']}")
    lines.append(
        f"Target workflow: {config['workflow']['current_phase']} "
        f"({len(config['workflow']['phases'])} migration phases)"
    )
    lines.append("Migration Epic/Story: EPIC-MIGRATION › STO-MIGRATION-01 (opale_phase M-observe)")
    lines.append(f"Migration tasks to create: {len(tasks)}")
    lines.append(f"Proposed relocations: {len(relocations)} (original hierarchy preserved)")
    if relocations:
        lines.append("\nRelocations (first 15):")
        for item in relocations[:15]:
            lines.append(f"  • `{item['source']}` -> `{item['target']}`")
        if len(relocations) > 15:
            lines.append(f"  … and {len(relocations) - 15} more.")
    lines.append(
        "\n👉 Non-destructive preview. Re-run effortless_migrate_init(..., confirm=True) "
        "to actually scaffold the Effortless config, tasks and doc templates."
    )
    return "\n".join(lines)


def init_migration_project(repo_path: str, analysis: Dict[str, Any],
                           force: bool = False, dry_run: bool = True) -> str:
    """
    Initialise la configuration Effortless locale dans le dépôt cible avec le backlog de migration.

    Sûr par défaut : `dry_run=True` n'écrit RIEN et retourne un aperçu. Pour scaffolder
    réellement, appeler avec `dry_run=False`. Refuse d'écraser une init Effortless existante
    sauf `force=True`, qui sauvegarde d'abord l'existant en `.bak`.
    """
    effortless_dir = os.path.join(repo_path, ".effortless")
    config_path = os.path.join(repo_path, "effortless.json")

    # 1. Données cibles (construites AVANT tout I/O pour permettre l'aperçu dry-run)
    config = {
        "project": {
            "name": os.path.basename(os.path.normpath(repo_path)),
            "description": "Projet migré vers le framework Effortless",
            "version": "0.1.0"
        },
        "workflow": {
            "current_phase": "M-observe",
            "phases": [
                {
                    "id": "M-observe",
                    "name": "Migration - Observer",
                    "description": "Observation de la codebase et documentation existante",
                    "required_documents": [
                        "cadrage/Phase-001/00-FNC-GLO-glossaire.md",
                        "cadrage/Phase-001/01-TEC-ANA-analyse.md"
                    ]
                },
                {
                    "id": "M-position",
                    "name": "Migration - Positionner",
                    "description": "Restructuration de la documentation et registre des décisions",
                    "required_documents": [
                        "cadrage/Phase-001/03-MET-DEC-registre-decisions.md"
                    ]
                },
                {
                    "id": "M-articulate",
                    "name": "Migration - Articuler",
                    "description": "Règles de refactoring et architecture cible de la codebase",
                    "required_documents": [
                        "cadrage/Phase-001/02-TEC-ARC-architecture-cible.md",
                        "cadrage/Phase-001/04-FNC-SPE-specifications.md"
                    ]
                },
                {
                    "id": "M-launch",
                    "name": "Migration - Lancer",
                    "description": "Plan de développement et de recette de la restructuration",
                    "required_documents": [
                        "cadrage/Phase-001/06-MET-PLN-plan-action.md"
                    ]
                },
                {
                    "id": "M-execute",
                    "name": "Migration - Exécuter",
                    "description": "Application finale des réorganisations physiques de code",
                    "required_documents": []
                }
            ]
        },
        "settings": {
            "storage_dir": ".effortless",
            "documents_dir": "cadrage/Phase-001"
        }
    }

    # 2. État cible (state.json)
    state = {
        "project_name": config["project"]["name"],
        "current_phase": "M-observe",            # keep (transitional fallback)
        "active_epic_id": "EPIC-MIGRATION",      # NEW
        "active_story_id": "STO-MIGRATION-01",   # NEW
        "started_at": "2026-06-28T18:00:00Z",
        "completed_phases": []
    }

    # 3. Tâches de migration initiales
    tasks = [
        {
            "id": "TSK-M-01",
            "title": "Observer la codebase existante et valider le glossaire",
            "description": "Analyser en profondeur les fichiers de code et de documentation existants pour aligner la terminologie.",
            "status": "Doing",
            "depends_on": [],
            "phase": "M-execute"
        },
        {
            "id": "TSK-M-02",
            "title": "Restructurer la documentation existante dans cadrage/",
            "description": "Déplacer et organiser les fichiers Markdown existants dans cadrage/Phase-001/.",
            "status": "Todo",
            "depends_on": ["TSK-M-01"],
            "phase": "M-execute"
        },
        {
            "id": "TSK-M-03",
            "title": "Refactoriser la codebase dans src/",
            "description": "Déplacer les fichiers sources du projet sous src/ et appliquer les conventions monorepos.",
            "status": "Todo",
            "depends_on": ["TSK-M-02"],
            "phase": "M-execute"
        },
        {
            "id": "TSK-M-04",
            "title": "Configurer les outils de tests et de validation",
            "description": "Activer le validateur Effortless et installer le hook Git anti-drift.",
            "status": "Todo",
            "depends_on": ["TSK-M-03"],
            "phase": "M-execute"
        }
    ]

    # 3b. Epic + Story cibles (modèle fractal DEC-22) — émis pour compat resolve_active_phase.
    epic = {
        "id": "EPIC-MIGRATION",
        "title": "Migration vers le framework Effortless",
        "zone": "MIGRATION",
        "stories": ["STO-MIGRATION-01"],
    }
    story = {
        "id": "STO-MIGRATION-01",
        "title": "Onboarding brownfield",
        "epic_id": "EPIC-MIGRATION",
        "opale_phase": "M-observe",
    }

    # 4. Aperçu non destructif (défaut) : ne rien écrire, retourner le plan.
    already = os.path.exists(config_path) or os.path.exists(effortless_dir)
    if dry_run:
        preview = _render_migration_preview(config, tasks, analysis)
        if already:
            preview = (
                "⚠️ NOTE: this project already looks initialised; a real run would require "
                "force=True (existing config/.effortless are backed up first).\n\n"
            ) + preview
        return preview

    # 5. Garde-fou « déjà initialisé » : ne jamais écraser config/docs/workflow sans force.
    if already and not force:
        found = "effortless.json" if os.path.exists(config_path) else ".effortless/"
        return (
            f"⛔ Project already initialised for Effortless (found {found}). "
            "migrate_init will NOT overwrite existing config, docs or workflow.\n"
            "👉 To re-initialise anyway, call effortless_migrate_init(..., confirm=True, force=True) "
            "— the existing effortless.json and .effortless/ are backed up to .bak first."
        )

    backup_note = ""
    if already and force:
        backed = _backup_existing(repo_path)
        if backed:
            backup_note = f" (backed up: {', '.join(backed)})"

    # 6. Écritures réelles (uniquement après dry-run levé et garde-fou franchi)
    os.makedirs(effortless_dir, exist_ok=True)

    # Stockage fractal imbriqué (DEC-22) — chemins construits inline (pas d'import server.py : circulaire).
    epic_dir = os.path.join(effortless_dir, "epics", "EPIC-MIGRATION")
    story_dir = os.path.join(epic_dir, "stories", "STO-MIGRATION-01")
    story_tasks_dir = os.path.join(story_dir, "tasks")
    os.makedirs(story_tasks_dir, exist_ok=True)
    os.makedirs(os.path.join(story_dir, "decisions"), exist_ok=True)
    os.makedirs(os.path.join(story_dir, "questions"), exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    with open(os.path.join(effortless_dir, "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    with open(os.path.join(epic_dir, "epic.json"), "w", encoding="utf-8") as f:
        json.dump(epic, f, indent=2, ensure_ascii=False)

    with open(os.path.join(story_dir, "story.json"), "w", encoding="utf-8") as f:
        json.dump(story, f, indent=2, ensure_ascii=False)

    for t in tasks:
        with open(os.path.join(story_tasks_dir, f"{t['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(t, f, indent=2, ensure_ascii=False)

    with open(os.path.join(effortless_dir, "migration_plan.json"), "w", encoding="utf-8") as f:
        json.dump(analysis["proposed_relocations"], f, indent=2, ensure_ascii=False)

    os.makedirs(os.path.join(repo_path, "cadrage", "Phase-001"), exist_ok=True)

    # Templates initiaux de cadrage M-observe
    with open(os.path.join(repo_path, "cadrage", "Phase-001", "00-FNC-GLO-glossaire.md"), "w", encoding="utf-8") as f:
        f.write("---\nphase: M-observe\nstatut: Active\n---\n# Migration Glossary\n\n- **Migration** : Onboarding onto the Effortless framework.\n")

    with open(os.path.join(repo_path, "cadrage", "Phase-001", "01-TEC-ANA-analyse.md"), "w", encoding="utf-8") as f:
        f.write("---\nphase: M-observe\nstatut: Active\n---\n# Migration Analysis\n\nDetected stack: " + ", ".join(analysis["stack"]) + "\n")

    return f"Project {config['project']['name']} initialised under Effortless with 4 migration tasks{backup_note}."


def apply_migration_project(repo_path: str, dry_run: bool = False) -> str:
    """
    Exécute physiquement les déplacements de fichiers configurés dans le plan de migration.

    `dry_run=True` n'effectue AUCUN déplacement et n'écrit aucun rapport : il retourne
    seulement ce qui serait déplacé (audit non destructif avant validation).
    """
    plan_path = os.path.join(repo_path, ".effortless", "migration_plan.json")
    if not os.path.exists(plan_path):
        return "Error: Migration plan (.effortless/migration_plan.json) not found. Please run effortless_migrate_init first."

    with open(plan_path, "r", encoding="utf-8") as f:
        relocations = json.load(f)

    report_lines = []
    success_count = 0
    movable_count = 0

    for item in relocations:
        src = os.path.join(repo_path, item["source"])
        dst = os.path.join(repo_path, item["target"])

        if os.path.exists(src):
            if dry_run:
                # Audit seul : on n'écrit rien, on ne déplace rien.
                report_lines.append(f"• WOULD MOVE: `{item['source']}` -> `{item['target']}`")
                movable_count += 1
                continue
            # Créer le répertoire parent si nécessaire
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                # shutil.move gère fichier comme dossier de façon identique ici.
                shutil.move(src, dst)
                report_lines.append(f"✅ Moved: `{item['source']}` -> `{item['target']}`")
                success_count += 1
            except Exception as e:
                report_lines.append(f"❌ Failed to move `{item['source']}` : {str(e)}")
        else:
            report_lines.append(f"⚠️ Source not found: `{item['source']}` (already moved?)")

    if dry_run:
        # Aucun effet de bord : ni déplacement, ni migration_report.md écrit.
        body = "\n".join(report_lines) if report_lines else "(nothing to move)"
        return (
            f"🔬 MIGRATION APPLY PREVIEW (dry-run — nothing moved): "
            f"{movable_count}/{len(relocations)} relocations would run.\n{body}\n"
            "👉 Re-run effortless_migrate_apply(..., dry_run=False) to perform the moves."
        )

    # Écrire le rapport de migration
    report_content = "# Physical Migration Report\n\n"
    report_content += "\n".join(report_lines)

    with open(os.path.join(repo_path, "migration_report.md"), "w", encoding="utf-8") as f:
        f.write(report_content)

    return f"Migration applied: {success_count}/{len(relocations)} relocations completed. Details in 'migration_report.md'."
