import os
import json
import shutil
import sys
from typing import List, Dict, Any


def inject_toml_block(config_path: str, block: str):
    """
    Injecte de manière idempotente un bloc TOML délimité par des marqueurs Effortless.
    """
    start_marker = "# EFFORTLESS:START"
    end_marker = "# EFFORTLESS:END"

    existing = ""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = f.read()
        except Exception:
            pass

    if start_marker in existing and end_marker in existing:
        # Remplacer le bloc existant
        before = existing.split(start_marker)[0]
        after = existing.split(end_marker)[1]
        new_content = before + start_marker + "\n" + block.strip() + "\n" + end_marker + after
    else:
        # Appendre à la fin
        new_content = existing.strip() + "\n\n" + start_marker + "\n" + block.strip() + "\n" + end_marker + "\n"

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def inject_json_mcp_server(config_path: str, server_name: str, entry: Dict[str, Any]):
    """
    Déclare/met à jour de manière idempotente un serveur MCP dans un fichier de
    configuration JSON exposant une clé `mcpServers`. Préserve les autres serveurs
    et le reste de la configuration. UTF-8 sans BOM, accents conservés.
    """
    config_data: Dict[str, Any] = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception:
            config_data = {}

    if not isinstance(config_data, dict):
        config_data = {}
    if not isinstance(config_data.get("mcpServers"), dict):
        config_data["mcpServers"] = {}

    config_data["mcpServers"][server_name] = entry

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)


def deploy_to_mcp_clients(project_root: str) -> List[Dict[str, Any]]:
    """
    Détecte et configure le serveur MCP et ses Skills sur l'ensemble des CLI IA
    (Claude Desktop, Claude Code, Codex, Mistral Vibe, Copilot CLI, Antigravity).

    Le serveur MCP est déclaré GLOBALEMENT sur chaque client, en injectant la
    variable d'environnement EFFORTLESS_PROJECT_ROOT (le serveur l'utilise pour
    localiser le projet : la plupart des clients ne fixent pas le cwd sur la racine).
    """
    results = []
    # Le Skill et le binaire MCP vivent dans l'INSTALLATION Effortless (venv), pas dans le
    # projet cible. project_root ne sert qu'à pointer les DONNÉES (env EFFORTLESS_PROJECT_ROOT).
    from effortless_mcp.server import get_install_root
    install_root = get_install_root()
    source_skill = os.path.join(install_root, "skills", "effortless", "SKILL.md")
    mcp_cmd = os.path.join(
        install_root, "src", "mcp-server", ".venv", "bin", "effortless-mcp"
    )
    # Entrée MCP commune aux clients JSON.
    json_entry = {
        "command": mcp_cmd,
        "args": [],
        "env": {"EFFORTLESS_PROJECT_ROOT": project_root},
    }

    # 1. Claude Desktop
    claude_desktop_path = None
    if sys.platform == "darwin":
        claude_desktop_path = os.path.expanduser(
            "~/Library/Application Support/Claude/claude_desktop_config.json"
        )
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            claude_desktop_path = os.path.join(
                appdata, "Claude", "claude_desktop_config.json"
            )

    if claude_desktop_path and os.path.isdir(os.path.dirname(claude_desktop_path)):
        try:
            inject_json_mcp_server(claude_desktop_path, "effortless", json_entry)
            results.append({
                "name": "Claude Desktop",
                "status": "success",
                "path": claude_desktop_path,
                "action": "Configured MCP server"
            })
        except Exception as e:
            results.append({
                "name": "Claude Desktop",
                "status": "error",
                "path": claude_desktop_path,
                "action": f"Failed to configure: {str(e)}"
            })

    # 2. Claude Code
    claude_code_dir = os.path.expanduser("~/.claude")
    if os.path.exists(claude_code_dir):
        # 2a. Déclaration du serveur MCP dans ~/.claude.json (global)
        claude_code_config = os.path.expanduser("~/.claude.json")
        mcp_action = "Configured MCP server"
        mcp_status = "success"
        try:
            inject_json_mcp_server(claude_code_config, "effortless", json_entry)
        except Exception as e:
            mcp_status = "error"
            mcp_action = f"Failed to configure MCP: {str(e)}"

        # 2b. Copie du Skill d'instruction
        skills_target = os.path.join(claude_code_dir, "skills")
        os.makedirs(skills_target, exist_ok=True)
        target_file = os.path.join(skills_target, "effortless.md")
        if os.path.exists(source_skill):
            try:
                shutil.copy2(source_skill, target_file)
                if mcp_status == "success":
                    mcp_action = "Configured MCP server and copied Skill"
            except Exception as e:
                if mcp_status == "success":
                    mcp_status = "error"
                    mcp_action = f"MCP configured but Skill copy failed: {str(e)}"

        results.append({
            "name": "Claude Code",
            "status": mcp_status,
            "path": claude_code_config,
            "action": mcp_action
        })

    # 3. Codex (OpenAI)
    codex_dir = os.path.expanduser("~/.codex")
    if os.path.exists(codex_dir):
        skills_target = os.path.join(codex_dir, "skills", "effortless")
        os.makedirs(skills_target, exist_ok=True)
        target_file = os.path.join(skills_target, "SKILL.md")

        # Copier Skill
        skill_copied = False
        if os.path.exists(source_skill):
            try:
                shutil.copy2(source_skill, target_file)
                skill_copied = True
            except Exception:
                pass

        # Configurer TOML (avec env pour localiser le projet)
        toml_path = os.path.join(codex_dir, "config.toml")
        block = (
            "[mcp_servers.effortless]\n"
            f"command = '{mcp_cmd}'\n"
            "args = []\n"
            f"env = {{ EFFORTLESS_PROJECT_ROOT = '{project_root}' }}\n"
        )
        try:
            inject_toml_block(toml_path, block)
            results.append({
                "name": "Codex",
                "status": "success",
                "path": toml_path,
                "action": "Configured MCP server and copied Skill" if skill_copied else "Configured MCP server"
            })
        except Exception as e:
            results.append({
                "name": "Codex",
                "status": "error",
                "path": toml_path,
                "action": f"Failed to configure: {str(e)}"
            })

    # 4. Mistral Vibe
    vibe_dir = os.path.expanduser("~/.vibe")
    if os.path.exists(vibe_dir):
        skills_target = os.path.join(vibe_dir, "skills", "effortless")
        os.makedirs(skills_target, exist_ok=True)
        target_file = os.path.join(skills_target, "SKILL.md")

        # Copier Skill
        skill_copied = False
        if os.path.exists(source_skill):
            try:
                shutil.copy2(source_skill, target_file)
                skill_copied = True
            except Exception:
                pass

        # Configurer TOML (avec env pour localiser le projet)
        toml_path = os.path.join(vibe_dir, "config.toml")
        block = (
            "[[mcp_servers]]\n"
            "name = \"effortless\"\n"
            "transport = \"stdio\"\n"
            f"command = \"{mcp_cmd}\"\n"
            "args = []\n"
            f"env = {{ EFFORTLESS_PROJECT_ROOT = \"{project_root}\" }}\n"
        )
        try:
            inject_toml_block(toml_path, block)
            results.append({
                "name": "Mistral Vibe",
                "status": "success",
                "path": toml_path,
                "action": "Configured MCP server and copied Skill" if skill_copied else "Configured MCP server"
            })
        except Exception as e:
            results.append({
                "name": "Mistral Vibe",
                "status": "error",
                "path": toml_path,
                "action": f"Failed to configure: {str(e)}"
            })

    # 5. GitHub Copilot CLI
    copilot_dir = os.path.expanduser("~/.copilot")
    if os.path.exists(copilot_dir):
        skills_target = os.path.join(copilot_dir, "skills", "effortless")
        os.makedirs(skills_target, exist_ok=True)
        target_file = os.path.join(skills_target, "SKILL.md")

        skill_copied = False
        if os.path.exists(source_skill):
            try:
                shutil.copy2(source_skill, target_file)
                skill_copied = True
            except Exception:
                pass

        # Déclaration du serveur MCP dans ~/.copilot/mcp-config.json
        copilot_config = os.path.join(copilot_dir, "mcp-config.json")
        try:
            inject_json_mcp_server(copilot_config, "effortless", json_entry)
            results.append({
                "name": "GitHub Copilot",
                "status": "success",
                "path": copilot_config,
                "action": "Configured MCP server and copied Skill" if skill_copied else "Configured MCP server"
            })
        except Exception as e:
            results.append({
                "name": "GitHub Copilot",
                "status": "error",
                "path": copilot_config,
                "action": f"Failed to configure: {str(e)}"
            })

    # 6. Antigravity CLI (Gemini)
    gemini_config_dir = os.path.expanduser("~/.gemini/config")
    if os.path.exists(gemini_config_dir):
        skill_copied = False
        if os.path.exists(source_skill):
            try:
                antigravity_plugins_dir = os.path.join(gemini_config_dir, "plugins")
                target_plugin_dir = os.path.join(antigravity_plugins_dir, "effortless")
                os.makedirs(os.path.join(target_plugin_dir, "skills", "effortless"), exist_ok=True)
                target_skill = os.path.join(target_plugin_dir, "skills", "effortless", "SKILL.md")
                shutil.copy2(source_skill, target_skill)
                plugin_json = {
                    "name": "effortless",
                    "version": "0.3.0",
                    "description": "Framework de gestion de projet agnostique piloté par IA"
                }
                with open(os.path.join(target_plugin_dir, "plugin.json"), "w", encoding="utf-8") as f:
                    json.dump(plugin_json, f, indent=2)
                skill_copied = True
            except Exception:
                pass

        # Déclaration du serveur MCP dans ~/.gemini/settings.json
        gemini_settings = os.path.expanduser("~/.gemini/settings.json")
        try:
            inject_json_mcp_server(gemini_settings, "effortless", json_entry)
            results.append({
                "name": "Antigravity CLI",
                "status": "success",
                "path": gemini_settings,
                "action": "Configured MCP server and installed plugin/Skill" if skill_copied else "Configured MCP server"
            })
        except Exception as e:
            results.append({
                "name": "Antigravity CLI",
                "status": "error",
                "path": gemini_settings,
                "action": f"Failed to configure: {str(e)}"
            })

    return results
