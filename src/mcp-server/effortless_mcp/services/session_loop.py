import os
import json
import subprocess
from typing import Dict, Any, List


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
    with open(loop_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    return f"Boucle autonome initialisée avec succès pour l'objectif : '{goal}'."

def step_autonomous_loop(repo_path: str, test_command: str) -> str:
    """
    Évalue et fait avancer la machine à états de la boucle itérative d'Effortless.
    """
    from effortless_mcp.server import load_entities, save_entity

    loop_file = os.path.join(repo_path, ".effortless", "loop_state.json")
    if not os.path.exists(loop_file):
        return "Erreur : Boucle autonome non initialisée. Veuillez appeler effortless_loop_init."

    with open(loop_file, "r", encoding="utf-8") as f:
        loop_state = json.load(f)

    tasks_dir = os.path.join(repo_path, ".effortless", "tasks")
    tasks = load_entities(tasks_dir)

    step = loop_state.get("step", "Plan")
    current_task_id = loop_state.get("current_task")
    error_count = loop_state.get("error_count", 0)

    if step == "Plan":
        # Trouver la première tâche 'Todo'
        next_task = next((t for t in sorted(tasks, key=lambda x: x["id"]) if t.get("status") == "Todo"), None)
        if not next_task:
            loop_state["step"] = "Finished"
            loop_state["current_task"] = None
            with open(loop_file, "w", encoding="utf-8") as f:
                json.dump(loop_state, f, indent=2, ensure_ascii=False)
            return f"✅ OBJECTIF ATTEINT ! Toutes les tâches du backlog sont au statut 'Done'. L'objectif '{loop_state['goal']}' est rempli."

        # Activer la tâche
        next_task["status"] = "Doing"
        save_entity(tasks_dir, next_task["id"], next_task)

        loop_state["step"] = "Implementation"
        loop_state["current_task"] = next_task["id"]
        loop_state["error_count"] = 0
        with open(loop_file, "w", encoding="utf-8") as f:
            json.dump(loop_state, f, indent=2, ensure_ascii=False)

        return (
            f"📋 [PLAN] Tâche sélectionnée : **{next_task['id']}** : {next_task['title']}\n"
            f"Statut de la boucle : **Implementation**\n"
            f"👉 Consigne : Développez l'implémentation de cette tâche. Une fois fait, relancez `effortless_loop_step` pour lancer la recette."
        )

    elif step == "Implementation" or step == "Correction":
        # Passer à l'étape de Recette
        loop_state["step"] = "Recette"
        with open(loop_file, "w", encoding="utf-8") as f:
            json.dump(loop_state, f, indent=2, ensure_ascii=False)
        
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
                text=True
            )
            if res.returncode != 0:
                test_failed = True
                test_logs = res.stdout + "\n" + res.stderr
        except Exception as e:
            test_failed = True
            test_logs = f"Impossible de lancer les tests : {str(e)}"

        # 2. Vérifier la dérive (anti-drift)
        from effortless_mcp.services.drift import check_project_drift
        is_drifting, modified, active = check_project_drift(repo_path, tasks_dir)

        if test_failed or is_drifting:
            # Échec de recette
            error_count += 1
            loop_state["error_count"] = error_count

            if error_count >= 5:
                loop_state["step"] = "Aborted"
                # Rétablir la tâche en Todo
                if current_task_id:
                    task = next((t for t in tasks if t["id"] == current_task_id), None)
                    if task:
                        task["status"] = "Todo"
                        save_entity(tasks_dir, task["id"], task)
                
                with open(loop_file, "w", encoding="utf-8") as f:
                    json.dump(loop_state, f, indent=2, ensure_ascii=False)

                return (
                    f"❌ [BLOCAGE] La recette a échoué 5 fois consécutives pour la tâche {current_task_id}.\n"
                    f"Arrêt de sécurité de la boucle autonome pour éviter la surconsommation de ressources.\n"
                    f"Détails de l'erreur :\n```\n{test_logs[:1000]}\n```"
                )
            else:
                loop_state["step"] = "Correction"
                with open(loop_file, "w", encoding="utf-8") as f:
                    json.dump(loop_state, f, indent=2, ensure_ascii=False)
                
                drift_msg = "\n⚠️ Dérive détectée (modifs hors tâche active)." if is_drifting else ""
                return (
                    f"⚠️ [RECETTE] Échec de validation (Tentative {error_count}/5).{drift_msg}\n"
                    f"Logs d'erreurs des tests :\n```\n{test_logs[:800]}\n```\n"
                    f"👉 Consigne : Corrigez les erreurs signalées dans les tests puis relancez `effortless_loop_step`."
                )
        else:
            # Succès de recette -> Livraison & Passage à la tâche suivante
            if current_task_id:
                task = next((t for t in tasks if t["id"] == current_task_id), None)
                if task:
                    task["status"] = "Done"
                    save_entity(tasks_dir, task["id"], task)

            # Faire un commit Git automatique
            try:
                subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
                subprocess.run(["git", "commit", "-m", f"feat: complete task {current_task_id}"], cwd=repo_path, check=True)
                git_msg = "Changements commités dans Git."
            except Exception as e:
                git_msg = f"Impossible de commiter : {str(e)} (déjà commité ?)"

            # Repasser à l'étape Plan
            loop_state["step"] = "Plan"
            loop_state["current_task"] = None
            loop_state["error_count"] = 0
            with open(loop_file, "w", encoding="utf-8") as f:
                json.dump(loop_state, f, indent=2, ensure_ascii=False)

            return (
                f"✅ [LIVRAISON] Tâche {current_task_id} validée et terminée avec succès !\n"
                f"{git_msg}\n"
                f"👉 La boucle autonome repasse à l'étape Plan. Relancez `effortless_loop_step` pour la tâche suivante."
            )

    elif step == "Finished":
        return f"La boucle est déjà terminée avec succès pour l'objectif : '{loop_state['goal']}'."

    elif step == "Aborted":
        return "La boucle est actuellement bloquée/interrompue après 5 échecs de correction. Veuillez corriger le bug manuellement, puis réinitialiser la boucle."

    return f"État inconnu de la boucle : {step}"
