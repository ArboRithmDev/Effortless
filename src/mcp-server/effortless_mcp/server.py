import os
import json
import re
from datetime import datetime, timezone
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
from effortless_mcp.models.story import Story
from effortless_mcp.services.validation import validate_phase_documents
from effortless_mcp.services.sync import sync_decisions_to_markdown, sync_questions_to_markdown
from effortless_mcp.services.secondbrain import sync_phase_to_secondbrain, create_secondbrain_archive, get_secondbrain_vault_path
from effortless_mcp.services.drift import check_project_drift, install_git_pre_commit_hook
from effortless_mcp.services.deploy import deploy_to_mcp_clients
from effortless_mcp.services.repo_analyzer import analyze_target_repo
from effortless_mcp.services.migration_planner import init_migration_project, apply_migration_project
from effortless_mcp.services.session_loop import init_autonomous_loop, step_autonomous_loop
from effortless_mcp.services.state_migrator import migrate_state_to_fractal



# Initialisation de FastMCP
mcp = FastMCP("Effortless")

def get_project_root() -> str:
    """Retourne la racine du projet courant.

    Priorité à la variable d'environnement EFFORTLESS_PROJECT_ROOT (injectée par
    le déploiement multi-client), car la plupart des clients MCP ne lancent pas
    le serveur avec le cwd positionné sur la racine du projet. Repli sur le cwd.
    """
    return os.environ.get("EFFORTLESS_PROJECT_ROOT") or os.getcwd()

def get_install_root() -> str:
    """Racine de l'INSTALLATION Effortless (code, venv, Web UI), distincte de la racine
    du PROJET utilisateur (données dans .effortless/, docs dans cadrage/).

    server.py vit dans <install>/src/mcp-server/effortless_mcp/server.py : on remonte de
    trois niveaux. Indispensable pour le déploiement agnostique (le venv/CLI/dist ne sont
    pas dans le projet cible)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

def _utc_now_iso() -> str:
    """Horodatage ISO 8601 en UTC, timezone-aware (remplace datetime.utcnow() déprécié)."""
    return datetime.now(timezone.utc).isoformat()

def _today_iso() -> str:
    """Date du jour (UTC) au format AAAA-MM-JJ."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def next_sequential_id(existing_ids: List[str], prefix: str, width: int = 2) -> str:
    """Prochain ID = max(suffixe numérique existant pour ce préfixe) + 1.

    Robuste aux suppressions/fusions de fichiers (contrairement à len()+1 qui réutilise
    un ID après suppression et écrase silencieusement le fichier existant)."""
    max_n = 0
    plen = len(prefix)
    for eid in existing_ids:
        if isinstance(eid, str) and eid.startswith(prefix):
            suffix = eid[plen:]
            if suffix.isdigit():
                max_n = max(max_n, int(suffix))
    return f"{prefix}{max_n + 1:0{width}d}"

def resolve_phase_docs_dir(phase_cfg: Optional[Dict[str, Any]], fallback: str) -> str:
    """Répertoire des documents de la phase active, déduit de ses required_documents
    (pour ne pas écrire dans une mauvaise génération, ex. cadrage/Phase-003 codé en dur)."""
    if phase_cfg:
        for doc in phase_cfg.get("required_documents", []):
            d = os.path.dirname(doc)
            if d:
                return d
    return fallback

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
        "epics": os.path.join(storage_path, "epics"),
        "stories": os.path.join(storage_path, "stories"),
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


def get_active_story(root: str) -> Optional[Dict[str, Any]]:
    """Retourne la Story active depuis l'arbre nested epics/<EPIC>/stories/<STORY>/.

    Designee par state.active_epic_id + state.active_story_id ; sa fiche est le
    story.json dans get_story_dir(...). Sans pointeurs ou sans fiche, retourne None.
    """
    paths = get_paths(root)
    if not os.path.exists(paths["state"]):
        return None
    try:
        with open(paths["state"], "r", encoding="utf-8") as f:
            state_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    epic_id = state_data.get("active_epic_id")
    story_id = state_data.get("active_story_id")
    if not epic_id or not story_id:
        return None
    story_file = get_story_paths(root, epic_id, story_id)["story"]
    if not os.path.exists(story_file):
        return None
    try:
        with open(story_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def resolve_active_phase(root: str) -> Optional[str]:
    """Phase OPALE faisant autorité : opale_phase de la Story active."""
    story = get_active_story(root)
    if story is not None and story.get("opale_phase"):
        return story["opale_phase"]
    return None


# --- Couche stockage fractal (DEC-22/23) : nested epics/<EPIC>/stories/<STORY>/ ---

def get_epic_dir(root: str, epic_id: str) -> str:
    """Dossier physique d'un Epic : .effortless/epics/<EPIC>/."""
    return os.path.join(get_paths(root)["epics"], epic_id)


def get_story_dir(root: str, epic_id: str, story_id: str) -> str:
    """Dossier physique d'une Story : .effortless/epics/<EPIC>/stories/<STORY>/."""
    return os.path.join(get_epic_dir(root, epic_id), "stories", story_id)


def get_story_paths(root: str, epic_id: str, story_id: str) -> Dict[str, str]:
    """Chemins clés d'une Story : sa fiche + ses sous-registres tasks/decisions/questions."""
    sdir = get_story_dir(root, epic_id, story_id)
    return {
        "dir": sdir,
        "story": os.path.join(sdir, "story.json"),
        "tasks": os.path.join(sdir, "tasks"),
        "decisions": os.path.join(sdir, "decisions"),
        "questions": os.path.join(sdir, "questions"),
    }


def new_epic_id(zone: str) -> str:
    """ID d'Epic lisible scopé zone : EPIC-<ZONE>."""
    return f"EPIC-{zone.upper()}"


def new_story_id(root: str, epic_id: str, zone: str) -> str:
    """ID de Story sequentiel PAR Epic : STO-<ZONE>-NN (NN = max existant dans l'Epic + 1)."""
    stories_dir = os.path.join(get_epic_dir(root, epic_id), "stories")
    existing = os.listdir(stories_dir) if os.path.isdir(stories_dir) else []
    return next_sequential_id(existing, f"STO-{zone.upper()}-")


def new_entity_id(entity_dir: str, prefix: str) -> str:
    """ID d'entite sequentiel DANS une Story (TSK-NN / DEC-NN / Q-NN). Repart a 1 par Story."""
    existing = [e.get("id", "") for e in load_entities(entity_dir)]
    return next_sequential_id(existing, prefix)


def resolve_phase_docs_dir_nested(root: str, epic_id: str, story_id: str, documents_root: str = "cadrage") -> str:
    """Docs de cadrage Story-scopes : cadrage/<EPIC>/<STORY>/ (DEC-23)."""
    return os.path.join(root, documents_root, epic_id, story_id)


def resolve_registry_dir(root: str, kind: str) -> str:
    """Dossier d'un registre d'entités (kind in {'tasks','decisions','questions'}) :
    sous-registre de la Story active si présente, sinon repli sur le registre global plat."""
    story = get_active_story(root)
    if story is not None:
        return get_story_paths(root, story["epic_id"], story["id"])[kind]
    return get_paths(root)[kind]


def story_scoped_required_docs(root: str, phase_cfg: Optional[Dict[str, Any]]) -> List[str]:
    """Required_documents de la phase rescopés sur la Story active (DEC-23).

    Le workflow (effortless.json) déclare des chemins figés sur la première Story
    (scaffoldée par effortless_init). Dès qu'une AUTRE Story est active, la barrière
    doit valider les documents de CETTE Story — pas ceux de la première. On conserve
    le nom de fichier (convention de phase) et on rebascule le dossier sur
    cadrage/<EPIC>/<STORY>/ de la Story active. Sans Story active, on renvoie les
    chemins du workflow tels quels (compat mono-Story / legacy plat).

    Finding dogfood : révélé à l'ouverture de la 2e Story — la validation lisait des
    chemins absolus pinés sur STO-PROJET-01 alors que les écritures étaient déjà
    story-scopées (decision_add / question_ask)."""
    docs = phase_cfg.get("required_documents", []) if phase_cfg else []
    story = get_active_story(root)
    if story is None:
        return docs
    docs_dir_rel = os.path.relpath(
        resolve_phase_docs_dir_nested(root, story["epic_id"], story["id"]), root
    )
    return [os.path.join(docs_dir_rel, os.path.basename(d)) for d in docs]


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
        return "Error: An effortless.json file already exists. Use force=True to overwrite."

    # Nom de projet par défaut
    name = project_name or os.path.basename(os.path.abspath(root))

    # Racine documentaire story-scopée (alignée sur ce que produit le migrateur
    # d'état) : un projet fraîchement initialisé a la même forme qu'un projet migré.
    docs_root = "cadrage/EPIC-PROJET/STO-PROJET-01"

    # Configuration par défaut (OPAL)
    config = EffortlessConfig(
        project=ProjectMeta(name=name, description=description, version="0.1.0"),
        workflow=WorkflowConfig(
            phases=[
                PhaseConfig(
                    id="O-analyse",
                    name="Observer",
                    description="Analyse de l'existant, glossaire métier et cartographie technique",
                    required_documents=[
                        f"{docs_root}/00-FNC-GLO-glossaire.md",
                        f"{docs_root}/01-TEC-ANA-analyse.md",
                        f"{docs_root}/02-BQO-questions.md"
                    ]
                ),
                PhaseConfig(
                    id="P-cadrage",
                    name="Positionner",
                    description="Cadrage décisionnel et architecture cible",
                    required_documents=[
                        f"{docs_root}/03-TEC-ARC-architecture-cible.md",
                        f"{docs_root}/04-MET-DEC-registre-decisions.md"
                    ]
                ),
                PhaseConfig(
                    id="A-specs",
                    name="Articuler",
                    description="Spécifications fonctionnelles et techniques détaillées",
                    required_documents=[
                        f"{docs_root}/05-FNC-SPE-specifications.md",
                        f"{docs_root}/06-TEC-API-contrat-api.md"
                    ]
                ),
                PhaseConfig(
                    id="L-plan",
                    name="Lancer",
                    description="Plan d'implémentation et découpage en tâches",
                    required_documents=[
                        f"{docs_root}/07-MET-PLN-plan-action.md"
                    ]
                )
            ]
        ),
        settings=SettingsConfig(
            storage_dir=".effortless",
            documents_dir=docs_root
        )
    )

    # Création du fichier effortless.json
    with open(paths["config"], "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)

    # Création du dossier .effortless
    os.makedirs(paths["storage"], exist_ok=True)

    # Scaffolding fractal par défaut (L-31) : Epic + Story racine pour que le projet
    # fraîchement initialisé résolve sa phase via la Story active dès le départ.
    first_phase_id = config.workflow.phases[0].id
    epic = {
        "id": "EPIC-PROJET",
        "zone": "PROJET",
        "title": "Cadrage & pilotage du projet",
        "description": "Epic racine du projet (modèle fractal).",
        "status": "Open",
        "stories": ["STO-PROJET-01"],
    }
    story = {
        "id": "STO-PROJET-01",
        "epic_id": "EPIC-PROJET",
        "zone": "PROJET",
        "title": "Story par défaut — progression du projet",
        "opale_phase": first_phase_id,
        "status": "Doing",
    }

    # Initialisation de state.json (avec pointeurs vers la Story active fractale)
    state = ProjectState(
        project_name=name,
        active_epic_id="EPIC-PROJET",
        active_story_id="STO-PROJET-01",
        started_at=_utc_now_iso()
    )
    with open(paths["state"], "w", encoding="utf-8") as f:
        json.dump(state.model_dump(), f, indent=2, ensure_ascii=False)

    # Initialisation des répertoires d'entités
    for key in ["decisions", "questions", "tasks"]:
        os.makedirs(paths[key], exist_ok=True)

    # Création de l'arbre fractal nested epics/<EPIC>/stories/<STORY>/{tasks,decisions,questions}
    epic_dir = get_epic_dir(root, "EPIC-PROJET")
    story_paths = get_story_paths(root, "EPIC-PROJET", "STO-PROJET-01")
    os.makedirs(epic_dir, exist_ok=True)
    for key in ["tasks", "decisions", "questions"]:
        os.makedirs(story_paths[key], exist_ok=True)
    with open(os.path.join(epic_dir, "epic.json"), "w", encoding="utf-8") as f:
        json.dump(epic, f, indent=2, ensure_ascii=False)
    with open(story_paths["story"], "w", encoding="utf-8") as f:
        json.dump(story, f, indent=2, ensure_ascii=False)

    # Création du dossier de documents (story-scopé) + stubs Obsidian-ready.
    docs_dir = os.path.join(root, "cadrage", "EPIC-PROJET", "STO-PROJET-01")
    os.makedirs(docs_dir, exist_ok=True)

    # Scaffolde tous les docs de phase avec frontmatter riche (004-Story-Cadrage) :
    # le projet fraîchement initialisé est immédiatement ouvrable dans Obsidian.
    from effortless_mcp.services.cadrage_frontmatter import (
        scaffold_story_docs, phase_docs_from_workflow,
    )
    scaffold_story_docs(
        root, "EPIC-PROJET", "STO-PROJET-01",
        phase_docs_from_workflow(config.model_dump()),
    )

    return f"Project '{name}' successfully initialized under {root}."

@mcp.tool()
def effortless_story_start(
    title: str,
    zone: Optional[str] = None,
    description: Optional[str] = None,
    epic_id: Optional[str] = None,
    opale_phase: Optional[str] = None,
    depends_on: Optional[List[str]] = None,
    activate: bool = True,
) -> str:
    """
    Crée une nouvelle Story sous un Epic existant et (par défaut) l'active.

    Comble le trou [TOOLING] : sans cet outil, impossible d'amorcer une 2e Story —
    state.active_story_id restait figé sur la première, et la boucle autonome tournait
    à vide (backlog de l'ancienne Story tout 'Done' → faux « GOAL REACHED »).

    - Epic cible : `epic_id` sinon l'Epic actif (state.active_epic_id). Doit exister.
    - Zone : `zone` sinon celle de l'Epic. ID = STO-<ZONE>-NN (séquentiel par Epic).
    - Phase de départ : `opale_phase` (validée) sinon la 1re phase du workflow.
    - Scaffolde l'arbre fractal (story.json + tasks/decisions/questions) et le dossier
      cadrage/<EPIC>/<STORY>/. Référence la Story dans epic.json (stories[], dédup).
    - Si `activate`, bascule state.active_epic_id/active_story_id sur la nouvelle Story.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["config"]) or not os.path.exists(paths["state"]):
        return "Error: Project not initialized."

    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)

    # Epic cible : paramètre explicite sinon Epic actif.
    target_epic_id = epic_id or state_data.get("active_epic_id")
    if not target_epic_id:
        return "Error: no target epic (pass epic_id or set an active epic first)."
    epic_dir = get_epic_dir(root, target_epic_id)
    epic_file = os.path.join(epic_dir, "epic.json")
    if not os.path.exists(epic_file):
        return f"Error: epic '{target_epic_id}' not found. Create it before adding a Story."
    with open(epic_file, "r", encoding="utf-8") as f:
        epic_data = json.load(f)

    # Zone : paramètre sinon zone de l'Epic sinon dérivée de l'ID EPIC-<ZONE>.
    resolved_zone = zone or epic_data.get("zone") or target_epic_id.replace("EPIC-", "")

    # Phase de départ : paramètre validé contre le workflow sinon 1re phase.
    phases_list = config_data.get("workflow", {}).get("phases", [])
    if not phases_list:
        return "Error: workflow has no phases configured."
    valid_phase_ids = {p["id"] for p in phases_list}
    start_phase = opale_phase or phases_list[0]["id"]
    if start_phase not in valid_phase_ids:
        return (
            f"Error: invalid opale_phase '{start_phase}'. "
            f"Allowed: {', '.join(p['id'] for p in phases_list)}."
        )

    # ID séquentiel PAR Epic, nouvelle forme : <NNN>-Story-<Périmètre>.
    from effortless_mcp.services.nomenclature import (
        format_story_id, perimetre_of, next_story_seq,
    )
    story_perimetre = perimetre_of(resolved_zone, target_epic_id)
    story_seq = next_story_seq(root, target_epic_id)
    story_id = format_story_id(story_seq, story_perimetre)

    story = Story(
        id=story_id,
        epic_id=target_epic_id,
        zone=resolved_zone,
        title=title,
        opale_phase=start_phase,
        status="Doing" if activate else "Todo",
        depends_on=depends_on or [],
    ).model_dump()
    story["seq"] = story_seq

    # Scaffolding fractal : fiche story.json + sous-registres tasks/decisions/questions.
    story_paths = get_story_paths(root, target_epic_id, story_id)
    os.makedirs(story_paths["dir"], exist_ok=True)
    for key in ["tasks", "decisions", "questions"]:
        os.makedirs(story_paths[key], exist_ok=True)
    save_entity(story_paths["dir"], "story", story)

    # Dossier de cadrage story-scopé : cadrage/<EPIC>/<STORY>/.
    docs_dir = resolve_phase_docs_dir_nested(root, target_epic_id, story_id)
    os.makedirs(docs_dir, exist_ok=True)

    # Stubs Obsidian-ready des docs de cadrage (004-Story-Cadrage) : frontmatter
    # riche + titre, jamais d'écrasement. Rend chaque doc de phase présent dès la
    # création de la Story.
    from effortless_mcp.services.cadrage_frontmatter import (
        scaffold_story_docs, phase_docs_from_workflow,
    )
    scaffold_story_docs(
        root, target_epic_id, story_id, phase_docs_from_workflow(config_data)
    )

    # Référencement dans epic.json (dédup).
    stories = epic_data.setdefault("stories", [])
    if story_id not in stories:
        stories.append(story_id)
    with open(epic_file, "w", encoding="utf-8") as f:
        json.dump(epic_data, f, indent=2, ensure_ascii=False)

    # Rafraîchit le registre des stories de l'Epic (rendu dérivé).
    from effortless_mcp.services.epic_cadrage import refresh_epic_cadrage
    refresh_epic_cadrage(root, target_epic_id, epic_data)

    # Bascule de la Story active (modèle fractal : la phase suit la Story active).
    activated_msg = ""
    if activate:
        state_data["active_epic_id"] = target_epic_id
        state_data["active_story_id"] = story_id
        with open(paths["state"], "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)
        activated_msg = f" Active story switched to {story_id} (phase {start_phase})."

        # Si une boucle autonome existe et qu'elle s'est arrêtée (Finished/Aborted) sur
        # le backlog de l'ANCIENNE Story, la redémarrer au Plan sur la nouvelle (goal
        # conservé). Sans ça, le step suivant répondrait « already completed » et ne
        # replanifierait jamais le backlog de la Story fraîche (footgun observé en dogfood).
        loop_file = os.path.join(paths["storage"], "loop_state.json")
        if os.path.exists(loop_file):
            try:
                with open(loop_file, "r", encoding="utf-8") as f:
                    loop_state = json.load(f)
                if loop_state.get("step") in ("Finished", "Aborted"):
                    loop_state["step"] = "Plan"
                    loop_state["current_task"] = None
                    loop_state["error_count"] = 0
                    tmp = loop_file + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(loop_state, f, indent=2, ensure_ascii=False)
                    os.replace(tmp, loop_file)
                    activated_msg += " Autonomous loop reset to Plan on the new story."
            except (json.JSONDecodeError, OSError):
                pass

    return f"Story {story_id} created under {target_epic_id} ('{title}').{activated_msg}"


@mcp.tool()
def effortless_cadrage_docs_scaffold(story_id: Optional[str] = None) -> str:
    """
    Backfille les stubs Obsidian-ready des docs de cadrage d'une Story (004-Story-Cadrage).

    Dépose le frontmatter riche (type/projet/epic/story/code/tags) + titre pour chaque
    doc de phase encore ABSENT ; ne réécrit jamais un doc existant. Utile pour rendre
    conformes les Stories créées avant ce hook. Sans `story_id`, opère sur la Story active.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."
    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)

    if story_id:
        # Retrouve l'Epic parent en balayant les epics/<E>/stories/<story_id>.
        epics_root = os.path.join(paths["storage"], "epics")
        epic_id = None
        if os.path.isdir(epics_root):
            for e in os.listdir(epics_root):
                if os.path.isdir(os.path.join(epics_root, e, "stories", story_id)):
                    epic_id = e
                    break
        if not epic_id:
            return f"Error: story '{story_id}' introuvable."
        target_epic_id, target_story_id = epic_id, story_id
    else:
        story = get_active_story(root)
        if story is None:
            return "Error: aucune Story active (passe story_id)."
        target_epic_id, target_story_id = story["epic_id"], story["id"]

    from effortless_mcp.services.cadrage_frontmatter import (
        scaffold_story_docs, phase_docs_from_workflow,
    )
    created = scaffold_story_docs(
        root, target_epic_id, target_story_id, phase_docs_from_workflow(config_data)
    )
    if not created:
        return f"Story {target_story_id} : docs de cadrage déjà tous présents (no-op)."
    return (
        f"Story {target_story_id} : {len(created)} stub(s) de cadrage scaffoldé(s) "
        f"(frontmatter Obsidian) :\n- " + "\n- ".join(created)
    )


@mcp.tool()
def effortless_epic_start(zone: str, title: str, description: str = "", activate: bool = True) -> str:
    """
    Crée un nouvel Epic (EPIC-<ZONE>) et, par défaut, l'active.

    Comble le gap de bootstrap (EVO-003) : `effortless_init` ne crée que le premier
    Epic et `effortless_story_start` exige un Epic existant — rien ne permettait
    d'amorcer un Epic N+1. Idempotent : un Epic déjà présent n'est pas écrasé.
    Une Epic fraîche n'a pas de Story ; ajouter via effortless_story_start.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]) or not os.path.exists(paths["state"]):
        return "Error: Project not initialized."
    z = (zone or "").strip().upper()
    if not z:
        return "Error: zone requise."
    if not (title or "").strip():
        return "Error: title requis."

    from effortless_mcp.models.epic import Epic
    from effortless_mcp.services.nomenclature import (
        format_epic_id, perimetre_of, next_epic_seq, epic_with_perimetre_exists,
    )
    perimetre = perimetre_of(z, "")
    existing = epic_with_perimetre_exists(root, perimetre)
    if existing:
        return f"Epic de périmètre '{perimetre}' existe déjà ('{existing}', idempotent, non écrasé)."
    seq = next_epic_seq(root)
    epic_id = format_epic_id(seq, perimetre)
    epic_dir = get_epic_dir(root, epic_id)
    os.makedirs(os.path.join(epic_dir, "stories"), exist_ok=True)
    epic = Epic(id=epic_id, zone=z, title=title, description=description or None).model_dump()
    epic["seq"] = seq
    epic["stories"] = []
    save_entity(epic_dir, "epic", epic)
    # Dossier + docs de cadrage epic-scopés (charte 0-Epic + registre 1-Stories).
    os.makedirs(os.path.join(root, "cadrage", epic_id), exist_ok=True)
    from effortless_mcp.services.epic_cadrage import refresh_epic_cadrage
    refresh_epic_cadrage(root, epic_id, epic)

    activated = ""
    if activate:
        with open(paths["state"], "r", encoding="utf-8") as f:
            state_data = json.load(f)
        state_data["active_epic_id"] = epic_id
        state_data["active_story_id"] = None  # Epic vide : pas de Story active tant qu'aucune n'est amorcée.
        with open(paths["state"], "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)
        activated = f" Epic actif = {epic_id} (ajoute une Story via effortless_story_start)."
    return f"Epic {epic_id} créé ('{title}').{activated}"


@mcp.tool()
def effortless_story_complete(story_id: Optional[str] = None) -> str:
    """
    Passe une Story à 'Done' si toutes ses tâches sont 'Done'.

    Story active par défaut (ou `story_id` sous l'Epic actif). Ferme le gap de clôture
    (EVO-003) : les Stories restaient 'Doing' après livraison du code. Idempotent :
    une Story déjà Done est un no-op. Refuse si des tâches ne sont pas Done.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["state"]):
        return "Error: Project not initialized."
    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    epic_id = state_data.get("active_epic_id")
    sid = story_id or state_data.get("active_story_id")
    if not epic_id or not sid:
        return "Error: no target story (pass story_id or activate one)."
    sp = get_story_paths(root, epic_id, sid)
    if not os.path.exists(sp["story"]):
        return f"Error: story '{sid}' not found under {epic_id}."
    with open(sp["story"], "r", encoding="utf-8") as f:
        story = json.load(f)
    if story.get("status") == "Done":
        return f"Story '{sid}' déjà Done (idempotent)."
    tasks = load_entities(sp["tasks"])
    pending = [t.get("id") for t in tasks if t.get("status") != "Done"]
    if pending:
        return f"Error: story '{sid}' a {len(pending)} tâche(s) non Done : {', '.join(pending)}."
    story["status"] = "Done"
    save_entity(sp["dir"], "story", story)
    from effortless_mcp.services.epic_cadrage import render_story_registry
    try:
        render_story_registry(root, epic_id)
    except OSError:
        pass
    return f"Story '{sid}' clôturée (Done)."


@mcp.tool()
def effortless_epic_complete(epic_id: Optional[str] = None) -> str:
    """
    Passe un Epic à 'Done' si toutes ses Stories sont 'Done'.

    Epic actif par défaut (ou `epic_id`). Idempotent : un Epic déjà Done est un no-op.
    Refuse si des Stories ne sont pas Done.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["state"]):
        return "Error: Project not initialized."
    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    eid = epic_id or state_data.get("active_epic_id")
    if not eid:
        return "Error: no target epic (pass epic_id or activate one)."
    epic_file = os.path.join(get_epic_dir(root, eid), "epic.json")
    if not os.path.exists(epic_file):
        return f"Error: epic '{eid}' not found."
    with open(epic_file, "r", encoding="utf-8") as f:
        epic = json.load(f)
    if epic.get("status") == "Done":
        return f"Epic '{eid}' déjà Done (idempotent)."
    story_ids = epic.get("stories", [])
    if not story_ids:
        return f"Error: epic '{eid}' n'a aucune Story — rien à clôturer."
    not_done = []
    for sid in story_ids:
        sp = get_story_paths(root, eid, sid)
        st = None
        if os.path.exists(sp["story"]):
            with open(sp["story"], "r", encoding="utf-8") as f:
                st = json.load(f).get("status")
        if st != "Done":
            not_done.append(sid)
    if not_done:
        return f"Error: epic '{eid}' a {len(not_done)} story(ies) non Done : {', '.join(not_done)}."
    epic["status"] = "Done"
    with open(epic_file, "w", encoding="utf-8") as f:
        json.dump(epic, f, indent=2, ensure_ascii=False)
    return f"Epic '{eid}' clôturé (Done)."


@mcp.tool()
def effortless_migrate_nomenclature(confirm: bool = False) -> str:
    """
    Migre les identifiants fractals vers la forme <NNN>-Epic/Story-<Périmètre> (EVO-005).

    `confirm=False` (défaut) : DRY-RUN — retourne le plan de renommage (old → new)
    sans rien modifier. `confirm=True` : applique — renomme les répertoires
    (.effortless/epics + cadrage) et réécrit toutes les références (epic.json,
    story.json, state, backlog, frontmatter de cadrage). Idempotent : un arbre déjà
    migré ne change rien. À faire précéder d'une sauvegarde.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."
    from effortless_mcp.services.nomenclature import plan_nomenclature, apply_nomenclature

    plan = plan_nomenclature(root)
    lines = []
    for ep in plan["epics"]:
        arrow = "=" if ep["old_id"] == ep["new_id"] else "→"
        lines.append(f"  {ep['old_id']} {arrow} {ep['new_id']}")
        for st in ep["stories"]:
            sarrow = "=" if st["old_id"] == st["new_id"] else "→"
            lines.append(f"      {st['old_id']} {sarrow} {st['new_id']}")
    mapping = "\n".join(lines) or "  (aucun Epic)"

    if not plan["changed"]:
        return f"Nomenclature : déjà à jour (idempotent).\n{mapping}"
    if not confirm:
        return (
            "DRY-RUN — plan de migration nomenclature (rien modifié) :\n"
            f"{mapping}\n\nRelance avec confirm=True pour appliquer (sauvegarde recommandée)."
        )
    report = apply_nomenclature(root, plan)
    warns = report.get("warnings") or []
    warn_txt = ("\n⚠️ Cadrage (best-effort) : " + " | ".join(warns) +
                "\nRe-lance après avoir libéré le lock (idempotent).") if warns else ""
    return (
        f"Nomenclature migrée : {report['epics_renamed']} Epic(s), "
        f"{report['stories_renamed']} Story(ies) renommé(s).\n{mapping}{warn_txt}\n"
        f"⚠️ Reconnecte le MCP effortless."
    )


@mcp.tool()
def effortless_status() -> str:
    """
    Retourne le statut actuel du projet, la checklist de phase et l'éligibilité pour la phase suivante.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["config"]) or not os.path.exists(paths["state"]):
        return "Error: Project not initialized. Please run 'effortless_init'."

    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)

    # Phase faisant autorité : opale_phase de la Story active.
    current_phase_id = resolve_active_phase(root)

    # Trouver la phase de configuration correspondante
    phases_list = config_data.get("workflow", {}).get("phases", [])
    phase_config = next((p for p in phases_list if p["id"] == current_phase_id), None)

    if not phase_config:
        return f"Error: Active phase '{current_phase_id}' is not defined in effortless.json."

    required_docs = story_scoped_required_docs(root, phase_config)

    # Registre des questions : sous-registre de la Story active si présente.
    questions_dir = resolve_registry_dir(root, "questions")

    is_valid, checklist, blocking_reasons = validate_phase_documents(
        project_root=root,
        active_phase_id=current_phase_id,
        required_documents=required_docs,
        questions_file_path=questions_dir
    )

    # Récupérer les questions en suspens
    open_questions_list = []
    if os.path.exists(questions_dir):
        questions = load_entities(questions_dir)
        open_questions_list = [q for q in questions if q.get("status") != "Resolved" and q.get("phase") == current_phase_id]

    status_report = f"📋 Project Status: {state_data.get('project_name')}\n"
    status_report += f"Current phase: **{phase_config.get('name')}** ({current_phase_id})\n"
    status_report += f"Next-phase eligibility: {'✅ YES (Ready)' if is_valid else '❌ NO (Blocked)'}\n\n"

    status_report += "🔍 Required documents checklist:\n"
    for item in checklist:
        status_icon = "✅" if item["is_valid"] else ("⚠️" if item["is_present"] else "❌")
        error_msg = f" ({', '.join(item['errors'])})" if item["errors"] else ""
        status_report += f"- {status_icon} `{item['document_path']}`{error_msg}\n"

    if open_questions_list:
        status_report += "\n❓ Open questions for this phase:\n"
        for q in open_questions_list:
            status_report += f"- [`{q['id']}`] **{q['question']}** (Impact: {q['impact']})\n"

    if blocking_reasons:
        status_report += "\n❌ Blocking reasons:\n"
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
        return "Error: Project not initialized."

    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)

    # Phase faisant autorité : opale_phase de la Story active.
    current_phase_id = resolve_active_phase(root)
    phases_list = config_data.get("workflow", {}).get("phases", [])

    # Trouver l'index de la phase en cours
    current_idx = next((i for i, p in enumerate(phases_list) if p["id"] == current_phase_id), -1)

    if current_idx == -1:
        return f"Error: Active phase '{current_phase_id}' is unknown."

    if current_idx == len(phases_list) - 1:
        return "You are already on the last configured phase of the project!"

    # Valider les barrières de la phase en cours
    phase_config = phases_list[current_idx]
    required_docs = story_scoped_required_docs(root, phase_config)
    is_valid, checklist, blocking_reasons = validate_phase_documents(
        project_root=root,
        active_phase_id=current_phase_id,
        required_documents=required_docs,
        questions_file_path=resolve_registry_dir(root, "questions")
    )

    if not is_valid:
        return "Transition blocked:\n" + "\n".join([f"- {r}" for r in blocking_reasons])

    # Effectuer la transition
    next_phase = phases_list[current_idx + 1]

    # Dédup : ne pas ré-empiler une phase déjà marquée terminée.
    completed = state_data.setdefault("completed_phases", [])
    if not any(cp.get("id") == current_phase_id for cp in completed):
        completed.append({
            "id": current_phase_id,
            "completed_at": _utc_now_iso()
        })
    # Modèle fractal : si une Story est active, c'est SA phase OPALE qui avance.
    # On persiste le nouveau palier dans son story.json (source de vérité fractale).
    active_story = get_active_story(root)
    if active_story is not None:
        active_story["opale_phase"] = next_phase["id"]
        story_paths = get_story_paths(
            root, state_data.get("active_epic_id"), state_data.get("active_story_id")
        )
        save_entity(story_paths["dir"], "story", active_story)

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
        archive_subject = f"End of phase {current_phase_id} and transition to {next_phase['id']}"
        archive_body = f"# End-of-Phase Report -- {current_phase_id}\n\n"
        archive_body += f"Project **{state_data.get('project_name')}** has passed all gates for phase **{phase_config.get('name')}**.\n\n"
        archive_body += f"### 🔍 Document Checklist:\n"
        for item in checklist:
            status_icon = "✅" if item["is_valid"] else "❌"
            archive_body += f"- {status_icon} `{item['document_path']}`\n"
            
        archive_name = create_secondbrain_archive(project_slug, archive_subject, archive_body)
        if sync_success and archive_name:
            sb_msg = f"\n[SecondBrain Symbiosis] context.md sync and archive '{archive_name}' created in {vault_path}."
        else:
            sb_msg = "\n[SecondBrain Symbiosis] Link configured but unable to sync files (project not found in vault?)."
    else:
        sb_msg = "\n[SecondBrain Symbiosis] SecondBrain not detected or vault not configured in ~/.memory-kit/config.json."

    return f"Transition successfully completed from '{current_phase_id}' to '{next_phase['id']}' ({next_phase['name']}).{sb_msg}"

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

    if not os.path.exists(paths["config"]) or not os.path.exists(paths["decisions"]) or not os.path.exists(paths["state"]):
        return "Error: Project not initialized."

    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    # Phase faisant autorité : opale_phase de la Story active.
    current_phase_id = resolve_active_phase(root)

    # Registre des décisions : sous-registre de la Story active si présente.
    decisions_dir = resolve_registry_dir(root, "decisions")
    decisions = load_entities(decisions_dir)

    # ID = max existant + 1 (robuste aux suppressions)
    dec_id = next_sequential_id([d.get("id", "") for d in decisions], "DEC-")

    new_dec = Decision(
        id=dec_id,
        title=title,
        status="Accepted",
        phase=current_phase_id,
        date=_today_iso(),
        context=context,
        decision=decision,
        consequences=consequences,
        rejected_alternatives=rejected_alternatives or []
    )

    new_dec_dump = new_dec.model_dump()
    decisions.append(new_dec_dump)

    # Sauvegarde JSON individuelle
    save_entity(decisions_dir, dec_id, new_dec_dump)

    # Synchronisation Markdown
    # Trouver le chemin du fichier de décisions dans effortless.json
    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    # Rechercher s'il y a un document de type DEC requis dans la phase (pour le NOM de fichier)
    phases_list = config_data.get("workflow", {}).get("phases", [])
    current_phase_cfg = next((p for p in phases_list if p["id"] == current_phase_id), None)
    settings_documents_dir = config_data.get("settings", {}).get("documents_dir", "cadrage/Phase-001")

    # Le repertoire fait autorite via la Story active (DEC-23) -> chemin ABSOLU ;
    # sinon repli phase-scope (chemin RELATIF a prefixer par root).
    story = get_active_story(root)
    if story is not None:
        docs_abs = resolve_phase_docs_dir_nested(root, story["epic_id"], story["id"])
    else:
        docs_abs = os.path.join(root, resolve_phase_docs_dir(current_phase_cfg, settings_documents_dir))

    dec_filename = None
    if current_phase_cfg:
        for doc in current_phase_cfg.get("required_documents", []):
            if "dec" in doc.lower() or "decision" in doc.lower():
                dec_filename = os.path.basename(doc)
                break

    if not dec_filename:
        dec_filename = "03-MET-DEC-registre-decisions.md"

    markdown_path = os.path.join(docs_abs, dec_filename)
    sync_decisions_to_markdown(markdown_path, current_phase_id, decisions)

    dec_doc_rel = os.path.relpath(markdown_path, root).replace(os.sep, "/")
    return f"Decision {dec_id} added and synced to {dec_doc_rel}."

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

    if not os.path.exists(paths["config"]) or not os.path.exists(paths["questions"]) or not os.path.exists(paths["state"]):
        return "Error: Project not initialized."

    # B8 : valider l'impact AVANT toute écriture (un 'blocker' mal casé contournait la barrière).
    if impact not in ("Blocker", "Structuring", "Minor"):
        return f"Error: invalid impact '{impact}'. Allowed values: Blocker, Structuring, Minor."

    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    # Phase faisant autorité : opale_phase de la Story active.
    current_phase_id = resolve_active_phase(root)
    project_name = state_data.get("project_name")

    # Registre des questions : sous-registre de la Story active si présente.
    questions_dir = resolve_registry_dir(root, "questions")
    questions = load_entities(questions_dir)

    # ID = max existant + 1 (robuste aux suppressions)
    q_id = next_sequential_id([q.get("id", "") for q in questions], "Q-")

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
    save_entity(questions_dir, q_id, new_q_dump)

    # Synchronisation Markdown
    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    phases_list = config_data.get("workflow", {}).get("phases", [])
    current_phase_cfg = next((p for p in phases_list if p["id"] == current_phase_id), None)
    settings_documents_dir = config_data.get("settings", {}).get("documents_dir", "cadrage/Phase-001")

    # Le repertoire fait autorite via la Story active (DEC-23) -> chemin ABSOLU ;
    # sinon repli phase-scope (chemin RELATIF a prefixer par root).
    story = get_active_story(root)
    if story is not None:
        docs_abs = resolve_phase_docs_dir_nested(root, story["epic_id"], story["id"])
    else:
        docs_abs = os.path.join(root, resolve_phase_docs_dir(current_phase_cfg, settings_documents_dir))

    bqo_filename = None
    if current_phase_cfg:
        for doc in current_phase_cfg.get("required_documents", []):
            if "bqo" in doc.lower() or "question" in doc.lower():
                bqo_filename = os.path.basename(doc)
                break

    if not bqo_filename:
        bqo_filename = "02-BQO-questions.md"

    markdown_path = os.path.join(docs_abs, bqo_filename)
    # Ne synchroniser que les questions de la phase en cours pour le fichier de phase
    phase_questions = [q for q in questions if q.get("phase") == current_phase_id]
    sync_questions_to_markdown(markdown_path, current_phase_id, project_name, phase_questions)

    bqo_doc_rel = os.path.relpath(markdown_path, root).replace(os.sep, "/")
    return f"Question {q_id} submitted and synced to {bqo_doc_rel}."

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

    if not os.path.exists(paths["config"]) or not os.path.exists(paths["questions"]) or not os.path.exists(paths["state"]):
        return "Error: Project not initialized."

    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    project_name = state_data.get("project_name")

    # Registre des questions : sous-registre de la Story active si présente.
    questions_dir = resolve_registry_dir(root, "questions")
    questions = load_entities(questions_dir)

    target_q = next((q for q in questions if q["id"] == question_id), None)
    if not target_q:
        return f"Error: Question '{question_id}' not found."

    target_q["status"] = "Resolved"
    target_q["answer"] = answer
    target_q["date_resolved"] = _today_iso()

    # Sauvegarde JSON individuelle
    save_entity(questions_dir, question_id, target_q)

    # Récupérer la phase de la question pour mettre à jour son fichier Markdown
    q_phase_id = target_q["phase"]

    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    phases_list = config_data.get("workflow", {}).get("phases", [])
    q_phase_cfg = next((p for p in phases_list if p["id"] == q_phase_id), None)
    settings_documents_dir = config_data.get("settings", {}).get("documents_dir", "cadrage/Phase-001")

    # Le repertoire fait autorite via la Story active (DEC-23) -> chemin ABSOLU ;
    # sinon repli phase-scope (chemin RELATIF a prefixer par root). Aligne resolve
    # sur decision_add / question_ask : sans ca, la resolution ecrivait le BQO via
    # le chemin littéral d'effortless.json (piné sur la 1re Story) et corrompait le
    # BQO d'une AUTRE Story.
    story = get_active_story(root)
    if story is not None:
        docs_abs = resolve_phase_docs_dir_nested(root, story["epic_id"], story["id"])
    else:
        docs_abs = os.path.join(root, resolve_phase_docs_dir(q_phase_cfg, settings_documents_dir))

    bqo_filename = None
    if q_phase_cfg:
        for doc in q_phase_cfg.get("required_documents", []):
            if "bqo" in doc.lower() or "question" in doc.lower():
                bqo_filename = os.path.basename(doc)
                break

    if not bqo_filename:
        bqo_filename = "02-BQO-questions.md"

    markdown_path = os.path.join(docs_abs, bqo_filename)
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
    blocker_info = "There are still blocking questions for this phase." if has_more_blockers else "No more blocking questions for this phase."

    return f"Question {question_id} successfully resolved. {blocker_info}"

# --- 4. Outils de Tâches ---

@mcp.tool()
def effortless_task_add(
    title: str,
    description: Optional[str] = None,
    depends_on: Optional[List[str]] = None,
    complexity: Optional[str] = None
) -> str:
    """
    Crée une tâche associée à la phase active du projet.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["tasks"]) or not os.path.exists(paths["state"]):
        return "Error: Project not initialized."

    if complexity is not None and complexity not in ("simple", "complex"):
        return f"Error: invalid complexity '{complexity}'. Allowed values: simple, complex."

    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    # Phase faisant autorité : opale_phase de la Story active.
    current_phase_id = resolve_active_phase(root)

    # Modèle fractal : si une Story est active, la tâche est créée dans SON sous-registre
    # tasks/ avec un ID séquentiel par Story (TSK-NN). Sinon, comportement global historique.
    active_story = get_active_story(root)
    if active_story is not None:
        story_paths = get_story_paths(
            root, state_data.get("active_epic_id"), state_data.get("active_story_id")
        )
        tasks_dir = story_paths["tasks"]
        tasks = load_entities(tasks_dir)
        tsk_id = new_entity_id(tasks_dir, "TSK-")
    else:
        tasks_dir = paths["tasks"]
        tasks = load_entities(tasks_dir)

        # Déterminer le préfixe basé sur la phase active
        parts = current_phase_id.split("-")
        if len(parts) >= 3 and parts[0].lower() == "phase":
            prefix = "-".join(parts[:3])
        elif len(parts) >= 1:
            prefix = parts[0]
        else:
            prefix = "TSK"

        # ID = max existant pour CE préfixe + 1 : préfixe et index restent cohérents, et la
        # suppression d'une tâche ne provoque ni réutilisation ni écrasement (B1/B5).
        tsk_prefix = f"TSK-{prefix}-"
        tsk_id = next_sequential_id([t.get("id", "") for t in tasks], tsk_prefix)

    new_task = Task(
        id=tsk_id,
        title=title,
        description=description,
        status="Todo",
        phase=current_phase_id,
        depends_on=depends_on or [],
        complexity=complexity
    )

    new_task_dump = new_task.model_dump()

    # Projection tracker best-effort (DEC-05/DEC-06) : no-op sans couplage
    # (NullTracker), enrichit tracker_id/url sinon, jamais bloquant.
    try:
        from effortless_mcp.ports.integration import project_task_created
        new_task_dump = project_task_created(root, new_task_dump)
    except Exception:
        pass

    tasks.append(new_task_dump)

    # Sauvegarde JSON individuelle
    save_entity(tasks_dir, tsk_id, new_task_dump)

    return f"Task {tsk_id} created ('{title}') for phase {current_phase_id}."

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
        return "Error: Project not initialized."

    if status not in ["Todo", "Doing", "Done"]:
        return "Error: Status must be 'Todo', 'Doing', or 'Done'."

    # Registre des tâches : sous-registre de la Story active si présente.
    tasks_dir = resolve_registry_dir(root, "tasks")
    tasks = load_entities(tasks_dir)

    target_task = next((t for t in tasks if t["id"] == task_id), None)
    if not target_task:
        return f"Error: Task '{task_id}' not found."

    # Si on passe à Doing, vérifier les dépendances
    if status == "Doing":
        dependencies = target_task.get("depends_on", [])
        for dep_id in dependencies:
            dep_task = next((t for t in tasks if t["id"] == dep_id), None)
            if not dep_task or dep_task.get("status") != "Done":
                return f"Error: Cannot start task '{task_id}'. Dependent task '{dep_id}' is not done."

    target_task["status"] = status

    # Sauvegarde JSON individuelle
    save_entity(tasks_dir, task_id, target_task)

    # Projection tracker best-effort (DEC-05/DEC-06) : no-op sans couplage,
    # transition projetée ou consignée à l'outbox si tracker injoignable.
    try:
        from effortless_mcp.ports.integration import project_task_transitioned
        project_task_transitioned(root, target_task, status)
    except Exception:
        pass

    return f"Task '{task_id}' updated to status '{status}'."

@mcp.tool()
def effortless_task_classify(
    task_id: str,
    complexity: str  # simple | complex
) -> str:
    """
    Classe une tâche existante selon sa complexité (simple ou complex).
    Utilisé notamment par l'étape de triage de la boucle autonome.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["tasks"]):
        return "Error: Project not initialized."

    if complexity not in ("simple", "complex"):
        return f"Error: invalid complexity '{complexity}'. Allowed values: simple, complex."

    # Modèle fractal : la tâche vit dans le sous-registre tasks/ de la Story active si
    # présente ; sinon, registre global historique (cohérent avec effortless_task_add).
    active_story = get_active_story(root)
    if active_story is not None:
        tasks_dir = get_story_paths(root, active_story["epic_id"], active_story["id"])["tasks"]
    else:
        tasks_dir = paths["tasks"]

    tasks = load_entities(tasks_dir)
    target = next((t for t in tasks if t["id"] == task_id), None)
    if not target:
        return f"Error: Task '{task_id}' not found."

    target["complexity"] = complexity
    save_entity(tasks_dir, task_id, target)

    return f"Task '{task_id}' classified as '{complexity}'."

@mcp.tool()
def effortless_secondbrain_sync() -> str:
    """
    Force la synchronisation immédiate de l'état projet et des décisions vers le Vault SecondBrain.
    """
    root = get_project_root()
    paths = get_paths(root)

    if not os.path.exists(paths["config"]) or not os.path.exists(paths["state"]):
        return "Error: Project not initialized."

    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)
    # Phase faisant autorité : opale_phase de la Story active.
    current_phase_id = resolve_active_phase(root)
    project_slug = state_data.get("project_name", "effortless").lower()

    vault_path = get_secondbrain_vault_path()
    if not vault_path:
        return "Error: SecondBrain not configured (vault not found in ~/.memory-kit/config.json)."

    # 1. Sync phase
    sync_success = sync_phase_to_secondbrain(project_slug, current_phase_id)

    # 2. Archive
    archive_subject = f"Manual state sync -- {current_phase_id}"
    archive_body = f"# Manual Sync Report -- {current_phase_id}\n\n"
    archive_body += f"Project: {state_data.get('project_name')}\n"
    archive_body += f"Active phase: {current_phase_id}\n\n"
    
    # Décisions : sous-registre de la Story active si présente.
    decisions = load_entities(resolve_registry_dir(root, "decisions"))
    archive_body += "### 🏛️ Decisions made:\n"
    if not decisions:
        archive_body += "*No decisions*\n"
    else:
        for dec in decisions:
            archive_body += f"- **{dec['id']}** : {dec['title']} ({dec['status']})\n"

    archive_name = create_secondbrain_archive(project_slug, archive_subject, archive_body)

    if sync_success and archive_name:
        return f"Successfully synced with SecondBrain in {vault_path}. Archive created: '{archive_name}'."
    else:
        return f"Sync error (does the project folder '{project_slug}' exist in SecondBrain?)."

@mcp.tool()
def effortless_drift_check(strict: bool = False) -> str:
    """
    Compare les modifications de code Git locales avec les tâches actives du backlog pour détecter les dérives (drift).
    """
    root = get_project_root()
    paths = get_paths(root)

    is_drifting, modified_files, active_tasks = check_project_drift(root, paths["tasks"])

    report = "🛡️ ANTI-DRIFT SYSTEM\n"
    report += "====================\n"

    if len(modified_files) == 0:
        report += "✅ No modified source files locally. No drift possible.\n"
        return report

    report += f"📝 Modified source files ({len(modified_files)}):\n"
    for f in modified_files:
        report += f"- {f}\n"

    report += f"\n📋 Active tasks in progress ('Doing') ({len(active_tasks)}):\n"
    if len(active_tasks) == 0:
        report += "❌ NO TASK CURRENTLY RUNNING!\n"
    else:
        for t in active_tasks:
            report += f"- [{t['id']}] {t['title']}\n"

    if is_drifting:
        report += "\n⚠️ RESULT: DRIFT DETECTED! Source code was modified without an associated active task."
        # R6 : un outil MCP doit renvoyer une str sur tous les chemins (pas raise). Le mode
        # strict pour le hook git est géré par le CLI (main.py --drift-check-strict), qui
        # appelle check_project_drift et mappe la dérive sur un code de sortie non nul.
    else:
        report += "\n✅ RESULT: COMPLIANT. Code changes are covered by active tasks."

    return report

@mcp.tool()
def effortless_drift_hook_install() -> str:
    """
    Installe le hook Git de pre-commit dans le dépôt local de l'utilisateur.
    """
    root = get_project_root()
    try:
        hook_path = install_git_pre_commit_hook(root)
        return f"Git pre-commit hook successfully installed at: {hook_path}\nIt will block commits if code drift is detected."
    except Exception as e:
        return f"Error installing hook: {str(e)}"

@mcp.tool()
def effortless_deploy() -> str:
    """
    Déploie automatiquement la configuration du serveur MCP et les Skills sur tous les clients détectés (Claude Desktop, Claude Code, Antigravity).
    """
    root = get_project_root()
    results = deploy_to_mcp_clients(root)
    
    if not results:
        return "No compatible client detected for automatic deployment."

    report = "🚀 MULTI-CLI/APP DEPLOYMENT REPORT:\n"
    report += "========================================\n"
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "❌"
        report += f"{status_icon} **{r['name']}**: {r['action']} (path: {r['path']})\n"
        
    return report


def build_project_overview(root: str) -> Dict[str, Any]:
    """Agrège l'état complet du projet pour le dashboard Web (consommé via /api/overview)."""
    paths = get_paths(root)
    if not os.path.exists(paths["config"]) or not os.path.exists(paths["state"]):
        return {"initialized": False}

    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    with open(paths["state"], "r", encoding="utf-8") as f:
        state_data = json.load(f)

    # Phase faisant autorité : opale_phase de la Story active.
    current_phase_id = resolve_active_phase(root)
    phases_list = config_data.get("workflow", {}).get("phases", [])
    phase_cfg = next((p for p in phases_list if p["id"] == current_phase_id), None)
    required_docs = story_scoped_required_docs(root, phase_cfg)

    # Registres : sous-registres de la Story active si présente, sinon registres globaux plats.
    tasks_dir = resolve_registry_dir(root, "tasks")
    decisions_dir = resolve_registry_dir(root, "decisions")
    questions_dir = resolve_registry_dir(root, "questions")

    is_valid, checklist, blocking = validate_phase_documents(
        project_root=root,
        active_phase_id=current_phase_id,
        required_documents=required_docs,
        questions_file_path=questions_dir,
    )

    completed_ids = {cp.get("id") for cp in state_data.get("completed_phases", [])}
    phases = [{
        "id": p["id"],
        "name": p.get("name"),
        "description": p.get("description"),
        "completed": p["id"] in completed_ids,
        "current": p["id"] == current_phase_id,
    } for p in phases_list]

    return {
        "initialized": True,
        "project_name": state_data.get("project_name"),
        "current_phase": current_phase_id,
        "phase_name": phase_cfg.get("name") if phase_cfg else None,
        "is_valid": is_valid,
        "blocking_reasons": blocking,
        "checklist": checklist,
        "phases": phases,
        "tasks": load_entities(tasks_dir),
        "decisions": load_entities(decisions_dir),
        "questions": load_entities(questions_dir),
        "completed_phases": state_data.get("completed_phases", []),
    }


@mcp.tool()
def effortless_web_ui_launch() -> str:
    """
    Démarre le serveur HTTP intégré pour servir le dashboard Web d'Effortless et l'ouvre dans le navigateur.
    """
    root = get_project_root()
    # Le bundle Web UI vit dans l'installation Effortless, pas dans le projet utilisateur.
    web_ui_dist = os.path.join(get_install_root(), "src", "web-ui", "dist")

    if not os.path.exists(web_ui_dist):
        return (
            f"⚠️ Compiled dashboard not found ({web_ui_dist}).\n"
            "To build it, from the Effortless installation:\n"
            "  cd src/web-ui && npm install && npm run build"
        )

    # Trouver un port libre
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]
    except Exception:
        port = 8080 # Fallback

    # Handler : sert l'API JSON sous /api/*, sinon les fichiers statiques du bundle.
    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=web_ui_dist, **kwargs)

        def log_message(self, *args):
            pass  # silencieux

        def _send_json(self, payload, code=200):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.split("?")[0] == "/api/overview":
                try:
                    self._send_json(build_project_overview(root))
                except Exception as e:
                    self._send_json({"error": str(e)}, code=500)
                return
            return super().do_GET()

    # Lancer le serveur HTTP
    def start_server():
        server = HTTPServer(("localhost", port), DashboardHandler)
        server.serve_forever()

    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    url = f"http://localhost:{port}"
    webbrowser.open(url)

    return f"Dashboard started at {url} (API: {url}/api/overview) and opened in your browser."


@mcp.tool()
def effortless_migrate_init(target_path: str, confirm: bool = False, force: bool = False) -> str:
    """
    Analyse un projet cible existant et prépare sa migration vers Effortless.

    Sûr par défaut : sans `confirm=True`, retourne un APERÇU non destructif (rien n'est écrit).
    `confirm=True` scaffolde réellement la config, les tâches et les templates de cadrage.
    Refuse d'écraser un projet déjà initialisé sauf `force=True` (qui sauvegarde l'existant en .bak).
    """
    try:
        analysis = analyze_target_repo(target_path)
        report = init_migration_project(target_path, analysis, force=force, dry_run=not confirm)

        # Ajouter le diagnostic dans le rapport retourné
        diagnostic = f"🔍 MIGRATION SAFETY DIAGNOSTIC FOR {target_path}\n"
        diagnostic += f"- Detected stack: {', '.join(analysis['stack'])}\n"
        diagnostic += f"- Identified frameworks: {', '.join(analysis['frameworks']) or 'None'}\n"
        diagnostic += f"- Source file count: {analysis['source_files_count']}\n"
        diagnostic += f"- Detected doc files: {len(analysis['docs_files'])}\n"
        diagnostic += f"- Proposed reorganizations: {len(analysis['proposed_relocations'])}\n\n"

        return diagnostic + report
    except Exception as e:
        return f"Error initializing migration: {str(e)}"

@mcp.tool()
def effortless_migrate_apply(target_path: str, dry_run: bool = False) -> str:
    """
    Exécute physiquement les déplacements de réorganisation de documentation et de codebase.

    `dry_run=True` retourne un audit des déplacements prévus SANS rien déplacer ni écrire.
    """
    try:
        return apply_migration_project(target_path, dry_run=dry_run)
    except Exception as e:
        return f"Error applying migration: {str(e)}"

@mcp.tool()
def effortless_migrate_state(confirm: bool = False) -> str:
    """
    Migre un projet Effortless plat vers le modèle fractal (Epic / Story).

    Sûr par défaut : sans `confirm=True`, retourne un APERÇU non destructif (rien n'est écrit).
    `confirm=True` applique réellement la migration : scaffolde EPIC-PROJET / STO-PROJET-01,
    déplace les registres, relocalise le cadrage, réécrit la config et positionne les pointeurs d'état.
    """
    try:
        root = get_project_root()
        return migrate_state_to_fractal(root, dry_run=not confirm)
    except Exception as e:
        return f"Error migrating state to fractal model: {str(e)}"

@mcp.tool()
def effortless_tracker_couple(type: str, project_id: str, project_url: str) -> str:
    """
    Couple le projet Effortless à un projet du tracker (settings.tracker).

    Projection médiée par l'agent (STO-TRACKER-03) : aucun credential stocké ni lu.
    L'exécution Jira passe par le connecteur Rovo MCP côté agent (voir disclaimer).
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."

    from effortless_mcp.ports import ROVO_DISCLAIMER
    from effortless_mcp.ports.integration import couple_project
    couple_project(root, type, project_id, project_url)
    return (
        f"{ROVO_DISCLAIMER}\n\n"
        f"Projet couplé au tracker {type} '{project_id}' ({project_url}). "
        f"Aucun credential requis (projection médiée Rovo).\n"
        f"👉 Avant scaffold, fournis la taxonomie : agent → getJiraProjectIssueTypesMetadata, "
        f"puis effortless_tracker_discover_ack(taxonomy_json={{level: issue_type_id}})."
    )


@mcp.tool()
def effortless_tracker_scaffold(
    zone: str = "PROJET",
    template_name: str = "jira_project_scaffold",
    confirm_absent: bool = False,
) -> str:
    """
    Scaffolde l'arbre du template (défaut : [PROJET]) dans le projet tracker couplé.

    Idempotence Jira-as-truth (STO-TRACKER-12) : le `ScaffoldState` local
    (`.effortless/`, gitignoré) peut être perdu entre sessions — s'y fier seul a
    produit 3 arbres [PROJET] dupliqués. Garde à deux temps :
      1. `confirm_absent=False` (défaut) → N'ENQUEUE RIEN. Renvoie la JQL de garde ;
         l'agent vérifie l'absence du root sur Jira (label). Si des issues existent →
         `effortless_tracker_import_ack` (reconcile, NE PAS créer). Sinon relancer avec
         `confirm_absent=True`.
      2. `confirm_absent=True` (absence vérifiée par l'agent) → enqueue les créations.
    Fast-path : zone déjà connue localement (ScaffoldState) → no-op immédiat.
    Sans couplage (NullTracker) → no-op.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."
    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)

    from effortless_mcp.ports import resolve_tracker, ProjectRef, ROVO_DISCLAIMER, NullTracker
    from effortless_mcp.services.scaffolder import scaffold_project_from_template
    from effortless_mcp.services.scaffold_state import ScaffoldState
    from effortless_mcp.templates import load_scaffold_template

    settings = config_data.get("settings") or {}
    # root injecté : l'adapter médié (QueueTracker) écrit l'outbox sous <root>/.effortless/.
    tracker = resolve_tracker(settings, root)
    tcfg = settings.get("tracker") or {}
    project_ref = ProjectRef(tcfg.get("project_id", ""), tcfg.get("project_url", ""))
    try:
        template = load_scaffold_template(template_name)
    except OSError as e:
        return f"Error: template '{template_name}' introuvable ({e})."

    # Sans couplage : no-op sûr, aucune projection, aucun enqueue.
    if isinstance(tracker, NullTracker):
        return "Projet non couplé : aucune projection (no-op)."

    state = ScaffoldState(root)
    # Fast-path : identité de zone déjà connue localement → rien à recréer.
    if state.has(zone):
        return (
            f"{ROVO_DISCLAIMER}\n\n"
            f"Zone '{zone}' déjà scaffoldée ({len(state.get(zone))} refs connues). "
            f"Rien à exécuter (idempotent)."
        )

    # Garde Jira-as-truth : sans confirmation d'absence, on N'ENQUEUE RIEN.
    label = f"effortless-scaffold:{zone}"
    if not confirm_absent:
        return (
            f"{ROVO_DISCLAIMER}\n\n"
            f"⚠️ Garde d'idempotence : vérifie d'abord que la zone '{zone}' n'existe pas sur Jira.\n"
            f"1. Agent → searchJiraIssuesUsingJql : `labels = \"{label}\"`.\n"
            f"2. Si des issues existent → effortless_tracker_import_ack('{zone}', tree_json) "
            f"(reconcile Jira-as-truth, NE PAS créer).\n"
            f"3. Si AUCUNE issue → relance effortless_tracker_scaffold('{zone}', confirm_absent=True) "
            f"pour enqueue les créations."
        )

    # Absence confirmée par l'agent : on enqueue l'arbre.
    try:
        refs = scaffold_project_from_template(tracker, project_ref, template, zone, state)
    except Exception as e:
        return f"Error during scaffold: {e}"
    return (
        f"{ROVO_DISCLAIMER}\n\n"
        f"Scaffold '{zone}' planifié (absence confirmée) : {len(refs)} op(s) en attente. "
        f"Exécute via effortless_tracker_pending (Rovo), puis effortless_tracker_ack."
    )


@mcp.tool()
def effortless_tracker_discover_ack(taxonomy_json: str) -> str:
    """
    Persiste la taxonomie médiée (level → issue_type_id) dans settings.tracker.taxonomy.

    Fournie par l'agent après `getJiraProjectIssueTypesMetadata` (projection médiée,
    STO-TRACKER-04). Permet à QueueTracker de stamper l'`issue_type_id` autoritaire
    sur chaque op — indispensable pour les sous-tâches côté Rovo (DEC-07).
    Ex. : `{"epic":"10000","story":"10007","task":"10095"}`.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."
    try:
        tax = json.loads(taxonomy_json)
    except (json.JSONDecodeError, TypeError) as e:
        return f"Error: taxonomy_json invalide ({e})."
    if not isinstance(tax, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in tax.items()):
        return "Error: taxonomy doit être un objet {level: issue_type_id} (chaînes)."
    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    config_data.setdefault("settings", {}).setdefault("tracker", {})["taxonomy"] = tax
    with open(paths["config"], "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)
    return f"Taxonomie médiée persistée : {tax}."


@mcp.tool()
def effortless_tracker_ack(zone: str, refs_json: str) -> str:
    """
    Enregistre les refs Jira créées par l'agent et marque l'outbox joué (idempotent).

    `refs_json` = JSON `{"local:1": {"tracker_id": "EFL-1", "tracker_url": "…"}, …}`,
    la map id local → ref réelle produite par l'agent après exécution via Rovo.
    Persiste l'identité (ScaffoldState pour la zone) et vide les ops en attente.
    """
    root = get_project_root()
    from effortless_mcp.ports import SyncJournal
    from effortless_mcp.services.scaffold_state import ScaffoldState
    try:
        refs = json.loads(refs_json)
    except (json.JSONDecodeError, TypeError) as e:
        return f"Error: refs_json invalide ({e})."
    if not isinstance(refs, dict):
        return "Error: refs_json doit être un objet {local_id: {tracker_id, tracker_url}}."
    ScaffoldState(root).set(zone, refs)
    n = SyncJournal(root).replay(lambda e: None)  # marque tout joué, idempotent
    return f"Ack zone '{zone}' : {len(refs)} ref(s) persistée(s), {n} op(s) outbox marquée(s) jouée(s)."


@mcp.tool()
def effortless_tracker_pending() -> str:
    """
    Renvoie les opérations Jira en attente (le plan à exécuter par l'agent via Rovo).

    Projection médiée (STO-TRACKER-03) : le serveur n'exécute rien ; il liste les ops
    enqueue dans l'outbox. L'agent les joue via Rovo (createJiraIssue, parent+labels)
    en ordre `seq` croissant (parent avant enfant), puis appelle effortless_tracker_ack.
    """
    root = get_project_root()
    from effortless_mcp.ports import SyncJournal, ROVO_DISCLAIMER
    pend = SyncJournal(root).pending()
    if not pend:
        return f"{ROVO_DISCLAIMER}\n\nAucune opération en attente."
    ops = [{"seq": e["seq"], "op": e["op"], **(e.get("args") or {})} for e in pend]
    return f"{ROVO_DISCLAIMER}\n\n{json.dumps({'pending': ops}, ensure_ascii=False, indent=2)}"


@mcp.tool()
def effortless_tracker_transitions_ack(transitions_json: str) -> str:
    """
    Persiste la table de transitions médiée (statut local → id transition Jira) dans
    settings.tracker.transitions.

    Fournie par l'agent après `getTransitionsForJiraIssue` sur une issue témoin
    (projection médiée, STO-TRACKER-05). Permet à QueueTracker de stamper le
    `transition_id` autoritaire sur chaque op de transition — requis par
    transitionJiraIssue côté Rovo. Statuts locaux : Todo/Doing/Done (cycle en V).
    Ex. : `{"Todo":"11","Doing":"5","Done":"9"}`.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."
    try:
        trans = json.loads(transitions_json)
    except (json.JSONDecodeError, TypeError) as e:
        return f"Error: transitions_json invalide ({e})."
    if not isinstance(trans, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in trans.items()):
        return "Error: transitions doit être un objet {statut_local: transition_id} (chaînes)."
    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    config_data.setdefault("settings", {}).setdefault("tracker", {})["transitions"] = trans
    with open(paths["config"], "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)
    return f"Transitions médiées persistées : {trans}."


@mcp.tool()
def effortless_tracker_flush_ack(seqs_json: str = "") -> str:
    """
    Marque des opérations outbox comme jouées après leur flush par l'agent (Rovo).

    Pour les ops sans nouvelles refs à persister (transition, log_work) que
    `effortless_tracker_ack` (refs de scaffold) ne couvre pas. `seqs_json` = JSON
    d'une liste de `seq` (ceux exécutés) ; vide ou `[]` → marque toutes les ops en
    attente. Idempotent : une op déjà jouée est ignorée.
    """
    root = get_project_root()
    from effortless_mcp.ports import SyncJournal
    seqs = None
    s = (seqs_json or "").strip()
    if s:
        try:
            parsed = json.loads(s)
        except (json.JSONDecodeError, TypeError) as e:
            return f"Error: seqs_json invalide ({e})."
        if not isinstance(parsed, list) or not all(isinstance(x, int) for x in parsed):
            return "Error: seqs_json doit être une liste d'entiers (seq)."
        seqs = parsed
    n = SyncJournal(root).mark_played(seqs)
    return f"Flush ack : {n} op(s) outbox marquée(s) jouée(s)."


@mcp.tool()
def effortless_tracker_outbox_status() -> str:
    """
    Décompte l'outbox de synchronisation : ops en attente / jouées / total.

    Hygiène (STO-TRACKER-11) : révèle une accumulation d'ops non flushées (ex. projet
    dogfood couplé où task_add/task_update enqueue sans jamais flusher vers le tracker).
    """
    root = get_project_root()
    from effortless_mcp.ports import SyncJournal
    c = SyncJournal(root).counts()
    return f"Outbox : {c['pending']} en attente · {c['played']} jouée(s) · {c['total']} total."


@mcp.tool()
def effortless_tracker_outbox_purge(seqs_json: str = "") -> str:
    """
    DÉTRUIT des opérations outbox EN ATTENTE (abandon honnête), sans les exécuter.

    Distinct de `flush_ack` (qui marque JOUÉ, sémantiquement « exécuté via Rovo ») :
    `purge` supprime les fichiers d'ops erronées/obsolètes qui ne doivent jamais être
    projetées (STO-TRACKER-11). `seqs_json` = JSON d'une liste de `seq` ; vide ou `[]`
    → purge toutes les ops en attente. Les ops déjà jouées (audit) sont préservées.
    """
    root = get_project_root()
    from effortless_mcp.ports import SyncJournal
    seqs = None
    s = (seqs_json or "").strip()
    if s:
        try:
            parsed = json.loads(s)
        except (json.JSONDecodeError, TypeError) as e:
            return f"Error: seqs_json invalide ({e})."
        if not isinstance(parsed, list) or not all(isinstance(x, int) for x in parsed):
            return "Error: seqs_json doit être une liste d'entiers (seq)."
        seqs = parsed
    n = SyncJournal(root).purge(seqs)
    return f"Outbox purge : {n} op(s) en attente détruite(s) (abandonnées, non projetées)."


@mcp.tool()
def effortless_tracker_log_work(task_id: str, minutes: int, comment: str = "") -> str:
    """
    Enregistre du temps passé (minutes) sur une tâche et l'enqueue pour projection Jira.

    Projection médiée (STO-TRACKER-06) : le serveur enqueue une op « log_work » ;
    l'agent (Rovo) la joue via addWorklogToJiraIssue puis effortless_tracker_flush_ack.
    Le rollup temps sous-tâche→parent est natif Jira. Sans couplage : no-op.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["tasks"]):
        return "Error: Project not initialized."
    if not isinstance(minutes, int) or minutes <= 0:
        return "Error: minutes doit être un entier strictement positif."

    tasks_dir = resolve_registry_dir(root, "tasks")
    tasks = load_entities(tasks_dir)
    target_task = next((t for t in tasks if t["id"] == task_id), None)
    if not target_task:
        return f"Error: Task '{task_id}' not found."

    from effortless_mcp.ports import ROVO_DISCLAIMER, NullTracker, resolve_tracker
    from effortless_mcp.ports.integration import project_task_log_work

    with open(paths["config"], "r", encoding="utf-8") as f:
        settings = (json.load(f).get("settings") or {})
    if isinstance(resolve_tracker(settings, root), NullTracker):
        return f"Projet non couplé : temps non projeté (no-op). {minutes} min noté(es) localement."

    project_task_log_work(root, target_task, minutes, comment)
    return (
        f"{ROVO_DISCLAIMER}\n\n"
        f"Temps planifié : {minutes} min sur '{task_id}' ({target_task.get('tracker_id') or 'ref locale'}). "
        f"Exécute via effortless_tracker_pending (Rovo addWorklogToJiraIssue), puis effortless_tracker_flush_ack."
    )


@mcp.tool()
def effortless_tracker_import_plan(zone: str = "PROJET") -> str:
    """
    Renvoie le plan d'import read-mostly médié : la JQL que l'agent doit exécuter.

    Import « read-mostly » (STO-TRACKER-07) : Jira est source de vérité, aucune
    écriture. L'agent joue la JQL via Rovo `searchJiraIssuesUsingJql` (arbre marqué
    par le label de scaffold), reverse-mappe {level, tracker_id, tracker_url, title,
    parent_id}, puis appelle effortless_tracker_import_ack(zone, tree_json).
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."
    from effortless_mcp.ports import ROVO_DISCLAIMER
    label = f"effortless-scaffold:{zone}"
    jql = f'labels = "{label}" ORDER BY created ASC'
    plan = {
        "zone": zone,
        "jql": jql,
        "note": "L'Epic racine porte le label ; suivre parent → enfants pour reconstruire l'arbre.",
        "ack_shape": {"tree": [{"level": "epic|story|task", "tracker_id": "EFL-1",
                                "tracker_url": "…", "title": "…", "parent_id": "EFL-… | null"}]},
    }
    return f"{ROVO_DISCLAIMER}\n\n{json.dumps(plan, ensure_ascii=False, indent=2)}"


@mcp.tool()
def effortless_tracker_import_ack(zone: str, tree_json: str) -> str:
    """
    Reconcile l'arbre distant reverse-mappé par l'agent dans l'état local (Jira-as-truth).

    `tree_json` = JSON `{"tree": [{"level","tracker_id","tracker_url","title","parent_id"}]}`
    produit par l'agent après la JQL d'import_plan. Peuple ScaffoldState[zone]
    (`title → {tracker_id, tracker_url}`) pour rendre un futur scaffold idempotent
    (aucune recréation : la vérité Jira prime). Import read-mostly : aucune écriture Jira.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."
    from effortless_mcp.ports import ImportedObject, TrackerRef
    from effortless_mcp.services.scaffold_state import ScaffoldState
    try:
        payload = json.loads(tree_json)
    except (json.JSONDecodeError, TypeError) as e:
        return f"Error: tree_json invalide ({e})."
    tree = payload.get("tree") if isinstance(payload, dict) else payload
    if not isinstance(tree, list):
        return "Error: tree_json doit contenir une liste 'tree' d'objets d'issues."

    refs: dict = {}
    imported = []
    for node in tree:
        if not isinstance(node, dict):
            return "Error: chaque nœud doit être un objet {level, tracker_id, title, …}."
        tid, title = node.get("tracker_id"), node.get("title")
        if not tid or not title:
            return "Error: chaque nœud requiert au minimum tracker_id et title."
        url = node.get("tracker_url", "")
        refs[title] = {"tracker_id": tid, "tracker_url": url}
        imported.append(ImportedObject(
            level=node.get("level", "task"),
            ref=TrackerRef(tid, url),
            title=title,
            parent_id=node.get("parent_id"),
        ))
    ScaffoldState(root).set(zone, refs)
    return f"Import zone '{zone}' réconcilié : {len(imported)} issue(s) (Jira-as-truth). Re-scaffold désormais idempotent."


@mcp.tool()
def effortless_tracker_xray_discover_ack(xray_json: str) -> str:
    """
    Persiste la taxonomie Xray médiée dans settings.tracker.xray.

    Xray est un add-on Jira hors modèle fractal (STO-TRACKER-08). `xray_json` fournit
    l'id de type d'issue Test et le nom du type de lien Story↔Test, découverts par
    l'agent (getJiraProjectIssueTypesMetadata + getIssueLinkTypes via Rovo).
    Ex. : `{"test_issue_type_id":"10201","link_type":"Test"}`. `link_type` optionnel.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."
    try:
        xr = json.loads(xray_json)
    except (json.JSONDecodeError, TypeError) as e:
        return f"Error: xray_json invalide ({e})."
    if not isinstance(xr, dict) or not xr.get("test_issue_type_id"):
        return "Error: xray doit être un objet avec au minimum test_issue_type_id (chaîne)."
    if not all(isinstance(v, str) for v in xr.values()):
        return "Error: toutes les valeurs xray doivent être des chaînes."
    with open(paths["config"], "r", encoding="utf-8") as f:
        config_data = json.load(f)
    config_data.setdefault("settings", {}).setdefault("tracker", {})["xray"] = xr
    with open(paths["config"], "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)
    return f"Taxonomie Xray persistée : {xr}."


@mcp.tool()
def effortless_tracker_xray_add_test(title: str, link_tracker_id: str = "", test_type: str = "Manual") -> str:
    """
    Enqueue la création d'un Test Xray (médié), optionnellement lié à une Story/Task.

    Projection auxiliaire médiée (STO-TRACKER-08), hors modèle fractal. Enqueue une op
    « xray_create_test » ; l'agent (Rovo) crée l'issue via createJiraIssue (type Test,
    issue_type_id depuis settings.tracker.xray) puis, si `link_tracker_id` fourni, lie
    via createIssueLink (link_type), puis effortless_tracker_flush_ack. Sans couplage : no-op.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."
    if not (title or "").strip():
        return "Error: title requis."

    from effortless_mcp.ports import ROVO_DISCLAIMER, NullTracker, resolve_tracker, SyncJournal
    with open(paths["config"], "r", encoding="utf-8") as f:
        settings = (json.load(f).get("settings") or {})
    if isinstance(resolve_tracker(settings, root), NullTracker):
        return "Projet non couplé : Test Xray non projeté (no-op)."

    xr = (settings.get("tracker") or {}).get("xray") or {}
    SyncJournal(root).enqueue("xray_create_test", {
        "title": title,
        "issue_type_name": "Test",
        "issue_type_id": xr.get("test_issue_type_id"),  # None si discover Xray non fait
        "link_tracker_id": link_tracker_id or None,
        "link_type": xr.get("link_type") or "Test",
        "test_type": test_type,
    })
    linked = f" lié à {link_tracker_id}" if link_tracker_id else ""
    return (
        f"{ROVO_DISCLAIMER}\n\n"
        f"Test Xray '{title}'{linked} planifié. Exécute via effortless_tracker_pending "
        f"(Rovo createJiraIssue Test + createIssueLink), puis effortless_tracker_flush_ack."
    )


def _iter_task_files(root: str):
    """Itère tous les fichiers TSK-*.json : registre global plat + tous les
    sous-registres story-scopés (epics/<E>/stories/<S>/tasks/). Yield chaque
    (chemin, task_dict)."""
    paths = get_paths(root)
    dirs = [paths["tasks"]]
    epics_dir = paths["epics"]
    if os.path.isdir(epics_dir):
        for epic in os.listdir(epics_dir):
            stories = os.path.join(epics_dir, epic, "stories")
            if not os.path.isdir(stories):
                continue
            for story in os.listdir(stories):
                dirs.append(os.path.join(stories, story, "tasks"))
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".json"):
                continue
            fp = os.path.join(d, name)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    yield fp, json.load(f)
            except (json.JSONDecodeError, OSError):
                continue


@mcp.tool()
def effortless_tracker_reconcile_tasks(refs_json: str) -> str:
    """
    Réécrit le tracker_id/url des tâches locales depuis la map de refs de l'agent.

    Ferme le gap d'ordering (STO-TRACKER-09) : une tâche créée médié porte un
    placeholder `local:N` tant que son op create n'est pas flushée+réconciliée. Après
    que l'agent a créé les issues via Rovo, `refs_json` = `{"local:N": {"tracker_id":
    "EFL-…", "tracker_url": "…"}}` permet de rebrancher chaque tâche sur sa vraie clé
    Jira — transition/log_work médiés ciblent alors la clé réelle. Idempotent : une
    tâche déjà sur une clé réelle (hors map) est ignorée. Appeler flush_ack ensuite.
    """
    root = get_project_root()
    paths = get_paths(root)
    if not os.path.exists(paths["config"]):
        return "Error: Project not initialized."
    try:
        refs = json.loads(refs_json)
    except (json.JSONDecodeError, TypeError) as e:
        return f"Error: refs_json invalide ({e})."
    if not isinstance(refs, dict) or not all(
        isinstance(v, dict) and v.get("tracker_id") for v in refs.values()
    ):
        return "Error: refs_json doit être {local_id: {tracker_id, tracker_url}}."

    reconciled = 0
    for fp, task in _iter_task_files(root):
        ref = refs.get(task.get("tracker_id"))
        if not ref:
            continue
        task["tracker_id"] = ref["tracker_id"]
        task["tracker_url"] = ref.get("tracker_url", "")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(task, f, indent=2, ensure_ascii=False)
        reconciled += 1
    return f"Reconcile tâches : {reconciled} tâche(s) rebranchée(s) sur leur clé Jira réelle."


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
