---
name: effortless
description: Discipline méthodologique de gestion de projet agent-first pour initialiser, valider et exécuter les phases de développement.
---

# 🛠️ Skill Effortless

Ce Skill enseigne à l'agent comment utiliser le protocole et la méthodologie **Effortless** pour structurer son travail de développement sans brûler les étapes.

---

## 📋 Directives Comportementales

### 1. Prise de contact (Analyse du Contexte)
Dès que vous démarrez sur un projet équipé d'un fichier `effortless.json` ou d'un dossier `.effortless/` :
1. **Exécutez immédiatement** l'outil `effortless_status` pour connaître la phase active et la checklist de documents requis.
2. **Ne commencez aucun développement** si le projet est dans l'une des phases de cadrage (`O-analyse`, `P-cadrage`, `A-specs`, `L-plan`). Concentrez-vous uniquement sur la rédaction et la validation des documents requis pour la phase en cours.

---

## 🔄 Gestion du Cycle de Vie (Workflow)

### Étape A : Observation (`O-analyse`)
* Remplissez le Glossaire et l'Analyse comparative.
* Si des incertitudes métier surgissent, posez une question en utilisant l'outil `effortless_question_ask` avec l'impact approprié (`Blocker` si cela empêche d'avancer, `Structuring` ou `Minor`).
* Ne tentez pas de deviner les réponses : sollicitez explicitement l'arbitrage de l'utilisateur.

### Étape B : Cadrage Décisionnel (`P-cadrage`)
* Figez les choix techniques et l'architecture cible.
* Pour chaque décision d'architecture arrêtée (contexte, choix, alternatives rejetées), enregistrez-la à l'aide de l'outil `effortless_decision_add`.

### Étape C : Spécifications (`A-specs`)
* Rédigez les spécifications fonctionnelles détaillées et les contrats d'API.
* Validez que tous les documents requis sont complets et conformes.

### Étape D : Plan d'Action (`L-plan`)
* Rédigez le plan de développement et découpez le travail en tâches atomiques.
* Déclarez les tâches de développement via le MCP ou le système de backlog.

### Étape E : Exécution (`E-execute`)
* Avant de commencer une tâche, mettez son statut à `Doing` avec `effortless_task_update`.
* Lorsque la tâche est terminée et testée, passez-la à `Done`.

---

## 🚦 Règle d'Or des Transitions
Ne passez à la phase suivante (via `effortless_phase_next`) que si `effortless_status` indique `Éligibilité pour la phase suivante : ✅ OUI`. 

En cas de blocage, résolvez d'abord les raisons indiquées (documents manquants/invalides ou questions BQO bloquantes non résolues).
