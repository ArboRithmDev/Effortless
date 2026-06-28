import os
import tempfile
import json
import pytest
from effortless_mcp.services.markdown import parse_markdown_frontmatter, write_markdown_frontmatter
from effortless_mcp.services.validation import validate_phase_documents, validate_document_structure, load_questions_from_path
from effortless_mcp.services.sync import sync_decisions_to_markdown, sync_questions_to_markdown
from effortless_mcp.services.secondbrain import sync_phase_to_secondbrain, create_secondbrain_archive, get_secondbrain_vault_path
from effortless_mcp.services.drift import check_project_drift, install_git_pre_commit_hook
from effortless_mcp.services.deploy import deploy_to_mcp_clients
from effortless_mcp.services.repo_analyzer import analyze_target_repo
from effortless_mcp.services.migration_planner import init_migration_project, apply_migration_project
from effortless_mcp.services.session_loop import init_autonomous_loop, step_autonomous_loop



def test_markdown_frontmatter():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "test.md")
        metadata = {"phase": "O-analyse", "statut": "Actif", "version": 1}
        content = "# Titre\nContenu de test."

        write_markdown_frontmatter(file_path, metadata, content)

        assert os.path.exists(file_path)

        parsed_metadata, parsed_content = parse_markdown_frontmatter(file_path)
        assert parsed_metadata == metadata
        assert "Contenu de test." in parsed_content

def test_validate_phase_documents():
    with tempfile.TemporaryDirectory() as tmpdir:
        current_phase_id = "O-analyse"
        required_documents = [
            "cadrage/00-test.md",
            "cadrage/01-bqo.md"
        ]

        cadrage_dir = os.path.join(tmpdir, "cadrage")
        os.makedirs(cadrage_dir)

        # 1. Manquant
        questions_path = os.path.join(tmpdir, "questions.json")
        with open(questions_path, "w") as f:
            json.dump([], f)

        is_valid, checklist, reasons = validate_phase_documents(
            tmpdir, current_phase_id, required_documents, questions_path
        )
        assert not is_valid
        assert len(reasons) == 2

        # 2. Présents mais incorrects (pas de frontmatter)
        doc1_path = os.path.join(cadrage_dir, "00-test.md")
        doc2_path = os.path.join(cadrage_dir, "01-bqo.md")
        with open(doc1_path, "w") as f:
            f.write("# Pas de frontmatter")
        with open(doc2_path, "w") as f:
            f.write("# Pas de frontmatter")

        is_valid, checklist, reasons = validate_phase_documents(
            tmpdir, current_phase_id, required_documents, questions_path
        )
        assert not is_valid

        # 3. Présents et corrects (mais BQO non résolu par son statut)
        write_markdown_frontmatter(doc1_path, {"phase": "O-analyse", "statut": "Actif"}, "# Test")
        write_markdown_frontmatter(doc2_path, {"phase": "O-analyse", "statut": "En attente"}, "## Tableau Récapitulatif\n## Détail des Questions\n")

        is_valid, checklist, reasons = validate_phase_documents(
            tmpdir, current_phase_id, required_documents, questions_path
        )
        assert not is_valid
        assert any("BQO non résolu" in r for r in reasons)

        # 4. Résolu
        write_markdown_frontmatter(doc2_path, {"phase": "O-analyse", "statut": "Résolu"}, "## Tableau Récapitulatif\n## Détail des Questions\n")
        is_valid, checklist, reasons = validate_phase_documents(
            tmpdir, current_phase_id, required_documents, questions_path
        )
        assert is_valid
        assert len(reasons) == 0

def test_validate_document_structure():
    # Test placeholders
    errors = validate_document_structure("/path/to/test.md", "00-test.md", "Contenu avec TODO à faire.")
    assert len(errors) == 1
    assert "TODO" in errors[0]

    # Test glossaire ignore placeholders
    errors = validate_document_structure("/path/to/glossaire.md", "00-FNC-GLO-glossaire.md", "Contenu avec TODO.")
    assert len(errors) == 0

    # Test sections manquantes pour BQO
    errors = validate_document_structure("/path/to/01-bqo.md", "01-bqo.md", "## Tableau Récapitulatif\n")
    assert len(errors) == 1
    assert "Détail des Questions" in errors[0]

def test_sync_services():
    with tempfile.TemporaryDirectory() as tmpdir:
        decisions_path = os.path.join(tmpdir, "decisions.md")
        decisions = [
            {
                "id": "DEC-01",
                "title": "Test stack",
                "status": "Accepted",
                "phase": "O-analyse",
                "date": "2026-06-28",
                "context": "Context test",
                "decision": "Decision test",
                "consequences": ["Cons 1"],
                "rejected_alternatives": ["Alt 1"]
            }
        ]

        sync_decisions_to_markdown(decisions_path, "O-analyse", decisions)
        assert os.path.exists(decisions_path)
        
        metadata, content = parse_markdown_frontmatter(decisions_path)
        assert metadata["phase"] == "O-analyse"
        assert "DEC-01" in content
        assert "Test stack" in content

        questions_path = os.path.join(tmpdir, "questions.md")
        questions = [
            {
                "id": "Q-01",
                "question": "Question ?",
                "status": "Resolved",
                "impact": "Blocker",
                "context": "Context",
                "suggestion": "Suggestion",
                "answer": "Answer",
                "date_resolved": "2026-06-28"
            }
        ]

        sync_questions_to_markdown(questions_path, "O-analyse", "Effortless", questions)
        assert os.path.exists(questions_path)
        
        metadata, content = parse_markdown_frontmatter(questions_path)
        assert metadata["phase"] == "O-analyse"
        assert metadata["statut"] == "Résolu"
        assert "Q-01" in content
        assert "Question ?" in content
        assert "Answer" in content

def test_sync_questions_with_null_answer():
    # Régression : une question fraîche a answer=None ; sync_questions_to_markdown
    # ne doit pas planter sur len(None).
    with tempfile.TemporaryDirectory() as tmpdir:
        questions_path = os.path.join(tmpdir, "bqo.md")
        questions = [
            {"id": "Q-01", "question": "Pourquoi ?", "status": "Pending",
             "impact": "Blocker", "context": "ctx", "suggestion": "s", "answer": None}
        ]
        sync_questions_to_markdown(questions_path, "O-analyse", "Proj", questions)
        assert os.path.exists(questions_path)
        _, content = parse_markdown_frontmatter(questions_path)
        assert "Q-01" in content


def test_load_questions_from_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Créer des questions individuelles
        q1 = {"id": "Q-01", "question": "Q1", "status": "Pending"}
        q2 = {"id": "Q-02", "question": "Q2", "status": "Resolved"}
        
        with open(os.path.join(tmpdir, "Q-01.json"), "w") as f:
            json.dump(q1, f)
        with open(os.path.join(tmpdir, "Q-02.json"), "w") as f:
            json.dump(q2, f)
            
        questions = load_questions_from_path(tmpdir)
        assert len(questions) == 2
        assert any(q["id"] == "Q-01" for q in questions)
        assert any(q["id"] == "Q-02" for q in questions)

def test_secondbrain_integration(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock de get_secondbrain_vault_path pour renvoyer le répertoire temporaire
        monkeypatch.setattr(
            "effortless_mcp.services.secondbrain.get_secondbrain_vault_path",
            lambda: tmpdir
        )
        
        # Initialiser l'arborescence SecondBrain factice
        project_dir = os.path.join(tmpdir, "10-episodes", "projects", "effortless")
        os.makedirs(os.path.join(project_dir, "archives"))
        
        # 1. Créer context.md factice
        context_path = os.path.join(project_dir, "context.md")
        write_markdown_frontmatter(
            context_path,
            {"project": "effortless", "phase": "O-analyse", "last-session": "2026-06-27"},
            "## 🚦 Current Phase\n- **O-analyse** : Analyse en cours.\n"
        )
        
        # 2. Créer history.md factice
        history_path = os.path.join(project_dir, "history.md")
        write_markdown_frontmatter(
            history_path,
            {"project": "effortless"},
            "# Effortless — Historique des sessions\n\n_(no sessions yet)\n"
        )
        
        # Tester sync_phase_to_secondbrain
        success = sync_phase_to_secondbrain("effortless", "E-execute")
        assert success
        
        metadata, content = parse_markdown_frontmatter(context_path)
        assert metadata["phase"] == "E-execute"
        assert "E-execute" in content
        
        # Tester create_secondbrain_archive
        archive_name = create_secondbrain_archive("effortless", "Test subject", "# Content test")
        assert archive_name is not None
        assert os.path.exists(os.path.join(project_dir, "archives", archive_name))
        
        # Vérifier que history.md a été mis à jour
        _, hist_content = parse_markdown_frontmatter(history_path)
        assert "Test subject" in hist_content
        assert archive_name in hist_content

def test_drift_check_logic(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks_dir = os.path.join(tmpdir, "tasks")
        os.makedirs(tasks_dir)
        
        # 1. Pas de modifs, pas de tâches active -> pas de drift
        monkeypatch.setattr("effortless_mcp.services.drift.get_modified_git_files", lambda root: [])
        is_drifting, mod_files, active = check_project_drift(tmpdir, tasks_dir)
        assert not is_drifting
        assert len(mod_files) == 0
        
        # 2. Des modifs hors de src/ -> pas de drift
        monkeypatch.setattr("effortless_mcp.services.drift.get_modified_git_files", lambda root: ["README.md", "cadrage/test.md"])
        is_drifting, mod_files, active = check_project_drift(tmpdir, tasks_dir)
        assert not is_drifting
        
        # 3. Des modifs dans src/ mais 0 tâche active -> DRIFT !
        monkeypatch.setattr("effortless_mcp.services.drift.get_modified_git_files", lambda root: ["src/cli/main.py"])
        is_drifting, mod_files, active = check_project_drift(tmpdir, tasks_dir)
        assert is_drifting
        assert len(mod_files) == 1
        
        # 4. Des modifs dans src/ et 1 tâche active ("Doing") -> pas de drift
        t1 = {"id": "TSK-001", "status": "Doing", "title": "Active task"}
        with open(os.path.join(tasks_dir, "TSK-001.json"), "w") as f:
            json.dump(t1, f)
            
        is_drifting, mod_files, active = check_project_drift(tmpdir, tasks_dir)
        assert not is_drifting
        assert len(active) == 1

def test_deploy_to_mcp_clients(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock de os.path.expanduser pour rediriger vers notre tmpdir
        def mock_expanduser(path):
            clean_path = path.replace("~/", "")
            return os.path.join(tmpdir, clean_path)
            
        monkeypatch.setattr("os.path.expanduser", mock_expanduser)
        
        # Créer le répertoire .gemini/config, .claude, .codex, .vibe, et .copilot factices
        os.makedirs(os.path.join(tmpdir, ".gemini", "config"))
        os.makedirs(os.path.join(tmpdir, ".claude"))
        os.makedirs(os.path.join(tmpdir, ".codex"))
        os.makedirs(os.path.join(tmpdir, ".vibe"))
        os.makedirs(os.path.join(tmpdir, ".copilot"))
        
        # Créer un fichier de skill source factice dans le projet temporaire
        source_skill_dir = os.path.join(tmpdir, "skills", "effortless")
        os.makedirs(source_skill_dir)
        with open(os.path.join(source_skill_dir, "SKILL.md"), "w") as f:
            f.write("# Skill content")
            
        # Exécuter le déploiement
        results = deploy_to_mcp_clients(tmpdir)
        
        assert len(results) > 0
        # Vérifier que les fichiers ont été copiés/écrits sur tous les clients détectés
        assert any(r["name"] == "Antigravity CLI" and r["status"] == "success" for r in results)
        assert any(r["name"] == "Claude Code" and r["status"] == "success" for r in results)
        assert any(r["name"] == "Codex" and r["status"] == "success" for r in results)
        assert any(r["name"] == "Mistral Vibe" and r["status"] == "success" for r in results)
        assert any(r["name"] == "GitHub Copilot" and r["status"] == "success" for r in results)

        # Le serveur MCP doit être DÉCLARÉ (pas seulement le Skill copié) sur les
        # clients JSON. La commande pointe le binaire de l'INSTALLATION Effortless. Aucun
        # pin EFFORTLESS_PROJECT_ROOT n'est déployé : le serveur suit le cwd (projet courant).

        # Claude Code -> ~/.claude.json
        with open(os.path.join(tmpdir, ".claude.json"), encoding="utf-8") as f:
            cc = json.load(f)
        entry = cc["mcpServers"]["effortless"]
        assert entry["command"].endswith(os.path.join(".venv", "bin", "effortless-mcp"))
        assert "EFFORTLESS_PROJECT_ROOT" not in entry.get("env", {})

        # GitHub Copilot -> ~/.copilot/mcp-config.json
        with open(os.path.join(tmpdir, ".copilot", "mcp-config.json"), encoding="utf-8") as f:
            cop = json.load(f)
        assert "EFFORTLESS_PROJECT_ROOT" not in cop["mcpServers"]["effortless"].get("env", {})

        # Antigravity (Gemini) -> ~/.gemini/settings.json
        with open(os.path.join(tmpdir, ".gemini", "settings.json"), encoding="utf-8") as f:
            gem = json.load(f)
        assert "EFFORTLESS_PROJECT_ROOT" not in gem["mcpServers"]["effortless"].get("env", {})

        # Codex / Vibe -> bloc TOML idempotent, sans pin de projet
        with open(os.path.join(tmpdir, ".codex", "config.toml"), encoding="utf-8") as f:
            codex_toml = f.read()
        assert "[mcp_servers.effortless]" in codex_toml
        assert "EFFORTLESS_PROJECT_ROOT" not in codex_toml

        with open(os.path.join(tmpdir, ".vibe", "config.toml"), encoding="utf-8") as f:
            vibe_toml = f.read()
        assert "EFFORTLESS_PROJECT_ROOT" not in vibe_toml

        # Idempotence : un second déploiement ne duplique pas l'entrée.
        deploy_to_mcp_clients(tmpdir)
        with open(os.path.join(tmpdir, ".codex", "config.toml"), encoding="utf-8") as f:
            assert f.read().count("[mcp_servers.effortless]") == 1
        with open(os.path.join(tmpdir, ".claude.json"), encoding="utf-8") as f:
            assert len(json.load(f)["mcpServers"]) == 1


def test_next_sequential_id_is_max_plus_one():
    from effortless_mcp.server import next_sequential_id
    # max+1, pas count+1 : robuste aux suppressions.
    assert next_sequential_id([], "DEC-") == "DEC-01"
    assert next_sequential_id(["DEC-01", "DEC-02", "DEC-03"], "DEC-") == "DEC-04"
    # DEC-02 supprimé : on ne réutilise pas DEC-03, on prend max+1 = DEC-04.
    assert next_sequential_id(["DEC-01", "DEC-03"], "DEC-") == "DEC-04"
    # Préfixe composite TSK : seuls les IDs du préfixe comptent.
    ids = ["TSK-Phase-003-E-01", "TSK-Phase-003-E-07", "TSK-Phase-003-L-02"]
    assert next_sequential_id(ids, "TSK-Phase-003-E-") == "TSK-Phase-003-E-08"


def test_markdown_parse_without_trailing_newline():
    # Régression B3 : un fichier frontmatter-only (pas de \n après le --- final) ne doit
    # pas perdre son frontmatter.
    with tempfile.TemporaryDirectory() as tmpdir:
        p = os.path.join(tmpdir, "fm.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("---\nphase: O-analyse\nstatut: Actif\n---")
        meta, body = parse_markdown_frontmatter(p)
        assert meta == {"phase": "O-analyse", "statut": "Actif"}
        assert body == ""


def test_write_frontmatter_preserves_leading_horizontal_rule():
    # Régression B4 : un corps commençant par une règle horizontale --- ne doit pas être tronqué.
    with tempfile.TemporaryDirectory() as tmpdir:
        p = os.path.join(tmpdir, "doc.md")
        body = "---\nSection visuelle\n---\nVrai contenu"
        write_markdown_frontmatter(p, {"phase": "X"}, body)
        meta, parsed = parse_markdown_frontmatter(p)
        assert meta == {"phase": "X"}
        assert "Vrai contenu" in parsed
        assert "Section visuelle" in parsed


def test_task_update_returns_confirmation(monkeypatch):
    # Régression : effortless_task_update doit renvoyer une confirmation, pas None.
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        tasks_dir = os.path.join(tmpdir, ".effortless", "tasks")
        os.makedirs(tasks_dir)
        with open(os.path.join(tasks_dir, "TSK-001.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "TSK-001", "status": "Todo", "title": "T", "phase": "E-execute"}, f)

        result = server.effortless_task_update("TSK-001", "Doing")
        assert result is not None
        assert "TSK-001" in result
        assert "Doing" in result

        # La sauvegarde individuelle doit refléter le nouveau statut.
        with open(os.path.join(tasks_dir, "TSK-001.json"), encoding="utf-8") as f:
            assert json.load(f)["status"] == "Doing"


def test_repo_analyzer_and_migration_planner(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Créer des fichiers simulant un dépôt existant
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write("[tool.poetry]\nname = 'test-project'\n")
        with open(os.path.join(tmpdir, "README.md"), "w") as f:
            f.write("# Test Project\n")
        with open(os.path.join(tmpdir, "old_doc.md"), "w") as f:
            f.write("# Old documentation\n")
        
        src_dir = os.path.join(tmpdir, "my_source_folder")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "app.py"), "w") as f:
            f.write("print('hello')\n")
            
        # Tester l'analyseur
        analysis = analyze_target_repo(tmpdir)
        assert "Python" in analysis["stack"]
        assert len(analysis["proposed_relocations"]) > 0
        
        # Tester l'initialisation
        report = init_migration_project(tmpdir, analysis)
        assert "initialisé" in report
        assert os.path.exists(os.path.join(tmpdir, "effortless.json"))
        assert os.path.exists(os.path.join(tmpdir, ".effortless", "tasks", "TSK-M-01.json"))
        
        # Tester l'application de la migration
        apply_report = apply_migration_project(tmpdir)
        assert "Migration appliquée" in apply_report
        assert os.path.exists(os.path.join(tmpdir, "cadrage", "Phase-001", "01-MIG-old_doc.md"))
        assert os.path.exists(os.path.join(tmpdir, "src", "my_source_folder", "app.py"))

def test_autonomous_loop_lifecycle(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock de get_project_root pour pointer sur tmpdir
        monkeypatch.setattr("effortless_mcp.server.save_entity", lambda d, i, e: None)
        
        # 1. Initialisation
        init_report = init_autonomous_loop(tmpdir, "Complete tests")
        assert "initialisée" in init_report
        
        # Initialiser le dossier de tâches
        tasks_dir = os.path.join(tmpdir, ".effortless", "tasks")
        os.makedirs(tasks_dir)
        
        # Écrire une tâche Todo
        t1 = {"id": "TSK-001", "status": "Todo", "title": "Implement auth", "phase": "E-execute"}
        with open(os.path.join(tasks_dir, "TSK-001.json"), "w") as f:
            json.dump(t1, f)
            
        # Étape 1 : Plan
        step_report = step_autonomous_loop(tmpdir, "true")
        assert "PLAN" in step_report
        
        # Étape 2 : Lancer la boucle en Implementation
        # (doit passer à Recette et exécuter les tests)
        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: type("Res", (), {"returncode": 0, "stdout": "All tests passed", "stderr": ""})())
        monkeypatch.setattr("effortless_mcp.services.drift.get_modified_git_files", lambda root: [])
        
        step_report_2 = step_autonomous_loop(tmpdir, "true")
        assert "LIVRAISON" in step_report_2





