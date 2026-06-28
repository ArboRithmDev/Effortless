import os
import json
from typing import Dict, Any, List

def analyze_target_repo(repo_path: str) -> Dict[str, Any]:
    """
    Exécute une analyse statique de la structure de fichiers pour identifier la stack,
    les documentations et propose une réorganisation.
    """
    if not os.path.exists(repo_path):
        raise FileNotFoundError(f"Dépôt cible introuvable : {repo_path}")

    stack = []
    frameworks = []
    docs_files = []
    source_files_count = 0
    detected_folders = []

    # Parcourir les fichiers pour détecter la signature de la stack
    for root, dirs, files in os.walk(repo_path):
        # Ignorer les dossiers système ou virtuels
        if any(ignored in root for ignored in [".git", "node_modules", ".venv", "venv", ".effortless", "dist", "build"]):
            continue

        for file in files:
            # Détection Stack
            if file == "pyproject.toml" or file == "requirements.txt" or file == "setup.py":
                if "Python" not in stack:
                    stack.append("Python")
            elif file == "package.json":
                if "NodeJS/JavaScript" not in stack:
                    stack.append("NodeJS/JavaScript")
                # Détecter framework
                try:
                    with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                        pkg = json.load(f)
                        deps = pkg.get("dependencies", {})
                        dev_deps = pkg.get("devDependencies", {})
                        if "react" in deps or "react" in dev_deps:
                            frameworks.append("React")
                        if "next" in deps:
                            frameworks.append("Next.js")
                        if "vite" in dev_deps or "vite" in deps:
                            frameworks.append("Vite")
                except Exception:
                    pass
            elif file == "Cargo.toml":
                if "Rust" not in stack:
                    stack.append("Rust")
            elif file.endswith(".gradle") or file.endswith(".gradle.kts"):
                if "Kotlin/Java" not in stack:
                    stack.append("Kotlin/Java")
                if "build.gradle.kts" in file and "multiplatform" in root:
                    frameworks.append("Kotlin Multiplatform (KMP)")

            # Détection de docs
            if file.endswith(".md"):
                rel_path = os.path.relpath(os.path.join(root, file), repo_path)
                docs_files.append(rel_path)

            # Compter les fichiers sources
            if file.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".kt", ".rs")):
                source_files_count += 1

    # Identifier les dossiers principaux à la racine
    for entry in os.listdir(repo_path):
        entry_path = os.path.join(repo_path, entry)
        if os.path.isdir(entry_path) and not entry.startswith((".", "node_modules", "venv", "__pycache__")):
            detected_folders.append(entry)

    # Recommander l'organisation
    # Par défaut, toute codebase doit vivre dans src/ et la doc dans cadrage/
    # Si le projet a déjà un dossier src/, on conseille de l'isoler ou de le consolider
    has_src = "src" in detected_folders
    has_docs_folder = any(f.startswith(("docs/", "doc/", "wiki/")) for f in docs_files)

    relocations = []
    # Suggestion de déplacements doc
    for doc in docs_files:
        if doc.lower() == "readme.md":
            continue
        # Déplacer vers cadrage
        relocations.append({
            "source": doc,
            "target": f"cadrage/Phase-001/01-MIG-{os.path.basename(doc)}"
        })

    # Suggestion de déplacements sources si pas de dossier src/
    if not has_src and source_files_count > 0:
        for entry in detected_folders:
            if entry not in ["docs", "doc", "wiki", "tests", "test"]:
                # Vérifier s'il contient des fichiers de code
                relocations.append({
                    "source": entry,
                    "target": f"src/{entry}"
                })

    return {
        "repo_path": repo_path,
        "stack": stack or ["Inconnue"],
        "frameworks": frameworks,
        "docs_files": docs_files,
        "source_files_count": source_files_count,
        "detected_folders": detected_folders,
        "has_src": has_src,
        "has_docs_folder": has_docs_folder,
        "proposed_relocations": relocations
    }
