import os
import json
from datetime import datetime
import socket
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, HTTPServer
from typing import Optional, List, Dict, Any
from fastmcp import FastMCP
from pydantic import BaseModel, Field

# Imports internes
from effortless_mcp.models.config import EffortlessConfig, ProjectMeta, WorkflowConfig, PhaseConfig, SettingsConfig
from effortless_mcp.models.state import ProjectState, CompletedPhase
from effortless_mcp.models.decision import Decision
from effortless_mcp.models.question import Question
from effortless_mcp.models.task import Task
from effortless_mcp.services.validation import validate_phase_documents
from effortless_mcp.services.sync import sync_decisions_to_markdown, sync_questions_to_markdown
from effortless_mcp.services.secondbrain import sync_phase_to_secondbrain, create_secondbrain_archive, get_secondbrain_vault_path
from effortless_mcp.services.drift import check_project_drift, install_git_pre_commit_hook
from effortless_mcp.services.deploy import deploy_to_mcp_clients
from effortless_mcp.services.repo_analyzer import analyze_target_repo
from effortless_mcp.services.migration_planner import init_migration_project, apply_migration_project
from effortless_mcp.services.session_loop import init_autonomous_loop, step_autonomous_loop



# Initialisation de FastMCP
mcp = FastMCP("Effortless")

def get_project_root() -> str:
    """Retourne la racine du projet courant.

    Priorité à la variable d'environnement EFFORTLESS_PROJECT_ROOT (injectée par
    le déploiement multi-client), car la plupart des clients MCP ne lancent pas
    le serveur avec le cwd positionné sur la racine du projet. Repli sur le cwd.
    """
    return os.environ.get("EFFORTLESS_PROJECT_ROOT") or os.getcwd()

def get_paths(root: str) -> Dict[str, str]:
    """Retourne tous les chemins de fichiers clés pour un projet."""
    config_path = os.path.join(root, "effortless.json")
    
    # Lire le storage_dir depuis la config si présent
    storage_dir = ".effortless"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                storage_dir = data.get("settings", {}).get("storage_dir", ".effortless")
        except:
            pass
            
    storage_path = os.path.join(root, storage_dir)
    return {
        "config": config_path,
        "storage": storage_path,
        "state": os.path.join(storage_path, "state.json"),
        "decisions": os.path.join(storage_path, "decisions"),
        "questions": os.path.join(storage_path, "questions"),
        "tasks": os.path.join(storage_path, "tasks"),
    }

def load_entities(dir_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(dir_path):
        return []
    if not os.path.isdir(dir_path):
        # Fallback pour compatibilité si c'est encore un fichier
        try:
            with open(dir_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
            
    entities = []
    for filename in sorted(os.listdir(dir_path)):
        if filename.endswith(".json"):
            file_path = os.path.join(dir_path, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    entities.append(json.load(f))
            except:
                pass
    return entities

def save_entity(dir_path: str, entity_id: str, entity_data: Dict[str, Any]) -> None:
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, f"{entity_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(entity_data, f, indent=2, ensure_ascii=False)


# --- 1. Outils d'Initialisation & Statut ---

@mcp.tool()
def effortless_init(
    project_name: Optional[str] = None,
    description: Optional[str] = None,
    force: bool = False
) -> str:
    """
    Initialise la configuration Effortless et les répertoires de base dans le dépôt.
    """
    root = get_project_root()
    paths = get_paths(root)
    
    if os.path.exists(paths["config"]) and not force:
        return "Erreur : Un fichier effortless.json existe déjà. Utilisez force=True pour écraser."

    # Nom de projet par défaut
    name = project_name or os.path.basename(os.path.abspath(root))
    
    # Configuration par défaut (OPAL)
    config = EffortlessConfig(
        project=ProjectMeta(name=name, description=description, version="0.1.0"),
        workflow=WorkflowConfig(
            current_phase="O-analyse",
            phases=[
                PhaseConfig(
                    id="O-analyse",
                    name="Observer",
                    description="Analyse de l'existant, glossaire métier et cartographie technique",
                    required_documents=[
                        "cadrage/Phase-001/00-FNC-GLO-glossaire.md",
                        "cadrage/Phase-001/01-TEC-ANA-analyse.md",
                        "cadrage/Phase-001/02-BQO-questions.md"
                    ]
                ),
                PhaseConfig(
                    id="P-cadrage",
                    name="Positionner",
                    description="Cadrage décisionnel et architecture cible",
                    required_documents=[
                        "cadrage/Phase-001/03-TEC-ARC-architecture-cible.md",
                        "cadrage/Phase-001/04-MET-DEC-registre-decisions.md"
                    ]
                ),
                PhaseConfig(
                    id="A-specs",
                    name="Articuler",
                    description="Spécifications fonctionnelles et techniques détaillées",
                    required_documents=[
                        "cadrage/Phase-001/05-FNC-SPE-specifications.md",
                        "cadrage/Phase-001/06-TEC-API-contrat-api.md"
                    ]
                ),
                PhaseConfig(
                    id="L-plan",
                    name="Lancer",
                    description="Plan d'implémentation et découpage en tâches",
                    required_documents=[
                        "cadrage/Phase-001/07-MET-PLN-plan-action.md"
                    ]
                )
            ]
        ),
        settings=SettingsConfig(
            storage_dir=".effortless",
            documents_dir="cadrage/Phase-001"
        )
    )

    # Création du fichier effortless.json
    with open(paths["config"], "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)

    # Création du dossier .effortless
    os.makedirs(paths["storage"], exist_ok=True)

    # Initialisation de state.json
    state = ProjectState(
        project_name=name,
        current_phase="O-analyse",
        started_at=datetime.utcnow().isoformat() + "Z"
    )
    with open(paths["state"], "w", encoding="utf-8") as f:
        json.dump(state.model_dump(), f, indent=2, ensure_ascii=False)

    # Initialisation des répertoires d'entités
    for key in ["decisions", "questions", "tasks"]:
        os.makedirs(paths[key], exist_ok=True)

    # Création du dossier de documents
    os.makedirs(os.path.join(root, "cadrage", "Phase-001"), exist_ok=True)

    # Création d'un template de glossaire par défaut pour démarrer
    glossary_path = os.path.join(root, "cadrage", "Phase-001", "00-FNC-GLO-glossaire.md")
    if not os.path.exists(glossary_path):
        with open(glossary_path, "w", encoding="utf-8") as f:
            f.write("---\nphase: O-analyse\nstatut: Actif\n---\n\n# 📓 Glossaire Métier\n\nDéfinissez ici vos termes métiers.\n")

    return f"Projet '{name}' initialisé avec succès sous {root}."

@mcp.tool()
def effortless_status() -> str:
    """
    Retourne le statut actuel du projet, la checklist de phase et l'éligibilité pour la phase suivante.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["config"]) or not os.path.exists(paths["state"]):
        return "Erreur : Projet non initialisé. Veuillez exécuter 'effortless_init'."

    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)

    current_phase_id = state_data.get("current_phase")
    
    # Trouver la phase de configuration correspondante
    phases_list = config_data.get("workflow", {}).get("phases", [])
    phase_config = next((p for p in phases_list if p["id"] == current_phase_id), None)

    if not phase_config:
        return f"Erreur : La phase active '{current_phase_id}' n'est pas définie dans effortless.json."

    required_docs = phase_config.get("required_documents", [])
    
    is_valid, checklist, blocking_reasons = validate_phase_documents(
        project_root=root,
        current_phase_id=current_phase_id,
        required_documents=required_docs,
        questions_file_path=paths["questions"]
    )

    # Récupérer les questions en suspens
    open_questions_list = []
    if os.path.exists(paths["questions"]):
        questions = load_entities(paths["questions"])
        open_questions_list = [q for q in questions if q.get("status") != "Resolved" and q.get("phase") == current_phase_id]

    status_report = f"📋 Statut du Projet : {state_data.get('project_name')}\n"
    status_report += f"Phase en cours : **{phase_config.get('name')}** ({current_phase_id})\n"
    status_report += f"Éligibilité pour la phase suivante : {'✅ OUI (Prêt)' if is_valid else '❌ NON (Bloqué)'}\n\n"

    status_report += "🔍 Checklist des documents requis :\n"
    for item in checklist:
        status_icon = "✅" if item["is_valid"] else ("⚠️" if item["is_present"] else "❌")
        error_msg = f" ({', '.join(item['errors'])})" if item["errors"] else ""
        status_report += f"- {status_icon} `{item['document_path']}`{error_msg}\n"

    if open_questions_list:
        status_report += "\n❓ Questions ouvertes de cette phase :\n"
        for q in open_questions_list:
            status_report += f"- [`{q['id']}`] **{q['question']}** (Impact: {q['impact']})\n"

    if blocking_reasons:
        status_report += "\n❌ Raisons bloquantes :\n"
        for reason in blocking_reasons:
            status_report += f"- {reason}\n"

    return status_report

@mcp.tool()
def effortless_phase_next() -> str:
    """
    Transitionne le projet vers la phase suivante configurée si toutes les barrières sont levées.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["config"]) or not os.path.exists(paths["state"]):
        return "Erreur : Projet non initialisé."

    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)

    current_phase_id = state_data.get("current_phase")
    phases_list = config_data.get("workflow", {}).get("phases", [])
    
    # Trouver l'index de la phase en cours
    current_idx = next((i for i, p in enumerate(phases_list) if p["id"] == current_phase_id), -1)

    if current_idx == -1:
        return f"Erreur : Phase active '{current_phase_id}' inconnue."

    if current_idx == len(phases_list) - 1:
        return "Vous êtes déjà à la dernière phase configurée du projet !"

    # Valider les barrières de la phase en cours
    phase_config = phases_list[current_idx]
    required_docs = phase_config.get("required_documents", [])
    is_valid, checklist, blocking_reasons = validate_phase_documents(
        project_root=root,
        current_phase_id=current_phase_id,
        required_documents=required_docs,
        questions_file_path=paths["questions"]
    )

    if not is_valid:
        return "Transition bloquée :\n" + "\n".join([f"- {r}" for r in blocking_reasons])

    # Effectuer la transition
    next_phase = phases_list[current_idx + 1]
    
    state_data["completed_phases"].append({
        "id": current_phase_id,
        "completed_at": datetime.utcnow().isoformat() + "Z"
    })
    state_data["current_phase"] = next_phase["id"]

    with open(paths["state"], "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2, ensure_ascii=False)

    # --- Symbiose SecondBrain ---
    project_slug = state_data.get("project_name", "effortless").lower()
    sb_msg = ""
    vault_path = get_secondbrain_vault_path()
    if vault_path:
        # 1. Mettre à jour context.md dans SecondBrain
        sync_success = sync_phase_to_secondbrain(project_slug, next_phase["id"])
        
        # 2. Créer une archive récapitulative
        archive_subject = f"Fin de la phase {current_phase_id} et passage à {next_phase['id']}"
        archive_body = f"# Rapport de Fin de Phase -- {current_phase_id}\n\n"
        archive_body += f"Le projet **{state_data.get('project_name')}** a validé toutes les barrières de la phase **{phase_config.get('name')}**.\n\n"
        archive_body += f"### 🔍 Checklist des Documents :\n"
        for item in checklist:
            status_icon = "✅" if item["is_valid"] else "❌"
            archive_body += f"- {status_icon} `{item['document_path']}`\n"
            
        archive_name = create_secondbrain_archive(project_slug, archive_subject, archive_body)
        if sync_success and archive_name:
            sb_msg = f"\n[Symbiose SecondBrain] Synchro context.md et archive '{archive_name}' créés dans {vault_path}."
        else:
            sb_msg = "\n[Symbiose SecondBrain] Liaison configurée mais impossible de synchroniser les fichiers (projet introuvable dans le vault ?)."
    else:
        sb_msg = "\n[Symbiose SecondBrain] SecondBrain non détecté ou vault non configuré dans ~/.memory-kit/config.json."

    return f"Transition effectuée avec succès de '{current_phase_id}' vers '{next_phase['id']}' ({next_phase['name']}).{sb_msg}"

# --- 2. Outils de Décisions (ADR) ---

@mcp.tool()
def effortless_decision_add(
    title: str,
    context: str,
    decision: str,
    consequences: List[str],
    rejected_alternatives: Optional[List[str]] = None
) -> str:
    """
    Enregistre une décision d'architecture dans la base de données interne et synchronise le Markdown.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["decisions"]) or not os.path.exists(paths["state"]):
        return "Erreur : Projet non initialisé."

    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    current_phase_id = state_data.get("current_phase")

    decisions = load_entities(paths["decisions"])

    # ID Séquentiel
    dec_id = f"DEC-{len(decisions) + 1:02d}"
    
    new_dec = Decision(
        id=dec_id,
        title=title,
        status="Accepted",
        phase=current_phase_id,
        date=datetime.now().strftime("%Y-%m-%d"),
        context=context,
        decision=decision,
        consequences=consequences,
        rejected_alternatives=rejected_alternatives or []
    )

    new_dec_dump = new_dec.model_dump()
    decisions.append(new_dec_dump)

    # Sauvegarde JSON individuelle
    save_entity(paths["decisions"], dec_id, new_dec_dump)

    # Synchronisation Markdown
    # Trouver le chemin du fichier de décisions dans effortless.json
    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    docs_dir = config_data.get("settings", {}).get("documents_dir", "cadrage/Phase-001")
    # Rechercher s'il y a un document de type DEC requis dans la phase
    phases_list = config_data.get("workflow", {}).get("phases", [])
    current_phase_cfg = next((p for p in phases_list if p["id"] == current_phase_id), None)
    
    dec_doc_rel = None
    if current_phase_cfg:
        for doc in current_phase_cfg.get("required_documents", []):
            if "dec" in doc.lower() or "decision" in doc.lower():
                dec_doc_rel = doc
                break
                
    if not dec_doc_rel:
        dec_doc_rel = f"{docs_dir}/03-MET-DEC-registre-decisions.md"

    markdown_path = os.path.join(root, dec_doc_rel)
    sync_decisions_to_markdown(markdown_path, current_phase_id, decisions)

    return f"Décision {dec_id} ajoutée et synchronisée dans {dec_doc_rel}."

# --- 3. Outils de Questions (BQO) ---

@mcp.tool()
def effortless_question_ask(
    question: str,
    context: str,
    impact: str = "Structuring", # Blocker, Structuring, Minor
    suggestion: Optional[str] = None
) -> str:
    """
    Pose une nouvelle question dans le BQO (Bordereau de Questions Ouvertes) de la phase active.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["questions"]) or not os.path.exists(paths["state"]):
        return "Erreur : Projet non initialisé."

    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    current_phase_id = state_data.get("current_phase")
    project_name = state_data.get("project_name")

    questions = load_entities(paths["questions"])

    # ID Séquentiel
    q_id = f"Q-{len(questions) + 1:02d}"
    
    new_q = Question(
        id=q_id,
        phase=current_phase_id,
        question=question,
        status="Pending",
        impact=impact,
        context=context,
        suggestion=suggestion
    )

    new_q_dump = new_q.model_dump()
    questions.append(new_q_dump)

    # Sauvegarde JSON individuelle
    save_entity(paths["questions"], q_id, new_q_dump)

    # Synchronisation Markdown
    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    docs_dir = config_data.get("settings", {}).get("documents_dir", "cadrage/Phase-001")
    phases_list = config_data.get("workflow", {}).get("phases", [])
    current_phase_cfg = next((p for p in phases_list if p["id"] == current_phase_id), None)
    
    bqo_doc_rel = None
    if current_phase_cfg:
        for doc in current_phase_cfg.get("required_documents", []):
            if "bqo" in doc.lower() or "question" in doc.lower():
                bqo_doc_rel = doc
                break
                
    if not bqo_doc_rel:
        bqo_doc_rel = f"{docs_dir}/02-BQO-questions.md"

    markdown_path = os.path.join(root, bqo_doc_rel)
    # Ne synchroniser que les questions de la phase en cours pour le fichier de phase
    phase_questions = [q for q in questions if q.get("phase") == current_phase_id]
    sync_questions_to_markdown(markdown_path, current_phase_id, project_name, phase_questions)

    return f"Question {q_id} posée et synchronisée dans {bqo_doc_rel}."

@mcp.tool()
def effortless_question_resolve(
    question_id: str,
    answer: str
) -> str:
    """
    Résout une question du BQO en enregistrant la réponse officielle.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["questions"]) or not os.path.exists(paths["state"]):
        return "Erreur : Projet non initialisé."

    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    project_name = state_data.get("project_name")

    questions = load_entities(paths["questions"])

    target_q = next((q for q in questions if q["id"] == question_id), None)
    if not target_q:
        return f"Erreur : Question '{question_id}' introuvable."

    target_q["status"] = "Resolved"
    target_q["answer"] = answer
    target_q["date_resolved"] = datetime.now().strftime("%Y-%m-%d")

    # Sauvegarde JSON individuelle
    save_entity(paths["questions"], question_id, target_q)

    # Récupérer la phase de la question pour mettre à jour son fichier Markdown
    q_phase_id = target_q["phase"]

    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    docs_dir = config_data.get("settings", {}).get("documents_dir", "cadrage/Phase-001")
    phases_list = config_data.get("workflow", {}).get("phases", [])
    q_phase_cfg = next((p for p in phases_list if p["id"] == q_phase_id), None)
    
    bqo_doc_rel = None
    if q_phase_cfg:
        for doc in q_phase_cfg.get("required_documents", []):
            if "bqo" in doc.lower() or "question" in doc.lower():
                bqo_doc_rel = doc
                break
                
    if not bqo_doc_rel:
        bqo_doc_rel = f"{docs_dir}/02-BQO-questions.md"

    markdown_path = os.path.join(root, bqo_doc_rel)
    phase_questions = [q for q in questions if q.get("phase") == q_phase_id]
    sync_questions_to_markdown(markdown_path, q_phase_id, project_name, phase_questions)

    # Vérification s'il reste d'autres questions bloquantes pour la phase de la question
    has_more_blockers = any(
        q.get("phase") == q_phase_id
        and q.get("impact") == "Blocker"
        and q.get("status") != "Resolved"
        for q in questions
    )

    # Si c'était la dernière question bloquante et que tous les documents sont conformes,
    # nous pouvons le notifier.
    blocker_info = "Il reste des questions bloquantes pour cette phase." if has_more_blockers else "Plus aucune question bloquante pour cette phase."

    return f"Question {question_id} résolue avec succès. {blocker_info}"

# --- 4. Outils de Tâches ---

@mcp.tool()
def effortless_task_add(
    title: str,
    description: Optional[str] = None,
    depends_on: Optional[List[str]] = None
) -> str:
    """
    Crée une tâche associée à la phase active du projet.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["tasks"]) or not os.path.exists(paths["state"]):
        return "Erreur : Projet non initialisé."

    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    current_phase_id = state_data.get("current_phase")

    tasks = load_entities(paths["tasks"])

    # Déterminer le préfixe basé sur la phase active
    parts = current_phase_id.split("-")
    if len(parts) >= 3 and parts[0].lower() == "phase":
        prefix = "-".join(parts[:3])
    elif len(parts) >= 1:
        prefix = parts[0]
    else:
        prefix = "TSK"

    # Compter les tâches déjà créées dans cette même phase pour calculer le nouvel index
    phase_tasks = [t for t in tasks if t.get("phase") == current_phase_id]
    tsk_id = f"TSK-{prefix}-{len(phase_tasks) + 1:02d}"

    new_task = Task(
        id=tsk_id,
        title=title,
        description=description,
        status="Todo",
        phase=current_phase_id,
        depends_on=depends_on or []
    )

    new_task_dump = new_task.model_dump()
    tasks.append(new_task_dump)

    # Sauvegarde JSON individuelle
    save_entity(paths["tasks"], tsk_id, new_task_dump)

    return f"Tâche {tsk_id} créée ('{title}') associée à la phase {current_phase_id}."

@mcp.tool()
def effortless_task_update(
    task_id: str,
    status: str # Todo, Doing, Done
) -> str:
    """
    Met à jour le statut d'une tâche (en vérifiant les dépendances).
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["tasks"]):
        return "Erreur : Projet non initialisé."

    if status not in ["Todo", "Doing", "Done"]:
        return "Erreur : Le statut doit être 'Todo', 'Doing' ou 'Done'."

    tasks = load_entities(paths["tasks"])

    target_task = next((t for t in tasks if t["id"] == task_id), None)
    if not target_task:
        return f"Erreur : Tâche '{task_id}' introuvable."

    # Si on passe à Doing, vérifier les dépendances
    if status == "Doing":
        dependencies = target_task.get("depends_on", [])
        for dep_id in dependencies:
            dep_task = next((t for t in tasks if t["id"] == dep_id), None)
            if not dep_task or dep_task.get("status") != "Done":
                return f"Erreur : Impossible de démarrer la tâche '{task_id}'. La tâche dépendante '{dep_id}' n'est pas terminée."

    target_task["status"] = status

    # Sauvegarde JSON individuelle
    save_entity(paths["tasks"], task_id, target_task)

@mcp.tool()
def effortless_secondbrain_sync() -> str:
    """
    Force la synchronisation immédiate de l'état projet et des décisions vers le Vault SecondBrain.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["config"]) or not os.path.exists(paths["state"]):
        return "Erreur : Projet non initialisé."

    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    current_phase_id = state_data.get("current_phase")
    project_slug = state_data.get("project_name", "effortless").lower()

    vault_path = get_secondbrain_vault_path()
    if not vault_path:
        return "Erreur : SecondBrain non configuré (vault introuvable dans ~/.memory-kit/config.json)."

    # 1. Sync phase
    sync_success = sync_phase_to_secondbrain(project_slug, current_phase_id)

    # 2. Archive
    archive_subject = f"Synchronisation manuelle d'état -- {current_phase_id}"
    archive_body = f"# Rapport de Synchronisation Manuelle -- {current_phase_id}\n\n"
    archive_body += f"Projet : {state_data.get('project_name')}\n"
    archive_body += f"Phase active : {current_phase_id}\n\n"
    
    # Décisions
    decisions = load_entities(paths["decisions"])
    archive_body += "### 🏛️ Décisions prises :\n"
    if not decisions:
        archive_body += "*Aucune décision*\n"
    else:
        for dec in decisions:
            archive_body += f"- **{dec['id']}** : {dec['title']} ({dec['status']})\n"

    archive_name = create_secondbrain_archive(project_slug, archive_subject, archive_body)

    if sync_success and archive_name:
        return f"Synchronisation réussie avec SecondBrain dans {vault_path}. Archive créée : '{archive_name}'."
    else:
        return f"Erreur lors de la synchronisation (le dossier projet '{project_slug}' existe-t-il dans SecondBrain ?)."

@mcp.tool()
def effortless_drift_check(strict: bool = False) -> str:
    """
    Compare les modifications de code Git locales avec les tâches actives du backlog pour détecter les dérives (drift).
    """
    root = get_project_root()
    paths = get_paths(root)

    is_drifting, modified_files, active_tasks = check_project_drift(root, paths["tasks"])

    report = "🛡️ SYSTÈME ANTI-DRIFT\n"
    report += "====================\n"
    
    if len(modified_files) == 0:
        report += "✅ Aucun fichier de code source modifié localement. Pas de dérive possible.\n"
        return report

    report += f"📝 Fichiers de code source modifiés ({len(modified_files)}) :\n"
    for f in modified_files:
        report += f"- {f}\n"

    report += f"\n📋 Tâches actives en cours ('Doing') ({len(active_tasks)}) :\n"
    if len(active_tasks) == 0:
        report += "❌ AUCUNE TÂCHE EN COURS D'EXÉCUTION !\n"
    else:
        for t in active_tasks:
            report += f"- [{t['id']}] {t['title']}\n"

    if is_drifting:
        report += "\n⚠️ RÉSULTAT : DÉRIVE CONSTATÉE ! Du code source a été modifié sans tâche active associée."
        if strict:
            raise RuntimeError(report)
    else:
        report += "\n✅ RÉSULTAT : CONFORME. Les modifications de code sont couvertes par les tâches actives."

    return report

@mcp.tool()
def effortless_drift_hook_install() -> str:
    """
    Installe le hook Git de pre-commit dans le dépôt local de l'utilisateur.
    """
    root = get_project_root()
    try:
        hook_path = install_git_pre_commit_hook(root)
        return f"Hook Git pre-commit installé avec succès dans : {hook_path}\nIl bloquera les commits en cas de dérive de code (drift)."
    except Exception as e:
        return f"Erreur lors de l'installation du hook : {str(e)}"

@mcp.tool()
def effortless_deploy() -> str:
    """
    Déploie automatiquement la configuration du serveur MCP et les Skills sur tous les clients détectés (Claude Desktop, Claude Code, Antigravity).
    """
    root = get_project_root()
    results = deploy_to_mcp_clients(root)
    
    if not results:
        return "Aucun client compatible détecté pour le déploiement automatique."
        
    report = "🚀 RAPPORT DE DÉPLOIEMENT MULTI-CLI/APP :\n"
    report += "========================================\n"
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "❌"
        report += f"{status_icon} **{r['name']}** : {r['action']} (chemin : {r['path']})\n"
        
    return report


@mcp.tool()
def effortless_web_ui_launch() -> str:
    """
    Démarre le serveur HTTP intégré pour servir le dashboard Web d'Effortless et l'ouvre dans le navigateur.
    """
    root = get_project_root()
    web_ui_dist = os.path.join(root, "src", "web-ui", "dist")

    if not os.path.exists(web_ui_dist):
        return (
            "⚠️ Le dossier de l'interface Web ('src/web-ui/dist') est introuvable.\n"
            "Pour compiler le dashboard, veuillez exécuter :\n"
            "  cd src/web-ui && npm install && npm run build"
        )

    # Trouver un port libre
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]
    except Exception:
        port = 8080 # Fallback

    # Handler pour servir le dossier dist/
    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=web_ui_dist, **kwargs)

    # Lancer le serveur HTTP
    def start_server():
        server = HTTPServer(("localhost", port), DashboardHandler)
        server.serve_forever()

    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    url = f"http://localhost:{port}"
    webbrowser.open(url)

    return f"Dashboard démarré à l'adresse {url} et ouvert dans votre navigateur par défaut."


@mcp.tool()
def effortless_migrate_init(target_path: str) -> str:
    """
    Analyse un projet cible existant et l'initialise pour Effortless en générant les tâches de migration adaptées.
    """
    try:
        analysis = analyze_target_repo(target_path)
        report = init_migration_project(target_path, analysis)
        
        # Ajouter le diagnostic dans le rapport retourné
        diagnostic = f"🔍 DIAGNOSTIC DE SÉCURITÉ DE MIGRATION POUR {target_path}\n"
        diagnostic += f"- Stack détectée : {', '.join(analysis['stack'])}\n"
        diagnostic += f"- Frameworks identifiés : {', '.join(analysis['frameworks']) or 'Aucun'}\n"
        diagnostic += f"- Nombre de fichiers sources : {analysis['source_files_count']}\n"
        diagnostic += f"- Fichiers de doc détectés : {len(analysis['docs_files'])}\n"
        diagnostic += f"- Réorganisations proposées : {len(analysis['proposed_relocations'])}\n\n"
        
        return diagnostic + report
    except Exception as e:
        return f"Erreur lors de l'initialisation de la migration : {str(e)}"

@mcp.tool()
def effortless_migrate_apply(target_path: str) -> str:
    """
    Exécute physiquement les déplacements de réorganisation de dossiers de documentation et de codebase après validation.
    """
    try:
        return apply_migration_project(target_path)
    except Exception as e:
        return f"Erreur lors de l'application de la migration : {str(e)}"

@mcp.tool()
def effortless_loop_init(goal: str) -> str:
    """
    Initialise une session de développement itératif autonome avec un objectif global spécifié.
    """
    root = get_project_root()
    return init_autonomous_loop(root, goal)

@mcp.tool()
def effortless_loop_step(test_command: str) -> str:
    """
    Évalue et fait avancer la machine à états de la boucle itérative autonome en lançant la recette et la validation.
    """
    root = get_project_root()
    return step_autonomous_loop(root, test_command)


# Point d'entrée pour exécuter le serveur
def main():
    mcp.run()

if __name__ == "__main__":
    main()
