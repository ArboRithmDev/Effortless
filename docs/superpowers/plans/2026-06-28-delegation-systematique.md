# Délégation systématique — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classer la complexité des tâches (simple/complex) et faire émettre par la boucle autonome des consignes déterministes (TRIAGE / DÉCOMPOSER / DÉLÉGUER) pour que l'agent invocateur délègue systématiquement le travail simple à des sous-agents.

**Architecture:** Effortless ne spawn pas d'agents ; il instruit l'agent invocateur. On ajoute un champ `complexity` au modèle `Task`, un outil `effortless_task_classify`, un branchement dans l'étape PLAN de la boucle, une doctrine dans `SKILL.md`, et un badge dans le dashboard.

**Tech Stack:** Python 3.12, FastMCP, Pydantic, pytest ; React 19 / Vite (web-ui).

## Global Constraints

- Taxonomie binaire : `complexity ∈ {"simple", "complex"}` ; absent = `None` (non classée).
- Classée par l'agent à la création ; triage **une seule fois** si absente (pas par étape).
- Pas de champ `parent`, pas de hiérarchie persistée, pas de 3e niveau (YAGNI).
- Validation **avant écriture** ; aucune écriture partielle sur valeur invalide.
- Tests via `EFFORTLESS_PROJECT_ROOT` pointé sur un `tmpdir` (cf. tests existants).
- Répertoire de tests : `src/mcp-server/tests/test_services.py`. Lancer pytest depuis `src/mcp-server` avec le venv activé.
- Messages d'erreur et consignes en français (cohérence avec l'existant). Identifiants de code en anglais.
- Commits fréquents ; le hook pre-commit anti-drift exige une tâche `Doing` si `src/` est modifié — utiliser `git commit --no-verify` n'est PAS souhaité ; à la place, ces changements de dev sont hors boucle Effortless, donc committer normalement (le hook ne bloque que si des fichiers `src/` du projet courant sont modifiés sans tâche active ; ici on travaille sur Effortless lui-même — si le hook bloque, créer une tâche `Doing` via `effortless_task_add` + `effortless_task_update`, ou committer avec `--no-verify` en dernier recours documenté).

---

### Task 1: Champ `complexity` sur le modèle Task + paramètre dans `effortless_task_add`

**Files:**
- Modify: `src/mcp-server/effortless_mcp/models/task.py`
- Modify: `src/mcp-server/effortless_mcp/server.py` (fonction `effortless_task_add`, ~ligne 548)
- Test: `src/mcp-server/tests/test_services.py`

**Interfaces:**
- Produces: `Task.complexity: Optional[str]` (valeurs `"simple"`, `"complex"`, `None`).
- Produces: `effortless_task_add(title, description=None, depends_on=None, complexity=None) -> str` — rejette `complexity ∉ {simple, complex, None}` avant écriture.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `src/mcp-server/tests/test_services.py` :

```python
def test_task_add_stores_and_validates_complexity(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        # complexity valide stockée
        msg = server.effortless_task_add("T simple", complexity="simple")
        tsk_id = msg.split("Tâche ")[1].split(" ")[0]
        with open(os.path.join(tmpdir, ".effortless", "tasks", f"{tsk_id}.json"), encoding="utf-8") as f:
            assert json.load(f)["complexity"] == "simple"

        # absente => None
        msg2 = server.effortless_task_add("T sans")
        tsk_id2 = msg2.split("Tâche ")[1].split(" ")[0]
        with open(os.path.join(tmpdir, ".effortless", "tasks", f"{tsk_id2}.json"), encoding="utf-8") as f:
            assert json.load(f)["complexity"] is None

        # valeur invalide rejetée, pas d'écriture
        before = len(os.listdir(os.path.join(tmpdir, ".effortless", "tasks")))
        bad = server.effortless_task_add("T bad", complexity="trivial")
        assert "invalide" in bad
        after = len(os.listdir(os.path.join(tmpdir, ".effortless", "tasks")))
        assert before == after
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd src/mcp-server && source .venv/bin/activate && pytest tests/test_services.py::test_task_add_stores_and_validates_complexity -v`
Expected: FAIL (`effortless_task_add() got an unexpected keyword argument 'complexity'`).

- [ ] **Step 3: Ajouter le champ au modèle**

Dans `src/mcp-server/effortless_mcp/models/task.py`, ajouter la ligne `complexity` :

```python
class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str = "Todo"
    phase: str
    depends_on: List[str] = Field(default_factory=list)
    complexity: Optional[str] = None
```

- [ ] **Step 4: Ajouter le paramètre + validation dans `effortless_task_add`**

Dans `src/mcp-server/effortless_mcp/server.py`, modifier la signature de `effortless_task_add` :

```python
def effortless_task_add(
    title: str,
    description: Optional[str] = None,
    depends_on: Optional[List[str]] = None,
    complexity: Optional[str] = None
) -> str:
```

Juste après le garde « Projet non initialisé » de cette fonction, ajouter :

```python
    if complexity is not None and complexity not in ("simple", "complex"):
        return f"Erreur : complexity invalide '{complexity}'. Valeurs autorisées : simple, complex."
```

Et dans la construction `new_task = Task(...)`, ajouter le champ :

```python
    new_task = Task(
        id=tsk_id,
        title=title,
        description=description,
        status="Todo",
        phase=current_phase_id,
        depends_on=depends_on or [],
        complexity=complexity
    )
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `pytest tests/test_services.py::test_task_add_stores_and_validates_complexity -v`
Expected: PASS.

- [ ] **Step 6: Lancer toute la suite**

Run: `pytest -q`
Expected: tous verts.

- [ ] **Step 7: Commit**

```bash
git add src/mcp-server/effortless_mcp/models/task.py src/mcp-server/effortless_mcp/server.py src/mcp-server/tests/test_services.py
git commit -m "feat: add task complexity field and validation in task_add"
```

---

### Task 2: Outil `effortless_task_classify`

**Files:**
- Modify: `src/mcp-server/effortless_mcp/server.py` (ajouter après `effortless_task_update`)
- Test: `src/mcp-server/tests/test_services.py`

**Interfaces:**
- Consumes: `load_entities`, `save_entity`, `get_paths`, `get_project_root` (existants dans `server.py`).
- Produces: `effortless_task_classify(task_id: str, complexity: str) -> str` — pose `complexity` sur une tâche existante ; rejette valeur invalide / ID inconnu / projet non initialisé.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `src/mcp-server/tests/test_services.py` :

```python
def test_task_classify(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        msg = server.effortless_task_add("T")
        tsk_id = msg.split("Tâche ")[1].split(" ")[0]

        # classification réussie
        ok = server.effortless_task_classify(tsk_id, "complex")
        assert tsk_id in ok and "complex" in ok
        with open(os.path.join(tmpdir, ".effortless", "tasks", f"{tsk_id}.json"), encoding="utf-8") as f:
            assert json.load(f)["complexity"] == "complex"

        # valeur invalide
        assert "invalide" in server.effortless_task_classify(tsk_id, "trivial")
        # ID inconnu
        assert "introuvable" in server.effortless_task_classify("TSK-X-99", "simple")
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `pytest tests/test_services.py::test_task_classify -v`
Expected: FAIL (`module 'effortless_mcp.server' has no attribute 'effortless_task_classify'`).

- [ ] **Step 3: Implémenter l'outil**

Dans `src/mcp-server/effortless_mcp/server.py`, ajouter juste après la fonction `effortless_task_update` (avant `@mcp.tool()` suivant) :

```python
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
        return "Erreur : Projet non initialisé."

    if complexity not in ("simple", "complex"):
        return f"Erreur : complexity invalide '{complexity}'. Valeurs autorisées : simple, complex."

    tasks = load_entities(paths["tasks"])
    target = next((t for t in tasks if t["id"] == task_id), None)
    if not target:
        return f"Erreur : Tâche '{task_id}' introuvable."

    target["complexity"] = complexity
    save_entity(paths["tasks"], task_id, target)

    return f"Tâche '{task_id}' classée '{complexity}'."
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `pytest tests/test_services.py::test_task_classify -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mcp-server/effortless_mcp/server.py src/mcp-server/tests/test_services.py
git commit -m "feat: add effortless_task_classify tool"
```

---

### Task 3: Branchement TRIAGE / DÉCOMPOSER / DÉLÉGUER dans la boucle PLAN

**Files:**
- Modify: `src/mcp-server/effortless_mcp/services/session_loop.py` (étape `Plan`)
- Test: `src/mcp-server/tests/test_services.py`

**Interfaces:**
- Consumes: `Task.complexity` (Task 1), tâches via `load_entities`.
- Produces: comportement de `step_autonomous_loop` à l'étape `Plan` —
  `complexity is None` → texte contient `TRIAGE`, tâche reste `Todo` ;
  `complex` → texte contient `DÉCOMPOSER`, tâche reste `Todo` ;
  `simple` → texte contient `DÉLÉGUER`, `step` passe à `Implementation`, tâche `Doing`.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `src/mcp-server/tests/test_services.py` :

```python
def test_loop_plan_delegation_branches(monkeypatch):
    from effortless_mcp import server
    from effortless_mcp.services import session_loop as sl
    import json as _json
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        tasks_dir = os.path.join(tmpdir, ".effortless", "tasks")

        def add(title, complexity=None):
            msg = server.effortless_task_add(title, complexity=complexity)
            return msg.split("Tâche ")[1].split(" ")[0]

        # 1. Tâche non classée -> TRIAGE
        t_none = add("non classée")
        server.effortless_loop_init("g")
        out = sl.step_autonomous_loop(tmpdir, "true")
        assert "TRIAGE" in out
        with open(os.path.join(tasks_dir, f"{t_none}.json"), encoding="utf-8") as f:
            assert _json.load(f)["status"] == "Todo"  # pas avancée

        # 2. Classée complex -> DÉCOMPOSER
        server.effortless_task_classify(t_none, "complex")
        out2 = sl.step_autonomous_loop(tmpdir, "true")
        assert "DÉCOMPOSER" in out2
        with open(os.path.join(tasks_dir, f"{t_none}.json"), encoding="utf-8") as f:
            assert _json.load(f)["status"] == "Todo"

        # 3. Classée simple -> DÉLÉGUER + Implementation
        server.effortless_task_classify(t_none, "simple")
        out3 = sl.step_autonomous_loop(tmpdir, "true")
        assert "DÉLÉGUER" in out3
        with open(os.path.join(tmpdir, ".effortless", "loop_state.json"), encoding="utf-8") as f:
            assert _json.load(f)["step"] == "Implementation"
        with open(os.path.join(tasks_dir, f"{t_none}.json"), encoding="utf-8") as f:
            assert _json.load(f)["status"] == "Doing"
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `pytest tests/test_services.py::test_loop_plan_delegation_branches -v`
Expected: FAIL (`assert "TRIAGE" in out` — la sortie actuelle est le message PLAN nominal).

- [ ] **Step 3: Insérer le branchement dans l'étape Plan**

Dans `src/mcp-server/effortless_mcp/services/session_loop.py`, repérer dans `if step == "Plan":` la ligne `next_task = eligible[0]` suivie du commentaire `# Activer la tâche`. Insérer le branchement ENTRE `next_task = eligible[0]` et `# Activer la tâche` :

```python
        next_task = eligible[0]

        # --- Délégation systématique : aiguillage selon la complexité ---
        complexity = next_task.get("complexity")
        if complexity is None:
            return (
                f"🔎 [TRIAGE] Tâche {next_task['id']} : {next_task['title']} — non classée.\n"
                "👉 Classe-la via effortless_task_classify(task_id, 'simple'|'complex'), "
                "puis relance effortless_loop_step. (Critère : 'simple' = mécanique, sans "
                "réflexion ; 'complex' = raisonnement/architecture/arbitrage.)"
            )
        if complexity == "complex":
            return (
                f"🧩 [DÉCOMPOSER] Tâche complexe {next_task['id']} : {next_task['title']}.\n"
                "👉 Découpe-la en sous-tâches SIMPLES via "
                "effortless_task_add(title, complexity='simple', depends_on=[...]), "
                f"puis marque {next_task['id']} 'Done' via effortless_task_update. "
                "Relance ensuite effortless_loop_step."
            )
        # complexity == "simple" : flux nominal d'exécution, délégation imposée.

        # Activer la tâche
```

Puis remplacer le `return` final de l'étape Plan (le message `📋 [PLAN] Tâche sélectionnée …`) par la version DÉLÉGUER :

```python
        return (
            f"📋 [DÉLÉGUER] Tâche simple sélectionnée : **{next_task['id']}** : {next_task['title']}\n"
            f"Statut de la boucle : **Implementation**\n"
            "👉 Consigne : délègue cette tâche à un sous-agent (outil Agent), avec un prompt "
            "fermé et borné ; récupère un résultat compact ; n'implémente PAS toi-même "
            "(garde la conclusion, pas les détails). Une fois fait, relance effortless_loop_step "
            "pour lancer la recette."
        )
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `pytest tests/test_services.py::test_loop_plan_delegation_branches -v`
Expected: PASS.

- [ ] **Step 5: Lancer toute la suite (non-régression boucle)**

Run: `pytest -q`
Expected: tous verts (dont `test_autonomous_loop_lifecycle` — sa tâche TSK-001 a `complexity=None`, donc il faut l'adapter : voir Step 6).

- [ ] **Step 6: Adapter le test de cycle existant**

`test_autonomous_loop_lifecycle` écrit une tâche brute sans `complexity` → la boucle renverra désormais TRIAGE au lieu de PLAN. Dans `src/mcp-server/tests/test_services.py`, dans ce test, ajouter `"complexity": "simple"` au dict `t1` de la tâche `TSK-001` :

```python
        t1 = {"id": "TSK-001", "status": "Todo", "title": "Implement auth", "phase": "E-execute", "complexity": "simple"}
```

Re-lancer : `pytest -q` → tous verts.

- [ ] **Step 7: Commit**

```bash
git add src/mcp-server/effortless_mcp/services/session_loop.py src/mcp-server/tests/test_services.py
git commit -m "feat: loop emits triage/decompose/delegate consignes by task complexity"
```

---

### Task 4: Doctrine de délégation dans `SKILL.md`

**Files:**
- Modify: `skills/effortless/SKILL.md` (ajout d'une section)

**Interfaces:** Aucune (documentation). Pas de test automatisé.

- [ ] **Step 1: Ajouter la section**

À la fin de `skills/effortless/SKILL.md`, ajouter :

```markdown
## ⚡ Délégation systématique

Effortless ne lance pas de sous-agents lui-même : c'est **toi**, l'agent
invocateur, qui délègues via ton outil d'agents.

Règle : **traite uniquement le complexe** (raisonnement, architecture,
arbitrages) et **délègue systématiquement le simple/mécanique** à un sous-agent
à contexte frais.

- Classe chaque tâche à sa création : `effortless_task_add(..., complexity="simple"|"complex")`.
  Une tâche déjà créée se classe via `effortless_task_classify(task_id, complexity)`.
- `simple` = mécanique, sans réflexion (édition ciblée, boilerplate, renommage,
  exécution de tests, génération de doc) → **délègue** à un sous-agent : prompt
  fermé et borné, résultat compact attendu. Garde la conclusion, pas les détails :
  l'output verbeux ne doit pas entrer dans ton contexte.
- `complex` = raisonnement/architecture/arbitrage → **décompose** en sous-tâches
  simples (puis délègue celles-ci), ou traite directement la partie qui exige
  vraiment ta réflexion.

Dans la boucle autonome (`effortless_loop_step`), ces consignes sont émises
automatiquement : `🔎 [TRIAGE]` (classe), `🧩 [DÉCOMPOSER]` (découpe), `📋
[DÉLÉGUER]` (délègue). Hors boucle (mode OPAL manuel), applique la même doctrine.
```

- [ ] **Step 2: Commit**

```bash
git add skills/effortless/SKILL.md
git commit -m "docs: add systematic delegation doctrine to the skill"
```

---

### Task 5: Badge complexité dans le dashboard

**Files:**
- Modify: `src/web-ui/src/App.jsx` (composant `TaskBoard`, carte `.task`)
- Modify: `src/web-ui/src/App.css` (style du badge)
- Build: `npm --prefix src/web-ui run build`

**Interfaces:**
- Consumes: champ `complexity` déjà présent dans les tâches renvoyées par `/api/overview` (aucun changement serveur — `build_project_overview` renvoie la tâche entière).

- [ ] **Step 1: Ajouter le badge sur la carte de tâche**

Dans `src/web-ui/src/App.jsx`, dans le composant `TaskBoard`, remplacer le bloc `<article className="task" …>` par :

```jsx
                <article className="task" key={t.id}>
                  <div className="task-row">
                    <span className="task-id">{t.id}</span>
                    <span className={`cx cx-${t.complexity || 'none'}`}>
                      {t.complexity === 'complex' ? 'complex' : t.complexity === 'simple' ? 'simple' : '?'}
                    </span>
                  </div>
                  <div className="task-title">{t.title}</div>
                  {t.depends_on?.length > 0 && (
                    <div className="muted small">dépend de : {t.depends_on.join(', ')}</div>
                  )}
                </article>
```

- [ ] **Step 2: Ajouter le style**

À la fin de `src/web-ui/src/App.css`, ajouter :

```css
.task-row { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.cx { font-size: 0.62rem; font-weight: 700; text-transform: uppercase; padding: 1px 6px; border-radius: 999px; border: 1px solid var(--border); }
.cx-simple { color: #6fe3b2; border-color: #2c6b51; }
.cx-complex { color: #ff9aa3; border-color: #7a3038; }
.cx-none { color: var(--text-dim); }
```

- [ ] **Step 3: Builder le dashboard**

Run: `npm --prefix src/web-ui run build`
Expected: `✓ built` sans erreur ; un nouveau `dist/assets/index-*.js` est produit.

- [ ] **Step 4: Commit**

```bash
git add src/web-ui/src/App.jsx src/web-ui/src/App.css
git commit -m "feat: show task complexity badge in dashboard"
```

---

## Self-Review (effectuée à l'écriture)

- **Couverture spec** : modèle+task_add (Task 1), classify (Task 2), boucle TRIAGE/DÉCOMPOSER/DÉLÉGUER (Task 3), doctrine SKILL.md (Task 4), badge Web UI (Task 5). Gestion d'erreur couverte par les validations des Tasks 1-2. Tous les composants §4 du spec ont une tâche.
- **Placeholders** : aucun ; tout le code est fourni.
- **Cohérence des types** : `complexity` est partout `Optional[str]` ∈ `{simple, complex, None}` ; `effortless_task_classify(task_id, complexity)` et `effortless_task_add(..., complexity=None)` cohérents entre Tasks 1, 2, 3 et les tests.
- **Non-régression** : Task 3 Step 6 adapte explicitement `test_autonomous_loop_lifecycle` (tâche legacy sans complexity).
