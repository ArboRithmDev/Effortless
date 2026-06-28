import os
import json
import shutil
import sys
from typing import List, Dict, Any

def deploy_to_mcp_clients(project_root: str) -> List[Dict[str, Any]]:
    """
    Détecte et configure le serveur MCP et ses Skills sur les différents clients de la machine.
    """
    results = []

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

        # Mettre à jour l'entrée effortless
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

    # 2. Claude Code Skills
    claude_code_skills_dir = os.path.expanduser("~/.claude/skills")
    if os.path.exists(os.path.expanduser("~/.claude")):
        os.makedirs(claude_code_skills_dir, exist_ok=True)
        source_skill = os.path.join(project_root, "skills", "effortless", "SKILL.md")
        target_skill = os.path.join(claude_code_skills_dir, "effortless.md")
        
        if os.path.exists(source_skill):
            try:
                shutil.copy2(source_skill, target_skill)
                results.append({
                    "name": "Claude Code",
                    "status": "success",
                    "path": target_skill,
                    "action": "Copied instruction Skill"
                })
            except Exception as e:
                results.append({
                    "name": "Claude Code",
                    "status": "error",
                    "path": target_skill,
                    "action": f"Failed to copy Skill: {str(e)}"
                })

    # 3. Antigravity Plugins / Skills
    antigravity_plugins_dir = os.path.expanduser("~/.gemini/config/plugins")
    if os.path.exists(os.path.expanduser("~/.gemini/config")):
        os.makedirs(antigravity_plugins_dir, exist_ok=True)
        target_plugin_dir = os.path.join(antigravity_plugins_dir, "effortless")
        os.makedirs(os.path.join(target_plugin_dir, "skills", "effortless"), exist_ok=True)
        
        source_skill = os.path.join(project_root, "skills", "effortless", "SKILL.md")
        target_skill = os.path.join(target_plugin_dir, "skills", "effortless", "SKILL.md")
        
        if os.path.exists(source_skill):
            try:
                shutil.copy2(source_skill, target_skill)
                # Créer le plugin.json
                plugin_json = {
                    "name": "effortless",
                    "version": "0.2.0",
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
