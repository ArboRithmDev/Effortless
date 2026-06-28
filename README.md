# 🛠️ Effortless

**Effortless** est un framework de gestion de projet agnostique et modulaire conçu pour connecter harmonieusement les humains et les agents d'intelligence artificielle (LLM) autour d'un cycle de développement structuré.

Il fournit une architecture unifiée, des templates de **Skills** et un serveur **MCP (Model Context Protocol)** pour automatiser la tenue des phases, des registres de décisions et des incertitudes (BQO).

---

## 🎯 Concept
Nous appliquons le principe du *dogfooding* en gérant le projet **Effortless** avec sa propre méthodologie. 

Le dépôt est configuré à sa racine via le fichier [effortless.json](file:///file:///Users/Ben/Projets/Effortless/effortless.json), et l'état interne est suivi dans le dossier masqué [.effortless](file:///Users/Ben/Projets/Effortless/.effortless).

---

## 📂 Structure du Projet

```text
/Users/Ben/Projets/Effortless/
├── .effortless/               # Base de données interne du framework (JSON)
│   ├── state.json             # État actuel du workflow et de la phase active
│   ├── decisions.json         # Registre des décisions prises
│   ├── questions.json         # Bordereau des Questions Ouvertes (BQO) dynamique
│   └── tasks.json             # Liste des tâches et dépendances
├── cadrage/                   # Documents de cadrage métier et technique
│   ├── 01-VISION.md           # Vision et objectifs du projet
│   └── Phase-001/             # Phase d'observation active
│       ├── 00-FNC-GLO-glossaire.md  # Définition des termes clés
│       ├── 01-TEC-ANA-analyse.md    # Analyse des projets SecondBrain & Orcha OPAL
│       └── 02-BQO-questions.md      # Questions ouvertes de la phase d'observation
├── src/                       # Bases de code et applications (par stack)
│   └── mcp-server/            # Serveur MCP (Python + FastMCP + modèles + services)


└── skills/                    # Templates de Skills LLM (à implémenter)

```

---

## 🔄 Workflow en Cours
Nous sommes actuellement dans la phase **`O-analyse`** (Observer) du cycle de cadrage. Les documents obligatoires de cette phase ont été générés sous [cadrage/Phase-001/](file:///Users/Ben/Projets/Effortless/cadrage/Phase-001/).

La transition vers la phase **`P-cadrage`** (Positionner) nécessite de répondre aux questions ouvertes consignées dans le BQO : [02-BQO-questions.md](file:///Users/Ben/Projets/Effortless/cadrage/Phase-001/02-BQO-questions.md).
