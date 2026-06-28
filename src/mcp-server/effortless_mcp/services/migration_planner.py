import os
import json
import shutil
from typing import Dict, Any, List

def init_migration_project(repo_path: str, analysis: Dict[str, Any]) -> str:
    """
    Initialise la configuration Effortless locale dans le dépôt cible avec le backlog de migration.
    """
    effortless_dir = os.path.join(repo_path, ".effortless")
    os.makedirs(effortless_dir, exist_ok=True)
    os.makedirs(os.path.join(effortless_dir, "tasks"), exist_ok=True)
    os.makedirs(os.path.join(effortless_dir, "decisions"), exist_ok=True)
    os.makedirs(os.path.join(effortless_dir, "questions"), exist_ok=True)

    # 1. Écrire effortless.json cible
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

    with open(os.path.join(repo_path, "effortless.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # 2. Écrire state.json cible
    state = {
        "project_name": config["project"]["name"],
        "current_phase": "M-observe",
        "started_at": "2026-06-28T18:00:00Z",
        "completed_phases": []
    }
    with open(os.path.join(effortless_dir, "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    # 3. Écrire les tâches de migration initiales
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

    for t in tasks:
        with open(os.path.join(effortless_dir, "tasks", f"{t['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(t, f, indent=2, ensure_ascii=False)

    # 4. Sauvegarder la proposition de plan de migration physique
    with open(os.path.join(effortless_dir, "migration_plan.json"), "w", encoding="utf-8") as f:
        json.dump(analysis["proposed_relocations"], f, indent=2, ensure_ascii=False)

    # 5. Créer les dossiers de cadrage cibles
    os.makedirs(os.path.join(repo_path, "cadrage", "Phase-001"), exist_ok=True)

    # Créer les templates initiaux de cadrage M-observe
    with open(os.path.join(repo_path, "cadrage", "Phase-001", "00-FNC-GLO-glossaire.md"), "w", encoding="utf-8") as f:
        f.write("---\nphase: M-observe\nstatut: Actif\n---\n# Glossaire de Migration\n\n- **Migration** : Passage sous le framework Effortless.\n")

    with open(os.path.join(repo_path, "cadrage", "Phase-001", "01-TEC-ANA-analyse.md"), "w", encoding="utf-8") as f:
        f.write("---\nphase: M-observe\nstatut: Actif\n---\n# Analyse de Migration\n\nStack détectée : " + ", ".join(analysis["stack"]) + "\n")

    return f"Projet {config['project']['name']} initialisé sous Effortless avec 4 tâches de migration."


def apply_migration_project(repo_path: str) -> str:
    """
    Exécute physiquement les déplacements de fichiers configurés dans le plan de migration.
    """
    plan_path = os.path.join(repo_path, ".effortless", "migration_plan.json")
    if not os.path.exists(plan_path):
        return "Erreur : Plan de migration (.effortless/migration_plan.json) introuvable. Veuillez exécuter effortless_migrate_init d'abord."

    with open(plan_path, "r", encoding="utf-8") as f:
        relocations = json.load(f)

    report_lines = []
    success_count = 0

    for item in relocations:
        src = os.path.join(repo_path, item["source"])
        dst = os.path.join(repo_path, item["target"])

        if os.path.exists(src):
            # Créer le répertoire parent si nécessaire
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                if os.path.isdir(src):
                    # Déplacer le dossier
                    shutil.move(src, dst)
                else:
                    # Déplacer le fichier
                    shutil.move(src, dst)
                report_lines.append(f"✅ Déplacé: `{item['source']}` -> `{item['target']}`")
                success_count += 1
            except Exception as e:
                report_lines.append(f"❌ Échec de déplacement de `{item['source']}` : {str(e)}")
        else:
            report_lines.append(f"⚠️ Source introuvable : `{item['source']}` (déjà déplacé ?)")

    # Écrire le rapport de migration
    report_content = "# Rapport de Migration Physique\n\n"
    report_content += "\n".join(report_lines)
    
    with open(os.path.join(repo_path, "migration_report.md"), "w", encoding="utf-8") as f:
        f.write(report_content)

    return f"Migration appliquée : {success_count}/{len(relocations)} réorganisations effectuées. Détails dans 'migration_report.md'."
