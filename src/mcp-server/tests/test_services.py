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
        write_markdown_frontmatter(doc2_path, {"phase": "O-analyse", "statut": "En attente"}, "## Summary Table\n## Question Details\n")

        is_valid, checklist, reasons = validate_phase_documents(
            tmpdir, current_phase_id, required_documents, questions_path
        )
        assert not is_valid
        assert any("Unresolved BQO" in r for r in reasons)

        # 4. Résolu
        write_markdown_frontmatter(doc2_path, {"phase": "O-analyse", "statut": "Résolu"}, "## Summary Table\n## Question Details\n")
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

        # complexity valide stockée
        msg = server.effortless_task_add("T simple", complexity="simple")
        tsk_id = msg.split("Task ")[1].split(" ")[0]
        with open(os.path.join(tmpdir, ".effortless", "tasks", f"{tsk_id}.json"), encoding="utf-8") as f:
            assert json.load(f)["complexity"] == "simple"

        # absente => None
        msg2 = server.effortless_task_add("T sans")
        tsk_id2 = msg2.split("Task ")[1].split(" ")[0]
        with open(os.path.join(tmpdir, ".effortless", "tasks", f"{tsk_id2}.json"), encoding="utf-8") as f:
            assert json.load(f)["complexity"] is None

        # valeur invalide rejetée, pas d'écriture
        before = len(os.listdir(os.path.join(tmpdir, ".effortless", "tasks")))
        bad = server.effortless_task_add("T bad", complexity="trivial")
        assert "invalid" in bad
        after = len(os.listdir(os.path.join(tmpdir, ".effortless", "tasks")))
        assert before == after


def test_task_classify(monkeypatch):
    from effortless_mcp import server
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("EFFORTLESS_PROJECT_ROOT", tmpdir)
        server.effortless_init("P", "d")
        msg = server.effortless_task_add("T")
        tsk_id = msg.split("Task ")[1].split(" ")[0]

        # classification réussie
        ok = server.effortless_task_classify(tsk_id, "complex")
        assert tsk_id in ok and "complex" in ok
        with open(os.path.join(tmpdir, ".effortless", "tasks", f"{tsk_id}.json"), encoding="utf-8") as f:
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
        tasks_dir = os.path.join(tmpdir, ".effortless", "tasks")

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
