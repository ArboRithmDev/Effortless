#!/bin/bash

# Script d'installation et de déploiement pour Effortless

# Couleurs pour le terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Pas de couleur

PROJECT_ROOT=$(pwd)
MCP_SERVER_DIR="$PROJECT_ROOT/src/mcp-server"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE} 🛠️  EFFORTLESS - SCRIPT D'INSTALLATION & CONFIGURATION${NC}"
echo -e "${BLUE}============================================================${NC}"

# 1. Vérification de uv
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}[!] Le gestionnaire de paquets 'uv' n'a pas été détecté.${NC}"
    echo -e "Installation de 'uv' via curl..."
    curl -fsSL https://astral.sh/uv/install.sh | sh
    # Recharger le PATH
    export PATH="$HOME/.local/bin:$PATH"
else
    echo -e "${GREEN}[✓] 'uv' est installé.${NC}"
fi

# 2. Initialisation de l'environnement virtuel pour le serveur MCP
echo -e "\n${BLUE}[1/3] Configuration de l'environnement Python...${NC}"
cd "$MCP_SERVER_DIR" || exit 1

if [ ! -d ".venv" ]; then
    echo "Création de l'environnement virtuel (.venv)..."
    uv venv
else
    echo "L'environnement virtuel existe déjà."
fi

# Activer l'environnement
source .venv/bin/activate

# Installer les dépendances en mode éditable et pytest
echo "Installation des dépendances du projet..."
uv pip install -e . pytest

# Revenir à la racine
cd "$PROJECT_ROOT" || exit 1

# 3. Compilation du dashboard Web (optionnelle, nécessite npm)
echo -e "\n${BLUE}[2/4] Compilation du dashboard Web...${NC}"
if command -v npm &> /dev/null; then
    npm --prefix "$PROJECT_ROOT/src/web-ui" install --no-audit --no-fund
    npm --prefix "$PROJECT_ROOT/src/web-ui" run build
    echo -e "${GREEN}[✓] Dashboard Web compilé (src/web-ui/dist).${NC}"
else
    echo -e "${YELLOW}[!] 'npm' introuvable — dashboard Web non compilé. Installez Node.js puis lancez : cd src/web-ui && npm install && npm run build${NC}"
fi

# 4. Déploiement automatique multi-CLI / multi-App
echo -e "\n${BLUE}[3/4] Déploiement automatique sur les clients MCP détectés...${NC}"
"$PROJECT_ROOT/src/mcp-server/.venv/bin/python" -c "from effortless_mcp.server import effortless_deploy; print(effortless_deploy())"

# 5. Installation du hook Git pre-commit
echo -e "\n${BLUE}[4/4] Installation du hook Git pre-commit anti-drift...${NC}"
"$PROJECT_ROOT/src/mcp-server/.venv/bin/python" -c "from effortless_mcp.server import effortless_drift_hook_install; print(effortless_drift_hook_install())"

# 5. Message de succès
echo -e "\n${GREEN}[✓] Installation, déploiement et sécurisation terminés avec succès !${NC}"
echo -e "${BLUE}============================================================${NC}"
echo -e "${YELLOW}🚀 COMMANDES DISPONIBLES :${NC}"
echo -e "• Tester le serveur MCP localement :"
echo -e "  ${GREEN}cd src/mcp-server && source .venv/bin/activate && effortless-mcp${NC}"
echo -e "• Lancer le client CLI de test interactif :"
echo -e "  ${GREEN}./src/mcp-server/.venv/bin/python src/cli/main.py${NC}"
echo -e "• Exécuter les tests unitaires :"
echo -e "  ${GREEN}cd src/mcp-server && source .venv/bin/activate && pytest${NC}"
echo -e "${BLUE}============================================================${NC}"
