import os
import yaml
import re
from typing import Dict, Tuple, Any

def parse_markdown_frontmatter(file_path: str) -> Tuple[Dict[str, Any], str]:
    """
    Lit un fichier Markdown et extrait le Frontmatter YAML et le reste du contenu.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Le fichier {file_path} n'existe pas.")

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Recherche du frontmatter YAML entre les marqueurs --- au tout début du fichier
    pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
    match = pattern.match(text)

    if not match:
        return {}, text

    yaml_text = match.group(1)
    content = match.group(2)

    try:
        metadata = yaml.safe_load(yaml_text) or {}
    except Exception as e:
        raise ValueError(f"Erreur lors du parsing YAML du Frontmatter dans {file_path}: {e}")

    return metadata, content

def write_markdown_frontmatter(file_path: str, metadata: Dict[str, Any], content: str) -> None:
    """
    Écrit un fichier Markdown avec le Frontmatter YAML fourni et le reste du contenu.
    """
    # Nettoyer le contenu pour éviter d'avoir plusieurs blocs de frontmatter dupliqués
    content_clean = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL).strip()

    yaml_text = yaml.safe_dump(metadata, default_flow_style=False, allow_unicode=True)
    
    # Formater le texte final
    final_text = f"---\n{yaml_text}---\n\n{content_clean}\n"

    # S'assurer que le dossier parent existe
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(final_text)
