import os
import subprocess
import json
from typing import List, Dict, Any, Tuple

def get_modified_git_files(project_root: str) -> List[str]:
    """
    Exécute git status pour lister tous les fichiers modifiés, ajoutés ou non suivis.
    """
    try:
        # Fichiers indexés et non indexés
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True
        )
        lines = result.stdout.strip().split("\n")
        modified_files = []
        for line in lines:
            if not line:
                continue
            # La sortie de porcelain est : XY path/to/file
            # Par exemple: M  src/cli/main.py ou ?? src/cli/test.py
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                file_path = parts[1].strip()
                modified_files.append(file_path)
        return modified_files
    except Exception:
        return []

def check_project_drift(project_root: str, tasks_dir: str) -> Tuple[bool, List[str], List[Dict[str, Any]]]:
    """
    Vérifie si le projet dérive : des fichiers de code sous src/ sont modifiés 
    mais aucune tâche dans tasks_dir n'est au statut 'Doing'.
    """
    # 1. Récupérer les fichiers modifiés sous src/
    modified_files = get_modified_git_files(project_root)
    code_modifications = [
        f for f in modified_files 
        if f.startswith("src/") and (f.endswith(".py") or f.endswith(".js") or f.endswith(".ts") or f.endswith(".tsx"))
    ]

    # 2. Charger les tâches actives
    active_tasks = []
    if os.path.exists(tasks_dir) and os.path.isdir(tasks_dir):
        for filename in os.listdir(tasks_dir):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(tasks_dir, filename), "r", encoding="utf-8") as f:
                        task = json.load(f)
                        if task.get("status") == "Doing":
                            active_tasks.append(task)
                except Exception:
                    pass

    # 3. Évaluer la dérive
    # Drift = des fichiers de code sont modifiés, mais 0 tâche n'est active ("Doing")
    is_drifting = len(code_modifications) > 0 and len(active_tasks) == 0

    return is_drifting, code_modifications, active_tasks

def install_git_pre_commit_hook(project_root: str) -> str:
    """
    Écrit un script de pre-commit Git dans .git/hooks/pre-commit qui appelle notre validateur de drift.
    """
    hooks_dir = os.path.join(project_root, ".git", "hooks")
    if not os.path.exists(hooks_dir):
        os.makedirs(hooks_dir, exist_ok=True)
        
    hook_path = os.path.join(hooks_dir, "pre-commit")

    # Le venv et le CLI vivent dans l'INSTALLATION Effortless, PAS dans le projet cible
    # (promesse agnostique : un repo migré n'a pas src/mcp-server). On bake donc les chemins
    # absolus de l'install. Le CLI déduit le projet à valider via son cwd = repo en cours de commit.
    from effortless_mcp.server import get_install_root
    install_root = get_install_root()
    install_python = os.path.join(install_root, "src", "mcp-server", ".venv", "bin", "python")
    install_cli = os.path.join(install_root, "src", "cli", "main.py")

    hook_content = f"""#!/bin/bash
# Hook de pre-commit installé par Effortless pour détecter les dérives de développement (drift)

echo -e "\\033[0;34m[Effortless] Running anti-drift check before commit...\\033[0m"

# Validateur Effortless (interpréteur + CLI résolus dans l'installation Effortless).
# Le drift est évalué sur le dépôt courant (cwd du hook = racine du repo commité).
"{install_python}" "{install_cli}" --drift-check-strict

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo -e "\\033[0;31m[Effortless] [ERROR] Commit blocked: you have modified files but no task is active (status 'Doing') in the backlog.\\033[0m"
    echo -e "Use the interactive test CLI to set the relevant task to 'Doing', or run git commit with --no-verify if needed."
    exit 1
fi

echo -e "\\033[0;32m[Effortless] No drift detected. Pre-commit validation OK.\\033[0m"
exit 0
"""

    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(hook_content)
        
    # Rendre le hook exécutable
    try:
        subprocess.run(["chmod", "+x", hook_path], check=True)
    except Exception:
        pass
        
    return hook_path
