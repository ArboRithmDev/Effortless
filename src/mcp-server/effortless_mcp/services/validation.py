import os
import json
import re
from typing import Dict, List, Any, Tuple
from effortless_mcp.services.markdown import parse_markdown_frontmatter

def validate_document_structure(doc_path: str, doc_rel_path: str, content: str) -> List[str]:
    """
    Analyse la structure du document Markdown pour s'assurer que :
    1. Il ne contient pas de placeholders non remplis (ex.: TODO, FIXME, ...).
    2. Les sections principales requises sont présentes.
    """
    errors = []
    
    # 1. Vérification des placeholders
    placeholders = [r"\.\.\.", r"\[insérer", r"TODO", r"FIXME", r"<insérer"]
    for pattern in placeholders:
        if re.search(pattern, content, re.IGNORECASE):
            # Ignorer le glossaire qui peut légitimement lister ces termes
            if "glossaire" not in doc_rel_path.lower():
                errors.append(f"Placeholders non remplis détectés ('{pattern.replace('\\', '')}')")
                break
                
    # 2. Vérification des sections obligatoires selon le type de document
    doc_lower = doc_rel_path.lower()
    
    if "bqo" in doc_lower or "questions" in doc_lower:
        if "## tableau récapitulatif" not in content.lower():
            errors.append("Section obligatoire manquante : '## Tableau Récapitulatif'")
        if "## détail des questions" not in content.lower():
            errors.append("Section obligatoire manquante : '## Détail des Questions'")
            
    elif "dec" in doc_lower or "decision" in doc_lower:
        if "## liste des décisions" not in content.lower():
            errors.append("Section obligatoire manquante : '## Liste des Décisions'")
            
    elif "arc" in doc_lower or "architecture" in doc_lower:
        if "## composants clés" not in content.lower():
            errors.append("Section obligatoire manquante : '## Composants Clés'")
            
    elif "pln" in doc_lower or "plan" in doc_lower:
        if "## découpage des tâches" not in content.lower():
            errors.append("Section obligatoire manquante : '## Découpage des Tâches'")
            
    return errors

def load_questions_from_path(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    if os.path.isdir(path):
        questions = []
        for filename in sorted(os.listdir(path)):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(path, filename), "r", encoding="utf-8") as f:
                        questions.append(json.load(f))
                except:
                    pass
        return questions
    else:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []

def validate_phase_documents(
    project_root: str,
    current_phase_id: str,
    required_documents: List[str],
    questions_file_path: str
) -> Tuple[bool, List[Dict[str, Any]], List[str]]:
    """
    Valide les documents requis pour une phase donnée.
    Renvoie :
    - is_valid : booléen (vrai si tout passe)
    - checklist : liste des statuts par document
    - blocking_reasons : liste des explications en cas de blocage
    """
    checklist = []
    blocking_reasons = []
    is_valid = True

    for doc_rel_path in required_documents:
        doc_path = os.path.join(project_root, doc_rel_path)
        doc_status = {
            "document_path": doc_rel_path,
            "is_present": False,
            "is_valid": False,
            "errors": []
        }

        # 1. Existence
        if not os.path.exists(doc_path):
            doc_status["errors"].append("Fichier manquant")
            blocking_reasons.append(f"Document requis manquant : {doc_rel_path}")
            checklist.append(doc_status)
            is_valid = False
            continue

        doc_status["is_present"] = True

        # 2. Contenu minimal (non vide)
        if os.path.getsize(doc_path) == 0:
            doc_status["errors"].append("Fichier vide")
            blocking_reasons.append(f"Document vide : {doc_rel_path}")
            checklist.append(doc_status)
            is_valid = False
            continue

        # 3. Frontmatter YAML et structure
        try:
            metadata, content = parse_markdown_frontmatter(doc_path)
            
            if not metadata:
                doc_status["errors"].append("Frontmatter YAML manquant ou incorrect")
                blocking_reasons.append(f"Frontmatter YAML manquant ou incorrect dans {doc_rel_path}")
                is_valid = False
            else:
                # Vérification des champs requis dans le frontmatter
                if "phase" not in metadata:
                    doc_status["errors"].append("Champ 'phase' manquant dans le Frontmatter")
                    blocking_reasons.append(f"Champ 'phase' manquant dans {doc_rel_path}")
                    is_valid = False
                elif metadata["phase"] != current_phase_id:
                    doc_status["errors"].append(
                        f"La phase du document ({metadata['phase']}) ne correspond pas à la phase active ({current_phase_id})"
                    )
                    blocking_reasons.append(f"Phase incohérente dans {doc_rel_path}")
                    is_valid = False

                if "statut" not in metadata:
                    doc_status["errors"].append("Champ 'statut' manquant dans le Frontmatter")
                    blocking_reasons.append(f"Champ 'statut' manquant dans {doc_rel_path}")
                    is_valid = False
                
                # Validation structurelle et sémantique (placeholders + sections requis)
                struct_errors = validate_document_structure(doc_path, doc_rel_path, content)
                if struct_errors:
                    for err in struct_errors:
                        doc_status["errors"].append(err)
                        blocking_reasons.append(f"Structure invalide dans {doc_rel_path} : {err}")
                    is_valid = False
                
                # Cas spécial : validation BQO
                is_bqo = "bqo" in doc_rel_path.lower() or "questions" in doc_rel_path.lower()
                if is_bqo:
                    if metadata.get("statut") not in ["Résolu", "Resolved"]:
                        doc_status["errors"].append(
                            f"Le statut du BQO ({metadata.get('statut')}) doit être 'Résolu' ou 'Resolved' pour valider la phase"
                        )
                        blocking_reasons.append(f"BQO non résolu : {doc_rel_path}")
                        is_valid = False

            if len(doc_status["errors"]) == 0:
                doc_status["is_valid"] = True

        except Exception as e:
            doc_status["errors"].append(f"Erreur d'analyse : {str(e)}")
            blocking_reasons.append(f"Erreur d'analyse sur {doc_rel_path} : {str(e)}")
            is_valid = False

        checklist.append(doc_status)

    # 4. Validation des questions bloquantes
    if os.path.exists(questions_file_path):
        try:
            questions = load_questions_from_path(questions_file_path)
            for q in questions:
                if (
                    q.get("phase") == current_phase_id
                    and q.get("impact") == "Blocker"
                    and q.get("status") in ["Pending", "En attente"]
                ):
                    blocking_reasons.append(f"Question bloquante non résolue : {q.get('id')} - {q.get('question')}")
                    is_valid = False
        except Exception as e:
            blocking_reasons.append(f"Erreur lors de la lecture des questions : {str(e)}")
            is_valid = False

    return is_valid, checklist, blocking_reasons

