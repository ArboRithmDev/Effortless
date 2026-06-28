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

def deploy_to_mcp_clients(project_root: str) -> List[Dict[str, Any]]:
    """
    Détecte et configure le serveur MCP et ses Skills sur l'ensemble des CLI IA
    (Claude Desktop, Claude Code, Codex, Mistral Vibe, Copilot CLI, Antigravity).
    """
    results = []
    source_skill = os.path.join(project_root, "skills", "effortless", "SKILL.md")

    # 1. Claude Desktop Config
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

    if claude_desktop_path:
        os.makedirs(os.path.dirname(claude_desktop_path), exist_ok=True)
        config_data = {"mcpServers": {}}
        
        if os.path.exists(claude_desktop_path):
            try:
                with open(claude_desktop_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception:
                pass

        if "mcpServers" not in config_data:
            config_data["mcpServers"] = {}

        config_data["mcpServers"]["effortless"] = {
            "command": os.path.join(
                project_root, "src", "mcp-server", ".venv", "bin", "effortless-mcp"
            ),
            "cwd": project_root
        }

        try:
            with open(claude_desktop_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
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
        skills_target = os.path.join(claude_code_dir, "skills")
        os.makedirs(skills_target, exist_ok=True)
        target_file = os.path.join(skills_target, "effortless.md")
        if os.path.exists(source_skill):
            try:
                shutil.copy2(source_skill, target_file)
                results.append({
                    "name": "Claude Code",
                    "status": "success",
                    "path": target_file,
                    "action": "Copied instruction Skill"
                })
            except Exception as e:
                results.append({
                    "name": "Claude Code",
                    "status": "error",
                    "path": target_file,
                    "action": f"Failed: {str(e)}"
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

        # Configurer TOML
        toml_path = os.path.join(codex_dir, "config.toml")
        mcp_cmd = os.path.join(project_root, "src", "mcp-server", ".venv", "bin", "effortless-mcp")
        block = f"[mcp_servers.effortless]\ncommand = '{mcp_cmd}'\nargs = []\n"
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

        # Configurer TOML
        toml_path = os.path.join(vibe_dir, "config.toml")
        mcp_cmd = os.path.join(project_root, "src", "mcp-server", ".venv", "bin", "effortless-mcp")
        block = f"[[mcp_servers]]\nname = \"effortless\"\ntransport = \"stdio\"\ncommand = \"{mcp_cmd}\"\nargs = []\n"
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
        if os.path.exists(source_skill):
            try:
                shutil.copy2(source_skill, target_file)
                results.append({
                    "name": "GitHub Copilot",
                    "status": "success",
                    "path": target_file,
                    "action": "Copied instruction Skill"
                })
            except Exception as e:
                results.append({
                    "name": "GitHub Copilot",
                    "status": "error",
                    "path": target_file,
                    "action": f"Failed: {str(e)}"
                })

    # 6. Antigravity CLI
    antigravity_plugins_dir = os.path.expanduser("~/.gemini/config/plugins")
    if os.path.exists(os.path.expanduser("~/.gemini/config")):
        os.makedirs(antigravity_plugins_dir, exist_ok=True)
        target_plugin_dir = os.path.join(antigravity_plugins_dir, "effortless")
        os.makedirs(os.path.join(target_plugin_dir, "skills", "effortless"), exist_ok=True)
        
        target_skill = os.path.join(target_plugin_dir, "skills", "effortless", "SKILL.md")
        
        if os.path.exists(source_skill):
            try:
                shutil.copy2(source_skill, target_skill)
                # Créer le plugin.json
                plugin_json = {
                    "name": "effortless",
                    "version": "0.3.0",
                    "description": "Framework de gestion de projet agnostique piloté par IA"
                }
                with open(os.path.join(target_plugin_dir, "plugin.json"), "w", encoding="utf-8") as f:
                    json.dump(plugin_json, f, indent=2)
                    
                results.append({
                    "name": "Antigravity CLI",
                    "status": "success",
                    "path": target_plugin_dir,
                    "action": "Installed plugin and Skill"
                })
            except Exception as e:
                results.append({
                    "name": "Antigravity CLI",
                    "status": "error",
                    "path": target_plugin_dir,
                    "action": f"Failed to install plugin: {str(e)}"
                })

    return results
