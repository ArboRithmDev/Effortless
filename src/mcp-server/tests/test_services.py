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

        # 3. Présents et corrects. Gate impact-aware (L-04) : un BQO « En attente »
        #    SANS question Blocker ouverte ne bloque PLUS la transition. Le document
        #    reste signalé (⚠️ non valide) mais l'éligibilité de phase reste verte.
        write_markdown_frontmatter(doc1_path, {"phase": "O-analyse", "statut": "Actif"}, "# Test")
        write_markdown_frontmatter(doc2_path, {"phase": "O-analyse", "statut": "En attente"}, "## Summary Table\n## Question Details\n")

        is_valid, checklist, reasons = validate_phase_documents(
            tmpdir, current_phase_id, required_documents, questions_path
        )
        assert is_valid
        assert len(reasons) == 0
        # Le BQO non clôturé est tout de même remonté comme avertissement non bloquant.
        bqo_item = next(c for c in checklist if c["document_path"].endswith("01-bqo.md"))
        assert not bqo_item["is_valid"]
        assert any("not resolved" in e for e in bqo_item["errors"])

        # 3b. Une question d'impact Blocker NON résolue de la phase bloque la transition.
        with open(questions_path, "w", encoding="utf-8") as f:
            json.dump([
                {"id": "Q-01", "question": "Choix moteur ?", "phase": "O-analyse",
                 "impact": "Blocker", "status": "Pending"}
            ], f)
        is_valid, checklist, reasons = validate_phase_documents(
            tmpdir, current_phase_id, required_documents, questions_path
        )
        assert not is_valid
        assert any("Unresolved blocking question" in r and "Q-01" in r for r in reasons)

        # 3c. Une question d'impact faible (Structuring) ouverte ne bloque PAS.
        with open(questions_path, "w", encoding="utf-8") as f:
            json.dump([
                {"id": "Q-02", "question": "Renommer le module ?", "phase": "O-analyse",
                 "impact": "Structuring", "status": "Pending"}
            ], f)
        is_valid, checklist, reasons = validate_phase_documents(
            tmpdir, current_phase_id, required_documents, questions_path
        )
        assert is_valid
        assert len(reasons) == 0

        # 4. BQO clôturé (statut Résolu) + aucune question bloquante → vert et sans warning.
        with open(questions_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        write_markdown_frontmatter(doc2_path, {"phase": "O-analyse", "statut": "Résolu"}, "## Summary Table\n## Question Details\n")
        is_valid, checklist, reasons = validate_phase_documents(
            tmpdir, current_phase_id, required_documents, questions_path
        )
        assert is_valid
        assert len(reasons) == 0
        bqo_item = next(c for c in checklist if c["document_path"].endswith("01-bqo.md"))
        assert bqo_item["is_valid"]

def test_validate_document_structure():
    # Test placeholders
    errors = validate_document_structure("/path/to/test.md", "00-test.md", "Contenu avec TODO à faire.")
    assert len(errors) == 1
    assert "TODO" in errors[0]

    # Test glossaire ignore placeholders
    errors = validate_document_structure("/path/to/glossaire.md", "00-FNC-GLO-glossaire.md", "Contenu avec TODO.")
    assert len(errors) == 0

    # Régression : le statut de tâche légitime `Todo` (casse différente) ne doit PAS être
    # pris pour la sentinelle majuscule TODO (détection mot-clé sensible à la casse).
    errors = validate_document_structure("/path/to/doc.md", "06-api.md", "Move a task across `Todo`, `Doing`, `Done`.")
    assert errors == []
    # Mais la sentinelle en majuscules reste détectée.
    errors = validate_document_structure("/path/to/doc.md", "06-api.md", "Section TODO non remplie.")
    assert len(errors) == 1 and "TODO" in errors[0]

    # Test sections manquantes pour BQO
    errors = validate_document_structure("/path/to/01-bqo.md", "01-bqo.md", "## Summary Table\n")
    assert len(errors) == 1
    assert "Question Details" in errors[0]

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
        assert metadata["statut"] == "Resolved"
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


def test_generated_docs_pass_structure_validator():
    # Régression : le générateur émet des en-têtes décorés (## 📋 Summary Table) ;
    # le validateur doit les reconnaître, sinon il bloque à tort tout BQO / registre de décisions.
    with tempfile.TemporaryDirectory() as tmpdir:
        bqo = os.path.join(tmpdir, "02-BQO-questions.md")
        sync_questions_to_markdown(bqo, "O-analyse", "Proj", [
            {"id": "Q-01", "question": "Quand purger Qt ?", "status": "Pending",
             "impact": "Blocker", "context": "c", "suggestion": "s", "answer": None}
        ])
        _, bqo_body = parse_markdown_frontmatter(bqo)
        errs = validate_document_structure(bqo, "02-BQO-questions.md", bqo_body)
        assert not any("manquante" in e for e in errs), errs

        dec = os.path.join(tmpdir, "03-MET-DEC-registre-decisions.md")
        sync_decisions_to_markdown(dec, "O-analyse", [
            {"id": "DEC-01", "title": "X", "status": "Accepted", "phase": "O-analyse",
             "date": "2026-06-28", "context": "c", "decision": "d",
             "consequences": ["a"], "rejected_alternatives": []}
        ])
        _, dec_body = parse_markdown_frontmatter(dec)
        errs2 = validate_document_structure(dec, "03-MET-DEC-registre-decisions.md", dec_body)
        assert not any("manquante" in e for e in errs2), errs2


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
        
        # 1. Créer context.md factice — `phase` porte un résumé Memory Kit (une ligne)
        # que la symbiose ne doit PAS écraser.
        context_path = os.path.join(project_dir, "context.md")
        mk_phase_summary = "Cadrage du moteur de purge"
        original_body = "## 🚦 Current Phase\n- Résumé Memory Kit à préserver.\n"
        write_markdown_frontmatter(
            context_path,
            {"project": "effortless", "phase": mk_phase_summary, "last-session": "2026-06-27"},
            original_body
        )

        # 2. Créer history.md factice
        history_path = os.path.join(project_dir, "history.md")
        write_markdown_frontmatter(
            history_path,
            {"project": "effortless"},
            "# Effortless — Historique des sessions\n\n_(no sessions yet)\n"
        )

        # Tester sync_phase_to_secondbrain : NON-DESTRUCTIF.
        success = sync_phase_to_secondbrain("effortless", "E-execute")
        assert success

        metadata, content = parse_markdown_frontmatter(context_path)
        # Champs Memory Kit préservés
        assert metadata["phase"] == mk_phase_summary
        assert metadata["last-session"] == "2026-06-27"
        # Effortless écrit ses champs namespacés
        assert metadata["effortless_phase"] == "E-execute"
        assert "effortless_last_sync" in metadata
        # Le corps n'est pas réécrit
        assert "Résumé Memory Kit à préserver." in content
        
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
        expected_bin = (
            os.path.join(".venv", "Scripts", "effortless-mcp.exe")
            if os.name == "nt"
            else os.path.join(".venv", "bin", "effortless-mcp")
        )
        assert entry["command"].endswith(expected_bin)
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
        
        # dry-run par défaut : APERÇU non destructif, rien n'est écrit.
        preview = init_migration_project(tmpdir, analysis)
        assert "PREVIEW" in preview
        assert not os.path.exists(os.path.join(tmpdir, "effortless.json"))
        assert not os.path.exists(os.path.join(tmpdir, ".effortless"))

        # Initialisation réelle (confirm) : scaffolde la config et les tâches.
        report = init_migration_project(tmpdir, analysis, dry_run=False)
        assert "initialised" in report
        assert os.path.exists(os.path.join(tmpdir, "effortless.json"))
        assert os.path.exists(os.path.join(tmpdir, ".effortless", "epics", "EPIC-MIGRATION", "stories", "STO-MIGRATION-01", "tasks", "TSK-M-01.json"))

        # Tester l'application de la migration
        apply_report = apply_migration_project(tmpdir)
        assert "Migration applied" in apply_report
        # Hiérarchie préservée : le doc racine atterrit sous migrated-docs/ (plus d'aplatissement 01-MIG-).
        assert os.path.exists(os.path.join(tmpdir, "cadrage", "Phase-001", "migrated-docs", "old_doc.md"))
        assert os.path.exists(os.path.join(tmpdir, "src", "my_source_folder", "app.py"))


def test_migrate_init_guardrail_and_dry_run(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write("[tool.poetry]\nname = 'p'\n")
        analysis = analyze_target_repo(tmpdir)

        # 1. dry-run (défaut) n'écrit rien.
        out = init_migration_project(tmpdir, analysis)
        assert "PREVIEW" in out
        assert not os.path.exists(os.path.join(tmpdir, "effortless.json"))

        # 2. init réel.
        init_migration_project(tmpdir, analysis, dry_run=False)
        cfg_path = os.path.join(tmpdir, "effortless.json")
        assert os.path.exists(cfg_path)
        # Marqueur pour détecter un éventuel overwrite non sollicité.
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg_before = f.read()

        # 3. Garde-fou : ré-init sans force est REFUSÉE et n'écrase rien.
        refused = init_migration_project(tmpdir, analysis, dry_run=False)
        assert "already initialised" in refused
        with open(cfg_path, "r", encoding="utf-8") as f:
            assert f.read() == cfg_before  # config intacte

        # 4. force=True : ré-init autorisée + sauvegarde .bak de l'existant.
        forced = init_migration_project(tmpdir, analysis, dry_run=False, force=True)
        assert "initialised" in forced
        assert os.path.exists(cfg_path + ".bak")
        assert os.path.exists(os.path.join(tmpdir, ".effortless.bak"))


def test_migrate_preserves_doc_hierarchy_and_apply_dry_run(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write("[tool.poetry]\nname = 'p'\n")
        # Deux docs homonymes dans des sous-dossiers distincts : l'aplatissement les écrasait.
        os.makedirs(os.path.join(tmpdir, "docs", "api"))
        os.makedirs(os.path.join(tmpdir, "docs", "guide"))
        with open(os.path.join(tmpdir, "docs", "api", "index.md"), "w") as f:
            f.write("# API\n")
        with open(os.path.join(tmpdir, "docs", "guide", "index.md"), "w") as f:
            f.write("# Guide\n")

        analysis = analyze_target_repo(tmpdir)
        targets = [r["target"] for r in analysis["proposed_relocations"]]
        # Hiérarchie préservée + pas de collision de basename.
        assert "cadrage/Phase-001/migrated-docs/docs/api/index.md" in targets
        assert "cadrage/Phase-001/migrated-docs/docs/guide/index.md" in targets
        assert len(targets) == len(set(targets))

        init_migration_project(tmpdir, analysis, dry_run=False)

        # apply en dry-run : aucun déplacement, aucun rapport écrit.
        preview = apply_migration_project(tmpdir, dry_run=True)
        assert "dry-run" in preview
        assert os.path.exists(os.path.join(tmpdir, "docs", "api", "index.md"))  # source non déplacée
        assert not os.path.exists(os.path.join(tmpdir, "migration_report.md"))  # pas d'effet de bord

def test_autonomous_loop_lifecycle(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock de get_project_root pour pointer sur tmpdir
        monkeypatch.setattr("effortless_mcp.server.save_entity", lambda d, i, e: None)

        # 1. Initialisation
        init_report = init_autonomous_loop(tmpdir, "Complete tests")
        assert "initialized" in init_report

        # Initialiser le dossier de tâches
        tasks_dir = os.path.join(tmpdir, ".effortless", "tasks")
        os.makedirs(tasks_dir)

        # Écrire une tâche Todo
        t1 = {"id": "TSK-001", "status": "Todo", "title": "Implement auth", "phase": "E-execute", "complexity": "simple"}
        with open(os.path.join(tasks_dir, "TSK-001.json"), "w") as f:
            json.dump(t1, f)

        # Étape 1 : Plan
        step_report = step_autonomous_loop(tmpdir, "true")
        assert "DELEGATE" in step_report

        # Étape 2 : Lancer la boucle en Implementation
        # (doit passer à Recette et exécuter les tests)
        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: type("Res", (), {"returncode": 0, "stdout": "All tests passed", "stderr": ""})())
        monkeypatch.setattr("effortless_mcp.services.drift.get_modified_git_files", lambda root: [])

        step_report_2 = step_autonomous_loop(tmpdir, "true")
        assert "DELIVERY" in step_report_2


def test_task_add_stores_and_validates_complexity(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        tasks_dir = os.path.join(tmpdir, ".effortless", "epics", "EPIC-PROJET", "stories", "STO-PROJET-01", "tasks")

        # complexity valide stockée
        msg = server.effortless_task_add("T simple", complexity="simple")
        tsk_id = msg.split("Task ")[1].split(" ")[0]
        with open(os.path.join(tasks_dir, f"{tsk_id}.json"), encoding="utf-8") as f:
            assert json.load(f)["complexity"] == "simple"

        # absente => None
        msg2 = server.effortless_task_add("T sans")
        tsk_id2 = msg2.split("Task ")[1].split(" ")[0]
        with open(os.path.join(tasks_dir, f"{tsk_id2}.json"), encoding="utf-8") as f:
            assert json.load(f)["complexity"] is None

        # valeur invalide rejetée, pas d'écriture
        before = len(os.listdir(tasks_dir))
        bad = server.effortless_task_add("T bad", complexity="trivial")
        assert "invalid" in bad
        after = len(os.listdir(tasks_dir))
        assert before == after


def test_task_classify(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        tasks_dir = os.path.join(tmpdir, ".effortless", "epics", "EPIC-PROJET", "stories", "STO-PROJET-01", "tasks")
        msg = server.effortless_task_add("T")
        tsk_id = msg.split("Task ")[1].split(" ")[0]

        # classification réussie
        ok = server.effortless_task_classify(tsk_id, "complex")
        assert tsk_id in ok and "complex" in ok
        with open(os.path.join(tasks_dir, f"{tsk_id}.json"), encoding="utf-8") as f:
            assert json.load(f)["complexity"] == "complex"

        # valeur invalide
        assert "invalid" in server.effortless_task_classify(tsk_id, "trivial")
        # ID inconnu
        assert "not found" in server.effortless_task_classify("TSK-X-99", "simple")


def test_loop_plan_delegation_branches(monkeypatch):
    from effortless_mcp import server
    from effortless_mcp.services import session_loop as sl
    import json as _json
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        tasks_dir = os.path.join(tmpdir, ".effortless", "epics", "EPIC-PROJET", "stories", "STO-PROJET-01", "tasks")

        def add(title, complexity=None):
            msg = server.effortless_task_add(title, complexity=complexity)
            return msg.split("Task ")[1].split(" ")[0]

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
        assert "DECOMPOSE" in out2
        with open(os.path.join(tasks_dir, f"{t_none}.json"), encoding="utf-8") as f:
            assert _json.load(f)["status"] == "Todo"

        # 3. Classée simple -> DÉLÉGUER + Implementation
        server.effortless_task_classify(t_none, "simple")
        out3 = sl.step_autonomous_loop(tmpdir, "true")
        assert "DELEGATE" in out3
        with open(os.path.join(tmpdir, ".effortless", "loop_state.json"), encoding="utf-8") as f:
            assert _json.load(f)["step"] == "Implementation"
        with open(os.path.join(tasks_dir, f"{t_none}.json"), encoding="utf-8") as f:
            assert _json.load(f)["status"] == "Doing"


def test_epic_model_defaults():
    from effortless_mcp.models.epic import Epic
    epic = Epic(id="EPIC-CORE", title="Core")
    assert epic.zone is None
    assert epic.status == "Open"


def test_story_model_defaults():
    from effortless_mcp.models.story import Story
    story = Story(id="STO-1", epic_id="EPIC-CORE", title="x")
    assert story.opale_phase == "O-analyse"
    assert story.status == "Todo"
    assert story.depends_on == []


def test_task_model_has_story_id():
    from effortless_mcp.models.task import Task
    task = Task(id="T1", title="x", phase="L-plan")
    assert task.story_id is None


def test_epic_story_round_trip_persistence(tmp_path):
    from effortless_mcp.server import save_entity, load_entities
    from effortless_mcp.models.epic import Epic
    from effortless_mcp.models.story import Story

    epics_dir = os.path.join(str(tmp_path), "epics")
    stories_dir = os.path.join(str(tmp_path), "stories")

    epic = Epic(id="EPIC-CORE", title="Core")
    story = Story(id="STO-1", epic_id="EPIC-CORE", title="x")

    save_entity(epics_dir, epic.id, epic.model_dump())
    save_entity(stories_dir, story.id, story.model_dump())

    loaded_epics = load_entities(epics_dir)
    loaded_stories = load_entities(stories_dir)

    assert any(e["id"] == "EPIC-CORE" for e in loaded_epics)
    assert any(s["id"] == "STO-1" for s in loaded_stories)


def test_get_paths_exposes_epics_and_stories(tmp_path):
    from effortless_mcp.server import get_paths
    paths = get_paths(str(tmp_path))
    assert "epics" in paths
    assert "stories" in paths
    assert paths["epics"].endswith("epics")
    assert paths["stories"].endswith("stories")


def test_new_epic_id():
    from effortless_mcp.server import new_epic_id
    assert new_epic_id("core") == "EPIC-CORE"


def test_get_story_paths_nested_layout(tmp_path):
    from effortless_mcp.server import get_story_paths
    root = str(tmp_path)
    paths = get_story_paths(root, "EPIC-CORE", "STO-CORE-01")
    expected_tasks = os.path.join(
        ".effortless", "epics", "EPIC-CORE", "stories", "STO-CORE-01", "tasks"
    )
    assert paths["tasks"].endswith(expected_tasks)
    assert paths["story"].endswith("story.json")


def test_new_story_id_sequence_per_epic(tmp_path):
    from effortless_mcp.server import new_story_id
    root = str(tmp_path)
    os.makedirs(
        os.path.join(root, ".effortless", "epics", "EPIC-CORE", "stories", "STO-CORE-01"),
        exist_ok=True,
    )
    assert new_story_id(root, "EPIC-CORE", "CORE") == "STO-CORE-02"


def test_get_active_story_nested(tmp_path):
    from effortless_mcp.server import get_active_story
    root = str(tmp_path)
    eff_dir = os.path.join(root, ".effortless")
    story_dir = os.path.join(eff_dir, "epics", "EPIC-CORE", "stories", "STO-CORE-01")
    os.makedirs(story_dir, exist_ok=True)

    with open(os.path.join(eff_dir, "state.json"), "w", encoding="utf-8") as f:
        json.dump({
            "project_name": "x",
            "current_phase": "L-plan",
            "active_epic_id": "EPIC-CORE",
            "active_story_id": "STO-CORE-01",
            "started_at": "t",
            "completed_phases": [],
        }, f)
    with open(os.path.join(story_dir, "story.json"), "w", encoding="utf-8") as f:
        json.dump({
            "id": "STO-CORE-01",
            "epic_id": "EPIC-CORE",
            "title": "x",
            "opale_phase": "A-specs",
        }, f)

    assert get_active_story(root)["opale_phase"] == "A-specs"

    # Sans pointeurs actifs -> None.
    other_root = os.path.join(root, "no-active")
    other_eff = os.path.join(other_root, ".effortless")
    os.makedirs(other_eff, exist_ok=True)
    with open(os.path.join(other_eff, "state.json"), "w", encoding="utf-8") as f:
        json.dump({
            "project_name": "x",
            "current_phase": "L-plan",
            "started_at": "t",
            "completed_phases": [],
        }, f)
    assert get_active_story(other_root) is None


def test_story_scoped_required_docs(tmp_path):
    # Finding dogfood : la barrière de phase doit valider les documents de la
    # Story ACTIVE, pas ceux pinés sur la première Story par effortless.json.
    from effortless_mcp.server import story_scoped_required_docs
    root = str(tmp_path)
    eff_dir = os.path.join(root, ".effortless")
    story_dir = os.path.join(eff_dir, "epics", "EPIC-TRACKER", "stories", "STO-TRACKER-01")
    os.makedirs(story_dir, exist_ok=True)
    with open(os.path.join(eff_dir, "state.json"), "w", encoding="utf-8") as f:
        json.dump({
            "project_name": "x", "current_phase": "O-analyse",
            "active_epic_id": "EPIC-TRACKER", "active_story_id": "STO-TRACKER-01",
            "started_at": "t", "completed_phases": [],
        }, f)
    with open(os.path.join(story_dir, "story.json"), "w", encoding="utf-8") as f:
        json.dump({
            "id": "STO-TRACKER-01", "epic_id": "EPIC-TRACKER",
            "title": "x", "opale_phase": "O-analyse",
        }, f)

    # Le workflow déclare des chemins pinés sur une AUTRE Story (la première).
    phase_cfg = {"id": "O-analyse", "required_documents": [
        "cadrage/EPIC-PROJET/STO-PROJET-01/00-FNC-GLO-glossaire.md",
        "cadrage/EPIC-PROJET/STO-PROJET-01/02-BQO-questions.md",
    ]}
    # Rebasculés sur la Story active, basename conservé.
    assert story_scoped_required_docs(root, phase_cfg) == [
        os.path.join("cadrage", "EPIC-TRACKER", "STO-TRACKER-01", "00-FNC-GLO-glossaire.md"),
        os.path.join("cadrage", "EPIC-TRACKER", "STO-TRACKER-01", "02-BQO-questions.md"),
    ]

    # Sans Story active -> chemins du workflow inchangés (compat legacy plat).
    other_root = os.path.join(root, "no-active")
    os.makedirs(os.path.join(other_root, ".effortless"), exist_ok=True)
    with open(os.path.join(other_root, ".effortless", "state.json"), "w", encoding="utf-8") as f:
        json.dump({"project_name": "x", "current_phase": "O-analyse",
                   "started_at": "t", "completed_phases": []}, f)
    assert story_scoped_required_docs(other_root, phase_cfg) == phase_cfg["required_documents"]

    # phase_cfg absente -> liste vide.
    assert story_scoped_required_docs(root, None) == []


def test_migrate_state_to_fractal_scaffold():
    from effortless_mcp.services.state_migrator import migrate_state_to_fractal

    with tempfile.TemporaryDirectory() as tmpdir:
        eff_dir = os.path.join(tmpdir, ".effortless")
        os.makedirs(eff_dir)
        state_path = os.path.join(eff_dir, "state.json")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({
                "project_name": "effortless",
                "current_phase": "L-plan",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_phases": [],
            }, f)

        epic_path = os.path.join(eff_dir, "epics", "EPIC-PROJET", "epic.json")
        story_path = os.path.join(
            eff_dir, "epics", "EPIC-PROJET", "stories", "STO-PROJET-01", "story.json"
        )

        # 1. Dry-run (défaut) : aperçu non destructif, rien n'est écrit.
        preview = migrate_state_to_fractal(tmpdir)
        assert "PREVIEW" in preview
        assert not os.path.exists(epic_path)
        assert not os.path.exists(story_path)

        # 2. Réel : scaffolde Epic + Story et positionne les pointeurs.
        report = migrate_state_to_fractal(tmpdir, dry_run=False)
        assert "EPIC-PROJET" in report and "STO-PROJET-01" in report
        assert os.path.exists(epic_path)
        assert os.path.exists(story_path)

        with open(story_path, encoding="utf-8") as f:
            story = json.load(f)
        assert story["opale_phase"] == "L-plan"

        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
        assert state["active_epic_id"] == "EPIC-PROJET"
        assert state["active_story_id"] == "STO-PROJET-01"
        assert state["current_phase"] == "L-plan"  # conservé (fallback transitoire)

        # 3. Idempotence : un second passage réel ne plante pas et ne réécrit rien.
        again = migrate_state_to_fractal(tmpdir, dry_run=False)
        assert "Already migrated" in again


def test_migrate_state_moves_registries():
    from effortless_mcp.services.state_migrator import migrate_state_to_fractal

    with tempfile.TemporaryDirectory() as tmpdir:
        eff_dir = os.path.join(tmpdir, ".effortless")
        tasks_dir = os.path.join(eff_dir, "tasks")
        decisions_dir = os.path.join(eff_dir, "decisions")
        questions_dir = os.path.join(eff_dir, "questions")
        os.makedirs(tasks_dir)
        os.makedirs(decisions_dir)
        os.makedirs(questions_dir)

        with open(os.path.join(eff_dir, "state.json"), "w", encoding="utf-8") as f:
            json.dump({
                "project_name": "effortless",
                "current_phase": "L-plan",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_phases": [],
            }, f)

        # Registres globaux plats à déplacer.
        for name in ("TSK-L-01.json", "TSK-L-02.json"):
            with open(os.path.join(tasks_dir, name), "w", encoding="utf-8") as f:
                json.dump({"id": name[:-5]}, f)
        with open(os.path.join(decisions_dir, "DEC-01.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "DEC-01"}, f)
        with open(os.path.join(questions_dir, "QST-01.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "QST-01"}, f)

        report = migrate_state_to_fractal(tmpdir, dry_run=False)
        assert "EPIC-PROJET" in report and "STO-PROJET-01" in report

        story_dir = os.path.join(eff_dir, "epics", "EPIC-PROJET", "stories", "STO-PROJET-01")
        # Les fichiers sont désormais sous les sous-registres de la Story.
        assert os.path.exists(os.path.join(story_dir, "tasks", "TSK-L-01.json"))
        assert os.path.exists(os.path.join(story_dir, "tasks", "TSK-L-02.json"))
        assert os.path.exists(os.path.join(story_dir, "decisions", "DEC-01.json"))
        assert os.path.exists(os.path.join(story_dir, "questions", "QST-01.json"))

        # Les registres globaux plats ne contiennent plus de *.json.
        assert [n for n in os.listdir(tasks_dir) if n.endswith(".json")] == []
        assert [n for n in os.listdir(decisions_dir) if n.endswith(".json")] == []
        assert [n for n in os.listdir(questions_dir) if n.endswith(".json")] == []

        with open(os.path.join(eff_dir, "epics", "EPIC-PROJET", "epic.json"), encoding="utf-8") as f:
            epic = json.load(f)
        assert "STO-PROJET-01" in epic["stories"]

        # Idempotence : un second passage ne plante pas.
        again = migrate_state_to_fractal(tmpdir, dry_run=False)
        assert "Already migrated" in again


def test_migrate_state_relocates_cadrage_and_rewrites_config():
    from effortless_mcp.services.state_migrator import migrate_state_to_fractal

    with tempfile.TemporaryDirectory() as tmpdir:
        eff_dir = os.path.join(tmpdir, ".effortless")
        os.makedirs(eff_dir)

        with open(os.path.join(tmpdir, "effortless.json"), "w", encoding="utf-8") as f:
            json.dump({
                "settings": {"storage_dir": ".effortless", "documents_dir": "cadrage/Phase-001"},
                "workflow": {"phases": [{
                    "id": "L-plan",
                    "name": "Lancer",
                    "required_documents": ["cadrage/Phase-001/07-MET-PLN-plan-action.md"],
                }]},
                "project": {"name": "effortless"},
            }, f, ensure_ascii=False)

        with open(os.path.join(eff_dir, "state.json"), "w", encoding="utf-8") as f:
            json.dump({
                "project_name": "effortless",
                "current_phase": "L-plan",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_phases": [],
            }, f)

        doc_dir = os.path.join(tmpdir, "cadrage", "Phase-001")
        os.makedirs(doc_dir)
        with open(os.path.join(doc_dir, "07-MET-PLN-plan-action.md"), "w", encoding="utf-8") as f:
            f.write("# Plan d'action\n\nContenu de cadrage.\n")

        migrate_state_to_fractal(tmpdir, dry_run=False)

        new_doc = os.path.join(tmpdir, "cadrage", "EPIC-PROJET", "STO-PROJET-01", "07-MET-PLN-plan-action.md")
        old_doc = os.path.join(tmpdir, "cadrage", "Phase-001", "07-MET-PLN-plan-action.md")
        assert os.path.exists(new_doc)
        assert not os.path.exists(old_doc)

        with open(os.path.join(tmpdir, "effortless.json"), encoding="utf-8") as f:
            config = json.load(f)
        assert config["settings"]["documents_dir"] == "cadrage/EPIC-PROJET/STO-PROJET-01"
        phase = config["workflow"]["phases"][0]
        assert phase["id"] == "L-plan"
        assert phase["required_documents"] == ["cadrage/EPIC-PROJET/STO-PROJET-01/07-MET-PLN-plan-action.md"]


def test_effortless_migrate_state_tool(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        # init scaffolde le cadrage story-scopé (identique à la sortie du migrateur).
        assert os.path.exists(os.path.join(
            tmpdir, "cadrage", "EPIC-PROJET", "STO-PROJET-01", "00-FNC-GLO-glossaire.md"
        ))

        # effortless_init est désormais fractal-native (L-31). Pour exercer l'outil de
        # migration legacy -> fractal, on ramène le projet à un état plat pré-fractal :
        # suppression de l'arbre epics/ scaffoldé et retrait des pointeurs d'état.
        import shutil
        shutil.rmtree(os.path.join(tmpdir, ".effortless", "epics"))
        state_path = os.path.join(tmpdir, ".effortless", "state.json")
        with open(state_path, encoding="utf-8") as f:
            _st = json.load(f)
        _st.pop("active_epic_id", None)
        _st.pop("active_story_id", None)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(_st, f, indent=2, ensure_ascii=False)

        epic_file = os.path.join(tmpdir, ".effortless", "epics", "EPIC-PROJET", "epic.json")
        story_file = os.path.join(
            tmpdir, ".effortless", "epics", "EPIC-PROJET", "stories", "STO-PROJET-01", "story.json"
        )

        # Aperçu (confirm=False) : non destructif
        preview = server.effortless_migrate_state()
        assert "PREVIEW" in preview
        assert not os.path.exists(epic_file)

        # Application (confirm=True)
        applied = server.effortless_migrate_state(confirm=True)
        assert os.path.exists(epic_file)
        assert os.path.exists(story_file)

        with open(os.path.join(tmpdir, ".effortless", "state.json"), encoding="utf-8") as f:
            state = json.load(f)
        assert state["active_epic_id"] == "EPIC-PROJET"
        assert state["active_story_id"] == "STO-PROJET-01"

        # Idempotence
        again = server.effortless_migrate_state(confirm=True)
        assert "Already migrated" in again


def test_resolve_active_phase_ignores_current_phase_when_story_active(tmp_path):
    from effortless_mcp.server import resolve_active_phase
    root = str(tmp_path)
    eff_dir = os.path.join(root, ".effortless")
    story_dir = os.path.join(eff_dir, "epics", "EPIC-CORE", "stories", "STO-CORE-01")
    os.makedirs(story_dir, exist_ok=True)

    # current_phase est DELIBEREMENT different de l'opale_phase de la Story active.
    with open(os.path.join(eff_dir, "state.json"), "w", encoding="utf-8") as f:
        json.dump({
            "project_name": "x",
            "current_phase": "O-analyse",
            "active_epic_id": "EPIC-CORE",
            "active_story_id": "STO-CORE-01",
            "started_at": "t",
            "completed_phases": [],
        }, f)
    with open(os.path.join(story_dir, "story.json"), "w", encoding="utf-8") as f:
        json.dump({
            "id": "STO-CORE-01",
            "epic_id": "EPIC-CORE",
            "title": "x",
            "opale_phase": "L-plan",
            "status": "Doing",
        }, f)

    # Invariant verrouille : quand une Story est active, current_phase est ignore.
    # (Un fallback transitoire sur state.current_phase existe encore quand aucune
    # Story n'est active, mais il va etre retire -> on ne l'assert pas ici.)
    assert resolve_active_phase(root) == "L-plan"


def test_phase_next_advances_story_opale_phase(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        # Neutraliser la barrière de validation des documents de phase.
        monkeypatch.setattr(
            "effortless_mcp.server.validate_phase_documents",
            lambda **kwargs: (True, [], []),
        )
        # Éviter les effets de bord SecondBrain.
        monkeypatch.setattr(
            "effortless_mcp.server.get_secondbrain_vault_path", lambda: None
        )

        story_path = os.path.join(
            tmpdir, ".effortless", "epics", "EPIC-PROJET", "stories",
            "STO-PROJET-01", "story.json",
        )

        # Avant : la Story active est sur la première phase OPALE.
        with open(story_path, encoding="utf-8") as f:
            assert json.load(f)["opale_phase"] == "O-analyse"

        server.effortless_phase_next()

        # Après : la phase OPALE de la Story a avancé.
        with open(story_path, encoding="utf-8") as f:
            assert json.load(f)["opale_phase"] == "P-cadrage"

        # Aucun current_phase global ne doit être écrit dans state.json.
        with open(os.path.join(tmpdir, ".effortless", "state.json"), encoding="utf-8") as f:
            state = json.load(f)
        assert "current_phase" not in state

        # Ni dans la config workflow.
        with open(os.path.join(tmpdir, "effortless.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        assert "current_phase" not in cfg.get("workflow", {})

        # La phase quittée est marquée terminée.
        assert "O-analyse" in [cp.get("id") for cp in state.get("completed_phases", [])]


def test_task_add_uses_active_story_phase(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        msg = server.effortless_task_add("My task")
        tsk_id = msg.split("Task ")[1].split(" ")[0]

        # La tâche vit dans le dossier tasks imbriqué de la Story active.
        nested_path = os.path.join(
            tmpdir, ".effortless", "epics", "EPIC-PROJET", "stories",
            "STO-PROJET-01", "tasks", f"{tsk_id}.json",
        )
        assert os.path.exists(nested_path)

        with open(nested_path, encoding="utf-8") as f:
            task = json.load(f)
        # La phase est estampillée depuis l'opale_phase de la Story active.
        assert task["phase"] == "O-analyse"

        # Elle ne doit PAS exister dans le dossier plat .effortless/tasks/.
        assert not os.path.exists(
            os.path.join(tmpdir, ".effortless", "tasks", f"{tsk_id}.json")
        )


def test_decision_add_syncs_under_active_story_docs_dir(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        msg = server.effortless_decision_add(
            title="Choix du stockage",
            context="On hésite entre A et B.",
            decision="On prend A.",
            consequences=["Moins de latence"],
        )

        # Le Markdown des décisions atterrit dans le dossier cadrage scopé Story.
        story_docs_dir = os.path.join(
            tmpdir, "cadrage", "EPIC-PROJET", "STO-PROJET-01"
        )
        md_path = os.path.join(story_docs_dir, "03-MET-DEC-registre-decisions.md")
        assert os.path.exists(md_path)
        # Pas de double-préfixe root (pas de cadrage/.../cadrage/...).
        assert "cadrage/EPIC-PROJET/STO-PROJET-01/" in msg.replace(os.sep, "/")
        assert msg.count("cadrage") == 1


def test_question_resolve_syncs_under_active_story_docs_dir(monkeypatch):
    # Régression : resolve écrivait le BQO via le chemin littéral d'effortless.json
    # (piné sur la 1re Story) → il re-synchronisait le BQO de la MAUVAISE Story dès
    # qu'une autre Story était active (corruption croisée observée en dogfood).
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        # Repointer l'état sur une 2e Story (dossier cadrage != celui pinné en config).
        eff = os.path.join(tmpdir, ".effortless")
        story_dir = os.path.join(eff, "epics", "EPIC-TRACKER", "stories", "STO-TRACKER-01")
        os.makedirs(os.path.join(story_dir, "questions"), exist_ok=True)
        with open(os.path.join(eff, "state.json"), encoding="utf-8") as f:
            st = json.load(f)
        st["active_epic_id"] = "EPIC-TRACKER"
        st["active_story_id"] = "STO-TRACKER-01"
        with open(os.path.join(eff, "state.json"), "w", encoding="utf-8") as f:
            json.dump(st, f)
        with open(os.path.join(story_dir, "story.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "STO-TRACKER-01", "epic_id": "EPIC-TRACKER",
                       "title": "x", "opale_phase": "O-analyse"}, f)

        server.effortless_question_ask(question="Q ?", context="ctx", impact="Structuring")
        server.effortless_question_resolve(question_id="Q-01", answer="Oui.")

        # Le BQO de la Story ACTIVE est re-synchronisé et clôturé.
        tracker_bqo = os.path.join(tmpdir, "cadrage", "EPIC-TRACKER",
                                   "STO-TRACKER-01", "02-BQO-questions.md")
        assert os.path.exists(tracker_bqo)
        meta, _ = parse_markdown_frontmatter(tracker_bqo)
        assert meta["statut"] in ("Résolu", "Resolved")


def test_decision_add_entity_stored_in_story_dir(monkeypatch):
    # Le JSON de décision atterrit dans le sous-registre de la Story active,
    # PAS dans le registre global plat .effortless/decisions/.
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        server.effortless_decision_add(
            title="Choix du stockage",
            context="On hésite entre A et B.",
            decision="On prend A.",
            consequences=["Moins de latence"],
        )

        story_dec_dir = os.path.join(
            tmpdir, ".effortless", "epics", "EPIC-PROJET", "stories",
            "STO-PROJET-01", "decisions",
        )
        dec_files = [n for n in os.listdir(story_dec_dir)
                     if n.startswith("DEC-") and n.endswith(".json")]
        assert len(dec_files) == 1

        # Aucun DEC-*.json dans le registre global plat.
        flat_dec_dir = os.path.join(tmpdir, ".effortless", "decisions")
        flat_dec = [n for n in os.listdir(flat_dec_dir)
                    if n.startswith("DEC-") and n.endswith(".json")]
        assert flat_dec == []


def test_task_update_finds_story_task(monkeypatch):
    # task_update doit trouver la tâche dans le sous-registre de la Story active
    # et persister le nouveau statut (et non échouer en 'task not found').
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        msg = server.effortless_task_add("Implement X")
        tsk_id = msg.split("Task ")[1].split(" ")[0]

        result = server.effortless_task_update(tsk_id, "Doing")
        assert "not found" not in result
        assert tsk_id in result and "Doing" in result

        nested_path = os.path.join(
            tmpdir, ".effortless", "epics", "EPIC-PROJET", "stories",
            "STO-PROJET-01", "tasks", f"{tsk_id}.json",
        )
        with open(nested_path, encoding="utf-8") as f:
            assert json.load(f)["status"] == "Doing"


def test_overview_lists_story_entities(monkeypatch):
    # build_project_overview agrège les entités de la Story active (sous-registres),
    # donc la liste tasks n'est pas vide après un ajout.
    from effortless_mcp import server
    from effortless_mcp.server import build_project_overview
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        server.effortless_task_add("Une tâche")

        overview = build_project_overview(tmpdir)
        assert overview["initialized"] is True
        assert len(overview["tasks"]) >= 1


def test_question_ask_syncs_under_active_story_docs_dir(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        msg = server.effortless_question_ask(
            question="Quel format pour l'export ?",
            context="L'export doit être interopérable.",
            impact="Structuring",
        )

        # Le Markdown du BQO atterrit dans le dossier cadrage scopé Story.
        story_docs_dir = os.path.join(
            tmpdir, "cadrage", "EPIC-PROJET", "STO-PROJET-01"
        )
        md_path = os.path.join(story_docs_dir, "02-BQO-questions.md")
        assert os.path.exists(md_path)
        # Pas de double-préfixe root (pas de cadrage/.../cadrage/...).
        assert "cadrage/EPIC-PROJET/STO-PROJET-01/" in msg.replace(os.sep, "/")
        assert msg.count("cadrage") == 1


# --- Port Tracker (STO-TRACKER-01) -------------------------------------------

class _FakeTracker:
    """Adapter de test : enregistre les appels, retourne une ref non vide."""
    def __init__(self, cfg=None):
        self.created = []
        self.transitions = []
    def discover_taxonomy(self, project):
        from effortless_mcp.ports import Taxonomy
        return Taxonomy()
    def create(self, payload):
        from effortless_mcp.ports import TrackerRef
        self.created.append(payload)
        return TrackerRef("IFX-99", "https://x/IFX-99")
    def transition(self, ref, status):
        self.transitions.append((ref, status))
    def log_work(self, ref, minutes, comment):
        pass
    def import_tree(self, project):
        return []


class _BoomTracker(_FakeTracker):
    """Adapter injoignable : lève sur create/transition."""
    def create(self, payload):
        raise RuntimeError("tracker offline")
    def transition(self, ref, status):
        raise RuntimeError("tracker offline")


def test_null_tracker_conforms_protocol():
    from effortless_mcp.ports import Tracker, NullTracker, resolve_tracker
    assert isinstance(NullTracker(), Tracker)
    # Type absent / inconnu -> NullTracker.
    assert isinstance(resolve_tracker(None), NullTracker)
    assert isinstance(resolve_tracker({"tracker": {"type": "unknown"}}), NullTracker)


def test_resolve_tracker_uses_registered_adapter():
    from effortless_mcp.ports import register_adapter, resolve_tracker
    fake = _FakeTracker()
    register_adapter("faketype", lambda cfg: fake)
    assert resolve_tracker({"tracker": {"type": "faketype"}}) is fake


def test_sync_journal_replay_idempotent(tmp_path):
    from effortless_mcp.ports import SyncJournal
    seq = {"n": 0}
    def clock():
        seq["n"] += 1
        return f"t{seq['n']}"
    j = SyncJournal(str(tmp_path), now=clock)
    j.enqueue("create", {"a": 1})
    j.enqueue("transition", {"b": 2})
    assert [e["seq"] for e in j.pending()] == [1, 2]
    seen = []
    assert j.replay(lambda e: seen.append(e["seq"])) == 2
    assert seen == [1, 2]
    assert j.pending() == []
    # Idempotent : un 2e replay ne rejoue rien.
    assert j.replay(lambda e: seen.append(("AGAIN", e["seq"]))) == 0
    # Les entrées jouées portent played + played_at.
    played = [e for e in j._load_all() if e["played"]]
    assert len(played) == 2 and all(e["played_at"] for e in played)


def test_couple_project_writes_settings_and_ref(tmp_path):
    from effortless_mcp.ports.integration import couple_project, tracker_project_ref
    cfg_path = os.path.join(str(tmp_path), "effortless.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"settings": {}}, f)
    ref = couple_project(str(tmp_path), "jira", "IFX", "https://x/IFX")
    assert (ref.project_id, ref.project_url) == ("IFX", "https://x/IFX")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["settings"]["tracker"] == {"type": "jira", "project_id": "IFX", "project_url": "https://x/IFX"}
    pr = tracker_project_ref(str(tmp_path))
    assert pr is not None and pr.project_id == "IFX"


def test_project_task_created_persists_ref_when_coupled(tmp_path):
    from effortless_mcp.ports import register_adapter
    from effortless_mcp.ports.integration import project_task_created
    fake = _FakeTracker()
    register_adapter("faketype2", lambda cfg: fake)
    with open(os.path.join(str(tmp_path), "effortless.json"), "w", encoding="utf-8") as f:
        json.dump({"settings": {"tracker": {"type": "faketype2"}}}, f)
    task = {"id": "TSK-01", "title": "x", "tracker_id": "", "tracker_url": ""}
    out = project_task_created(str(tmp_path), task)
    assert out["tracker_id"] == "IFX-99" and out["tracker_url"] == "https://x/IFX-99"
    assert len(fake.created) == 1


def test_project_task_offline_enqueues_outbox(tmp_path):
    from effortless_mcp.ports import register_adapter, SyncJournal
    from effortless_mcp.ports.integration import project_task_created
    register_adapter("boomtype", lambda cfg: _BoomTracker())
    with open(os.path.join(str(tmp_path), "effortless.json"), "w", encoding="utf-8") as f:
        json.dump({"settings": {"tracker": {"type": "boomtype"}}}, f)
    task = {"id": "TSK-07", "title": "x", "tracker_id": "", "tracker_url": ""}
    out = project_task_created(str(tmp_path), task)
    # L'opération locale n'échoue pas ; la projection est consignée.
    assert out["tracker_id"] == ""
    pending = SyncJournal(str(tmp_path)).pending()
    assert len(pending) == 1 and pending[0]["op"] == "create"


def test_project_uncoupled_no_io(tmp_path):
    # Projet non couplé (NullTracker) : aucune écriture outbox.
    from effortless_mcp.ports.integration import project_task_created, project_task_transitioned
    with open(os.path.join(str(tmp_path), "effortless.json"), "w", encoding="utf-8") as f:
        json.dump({"settings": {}}, f)
    task = {"id": "TSK-01", "title": "x", "tracker_id": "", "tracker_url": ""}
    project_task_created(str(tmp_path), task)
    project_task_transitioned(str(tmp_path), task, "Done")
    assert not os.path.isdir(os.path.join(str(tmp_path), ".effortless", "tracker_outbox"))


# --- effortless_story_start ([TOOLING]) --------------------------------------

def test_story_start_scaffolds_and_activates_new_story(monkeypatch):
    # Comble le trou : amorcer une 2e Story sous l'Epic actif et basculer dessus.
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        server.effortless_story_start("Migration des données")
        # Forme <NNN>-Story-<Sujet> : le sujet dérive du TITRE (EVO-011).
        with open(os.path.join(tmpdir, ".effortless", "state.json"), encoding="utf-8") as f:
            state = json.load(f)
        sid = state["active_story_id"]
        eid = state["active_epic_id"]
        assert sid == "001-Story-Migration-Donnees"

        # Arbre fractal scaffoldé : fiche + sous-registres.
        sdir = os.path.join(tmpdir, ".effortless", "epics", eid, "stories", sid)
        for sub in ("story.json", "tasks", "decisions", "questions"):
            assert os.path.exists(os.path.join(sdir, sub))
        # Dossier de cadrage story-scopé.
        assert os.path.isdir(os.path.join(tmpdir, "cadrage", eid, sid))

        # Story démarre sur la 1re phase OPALE, statut Doing, avec seq.
        with open(os.path.join(sdir, "story.json"), encoding="utf-8") as f:
            story = json.load(f)
        assert story["opale_phase"] == "O-analyse"
        assert story["status"] == "Doing"
        assert story["epic_id"] == eid and story["zone"] == "PROJET" and isinstance(story["seq"], int)

        # Référencée dans epic.json (dédup), pas de doublon.
        with open(os.path.join(tmpdir, ".effortless", "epics", eid, "epic.json"), encoding="utf-8") as f:
            epic = json.load(f)
        assert epic["stories"].count(sid) == 1

        # La phase faisant autorité suit la nouvelle Story active.
        assert server.resolve_active_phase(tmpdir) == "O-analyse"


def test_story_start_unblocks_autonomous_loop(monkeypatch):
    # Régression de la cause racine : une Story 'Done' faisait croire « GOAL REACHED » ;
    # story_start ouvre une Story fraîche dont le backlog vide redonne du travail à la boucle.
    from effortless_mcp import server
    from effortless_mcp.services import session_loop as sl
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        # Clore la story initiale (tâche unique Done) puis re-planifier : faux « GOAL REACHED ».
        tid = server.effortless_task_add("seule", complexity="simple").split("Task ")[1].split(" ")[0]
        server.effortless_task_update(tid, "Done")
        server.effortless_loop_init("g")
        assert "GOAL REACHED" in sl.step_autonomous_loop(tmpdir, "true")

        # Ouvrir une nouvelle Story : la boucle a de nouveau un backlog vide à remplir.
        server.effortless_story_start("Suite du travail")
        out = sl.step_autonomous_loop(tmpdir, "true")
        assert "GOAL REACHED" not in out
        # Backlog vide de la nouvelle Story -> invite à ajouter des tâches, pas une fausse victoire.
        assert "No tasks in the backlog" in out


def test_story_start_validates_phase_and_epic(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        # Phase OPALE invalide rejetée.
        assert "invalid opale_phase" in server.effortless_story_start("x", opale_phase="Z-nope")
        # Epic inexistant rejeté.
        assert "not found" in server.effortless_story_start("x", epic_id="EPIC-GHOST")

        # activate=False : la Story est créée mais l'active ne bascule pas.
        server.effortless_story_start("non active", activate=False)
        with open(os.path.join(tmpdir, ".effortless", "state.json"), encoding="utf-8") as f:
            assert json.load(f)["active_story_id"] == "STO-PROJET-01"




# --- Projection médiée agent / QueueTracker (STO-TRACKER-03) ------------------

def _journal(tmp_path):
    from effortless_mcp.ports import SyncJournal
    return SyncJournal(str(tmp_path))


def test_queue_tracker_create_enqueues(tmp_path):
    from effortless_mcp.ports import ObjectPayload, TrackerRef
    from effortless_mcp.ports.adapters.jira import QueueTracker
    j = _journal(tmp_path)
    qt = QueueTracker(j)
    epic = qt.create(ObjectPayload(level="epic", title="[PROJET]", labels=["effortless-scaffold:PROJET"]))
    # Ref placeholder à id local, aucun appel réseau.
    assert epic.tracker_id == "local:1" and epic.tracker_url == ""
    sub = qt.create(ObjectPayload(level="task", title="[PROJET] Doc", parent_ref=epic))
    pend = j.pending()
    assert len(pend) == 2
    a0 = pend[0]["args"]
    assert a0["issue_type_name"] == "Epic" and a0["parent_local_id"] is None
    assert a0["labels"] == ["effortless-scaffold:PROJET"]
    a1 = pend[1]["args"]
    assert a1["issue_type_name"] == "Sous-tâche" and a1["parent_local_id"] == "local:1"


def test_scaffolder_via_queue_enqueues_tree(tmp_path):
    from effortless_mcp.ports import ProjectRef
    from effortless_mcp.ports.adapters.jira import QueueTracker
    from effortless_mcp.services.scaffolder import scaffold_project_from_template
    from effortless_mcp.services.scaffold_state import ScaffoldState
    from effortless_mcp.templates import load_scaffold_template
    j = _journal(tmp_path)
    refs = scaffold_project_from_template(
        QueueTracker(j), ProjectRef("EFL", "u"), load_scaffold_template(), "PROJET", ScaffoldState(str(tmp_path))
    )
    assert len(refs) == 6
    ops = j.pending()
    assert len(ops) == 6
    # Racine porte le label, parent None.
    root = ops[0]["args"]
    assert root["issue_type_name"] == "Epic" and root["labels"] == ["effortless-scaffold:PROJET"]
    # Les 2 sous-tâches pointent vers la story "Divers" (local:4).
    subs = [o["args"] for o in ops if o["args"]["issue_type_name"] == "Sous-tâche"]
    assert len(subs) == 2 and all(s["parent_local_id"] == "local:4" for s in subs)


def test_scaffolder_idempotent_via_queue(tmp_path):
    from effortless_mcp.ports import ProjectRef
    from effortless_mcp.ports.adapters.jira import QueueTracker
    from effortless_mcp.services.scaffolder import scaffold_project_from_template
    from effortless_mcp.services.scaffold_state import ScaffoldState
    from effortless_mcp.templates import load_scaffold_template
    j, state, tmpl = _journal(tmp_path), ScaffoldState(str(tmp_path)), load_scaffold_template()
    first = scaffold_project_from_template(QueueTracker(j), ProjectRef("EFL", "u"), tmpl, "PROJET", state)
    # 2e run : ScaffoldState garde -> 0 op neuve.
    second = scaffold_project_from_template(QueueTracker(j), ProjectRef("EFL", "u"), tmpl, "PROJET", state)
    assert second == first
    assert len(j.pending()) == 6  # toujours 6, pas 12


def test_resolve_tracker_jira_is_queue(tmp_path):
    from effortless_mcp.ports import resolve_tracker
    from effortless_mcp.ports.adapters.jira import QueueTracker
    # La fabrique réelle « jira » est le QueueTracker médié (zéro creds).
    tracker = resolve_tracker({"tracker": {"type": "jira", "project_id": "EFL"}}, root=str(tmp_path))
    assert isinstance(tracker, QueueTracker)


def test_scaffold_state_persists_and_guards(tmp_path):
    from effortless_mcp.services.scaffold_state import ScaffoldState
    st = ScaffoldState(str(tmp_path))
    assert not st.has("PROJET")
    st.set("PROJET", {"[PROJET]": {"tracker_id": "EFL-1", "tracker_url": "u"}})
    assert st.has("PROJET") and st.get("PROJET")["[PROJET]"]["tracker_id"] == "EFL-1"
    assert ScaffoldState(str(tmp_path)).has("PROJET")


def test_rest_jiraclient_removed():
    # Le client REST + token est retiré (DEC-02) ; FakeJiraClient conservé.
    from effortless_mcp.ports.adapters import jira_client, jira
    assert hasattr(jira_client, "FakeJiraClient")
    assert not hasattr(jira_client, "JiraClient")
    assert not hasattr(jira, "JiraTracker")


def test_tracker_tools_queue_flow(monkeypatch):
    # Flux médié complet : couple -> scaffold (enqueue) -> pending -> ack -> idempotent.
    from effortless_mcp import server
    import json as _json
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")

        couple = server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        assert "couplé" in couple and "Rovo" in couple

        # Garde d'idempotence : sans confirm_absent, aucun enqueue (STO-TRACKER-12).
        guard = server.effortless_tracker_scaffold("PROJET")
        assert "Garde d'idempotence" in guard and "confirm_absent=True" in guard
        assert "Aucune opération" in server.effortless_tracker_pending()

        # Absence confirmée par l'agent → enqueue.
        out = server.effortless_tracker_scaffold("PROJET", confirm_absent=True)
        assert "6 op(s) en attente" in out

        pend = server.effortless_tracker_pending()
        assert "pending" in pend and "local:1" in pend
        data = _json.loads(pend.split("\n\n", 1)[1])["pending"]
        assert len(data) == 6
        # L'agent (simulé) crée les vraies clés et ack.
        refs = {op["local_id"]: {"tracker_id": f"EFL-{op['seq']}", "tracker_url": f"u/EFL-{op['seq']}"}
                for op in data}
        ack = server.effortless_tracker_ack("PROJET", _json.dumps(refs))
        assert "6 ref" in ack

        # Outbox vidé après ack.
        assert "Aucune opération" in server.effortless_tracker_pending()
        # Re-scaffold : idempotent (ScaffoldState).
        assert "déjà scaffoldée" in server.effortless_tracker_scaffold("PROJET")


def test_tracker_scaffold_uncoupled_noop(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        out = server.effortless_tracker_scaffold("PROJET")
        assert "no-op" in out
        # Aucune op enqueue côté outbox.
        assert "Aucune opération" in server.effortless_tracker_pending()


def test_tracker_ack_rejects_bad_json(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        assert "invalide" in server.effortless_tracker_ack("PROJET", "{not json")


# --- Discover médié + issue_type_id (STO-TRACKER-04) --------------------------

def test_queue_tracker_stamps_issue_type_id(tmp_path):
    from effortless_mcp.ports import ObjectPayload, SyncJournal
    from effortless_mcp.ports.adapters.jira import QueueTracker
    tax = {"epic": "10000", "story": "10007", "task": "10095"}
    j = SyncJournal(str(tmp_path))
    qt = QueueTracker(j, taxonomy=tax)
    qt.create(ObjectPayload(level="task", title="[PROJET] Doc"))
    assert j.pending()[0]["args"]["issue_type_id"] == "10095"


def test_queue_tracker_issue_type_id_null_without_taxonomy(tmp_path):
    from effortless_mcp.ports import ObjectPayload, SyncJournal
    from effortless_mcp.ports.adapters.jira import QueueTracker
    j = SyncJournal(str(tmp_path))
    QueueTracker(j).create(ObjectPayload(level="task", title="x"))
    # Sans taxonomie ackée -> id None, pas d'échec (fallback nom).
    op = j.pending()[0]["args"]
    assert op["issue_type_id"] is None and op["issue_type_name"] == "Sous-tâche"


def test_discover_ack_persists_taxonomy(monkeypatch):
    from effortless_mcp import server
    import json as _json
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        tax = {"epic": "10000", "story": "10007", "task": "10095"}
        out = server.effortless_tracker_discover_ack(_json.dumps(tax))
        assert "persistée" in out
        with open(os.path.join(tmpdir, "effortless.json"), encoding="utf-8") as f:
            assert _json.load(f)["settings"]["tracker"]["taxonomy"] == tax


def test_scaffold_ops_carry_issue_type_id_after_discover(monkeypatch):
    from effortless_mcp import server
    import json as _json
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        server.effortless_tracker_discover_ack(_json.dumps({"epic": "10000", "story": "10007", "task": "10095"}))
        server.effortless_tracker_scaffold("PROJET", confirm_absent=True)
        data = _json.loads(server.effortless_tracker_pending().split("\n\n", 1)[1])["pending"]
        by_type = {op["issue_type_name"]: op["issue_type_id"] for op in data}
        assert by_type["Epic"] == "10000" and by_type["Story"] == "10007" and by_type["Sous-tâche"] == "10095"


def test_discover_ack_rejects_bad_input(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        assert "invalide" in server.effortless_tracker_discover_ack("{bad")
        assert "level" in server.effortless_tracker_discover_ack('{"epic": 10000}')


# --- Transition médiée (cycle en V) — STO-TRACKER-05 --------------------------

def test_queue_tracker_transition_enqueues_with_id(tmp_path):
    from effortless_mcp.ports import SyncJournal, TrackerRef
    from effortless_mcp.ports.adapters.jira import QueueTracker
    j = SyncJournal(str(tmp_path))
    qt = QueueTracker(j, transitions={"Todo": "11", "Doing": "5", "Done": "9"})
    qt.transition(TrackerRef("EFL-42", "u/EFL-42"), "Done")
    op = j.pending()[0]
    assert op["op"] == "transition"
    assert op["args"] == {"tracker_id": "EFL-42", "status": "Done", "transition_id": "9"}


def test_queue_tracker_transition_id_null_without_table(tmp_path):
    from effortless_mcp.ports import SyncJournal, TrackerRef
    from effortless_mcp.ports.adapters.jira import QueueTracker
    j = SyncJournal(str(tmp_path))
    QueueTracker(j).transition(TrackerRef("local:3", ""), "Doing")
    # Sans table ackée -> transition_id None (fallback agent), pas d'échec.
    op = j.pending()[0]["args"]
    assert op["transition_id"] is None and op["tracker_id"] == "local:3" and op["status"] == "Doing"


def test_build_queue_tracker_wires_transitions(tmp_path):
    from effortless_mcp.ports import resolve_tracker, SyncJournal, TrackerRef
    tracker = resolve_tracker(
        {"tracker": {"type": "jira", "project_id": "EFL", "transitions": {"Done": "9"}}},
        root=str(tmp_path),
    )
    tracker.transition(TrackerRef("EFL-1", "u"), "Done")
    assert SyncJournal(str(tmp_path)).pending()[0]["args"]["transition_id"] == "9"


def test_sync_journal_mark_played_by_seq(tmp_path):
    from effortless_mcp.ports import SyncJournal
    j = SyncJournal(str(tmp_path), now=lambda: "T")
    j.enqueue("create", {"a": 1})       # seq 1
    j.enqueue("transition", {"b": 2})   # seq 2
    j.enqueue("transition", {"c": 3})   # seq 3
    # Cible seq 2 uniquement.
    assert j.mark_played([2]) == 1
    remaining = [e["seq"] for e in j.pending()]
    assert remaining == [1, 3]
    # Idempotent : re-marquer seq 2 ne fait rien.
    assert j.mark_played([2]) == 0
    # None -> marque tout le reste.
    assert j.mark_played() == 2
    assert j.pending() == []


def test_transition_projected_via_integration(tmp_path):
    from effortless_mcp.ports import register_adapter, SyncJournal
    from effortless_mcp.ports.adapters.jira import build_queue_tracker
    from effortless_mcp.ports.integration import project_task_transitioned
    register_adapter("jira", build_queue_tracker)
    cfg = os.path.join(str(tmp_path), "effortless.json")
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump({"settings": {"tracker": {"type": "jira", "project_id": "EFL",
                                            "transitions": {"Done": "9"}}}}, f)
    task = {"id": "TSK-01", "tracker_id": "EFL-7", "tracker_url": "u/EFL-7"}
    project_task_transitioned(str(tmp_path), task, "Done")
    op = SyncJournal(str(tmp_path)).pending()[0]["args"]
    assert op["tracker_id"] == "EFL-7" and op["status"] == "Done" and op["transition_id"] == "9"


def test_transitions_ack_persists_table(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        table = {"Todo": "11", "Doing": "5", "Done": "9"}
        out = server.effortless_tracker_transitions_ack(json.dumps(table))
        assert "persistées" in out
        with open(os.path.join(tmpdir, "effortless.json"), encoding="utf-8") as f:
            assert json.load(f)["settings"]["tracker"]["transitions"] == table


def test_transitions_ack_rejects_bad_input(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        assert "invalide" in server.effortless_tracker_transitions_ack("{bad")
        assert "statut_local" in server.effortless_tracker_transitions_ack('{"Done": 9}')


def test_flush_ack_marks_transition_ops_played(monkeypatch):
    # Flux médié transition : couple -> discover transitions -> transition (enqueue)
    # -> pending -> flush_ack -> outbox vidé.
    from effortless_mcp import server
    from effortless_mcp.ports.integration import project_task_transitioned
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        server.effortless_tracker_transitions_ack(json.dumps({"Done": "9"}))

        task = {"id": "TSK-01", "tracker_id": "EFL-7", "tracker_url": "u/EFL-7"}
        project_task_transitioned(tmpdir, task, "Done")

        pend = server.effortless_tracker_pending()
        data = json.loads(pend.split("\n\n", 1)[1])["pending"]
        assert len(data) == 1 and data[0]["op"] == "transition" and data[0]["transition_id"] == "9"
        seq = data[0]["seq"]

        out = server.effortless_tracker_flush_ack(json.dumps([seq]))
        assert "1 op" in out
        assert "Aucune opération" in server.effortless_tracker_pending()


def test_flush_ack_rejects_bad_input(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        assert "invalide" in server.effortless_tracker_flush_ack("{bad")
        assert "entiers" in server.effortless_tracker_flush_ack('["x"]')


# --- Log_work médié — STO-TRACKER-06 ------------------------------------------

def test_queue_tracker_log_work_enqueues(tmp_path):
    from effortless_mcp.ports import SyncJournal, TrackerRef
    from effortless_mcp.ports.adapters.jira import QueueTracker
    j = SyncJournal(str(tmp_path))
    QueueTracker(j).log_work(TrackerRef("EFL-42", "u/EFL-42"), 90, "dev transition")
    op = j.pending()[0]
    assert op["op"] == "log_work"
    assert op["args"] == {"tracker_id": "EFL-42", "minutes": 90, "comment": "dev transition"}


def test_log_work_projected_via_integration(tmp_path):
    from effortless_mcp.ports import register_adapter, SyncJournal
    from effortless_mcp.ports.adapters.jira import build_queue_tracker
    from effortless_mcp.ports.integration import project_task_log_work
    register_adapter("jira", build_queue_tracker)
    cfg = os.path.join(str(tmp_path), "effortless.json")
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump({"settings": {"tracker": {"type": "jira", "project_id": "EFL"}}}, f)
    task = {"id": "TSK-01", "tracker_id": "EFL-7", "tracker_url": "u/EFL-7"}
    project_task_log_work(str(tmp_path), task, 30, "revue")
    op = SyncJournal(str(tmp_path)).pending()[0]["args"]
    assert op["tracker_id"] == "EFL-7" and op["minutes"] == 30 and op["comment"] == "revue"


def test_log_work_uncoupled_no_io(tmp_path):
    from effortless_mcp.ports.integration import project_task_log_work
    from effortless_mcp.ports import SyncJournal
    # Non couplé (pas d'effortless.json / tracker) : no-op, aucun outbox.
    project_task_log_work(str(tmp_path), {"id": "T", "tracker_id": "EFL-1"}, 10, "x")
    assert SyncJournal(str(tmp_path)).pending() == []


def test_tracker_log_work_tool_flow(monkeypatch):
    # couple -> task_add (create enqueue) -> log_work (enqueue) -> pending -> flush_ack.
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        server.effortless_task_add("Tâche témoin")

        out = server.effortless_tracker_log_work("TSK-01", 45, "impl")
        assert "45 min" in out and "Rovo" in out

        data = json.loads(server.effortless_tracker_pending().split("\n\n", 1)[1])["pending"]
        lw = [o for o in data if o["op"] == "log_work"]
        assert len(lw) == 1 and lw[0]["minutes"] == 45 and lw[0]["comment"] == "impl"

        server.effortless_tracker_flush_ack("")  # marque tout joué
        assert "Aucune opération" in server.effortless_tracker_pending()


def test_tracker_log_work_tool_guards(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        server.effortless_task_add("T")
        assert "positif" in server.effortless_tracker_log_work("TSK-01", 0, "x")
        assert "not found" in server.effortless_tracker_log_work("TSK-99", 10, "x")


def test_tracker_log_work_uncoupled_noop(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_task_add("T")
        out = server.effortless_tracker_log_work("TSK-01", 20, "x")
        assert "no-op" in out
        assert "Aucune opération" in server.effortless_tracker_pending()


# --- Import read-mostly médié — STO-TRACKER-07 --------------------------------

def test_import_plan_suggests_label_jql(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        out = server.effortless_tracker_import_plan("PROJET")
        plan = json.loads(out.split("\n\n", 1)[1])
        assert plan["zone"] == "PROJET"
        assert 'labels = "effortless-scaffold:PROJET"' in plan["jql"]
        assert "tree" in plan["ack_shape"]


def test_import_ack_reconciles_scaffold_state(monkeypatch):
    from effortless_mcp import server
    from effortless_mcp.services.scaffold_state import ScaffoldState
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        tree = {"tree": [
            {"level": "epic", "tracker_id": "EFL-1", "tracker_url": "u/EFL-1",
             "title": "[PROJET]", "parent_id": None},
            {"level": "task", "tracker_id": "EFL-2", "tracker_url": "u/EFL-2",
             "title": "[PROJET] Doc", "parent_id": "EFL-1"},
        ]}
        out = server.effortless_tracker_import_ack("PROJET", json.dumps(tree))
        assert "2 issue" in out
        st = ScaffoldState(tmpdir)
        assert st.has("PROJET")
        assert st.get("PROJET")["[PROJET]"]["tracker_id"] == "EFL-1"


def test_rescaffold_idempotent_after_import(monkeypatch):
    # Jira-as-truth : après import_ack, un scaffold ne recrée rien (outbox vide).
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        tree = {"tree": [{"level": "epic", "tracker_id": "EFL-1", "tracker_url": "u",
                          "title": "[PROJET]", "parent_id": None}]}
        server.effortless_tracker_import_ack("PROJET", json.dumps(tree))
        out = server.effortless_tracker_scaffold("PROJET")
        assert "déjà scaffoldée" in out
        assert "Aucune opération" in server.effortless_tracker_pending()


def test_scaffold_guard_blocks_duplicate_without_confirm(monkeypatch):
    # STO-TRACKER-12 : sans ScaffoldState local ni confirm_absent, scaffold n'enqueue
    # RIEN et exige la vérification d'absence Jira (label) — évite les arbres dupliqués.
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        guard = server.effortless_tracker_scaffold("PROJET")
        assert 'labels = "effortless-scaffold:PROJET"' in guard
        assert "import_ack" in guard and "confirm_absent=True" in guard
        assert "Aucune opération" in server.effortless_tracker_pending()  # zéro enqueue


def test_import_ack_rejects_bad_input(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        assert "invalide" in server.effortless_tracker_import_ack("PROJET", "{bad")
        assert "liste" in server.effortless_tracker_import_ack("PROJET", '{"tree": 5}')
        # Nœud sans tracker_id rejeté.
        assert "tracker_id" in server.effortless_tracker_import_ack(
            "PROJET", '{"tree": [{"title": "x"}]}')


# --- Option Xray (MVP médié) — STO-TRACKER-08 ---------------------------------

def test_xray_discover_ack_persists(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        xr = {"test_issue_type_id": "10201", "link_type": "Test"}
        out = server.effortless_tracker_xray_discover_ack(json.dumps(xr))
        assert "persistée" in out
        with open(os.path.join(tmpdir, "effortless.json"), encoding="utf-8") as f:
            assert json.load(f)["settings"]["tracker"]["xray"] == xr


def test_xray_discover_ack_rejects_bad_input(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        assert "invalide" in server.effortless_tracker_xray_discover_ack("{bad")
        assert "test_issue_type_id" in server.effortless_tracker_xray_discover_ack('{"link_type": "Test"}')


def test_xray_add_test_enqueues_with_id_and_link(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        server.effortless_tracker_xray_discover_ack(
            json.dumps({"test_issue_type_id": "10201", "link_type": "Test"}))
        out = server.effortless_tracker_xray_add_test("Login OK", link_tracker_id="EFL-5")
        assert "Xray" in out and "EFL-5" in out
        data = json.loads(server.effortless_tracker_pending().split("\n\n", 1)[1])["pending"]
        op = next(o for o in data if o["op"] == "xray_create_test")
        assert op["title"] == "Login OK"
        assert op["issue_type_id"] == "10201" and op["issue_type_name"] == "Test"
        assert op["link_tracker_id"] == "EFL-5" and op["link_type"] == "Test"


def test_xray_add_test_id_null_without_discover(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        server.effortless_tracker_xray_add_test("T")
        op = json.loads(server.effortless_tracker_pending().split("\n\n", 1)[1])["pending"][0]
        # Sans discover Xray : id None (fallback nom), link_type défaut "Test", pas de lien.
        assert op["issue_type_id"] is None and op["link_type"] == "Test"
        assert op["link_tracker_id"] is None


def test_xray_add_test_flow_flush_ack(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        server.effortless_tracker_xray_add_test("T", link_tracker_id="EFL-5")
        server.effortless_tracker_flush_ack("")
        assert "Aucune opération" in server.effortless_tracker_pending()


def test_xray_add_test_guards(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        # Non couplé : no-op.
        assert "no-op" in server.effortless_tracker_xray_add_test("T")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        assert "title requis" in server.effortless_tracker_xray_add_test("  ")


# --- Reconcile task registry (local:N → clé réelle) — STO-TRACKER-09 ----------

def test_reconcile_tasks_rewrites_local_to_real(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        # task_add via projection médiée -> tracker_id = local:N.
        server.effortless_task_add("Tâche témoin")
        # Récupère le local id posé sur la tâche.
        tasks_dir = server.resolve_registry_dir(tmpdir, "tasks")
        task = next(t for t in server.load_entities(tasks_dir) if t["id"] == "TSK-01")
        local_id = task["tracker_id"]
        assert local_id.startswith("local:")

        refs = {local_id: {"tracker_id": "EFL-42", "tracker_url": "u/EFL-42"}}
        out = server.effortless_tracker_reconcile_tasks(json.dumps(refs))
        assert "1 tâche" in out
        task2 = next(t for t in server.load_entities(tasks_dir) if t["id"] == "TSK-01")
        assert task2["tracker_id"] == "EFL-42" and task2["tracker_url"] == "u/EFL-42"


def test_reconcile_tasks_idempotent_and_scoped(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        server.effortless_task_add("T")
        tasks_dir = server.resolve_registry_dir(tmpdir, "tasks")
        local_id = next(t for t in server.load_entities(tasks_dir) if t["id"] == "TSK-01")["tracker_id"]
        server.effortless_tracker_reconcile_tasks(json.dumps({local_id: {"tracker_id": "EFL-1", "tracker_url": "u"}}))
        # 2e run avec le même local id : déjà réel, plus de match -> 0.
        out2 = server.effortless_tracker_reconcile_tasks(json.dumps({local_id: {"tracker_id": "EFL-1", "tracker_url": "u"}}))
        assert "0 tâche" in out2


def test_reconcile_tasks_walks_multiple_stories(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        server.effortless_task_add("T story1")  # STO-PROJET-01 active
        # Nouvelle story sous le même Epic actif, task_add dedans.
        server.effortless_story_start("Deuxième story")
        server.effortless_task_add("T story2")

        # Collecte les 2 local ids (registres story distincts) — désormais UNIQUES
        # (local:1 / local:2) grâce au seq outbox global.
        local_ids = {task["tracker_id"] for _, task in server._iter_task_files(tmpdir)
                     if str(task.get("tracker_id", "")).startswith("local:")}
        assert len(local_ids) == 2  # pas de collision cross-instance
        refs = {lid: {"tracker_id": f"EFL-{i}", "tracker_url": f"u/{i}"} for i, lid in enumerate(local_ids, 1)}
        out = server.effortless_tracker_reconcile_tasks(json.dumps(refs))
        # Les deux tâches (2 stories) rebranchées via le walk multi-registres.
        assert "2 tâche" in out
        remaining = [t for _, t in server._iter_task_files(tmpdir)
                     if str(t.get("tracker_id", "")).startswith("local:")]
        assert remaining == []


def test_reconcile_tasks_rejects_bad_input(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        assert "invalide" in server.effortless_tracker_reconcile_tasks("{bad")
        assert "local_id" in server.effortless_tracker_reconcile_tasks('{"local:1": {"x": 1}}')


# --- Hygiène outbox : purge vs mark_played — STO-TRACKER-11 -------------------

def test_sync_journal_purge_removes_pending_by_seq(tmp_path):
    from effortless_mcp.ports import SyncJournal
    j = SyncJournal(str(tmp_path), now=lambda: "T")
    j.enqueue("create", {"a": 1})       # seq 1
    j.enqueue("transition", {"b": 2})   # seq 2
    j.enqueue("log_work", {"c": 3})     # seq 3
    assert j.purge([2]) == 1
    assert [e["seq"] for e in j.pending()] == [1, 3]
    # Purge idempotente (seq 2 déjà supprimé).
    assert j.purge([2]) == 0
    # None -> purge tout le reste.
    assert j.purge() == 2
    assert j.pending() == []


def test_sync_journal_purge_preserves_played(tmp_path):
    from effortless_mcp.ports import SyncJournal
    j = SyncJournal(str(tmp_path), now=lambda: "T")
    j.enqueue("create", {"a": 1})       # seq 1
    j.enqueue("transition", {"b": 2})   # seq 2
    j.mark_played([1])                  # seq 1 joué (audit)
    # purge ne touche QUE les ops en attente : seq 1 (joué) survit.
    assert j.purge() == 1               # seul seq 2 (pending) détruit
    c = j.counts()
    assert c == {"pending": 0, "played": 1, "total": 1}


def test_outbox_status_and_purge_tools(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_tracker_couple("jira", "EFL", "https://x/EFL")
        server.effortless_task_add("T1")
        server.effortless_task_add("T2")
        status = server.effortless_tracker_outbox_status()
        assert "2 en attente" in status
        out = server.effortless_tracker_outbox_purge("")
        assert "2 op" in out
        assert "0 en attente" in server.effortless_tracker_outbox_status()
        assert "Aucune opération" in server.effortless_tracker_pending()


def test_outbox_purge_rejects_bad_input(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        assert "invalide" in server.effortless_tracker_outbox_purge("{bad")
        assert "entiers" in server.effortless_tracker_outbox_purge('["x"]')


# --- Cycle de vie Epic/Story (epic_start / story_complete / epic_complete) — STO-CADRAGE-01

def _state(tmpdir):
    with open(os.path.join(tmpdir, ".effortless", "state.json"), encoding="utf-8") as f:
        return json.load(f)


def test_epic_start_creates_and_activates(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        out = server.effortless_epic_start("BILLING", "Facturation")
        assert "créé" in out
        st = _state(tmpdir)
        eid = st["active_epic_id"]
        # Nouvelle forme : <NNN>-Epic-Billing.
        assert eid.endswith("-Epic-Billing") and eid[:3].isdigit()
        assert st["active_story_id"] is None
        epic_file = os.path.join(tmpdir, ".effortless", "epics", eid, "epic.json")
        with open(epic_file, encoding="utf-8") as f:
            e = json.load(f)
        assert e["id"] == eid and e["zone"] == "BILLING" and e["status"] == "Open"
        assert e["stories"] == [] and isinstance(e["seq"], int)
        # Garde périmètre : un 2e Epic de même périmètre est refusé.
        assert "existe déjà" in server.effortless_epic_start("BILLING", "Autre")


def test_epic_start_guards(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        assert "zone requise" in server.effortless_epic_start("  ", "T")
        assert "title requis" in server.effortless_epic_start("Z", "  ")


def test_story_complete_requires_all_tasks_done(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_epic_start("BILLING", "Facturation")
        server.effortless_story_start("Story 1")
        server.effortless_task_add("T1")
        # Tâche Todo → refus.
        out = server.effortless_story_complete()
        assert "non Done" in out and "TSK-01" in out
        server.effortless_task_update("TSK-01", "Done")
        assert "clôturée" in server.effortless_story_complete()
        # Idempotent.
        assert "déjà Done" in server.effortless_story_complete()
        st = _state(tmpdir)
        sp = os.path.join(tmpdir, ".effortless", "epics", st["active_epic_id"], "stories",
                          st["active_story_id"], "story.json")
        with open(sp, encoding="utf-8") as f:
            assert json.load(f)["status"] == "Done"


def test_epic_complete_requires_all_stories_done(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        server.effortless_epic_start("BILLING", "Facturation")
        server.effortless_story_start("Story 1")
        # Story active Doing → epic_complete refuse.
        out = server.effortless_epic_complete()
        assert "non Done" in out
        # Clôture la story (sans tâches → 0 pending), puis l'Epic.
        assert "clôturée" in server.effortless_story_complete()
        assert "clôturé" in server.effortless_epic_complete()
        assert "déjà Done" in server.effortless_epic_complete()
        epic_file = os.path.join(tmpdir, ".effortless", "epics", _state(tmpdir)["active_epic_id"], "epic.json")
        with open(epic_file, encoding="utf-8") as f:
            assert json.load(f)["status"] == "Done"


# --- Nomenclature <NNN>-Epic/Story-<Périmètre> — STO-CADRAGE-02 ----------------

def _build_nomen_fixture(root):
    import io
    def wj(path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    eff = os.path.join(root, ".effortless")
    # EPIC-ALPHA (seq 1) : 2 stories ; EPIC-BETA (seq 2) : 1 story.
    wj(os.path.join(eff, "epics", "EPIC-ALPHA", "epic.json"),
       {"id": "EPIC-ALPHA", "zone": "ALPHA", "seq": 1, "status": "Open",
        "stories": ["STO-ALPHA-01", "STO-ALPHA-02"]})
    _titles = {"STO-ALPHA-01": "Cadrage initial", "STO-ALPHA-02": "Implémentation moteur"}
    for sid, ttl in _titles.items():
        wj(os.path.join(eff, "epics", "EPIC-ALPHA", "stories", sid, "story.json"),
           {"id": sid, "epic_id": "EPIC-ALPHA", "zone": "ALPHA", "title": ttl, "status": "Done"})
    wj(os.path.join(eff, "epics", "EPIC-BETA", "epic.json"),
       {"id": "EPIC-BETA", "zone": "BETA", "seq": 2, "status": "Open",
        "stories": ["STO-BETA-01"]})
    wj(os.path.join(eff, "epics", "EPIC-BETA", "stories", "STO-BETA-01", "story.json"),
       {"id": "STO-BETA-01", "epic_id": "EPIC-BETA", "zone": "BETA",
        "title": "Recette utilisateur", "status": "Doing"})
    wj(os.path.join(eff, "state.json"),
       {"active_epic_id": "EPIC-BETA", "active_story_id": "STO-BETA-01"})
    wj(os.path.join(eff, "backlog.json"),
       {"epics": [{"id": "EPIC-ALPHA"}, {"id": "EPIC-BETA"}, {"id": "EPIC-CORE"}]})
    # Doc de cadrage avec frontmatter.
    md = os.path.join(root, "cadrage", "EPIC-ALPHA", "STO-ALPHA-01", "00-FNC-GLO-x.md")
    os.makedirs(os.path.dirname(md), exist_ok=True)
    with io.open(md, "w", encoding="utf-8", newline="\n") as f:
        f.write("---\ntype: cadrage-story\nepic: EPIC-ALPHA\nstory: STO-ALPHA-01\n"
                "tags:\n  - cadrage/epic-alpha\n---\n\n# Doc\n")


def test_nomenclature_plan_maps_ids(tmp_path):
    from effortless_mcp.services.nomenclature import plan_nomenclature
    _build_nomen_fixture(str(tmp_path))
    plan = plan_nomenclature(str(tmp_path))
    assert plan["changed"] is True
    by_old = {e["old_id"]: e for e in plan["epics"]}
    assert by_old["EPIC-ALPHA"]["new_id"] == "001-Epic-Alpha"
    assert by_old["EPIC-BETA"]["new_id"] == "002-Epic-Beta"
    alpha_stories = {s["old_id"]: s["new_id"] for s in by_old["EPIC-ALPHA"]["stories"]}
    # Sujet dérivé du titre (EVO-011), pas du périmètre de l'Epic.
    assert alpha_stories == {
        "STO-ALPHA-01": "001-Story-Cadrage-Initial",
        "STO-ALPHA-02": "002-Story-Implementation-Moteur",
    }
    assert by_old["EPIC-BETA"]["stories"][0]["new_id"] == "001-Story-Recette-Utilisateur"


def test_nomenclature_apply_renames_and_rewrites(tmp_path):
    import io
    from effortless_mcp.services.nomenclature import apply_nomenclature, plan_nomenclature
    root = str(tmp_path)
    _build_nomen_fixture(root)
    report = apply_nomenclature(root, plan_nomenclature(root))
    assert report["epics_renamed"] == 2 and report["stories_renamed"] == 3
    eff = os.path.join(root, ".effortless")
    # Répertoires renommés (Story = sujet dérivé du titre).
    assert os.path.isdir(os.path.join(eff, "epics", "002-Epic-Beta", "stories", "001-Story-Recette-Utilisateur"))
    assert not os.path.exists(os.path.join(eff, "epics", "EPIC-BETA"))
    # epic.json réécrit (id + stories[]).
    with io.open(os.path.join(eff, "epics", "001-Epic-Alpha", "epic.json"), encoding="utf-8") as f:
        e = json.load(f)
    assert e["id"] == "001-Epic-Alpha" and e["stories"] == [
        "001-Story-Cadrage-Initial", "002-Story-Implementation-Moteur"]
    # story.json réécrit (id + epic_id).
    with io.open(os.path.join(eff, "epics", "002-Epic-Beta", "stories", "001-Story-Recette-Utilisateur", "story.json"), encoding="utf-8") as f:
        s = json.load(f)
    assert s["id"] == "001-Story-Recette-Utilisateur" and s["epic_id"] == "002-Epic-Beta"
    # state actif réécrit.
    with io.open(os.path.join(eff, "state.json"), encoding="utf-8") as f:
        st = json.load(f)
    assert st["active_epic_id"] == "002-Epic-Beta" and st["active_story_id"] == "001-Story-Recette-Utilisateur"
    # backlog : ids réels mappés, logique EPIC-CORE intact.
    with io.open(os.path.join(eff, "backlog.json"), encoding="utf-8") as f:
        ids = [x["id"] for x in json.load(f)["epics"]]
    assert ids == ["001-Epic-Alpha", "002-Epic-Beta", "EPIC-CORE"]
    # frontmatter réécrit.
    with io.open(os.path.join(root, "cadrage", "001-Epic-Alpha", "001-Story-Cadrage-Initial", "00-FNC-GLO-x.md"), encoding="utf-8") as f:
        fm = f.read()
    assert "epic: 001-Epic-Alpha" in fm and "story: 001-Story-Cadrage-Initial" in fm
    assert "cadrage/001-epic-alpha" in fm


def test_nomenclature_idempotent(tmp_path):
    from effortless_mcp.services.nomenclature import apply_nomenclature, plan_nomenclature
    root = str(tmp_path)
    _build_nomen_fixture(root)
    apply_nomenclature(root, plan_nomenclature(root))
    # 2e passe : plan sans changement, aucun renommage.
    plan2 = plan_nomenclature(root)
    assert plan2["changed"] is False
    report2 = apply_nomenclature(root, plan2)
    assert report2["epics_renamed"] == 0 and report2["stories_renamed"] == 0


def test_slugify_subject_variants():
    from effortless_mcp.services.nomenclature import slugify_subject
    # Parenthèses retirées, accents translittérés, stopword 'au' écarté, cap 4 mots.
    assert slugify_subject("Anti-dérive étendu au travail cadrage (gate)") == "Anti-Derive-Etendu-Travail"
    assert slugify_subject("Migration des données") == "Migration-Donnees"
    assert slugify_subject("Dispatch évolutions + moteur de rendu dérivé") == "Dispatch-Evolutions-Moteur-Rendu"
    assert slugify_subject("") == "Story"                 # repli
    assert slugify_subject("de la du des") == "De-La-Du-Des"  # tout stopword → brut


def test_migrate_nomenclature_tool_dry_run_then_apply(monkeypatch, tmp_path):
    from effortless_mcp import server
    monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", str(tmp_path))
    server.effortless_init("P", "d")
    _build_nomen_fixture(str(tmp_path))  # ajoute des epics à migrer
    dry = server.effortless_migrate_nomenclature()
    assert "DRY-RUN" in dry and "EPIC-ALPHA" in dry and "001-Epic-Alpha" in dry
    # Rien appliqué au dry-run.
    assert os.path.isdir(os.path.join(str(tmp_path), ".effortless", "epics", "EPIC-ALPHA"))
    out = server.effortless_migrate_nomenclature(confirm=True)
    assert "migrée" in out
    assert os.path.isdir(os.path.join(str(tmp_path), ".effortless", "epics", "001-Epic-Alpha"))


# --- Cadrage niveau Epic (charte + registre stories) — 003-Story-Cadrage -------

def _epic_fixture(root, epic_id="002-Epic-Demo", zone="DEMO"):
    import io
    def wj(p, d):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(d, io.open(p, "w", encoding="utf-8", newline="\n"), indent=2, ensure_ascii=False)
    eff = os.path.join(root, ".effortless", "epics", epic_id)
    wj(os.path.join(eff, "epic.json"),
       {"id": epic_id, "zone": zone, "seq": 2, "title": "Démo", "status": "Open",
        "stories": ["001-Story-Demo", "002-Story-Demo"]})
    wj(os.path.join(eff, "stories", "001-Story-Demo", "story.json"),
       {"id": "001-Story-Demo", "epic_id": epic_id, "seq": 1, "title": "Première", "status": "Done"})
    wj(os.path.join(eff, "stories", "002-Story-Demo", "story.json"),
       {"id": "002-Story-Demo", "epic_id": epic_id, "seq": 2, "title": "Deuxième | avec pipe", "status": "Doing"})
    return epic_id


def test_epic_charter_scaffolded_once_not_overwritten(tmp_path):
    from effortless_mcp.services.epic_cadrage import write_epic_charter
    root = str(tmp_path)
    eid = _epic_fixture(root)
    assert write_epic_charter(root, eid) is True
    charter = os.path.join(root, "cadrage", eid, "0-Epic.md")
    with open(charter, encoding="utf-8") as f:
        txt = f.read()
    assert "type: cadrage-epic" in txt and "perimetre: Demo" in txt and "Charte d'Epic" in txt
    # Édition auteur préservée : re-scaffold ne réécrit pas.
    with open(charter, "w", encoding="utf-8") as f:
        f.write(txt + "\nAJOUT AUTEUR\n")
    assert write_epic_charter(root, eid) is False
    with open(charter, encoding="utf-8") as f:
        assert "AJOUT AUTEUR" in f.read()


def test_story_registry_is_derived_render(tmp_path):
    from effortless_mcp.services.epic_cadrage import render_story_registry
    root = str(tmp_path)
    eid = _epic_fixture(root)
    render_story_registry(root, eid)
    with open(os.path.join(root, "cadrage", eid, "1-Stories.md"), encoding="utf-8") as f:
        reg = f.read()
    assert "type: cadrage-epic-registre" in reg
    assert "| 1 | 001-Story-Demo | Première | Done |" in reg
    # Pipe échappé, statut Doing reflété.
    assert "Deuxième \\| avec pipe" in reg and "Doing" in reg
    # Régénéré : un changement de statut dans story.json se reflète au re-render.
    sp = os.path.join(root, ".effortless", "epics", eid, "stories", "002-Story-Demo", "story.json")
    with open(sp, encoding="utf-8") as f:
        s = json.load(f)
    s["status"] = "Done"
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)
    render_story_registry(root, eid)
    with open(os.path.join(root, "cadrage", eid, "1-Stories.md"), encoding="utf-8") as f:
        assert "| 2 | 002-Story-Demo | Deuxième \\| avec pipe | Done |" in f.read()


def test_epic_start_scaffolds_epic_cadrage(monkeypatch, tmp_path):
    from effortless_mcp import server
    monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", str(tmp_path))
    server.effortless_init("P", "d")
    server.effortless_epic_start("PAYROLL", "Paie")
    eid = _state(str(tmp_path))["active_epic_id"]
    assert os.path.exists(os.path.join(str(tmp_path), "cadrage", eid, "0-Epic.md"))
    assert os.path.exists(os.path.join(str(tmp_path), "cadrage", eid, "1-Stories.md"))
    # Une Story ajoutée apparaît dans le registre régénéré.
    server.effortless_story_start("Story paie")
    sid = _state(str(tmp_path))["active_story_id"]
    with open(os.path.join(str(tmp_path), "cadrage", eid, "1-Stories.md"), encoding="utf-8") as f:
        assert sid in f.read()


def test_parse_doc_code_uppercase_run():
    from effortless_mcp.services.cadrage_frontmatter import parse_doc_code
    assert parse_doc_code("05-FNC-SPE-specifications.md") == "FNC-SPE"
    assert parse_doc_code("02-BQO-questions.md") == "BQO"
    assert parse_doc_code("07-MET-PLN-plan-action.md") == "MET-PLN"
    assert parse_doc_code("00-FNC-GLO-glossaire") == "FNC-GLO"


def test_story_doc_frontmatter_schema():
    from effortless_mcp.services.cadrage_frontmatter import story_doc_frontmatter
    fm = story_doc_frontmatter("003-Epic-Cadrage", "004-Story-Cadrage",
                               "05-FNC-SPE-specifications.md", "A-specs")
    assert "type: cadrage-story" in fm
    assert "epic: 003-Epic-Cadrage" in fm and "story: 004-Story-Cadrage" in fm
    assert "code: FNC-SPE" in fm and "phase: A-specs" in fm
    assert "  - cadrage/003-epic-cadrage" in fm and "  - cadrage/fnc-spe" in fm


def test_scaffold_story_docs_creates_missing_never_overwrites(tmp_path):
    from effortless_mcp.services.cadrage_frontmatter import scaffold_story_docs
    root = str(tmp_path)
    eid, sid = "003-Epic-Cadrage", "004-Story-Cadrage"
    docs = [("O-analyse", "00-FNC-GLO-glossaire.md"), ("A-specs", "05-FNC-SPE-specifications.md")]
    created = scaffold_story_docs(root, eid, sid, docs)
    assert len(created) == 2
    glo = os.path.join(root, "cadrage", eid, sid, "00-FNC-GLO-glossaire.md")
    with open(glo, encoding="utf-8") as f:
        assert "type: cadrage-story" in f.read()
    # Édition auteur préservée : re-scaffold n'écrase pas, n'en recrée aucun.
    with open(glo, "w", encoding="utf-8") as f:
        f.write("EDITÉ")
    again = scaffold_story_docs(root, eid, sid, docs)
    assert again == []
    with open(glo, encoding="utf-8") as f:
        assert f.read() == "EDITÉ"


def test_phase_docs_from_workflow_flattens():
    from effortless_mcp.services.cadrage_frontmatter import phase_docs_from_workflow
    cfg = {"workflow": {"phases": [
        {"id": "O-analyse", "required_documents": ["cadrage/E/S/00-FNC-GLO-glossaire.md"]},
        {"id": "L-plan", "required_documents": ["cadrage/E/S/07-MET-PLN-plan-action.md"]},
    ]}}
    pairs = phase_docs_from_workflow(cfg)
    assert pairs == [("O-analyse", "00-FNC-GLO-glossaire.md"), ("L-plan", "07-MET-PLN-plan-action.md")]


def test_init_scaffolds_obsidian_ready_docs(monkeypatch, tmp_path):
    from effortless_mcp import server
    monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", str(tmp_path))
    server.effortless_init("P", "d")
    base = os.path.join(str(tmp_path), "cadrage", "EPIC-PROJET", "STO-PROJET-01")
    glo = os.path.join(base, "00-FNC-GLO-glossaire.md")
    pln = os.path.join(base, "07-MET-PLN-plan-action.md")
    assert os.path.exists(glo) and os.path.exists(pln)
    with open(glo, encoding="utf-8") as f:
        txt = f.read()
    assert "type: cadrage-story" in txt and "code: FNC-GLO" in txt and "phase: O-analyse" in txt


def test_story_start_scaffolds_obsidian_docs(monkeypatch, tmp_path):
    from effortless_mcp import server
    monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", str(tmp_path))
    server.effortless_init("P", "d")
    server.effortless_epic_start("BILLING", "Facturation")
    server.effortless_story_start("Story facture")
    st = _state(str(tmp_path))
    eid, sid = st["active_epic_id"], st["active_story_id"]
    spe = os.path.join(str(tmp_path), "cadrage", eid, sid, "05-FNC-SPE-specifications.md")
    assert os.path.exists(spe)
    with open(spe, encoding="utf-8") as f:
        assert f"story: {sid}" in f.read()


def test_cadrage_docs_scaffold_backfills_active_story(monkeypatch, tmp_path):
    from effortless_mcp import server
    monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", str(tmp_path))
    server.effortless_init("P", "d")
    st = _state(str(tmp_path))
    eid, sid = st["active_epic_id"], st["active_story_id"]
    # Supprime un doc scaffoldé pour simuler une Story pré-hook incomplète.
    glo = os.path.join(str(tmp_path), "cadrage", eid, sid, "00-FNC-GLO-glossaire.md")
    os.remove(glo)
    out = server.effortless_cadrage_docs_scaffold()
    assert "00-FNC-GLO-glossaire" in out and os.path.exists(glo)
    # Idempotent : second appel = no-op.
    assert "no-op" in server.effortless_cadrage_docs_scaffold()


def test_init_modes_normalize_and_aliases():
    from effortless_mcp.services.init_modes import normalize_mode, AGILE, VCYCLE
    assert normalize_mode("agile") == AGILE
    assert normalize_mode("opale") == AGILE
    assert normalize_mode("") == AGILE
    assert normalize_mode("cycle-en-v") == VCYCLE
    assert normalize_mode("Jira") == VCYCLE
    with pytest.raises(ValueError):
        normalize_mode("waterfall")


def test_build_workflow_phases_per_mode():
    from effortless_mcp.services.init_modes import build_workflow
    agile = build_workflow("agile", "cadrage/E/S")
    assert [p.id for p in agile.phases] == ["O-analyse", "P-cadrage", "A-specs", "L-plan"]
    v = build_workflow("v-cycle", "cadrage/E/S")
    assert [p.id for p in v.phases] == [
        "B-besoins", "S-specifications", "C-conception", "R-realisation", "V-verification"]
    # Docs préfixés par le docs_root.
    assert v.phases[0].required_documents[0] == "cadrage/E/S/00-FNC-BES-besoins.md"


def test_init_agile_is_default(monkeypatch, tmp_path):
    from effortless_mcp import server
    monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", str(tmp_path))
    server.effortless_init("P", "d")
    cfg = json.load(open(os.path.join(str(tmp_path), "effortless.json"), encoding="utf-8"))
    assert cfg["settings"]["init_mode"] == "agile"
    assert [p["id"] for p in cfg["workflow"]["phases"]][0] == "O-analyse"


def test_init_vcycle_mode(monkeypatch, tmp_path):
    from effortless_mcp import server
    monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", str(tmp_path))
    out = server.effortless_init("P", "d", mode="cycle-en-v")
    assert "v-cycle" in out and "import" in out
    cfg = json.load(open(os.path.join(str(tmp_path), "effortless.json"), encoding="utf-8"))
    assert cfg["settings"]["init_mode"] == "v-cycle"
    pids = [p["id"] for p in cfg["workflow"]["phases"]]
    assert pids == ["B-besoins", "S-specifications", "C-conception", "R-realisation", "V-verification"]
    # Docs v-cycle scaffoldés Obsidian-ready avec frontmatter.
    bes = os.path.join(str(tmp_path), "cadrage", "EPIC-PROJET", "STO-PROJET-01", "00-FNC-BES-besoins.md")
    assert os.path.exists(bes)
    with open(bes, encoding="utf-8") as f:
        assert "code: FNC-BES" in f.read()


def test_init_rejects_unknown_mode(monkeypatch, tmp_path):
    from effortless_mcp import server
    monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", str(tmp_path))
    out = server.effortless_init("P", "d", mode="waterfall")
    assert out.startswith("Error:")
    assert not os.path.exists(os.path.join(str(tmp_path), "effortless.json"))


def test_bqo_add_and_render_project_questions(tmp_path):
    from effortless_mcp.services.bqo import add_project_question, load_project_questions
    root = str(tmp_path)
    q1 = add_project_question(root, "Faut-il gater l'enqueue en dogfood ?")
    q2 = add_project_question(root, "Registre pipe | échappé ?")
    assert q1["id"] == "PQ-001" and q2["id"] == "PQ-002"
    assert load_project_questions(root)["questions"][0]["status"] == "open"
    with open(os.path.join(root, "cadrage", "5-Questions.md"), encoding="utf-8") as f:
        doc = f.read()
    assert "type: cadrage-projet" in doc
    assert "| PQ-001 |" in doc and "Registre pipe \\| échappé" in doc


def test_bqo_graduate_to_epic(tmp_path):
    from effortless_mcp.services.bqo import add_project_question, graduate_question, load_project_questions
    root = str(tmp_path)
    eid = _epic_fixture(root)  # 002-Epic-Demo
    q = add_project_question(root, "Comment borner le périmètre de l'Epic ?")
    graduated = graduate_question(root, q["id"], eid)
    assert graduated["status"] == "graduated" and graduated["epic"] == eid
    # Question copiée dans epic.json["bqo"].
    ej = json.load(open(os.path.join(root, ".effortless", "epics", eid, "epic.json"), encoding="utf-8"))
    assert any(b["id"] == q["id"] for b in ej["bqo"])
    # Rendu BQO d'Epic dérivé.
    with open(os.path.join(root, "cadrage", eid, "2-BQO.md"), encoding="utf-8") as f:
        bqo = f.read()
    assert "type: cadrage-epic-bqo" in bqo and q["id"] in bqo
    # Graduation idempotente (pas de doublon dans le BQO).
    graduate_question(root, q["id"], eid)
    ej2 = json.load(open(os.path.join(root, ".effortless", "epics", eid, "epic.json"), encoding="utf-8"))
    assert len([b for b in ej2["bqo"] if b["id"] == q["id"]]) == 1


def test_bqo_graduate_unknown_returns_none(tmp_path):
    from effortless_mcp.services.bqo import graduate_question, add_project_question
    root = str(tmp_path)
    _epic_fixture(root)
    q = add_project_question(root, "X")
    assert graduate_question(root, q["id"], "999-Epic-Absent") is None
    assert graduate_question(root, "PQ-999", "002-Epic-Demo") is None


def test_bqo_tools_end_to_end(monkeypatch, tmp_path):
    from effortless_mcp import server
    monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", str(tmp_path))
    server.effortless_init("P", "d")
    server.effortless_bqo_ask("Question transverse ?")
    eid = _state(str(tmp_path))["active_epic_id"]
    out = server.effortless_bqo_graduate("PQ-001", eid)
    assert "graduée" in out
    listing = server.effortless_bqo_list()
    assert "PQ-001" in listing and "graduated" in listing


# ---- Évolutions + backlog : dispatch + rendu dérivé (004-Story-Process / EVO-010) ----

def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_evolution_add_render_and_sequence(tmp_path):
    from effortless_mcp.services.evolutions import add_evolution, load_evolutions
    root = str(tmp_path)
    e1 = add_evolution(root, "besoin", "Titre un", "détail un")
    e2 = add_evolution(root, "finding", "Titre | deux")
    assert e1["id"] == "EVO-001" and e2["id"] == "EVO-002"
    assert len(load_evolutions(root)["evolutions"]) == 2
    md = _read_text(os.path.join(root, "cadrage", "4-Evolutions.md"))
    assert "EVO-001" in md and "Titre un" in md and "besoin" in md
    assert "Titre \\| deux" in md          # pipe échappé dans le tableau
    assert "détail un" in md               # section Détails


def test_evolution_add_rejects_bad_type_and_status(tmp_path):
    from effortless_mcp.services.evolutions import add_evolution
    root = str(tmp_path)
    with pytest.raises(ValueError):
        add_evolution(root, "bug", "x")
    with pytest.raises(ValueError):
        add_evolution(root, "finding", "x", status="Wontfix")


def test_evolution_set_and_graduate(tmp_path):
    from effortless_mcp.services.evolutions import add_evolution, set_evolution, graduate_evolution
    root = str(tmp_path)
    add_evolution(root, "besoin", "T")
    upd = set_evolution(root, "EVO-001", status="En cours", resolution="fait")
    assert upd["status"] == "En cours" and upd["resolution"] == "fait"
    g = graduate_evolution(root, "EVO-001", "005-Epic-Obsidian")
    assert g["epic"] == "005-Epic-Obsidian"
    md = _read_text(os.path.join(root, "cadrage", "4-Evolutions.md"))
    assert "005-Epic-Obsidian" in md and "fait" in md


def test_evolution_graduate_planned_moves_to_en_cours(tmp_path):
    from effortless_mcp.services.evolutions import add_evolution, graduate_evolution
    root = str(tmp_path)
    add_evolution(root, "besoin", "T")  # Planifié par défaut
    assert graduate_evolution(root, "EVO-001", "005-Epic-X")["status"] == "En cours"


def test_evolution_graduate_resolved_not_downgraded(tmp_path):
    from effortless_mcp.services.evolutions import add_evolution, graduate_evolution
    root = str(tmp_path)
    add_evolution(root, "finding", "T", status="Résolu")
    assert graduate_evolution(root, "EVO-001", "005-Epic-X")["status"] == "Résolu"


def test_evolution_graduate_unknown_returns_none(tmp_path):
    from effortless_mcp.services.evolutions import graduate_evolution
    assert graduate_evolution(str(tmp_path), "EVO-999", "005-Epic-X") is None


def test_backlog_reconcile_from_real_epics(tmp_path):
    from effortless_mcp.services.backlog import reconcile_backlog
    root = str(tmp_path)
    _epic_fixture(root)  # 002-Epic-Demo : 1 Done / 2 stories
    data = reconcile_backlog(root)
    ent = next(e for e in data["epics"] if e["id"] == "002-Epic-Demo")
    assert ent["stories_done"] == 1 and ent["stories_total"] == 2
    assert ent["perimetre"] == "Demo" and ent["status"] == "Open"
    md = _read_text(os.path.join(root, "cadrage", "3-Backlog.md"))
    assert "002-Epic-Demo" in md and "1/2" in md


def test_backlog_reconcile_preserves_editorial_and_pinned(tmp_path):
    from effortless_mcp.services.backlog import reconcile_backlog, _backlog_path, _write_json
    root = str(tmp_path)
    _epic_fixture(root)
    _write_json(_backlog_path(root), {"version": 1, "epics": [
        {"id": "EPIC-CORE", "perimetre": "Core", "intent": "Noyau", "status": "Done"},
        {"id": "002-Epic-Demo", "perimetre": "Demo", "intent": "Intention éditoriale", "status": "Todo"},
    ]})
    data = reconcile_backlog(root)
    core = next(e for e in data["epics"] if e["id"] == "EPIC-CORE")
    demo = next(e for e in data["epics"] if e["id"] == "002-Epic-Demo")
    assert core["intent"] == "Noyau"                     # entrée sans dir préservée
    assert demo["intent"] == "Intention éditoriale"      # éditorial préservé
    assert demo["status"] == "Open" and demo["stories_done"] == 1  # état dérivé du réel


def test_backlog_reconcile_appends_new_epic(tmp_path):
    from effortless_mcp.services.backlog import reconcile_backlog
    root = str(tmp_path)
    _epic_fixture(root, epic_id="007-Epic-New", zone="NEW")
    ids = [e["id"] for e in reconcile_backlog(root)["epics"]]
    assert "007-Epic-New" in ids


def test_evolution_tools_end_to_end(monkeypatch, tmp_path):
    from effortless_mcp import server
    monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", str(tmp_path))
    server.effortless_init("P", "d")
    out = server.effortless_evolution_add("besoin", "Config Obsidian embarquée", "tweak + embed")
    assert "EVO-001" in out
    grad = server.effortless_evolution_graduate("EVO-001", zone="OBSIDIAN", title="Config Obsidian")
    assert "graduée" in grad
    # L'Epic est créé et inscrit dans le backlog (rendu dérivé, sans drift).
    backlog_md = _read_text(os.path.join(str(tmp_path), "cadrage", "3-Backlog.md"))
    assert "-Epic-Obsidian" in backlog_md
    evo_md = _read_text(os.path.join(str(tmp_path), "cadrage", "4-Evolutions.md"))
    assert "EVO-001" in evo_md and "-Epic-Obsidian" in evo_md
