import os
import json
import subprocess
from typing import Dict, Any, List

# Seuil DEC-11 : nombre d'échecs de recette consécutifs avant arrêt de sécurité de la boucle.
MAX_CORRECTION_ATTEMPTS = 5
# Délai max d'exécution de la commande de test (anti-blocage : un test qui hang figerait
# sinon l'appel MCP indéfiniment — le compteur d'échecs ne protège que des échecs, pas des hangs).
TEST_TIMEOUT_SECONDS = 600


def _save_loop_state(loop_file: str, state: Dict[str, Any]) -> None:
    """Écriture atomique (temp + os.replace) pour qu'un crash en cours d'écriture ne laisse
    pas un loop_state.json tronqué qui coincerait définitivement la boucle."""
    tmp = loop_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, loop_file)


def init_autonomous_loop(repo_path: str, goal: str) -> str:
    """
    Initialise le fichier de suivi de la boucle autonome.
    """
    loop_file = os.path.join(repo_path, ".effortless", "loop_state.json")
    state = {
        "goal": goal,
        "step": "Plan",
        "current_task": None,
        "error_count": 0,
        "logs": []
    }
    os.makedirs(os.path.dirname(loop_file), exist_ok=True)
    _save_loop_state(loop_file, state)
    return f"Autonomous loop successfully initialized for goal: '{goal}'."


def step_autonomous_loop(repo_path: str, test_command: str) -> str:
    """
    Évalue et fait avancer la machine à états de la boucle itérative d'Effortless.
    """
    from effortless_mcp.server import load_entities, save_entity

    loop_file = os.path.join(repo_path, ".effortless", "loop_state.json")
    if not os.path.exists(loop_file):
        return "Error: Autonomous loop not initialized. Please call effortless_loop_init."

    # R4 : lecture gardée — un loop_state.json corrompu donne un message clair plutôt qu'un crash.
    try:
        with open(loop_file, "r", encoding="utf-8") as f:
            loop_state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return (
            f"Error: loop_state.json unreadable ({e}). "
            "Reset the loop with effortless_loop_init."
        )

    tasks_dir = os.path.join(repo_path, ".effortless", "tasks")
    tasks = load_entities(tasks_dir)

    step = loop_state.get("step", "Plan")
    current_task_id = loop_state.get("current_task")
    error_count = loop_state.get("error_count", 0)

    if step == "Plan":
        # R7 : distinguer « backlog vide » (rien à faire) de « tout terminé ».
        if not tasks:
            return (
                "ℹ️ [PLAN] No tasks in the backlog (.effortless/tasks is empty). "
                "Add tasks with effortless_task_add before starting the loop."
            )

        # B6 : ne sélectionner qu'une tâche Todo dont TOUTES les dépendances sont Done.
        todo = [t for t in sorted(tasks, key=lambda x: x["id"]) if t.get("status") == "Todo"]
        done_ids = {t["id"] for t in tasks if t.get("status") == "Done"}
        eligible = [t for t in todo if all(dep in done_ids for dep in t.get("depends_on", []))]

        if not todo:
            loop_state["step"] = "Finished"
            loop_state["current_task"] = None
            _save_loop_state(loop_file, loop_state)
            return f"✅ GOAL REACHED! All backlog tasks are at status 'Done'. Goal '{loop_state['goal']}' is complete."

        if not eligible:
            # Des tâches Todo restent mais aucune n'est démarrable : dépendances non satisfaites.
            blocked = ", ".join(
                f"{t['id']} (attend {', '.join(d for d in t.get('depends_on', []) if d not in done_ids)})"
                for t in todo
            )
            return (
                "⏳ [PLAN] No startable task: all remaining Todo tasks have "
                f"unfinished dependencies.\nBlocked: {blocked}\n"
                "👉 Complete/reorder dependencies, or fix the depends_on values."
            )

        next_task = eligible[0]

        # --- Délégation systématique : aiguillage selon la complexité ---
        complexity = next_task.get("complexity")
        if complexity is None:
            return (
                f"🔎 [TRIAGE] Task {next_task['id']}: {next_task['title']} — unclassified.\n"
                "👉 Classify it via effortless_task_classify(task_id, 'simple'|'complex'), "
                "then re-run effortless_loop_step. (Rule: 'simple' = mechanical, no reasoning; "
                "'complex' = reasoning/architecture/tradeoff.)"
            )
        if complexity == "complex":
            return (
                f"🧩 [DECOMPOSE] Complex task {next_task['id']}: {next_task['title']}.\n"
                "👉 Break it down into SIMPLE sub-tasks via "
                "effortless_task_add(title, complexity='simple', depends_on=[...]), "
                f"then mark {next_task['id']} 'Done' via effortless_task_update. "
                "Then re-run effortless_loop_step."
            )
        # complexity == "simple" : flux nominal d'exécution, délégation imposée.

        # Activer la tâche
        next_task["status"] = "Doing"
        save_entity(tasks_dir, next_task["id"], next_task)

        loop_state["step"] = "Implementation"
        loop_state["current_task"] = next_task["id"]
        loop_state["error_count"] = 0
        _save_loop_state(loop_file, loop_state)

        return (
            f"📋 [DELEGATE] Simple task selected: **{next_task['id']}**: {next_task['title']}\n"
            f"Loop status: **Implementation**\n"
            "👉 Instruction: delegate this task to a sub-agent (Agent tool), with a closed and "
            "bounded prompt; retrieve a compact result; do NOT implement it yourself "
            "(keep the conclusion, not the details). Once done, re-run effortless_loop_step "
            "to start acceptance."
        )

    elif step == "Implementation" or step == "Correction":
        # Passer à l'étape de Recette
        loop_state["step"] = "Recette"
        _save_loop_state(loop_file, loop_state)

        # Lancer immédiatement l'évaluation récursive de Recette pour fluidifier la boucle
        return step_autonomous_loop(repo_path, test_command)

    elif step == "Recette":
        # 1. Exécuter la commande de test du projet
        test_failed = False
        test_logs = ""
        try:
            res = subprocess.run(
                test_command,
                shell=True,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT_SECONDS,
                stdin=subprocess.DEVNULL,  # ne pas hériter du pipe JSON-RPC (deadlock MCP/Windows)
                encoding="utf-8",
                errors="replace",  # F1 (DEC-19) : sous shell=True (cmd.exe) la sortie peut contenir
                                   # des octets OEM/cp850 invalides en utf-8 ; un décodage strict lève
                                   # UnicodeDecodeError dans le reader thread → stdout/stderr None →
                                   # plante la concat plus bas et masque le vrai code retour.
            )
            rc = res.returncode
            if rc == 5:
                # pytest exit 5 = aucun test collecté : pas un échec, rien à recetter.
                test_failed = False
            elif rc == 127:
                # B7 : commande introuvable. Erreur de configuration, NON corrigeable par
                # itération de code → on n'incrémente pas le compteur, on reste en Recette.
                return (
                    "❌ [ACCEPTANCE] Test command not found (exit 127).\n"
                    f"Command: `{test_command}`\n"
                    "👉 Fix the test_command (e.g. activate venv / check pytest path) and retry."
                )
            elif rc != 0:
                test_failed = True
                # Garde None (F1/DEC-19) : malgré errors='replace', rester défensif.
                test_logs = (res.stdout or "") + "\n" + (res.stderr or "")
        except subprocess.TimeoutExpired:
            test_failed = True
            test_logs = (
                f"Tests exceeded the {TEST_TIMEOUT_SECONDS}s timeout "
                "(likely hang: stdin wait, server started, deadlock)."
            )
        except Exception as e:
            test_failed = True
            test_logs = f"Failed to run tests: {str(e)}"

        # 2. Vérifier la dérive (anti-drift)
        from effortless_mcp.services.drift import check_project_drift
        is_drifting, modified, active = check_project_drift(repo_path, tasks_dir)

        if test_failed or is_drifting:
            # Échec de recette
            error_count += 1
            loop_state["error_count"] = error_count

            if error_count >= MAX_CORRECTION_ATTEMPTS:
                loop_state["step"] = "Aborted"
                # Rétablir la tâche en Todo
                if current_task_id:
                    task = next((t for t in tasks if t["id"] == current_task_id), None)
                    if task:
                        task["status"] = "Todo"
                        save_entity(tasks_dir, task["id"], task)

                _save_loop_state(loop_file, loop_state)

                return (
                    f"❌ [BLOCKED] Acceptance failed {MAX_CORRECTION_ATTEMPTS} consecutive times for task {current_task_id}.\n"
                    f"Safety stop of the autonomous loop to prevent resource overconsumption.\n"
                    f"Error details:\n```\n{test_logs[:1000]}\n```"
                )
            else:
                loop_state["step"] = "Correction"
                _save_loop_state(loop_file, loop_state)

                drift_msg = "\n⚠️ Drift detected (changes outside active task)." if is_drifting else ""
                return (
                    f"⚠️ [ACCEPTANCE] Validation failed (Attempt {error_count}/{MAX_CORRECTION_ATTEMPTS}).{drift_msg}\n"
                    f"Test error logs:\n```\n{test_logs[:800]}\n```\n"
                    f"👉 Instruction: Fix the errors reported in the tests, then re-run `effortless_loop_step`."
                )
        else:
            # Succès de recette -> Livraison & Passage à la tâche suivante.
            #
            # F3 (dogfood DEC-20) : committer PENDANT que la tâche est encore 'Doing'.
            # Le hook pre-commit anti-drift bloque tout commit s'il existe des fichiers
            # de code modifiés mais AUCUNE tâche 'Doing'. Marquer la tâche 'Done' AVANT
            # de committer supprimait la seule tâche active → le commit était rejeté
            # (erreur avalée en « already committed? »), le travail livré jamais persisté,
            # et le fichier non committé déclenchait une fausse dérive à la tâche suivante.
            # On commit d'abord (tâche encore active), on clôt ensuite.
            #
            # stdin=DEVNULL + capture_output : sinon git hérite du pipe JSON-RPC du
            # serveur MCP (deadlock Windows) et écrit sur le stdout du protocole.
            try:
                subprocess.run(
                    ["git", "add", "."], cwd=repo_path, check=True,
                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
                )
                subprocess.run(
                    ["git", "commit", "-m", f"feat: complete task {current_task_id}"],
                    cwd=repo_path, check=True,
                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
                )
                git_msg = "Changes committed to Git."
            except Exception as e:
                git_msg = f"Failed to commit: {str(e)} (already committed?)"

            # Tâche livrée et committée : on peut la clôturer. La bascule 'Done' (fichier
            # .effortless/, hors scope drift src/) sera incluse dans le prochain commit.
            if current_task_id:
                task = next((t for t in tasks if t["id"] == current_task_id), None)
                if task:
                    task["status"] = "Done"
                    save_entity(tasks_dir, task["id"], task)

            # Repasser à l'étape Plan
            loop_state["step"] = "Plan"
            loop_state["current_task"] = None
            loop_state["error_count"] = 0
            _save_loop_state(loop_file, loop_state)

            return (
                f"✅ [DELIVERY] Task {current_task_id} validated and completed successfully!\n"
                f"{git_msg}\n"
                f"👉 The autonomous loop returns to the Plan step. Re-run `effortless_loop_step` for the next task."
            )

    elif step == "Finished":
        return f"The loop has already completed successfully for goal: '{loop_state['goal']}'."

    elif step == "Aborted":
        return (
            f"The loop is currently blocked/aborted after {MAX_CORRECTION_ATTEMPTS} correction failures. "
            "Please fix the bug manually, then reset the loop."
        )

    return f"Unknown loop state: {step}"
