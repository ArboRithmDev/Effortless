import os
import sys

# Sous Windows, le stdout de la console est en cp1252 par défaut : les emojis
# des messages (⚠️, 🛠️, …) lèvent UnicodeEncodeError et font planter le CLI
# (notamment le hook anti-drift qui l'appelle en --drift-check-strict).
# On force UTF-8 UNIQUEMENT sur Windows ; macOS/Linux sont déjà en UTF-8 et
# restent inchangés.
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Ajouter le chemin de mcp-server/src pour pouvoir importer effortless_mcp
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp-server")))

from effortless_mcp.server import (
    effortless_init,
    effortless_status,
    effortless_phase_next,
    effortless_decision_add,
    effortless_question_ask,
    effortless_question_resolve,
    effortless_task_add,
    effortless_task_update,
    effortless_secondbrain_sync
)

def print_banner():
    print("=" * 60)
    print(" 🛠️  EFFORTLESS - CLIENT CLI DE TEST INTERACTIF")
    print("=" * 60)

def show_menu():
    print("\n--- MENU DES ACTIONS ---")
    print("1. [status]   Afficher le statut et la checklist du projet")
    print("2. [init]     Initialiser (ou réinitialiser) le projet")
    print("3. [next]     Transitionner vers la phase suivante")
    print("4. [decision] Enregistrer une décision d'architecture (ADR)")
    print("5. [ask]      Poser une question ouverte au BQO")
    print("6. [resolve]  Résoudre une question du BQO")
    print("7. [task-add] Créer une nouvelle tâche de développement")
    print("8. [task-up]  Mettre à jour le statut d'une tâche")
    print("9. [sync-sb]  Forcer la synchronisation avec SecondBrain")
    print("0. Quitter")
    print("-" * 24)

def run_interactive():
    print_banner()
    while True:
        show_menu()
        try:
            choice = input("Choisissez une option (0-9) : ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir !")
            break

        if choice == "0":
            print("Au revoir !")
            break
        elif choice == "1":
            print("\nExécution de effortless_status()...")
            print(effortless_status())
        elif choice == "2":
            name = input("Nom du projet (laisser vide pour valeur par défaut) : ").strip() or None
            desc = input("Description du projet : ").strip() or None
            force_str = input("Forcer l'initialisation si déjà configuré (y/N) : ").strip().lower()
            force = force_str == "y"
            print("\nExécution de effortless_init()...")
            print(effortless_init(project_name=name, description=desc, force=force))
        elif choice == "3":
            print("\nExécution de effortless_phase_next()...")
            print(effortless_phase_next())
        elif choice == "4":
            title = input("Titre de la décision (ex: Choix base SQLite) : ").strip()
            context = input("Contexte / Problème : ").strip()
            decision = input("Décision arrêtée : ").strip()
            
            consequences = []
            print("Entrez les conséquences (ligne vide pour terminer) :")
            while True:
                cons = input("- ").strip()
                if not cons:
                    break
                consequences.append(cons)
                
            rejected = []
            print("Entrez les alternatives rejetées (ligne vide pour terminer) :")
            while True:
                rej = input("- ").strip()
                if not rej:
                    break
                rejected.append(rej)
                
            print("\nExécution de effortless_decision_add()...")
            print(effortless_decision_add(
                title=title,
                context=context,
                decision=decision,
                consequences=consequences,
                rejected_alternatives=rejected
            ))
        elif choice == "5":
            question = input("Intitulé de la question : ").strip()
            context = input("Contexte / Pourquoi cette question : ").strip()
            impact = input("Impact (Blocker, Structuring, Minor) [Structuring] : ").strip() or "Structuring"
            suggestion = input("Suggestion de réponse (optionnel) : ").strip() or None
            print("\nExécution de effortless_question_ask()...")
            print(effortless_question_ask(
                question=question,
                context=context,
                impact=impact,
                suggestion=suggestion
            ))
        elif choice == "6":
            q_id = input("ID de la question à résoudre (ex: Q-01) : ").strip()
            answer = input("Réponse officielle : ").strip()
            print("\nExécution de effortless_question_resolve()...")
            print(effortless_question_resolve(question_id=q_id, answer=answer))
        elif choice == "7":
            title = input("Titre de la tâche : ").strip()
            desc = input("Description de la tâche : ").strip() or None
            
            depends = []
            print("Entrez les IDs de tâches dépendantes (ex: TSK-001, ligne vide pour terminer) :")
            while True:
                dep = input("- ").strip()
                if not dep:
                    break
                depends.append(dep)
                
            print("\nExécution de effortless_task_add()...")
            print(effortless_task_add(title=title, description=desc, depends_on=depends))
        elif choice == "8":
            t_id = input("ID de la tâche (ex: TSK-001) : ").strip()
            status = input("Nouveau statut (Todo, Doing, Done) : ").strip()
            print("\nExécution de effortless_task_update()...")
            print(effortless_task_update(task_id=t_id, status=status))
        elif choice == "9":
            print("\nExécution de effortless_secondbrain_sync()...")
            print(effortless_secondbrain_sync())
        else:
            print("Option invalide. Veuillez choisir entre 0 et 9.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if "--drift-check-strict" in sys.argv:
            from effortless_mcp.services.drift import check_project_drift
            from effortless_mcp.server import get_project_root, get_paths
            root = get_project_root()
            paths = get_paths(root)
            is_drifting, modified, active = check_project_drift(root, paths["tasks"])
            if is_drifting:
                print("⚠️ [Effortless] DRIFT DETECTED: Code modified without active task.")
                for f in modified:
                    print(f"  - {f}")
                sys.exit(1)
            else:
                print("✅ [Effortless] No drift detected.")
                sys.exit(0)
        else:
            print("Usage: python main.py [--drift-check-strict]")
            sys.exit(0)
    else:
        run_interactive()
