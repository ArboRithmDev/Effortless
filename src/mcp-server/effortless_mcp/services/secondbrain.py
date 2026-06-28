import os
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any

from effortless_mcp.services.markdown import parse_markdown_frontmatter, write_markdown_frontmatter

def get_secondbrain_vault_path() -> Optional[str]:
    """
    Tente de lire la configuration de SecondBrain pour récupérer le chemin du Vault.
    """
    # Ordre canonique : $CLAUDE_CONFIG_DIR/memory-kit.json → ~/.claude/memory-kit.json
    # → ~/.memory-kit/config.json (repli legacy). Le premier qui expose un `vault` gagne.
    candidates = []
    cfg_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg_dir:
        candidates.append(os.path.join(cfg_dir, "memory-kit.json"))
    candidates.append(os.path.expanduser("~/.claude/memory-kit.json"))
    candidates.append(os.path.expanduser("~/.memory-kit/config.json"))

    for config_path in candidates:
        if not os.path.exists(config_path):
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            vault = data.get("vault")
            if vault:
                return vault
        except Exception:
            continue
    return None

def sync_phase_to_secondbrain(project_slug: str, phase_id: str) -> bool:
    """
    Met à jour le statut de phase dans le fichier context.md du projet dans SecondBrain.
    """
    vault_path = get_secondbrain_vault_path()
    if not vault_path:
        return False

    context_path = os.path.join(vault_path, "10-episodes", "projects", project_slug, "context.md")
    if not os.path.exists(context_path):
        return False

    try:
        metadata, content = parse_markdown_frontmatter(context_path)

        # NON-DESTRUCTIF / COMPLÉMENTAIRE : Effortless n'écrit QUE ses propres champs
        # namespacés et ne touche à AUCUN champ géré par Memory Kit. En particulier il ne
        # touche pas `phase` (résumé d'une ligne lu par mem_recall) ni `last-session`, qui
        # ont une sémantique Memory Kit ; les écraser détruirait des données du vault.
        # Le corps Markdown appartient à Memory Kit : on ne le réécrit pas.
        metadata["effortless_phase"] = phase_id
        metadata["effortless_last_sync"] = datetime.now().strftime("%Y-%m-%d")

        write_markdown_frontmatter(context_path, metadata, content)
        return True
    except Exception:
        return False

def create_secondbrain_archive(
    project_slug: str,
    subject: str,
    body_md: str,
    extra_fm: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Crée un fichier d'archive dans SecondBrain et ajoute l'entrée dans history.md.
    """
    vault_path = get_secondbrain_vault_path()
    if not vault_path:
        return None

    project_dir = os.path.join(vault_path, "10-episodes", "projects", project_slug)
    if not os.path.exists(project_dir):
        return None

    # 1. Générer le nom de fichier d'archive
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Hh%M")
    
    # Nettoyer le sujet pour le nom de fichier (kebab-case)
    subject_slug = subject.lower()
    subject_slug = re.sub(r"[^a-z0-9\s-]", "", subject_slug)
    subject_slug = re.sub(r"[\s-]+", "-", subject_slug).strip("-")
    
    filename = f"{date_str}-{time_str}-{project_slug}-{subject_slug}.md"
    archive_path = os.path.join(project_dir, "archives", filename)

    # 2. Écrire le fichier d'archive avec le frontmatter standard
    metadata = {
        "project": project_slug,
        "tags": [f"project/{project_slug}", "zone/episodes", "kind/archive"],
        "zone": "episodes",
        "kind": "archive",
        "date": date_str,
        "subject": subject,
        "display": f"{project_slug} — {subject}"
    }
    if extra_fm:
        metadata.update(extra_fm)

    try:
        write_markdown_frontmatter(archive_path, metadata, body_md)

        # 3. Mettre à jour history.md
        history_path = os.path.join(project_dir, "history.md")
        if os.path.exists(history_path):
            hist_metadata, hist_content = parse_markdown_frontmatter(history_path)
            
            # Formater la nouvelle ligne d'historique
            new_entry = f"- [{date_str} {time_str} — {subject}](archives/{filename})\n"
            
            # Insérer après le titre principal ou après le premier paragraphe
            header_pattern = re.compile(r"(# [^\n]+\n\n)")
            match = header_pattern.search(hist_content)
            
            if match:
                pos = match.end()
                hist_content = hist_content[:pos] + new_entry + hist_content[pos:]
            else:
                hist_content = new_entry + hist_content
                
            write_markdown_frontmatter(history_path, hist_metadata, hist_content)

        return filename
    except Exception:
        return None
