import os
from typing import List, Dict, Any
from effortless_mcp.services.markdown import write_markdown_frontmatter

def sync_decisions_to_markdown(
    markdown_path: str,
    phase_id: str,
    decisions: List[Dict[str, Any]]
) -> None:
    """
    Génère le fichier Markdown du registre de décisions à partir du tableau JSON.
    """
    content = "# 🗃️ Registre de Décisions (ADR)\n\n"
    content += "Ce document récapitule les décisions de conception et d'architecture arrêtées.\n\n"
    content += "---\n\n## 🏛️ Liste des Décisions\n\n"

    if not decisions:
        content += "*Aucune décision enregistrée pour le moment.*\n"
    else:
        for idx, dec in enumerate(decisions, 1):
            content += f"### {idx}. `{dec['id']}` : {dec['title']}\n"
            content += f"* **Statut** : {dec.get('status', 'Accepted')}\n"
            content += f"* **Date** : {dec.get('date', '')}\n"
            content += f"* **Phase** : {dec.get('phase', '')}\n"
            content += f"* **Contexte** : {dec.get('context', '')}\n"
            content += f"* **Décision** : {dec.get('decision', '')}\n"
            
            consequences = dec.get("consequences", [])
            if consequences:
                content += "* **Conséquences** :\n"
                for cons in consequences:
                    content += f"  - {cons}\n"
            
            rejected = dec.get("rejected_alternatives", [])
            if rejected:
                content += "* **Alternatives rejetées** :\n"
                for rej in rejected:
                    content += f"  - {rej}\n"
            
            content += "\n---\n\n"

    metadata = {
        "phase": phase_id,
        "statut": "Actif"
    }

    write_markdown_frontmatter(markdown_path, metadata, content)

def sync_questions_to_markdown(
    markdown_path: str,
    phase_id: str,
    project_name: str,
    questions: List[Dict[str, Any]]
) -> None:
    """
    Génère le fichier Markdown BQO à partir du tableau JSON.
    """
    # Titre principal et métadonnées
    statut_global = "Résolu" if all(q.get("status") == "Resolved" for q in questions) and questions else "En attente"
    if not questions:
        statut_global = "Résolu"  # Pas de question = résolu par défaut

    content = f"# ❓ BQO -- Phase {phase_id} -- {project_name}\n\n"
    content += f"**Projet** : {project_name}  \n"
    content += f"**Phase** : {phase_id}  \n"
    content += f"**Statut** : {statut_global}  \n\n"
    content += "Ce document répertorie les questions ouvertes du projet.\n\n"
    content += "---\n\n## 📋 Tableau Récapitulatif\n\n"

    # Tableau
    content += "| # | Question | Impact | Statut | Confiance | Réponse |\n"
    content += "|---|----------|--------|--------|-----------|---------|\n"
    
    if not questions:
        content += "| - | Aucune question ouverte | - | - | - | - |\n\n"
    else:
        for q in questions:
            statut_fr = "Résolu" if q.get("status") == "Resolved" else "En attente"
            answer_summary = q.get("answer", "")
            if len(answer_summary) > 30:
                answer_summary = answer_summary[:27] + "..."
            content += f"| {q['id']} | {q['question']} | {q.get('impact', 'Structuring')} | {statut_fr} | Moyenne | {answer_summary or '-'} |\n"
        content += "\n"

    content += "---\n\n## 💬 Détail des Questions\n\n"

    if not questions:
        content += "*Aucune question enregistrée.*\n"
    else:
        for q in questions:
            statut_fr = "Résolu" if q.get("status") == "Resolved" else "En attente"
            content += f"### {q['id']} : {q['question']}\n"
            content += f"* **Contexte** : {q.get('context', '')}\n"
            content += f"* **Impact** : **{q.get('impact', 'Structuring')}**\n"
            
            if q.get("suggestion"):
                content += f"* **Suggestion LLM** : {q.get('suggestion')}\n"
                
            content += f"* **Statut** : {statut_fr}\n"
            
            if q.get("answer"):
                content += f"* **Réponse utilisateur** : {q.get('answer')}\n"
                content += f"* **Date de réponse** : {q.get('date_resolved', '')}\n"
            else:
                content += "* **Réponse utilisateur** : \n"
                content += "* **Date de réponse** : \n"
            
            content += "\n---\n\n"

    metadata = {
        "phase": phase_id,
        "statut": statut_global
    }

    write_markdown_frontmatter(markdown_path, metadata, content)
