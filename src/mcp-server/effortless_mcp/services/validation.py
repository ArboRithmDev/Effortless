import os
import json
import re
from typing import Dict, List, Any, Tuple
from effortless_mcp.services.markdown import parse_markdown_frontmatter


def _has_h2_section(content: str, phrase: str) -> bool:
    """Vrai si `content` contient un en-tête H2 (`## …`) incluant `phrase`, en tolérant
    un emoji ou une décoration entre `##` et le texte.

    Indispensable : le générateur (sync.py) émet des titres décorés
    (`## 📋 Summary Table`) ; un simple substring `## summary table`
    ne les reconnaîtrait pas et bloquerait à tort la barrière de phase."""
    return re.search(r"(?mi)^\s*##\s+.*" + re.escape(phrase), content) is not None


def validate_document_structure(doc_path: str, doc_rel_path: str, content: str) -> List[str]:
    """
    Analyse la structure du document Markdown pour s'assurer que :
    1. Il ne contient pas de placeholders non remplis (ex.: TODO, FIXME, ...).
    2. Les sections principales requises sont présentes.
    """
    errors = []
    
    # 1. Vérification des placeholders.
    # On exige des formes sentinelles explicites (crochets/chevrons) — un « ... » nu en
    # prose ou dans un extrait de code (def f(...)) est légitime et ne doit PAS bloquer.
    # Les sentinelles entre crochets/chevrons tolèrent la casse ; les sentinelles mot-clé
    # (TODO/FIXME/XXX) sont SENSIBLES à la casse — sinon le statut de tâche légitime `Todo`
    # (même mot, casse différente) déclencherait un faux positif dans un document valide.
    bracket_placeholders = [r"\[\.\.\.\]", r"\[à compléter\]", r"\[to complete\]", r"\[insérer", r"<insérer", r"\[insert", r"<insert"]
    word_placeholders = [r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b"]
    matched = None
    for pattern in bracket_placeholders:
        if re.search(pattern, content, re.IGNORECASE):
            matched = pattern
            break
    if matched is None:
        for pattern in word_placeholders:
            if re.search(pattern, content):  # sensible à la casse
                matched = pattern
                break
    # Ignorer le glossaire qui peut légitimement lister ces termes
    if matched is not None and "glossaire" not in doc_rel_path.lower():
        errors.append(f"Unfilled placeholders detected ('{matched.replace('\\', '')}')")
                
    # 2. Vérification des sections obligatoires selon le type de document
    doc_lower = doc_rel_path.lower()
    
    if "bqo" in doc_lower or "questions" in doc_lower:
        if not _has_h2_section(content, "summary table"):
            errors.append("Required section missing: '## Summary Table'")
        if not _has_h2_section(content, "question details"):
            errors.append("Required section missing: '## Question Details'")

    elif "dec" in doc_lower or "decision" in doc_lower:
        if not _has_h2_section(content, "decision list"):
            errors.append("Required section missing: '## Decision List'")

    elif "arc" in doc_lower or "architecture" in doc_lower:
        if not _has_h2_section(content, "key components"):
            errors.append("Required section missing: '## Key Components'")

    elif "pln" in doc_lower or "plan" in doc_lower:
        if not _has_h2_section(content, "task breakdown"):
            errors.append("Required section missing: '## Task Breakdown'")
            
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
                except (json.JSONDecodeError, OSError):
                    pass
        return questions
    else:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

def validate_phase_documents(
    project_root: str,
    active_phase_id: str,
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
            doc_status["errors"].append("File missing")
            blocking_reasons.append(f"Required document missing: {doc_rel_path}")
            checklist.append(doc_status)
            is_valid = False
            continue

        doc_status["is_present"] = True

        # 2. Contenu minimal (non vide)
        if os.path.getsize(doc_path) == 0:
            doc_status["errors"].append("Empty file")
            blocking_reasons.append(f"Empty document: {doc_rel_path}")
            checklist.append(doc_status)
            is_valid = False
            continue

        # 3. Frontmatter YAML et structure
        try:
            metadata, content = parse_markdown_frontmatter(doc_path)
            
            if not metadata:
                doc_status["errors"].append("Missing or invalid YAML frontmatter")
                blocking_reasons.append(f"Missing or invalid YAML frontmatter in {doc_rel_path}")
                is_valid = False
            else:
                # Vérification des champs requis dans le frontmatter
                if "phase" not in metadata:
                    doc_status["errors"].append("Missing 'phase' field in frontmatter")
                    blocking_reasons.append(f"Missing 'phase' field in {doc_rel_path}")
                    is_valid = False
                elif metadata["phase"] != active_phase_id:
                    doc_status["errors"].append(
                        f"Document phase ({metadata['phase']}) does not match active phase ({active_phase_id})"
                    )
                    blocking_reasons.append(f"Inconsistent phase in {doc_rel_path}")
                    is_valid = False

                if "statut" not in metadata:
                    doc_status["errors"].append("Missing 'statut' field in frontmatter")
                    blocking_reasons.append(f"Missing 'statut' field in {doc_rel_path}")
                    is_valid = False
                
                # Validation structurelle et sémantique (placeholders + sections requis)
                struct_errors = validate_document_structure(doc_path, doc_rel_path, content)
                if struct_errors:
                    for err in struct_errors:
                        doc_status["errors"].append(err)
                        blocking_reasons.append(f"Invalid structure in {doc_rel_path}: {err}")
                    is_valid = False
                
                # Cas spécial : validation BQO
                is_bqo = "bqo" in doc_rel_path.lower() or "questions" in doc_rel_path.lower()
                if is_bqo:
                    if metadata.get("statut") not in ["Résolu", "Resolved"]:
                        doc_status["errors"].append(
                            f"BQO status ({metadata.get('statut')}) must be 'Résolu' or 'Resolved' to validate the phase"
                        )
                        blocking_reasons.append(f"Unresolved BQO: {doc_rel_path}")
                        is_valid = False

            if len(doc_status["errors"]) == 0:
                doc_status["is_valid"] = True

        except Exception as e:
            doc_status["errors"].append(f"Parse error: {str(e)}")
            blocking_reasons.append(f"Parse error on {doc_rel_path}: {str(e)}")
            is_valid = False

        checklist.append(doc_status)

    # 4. Validation des questions bloquantes
    if os.path.exists(questions_file_path):
        try:
            questions = load_questions_from_path(questions_file_path)
            for q in questions:
                if (
                    q.get("phase") == active_phase_id
                    and str(q.get("impact", "")).lower() == "blocker"
                    and q.get("status") not in ["Resolved", "Résolu"]
                ):
                    blocking_reasons.append(f"Unresolved blocking question: {q.get('id')} - {q.get('question')}")
                    is_valid = False
        except Exception as e:
            blocking_reasons.append(f"Error reading questions: {str(e)}")
            is_valid = False

    return is_valid, checklist, blocking_reasons

