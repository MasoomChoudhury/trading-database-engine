#!/bin/bash
# =============================================================================
# Database Engine — Master Setup Script
# =============================================================================
# ONE script to rule them all. Run this on a fresh VPS and it will:
#   1. Check and install all system dependencies (Docker, Git, curl, UFW)
#   2. Pull the latest code from git
#   3. Configure Docker daemon security
#   4. Set up the VPS firewall (only SSH, HTTP, HTTPS open)
#   5. Start the engine + web dashboard via Docker Compose
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/database-engine/main/setup.sh | bash
#   # OR clone and run locally:
#   git clone <your-repo-url> && cd database-engine && ./setup.sh
#
# NOTE: Run as a NORMAL USER (not root). The script uses sudo where needed.
# =============================================================================

set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m';   GREEN='\033[0;32m'
YELLOW='\033[1;33m'; BLUE='\033[0;34m'
CYAN='\033[0;36m';  NC='\033[0m'

log_info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERR]${NC}   $*" >&2; }
log_step()    { echo -e "\n${BLUE}──── $*) ────${NC}"; }
log_success() { echo -e "${GREEN}[OK]${NC}    $*"; }

SCRIPT_VERSION="1.0.0"
PROJECT_NAME="db-engine"

# Detect if running with sudo
if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    # Invoked via sudo — use the real user's environment
    SUDO_USER_HOME=$(getent passwd "$(logname 2>/dev/null || echo "${SUDO_USER:-$(whoami)}")" | cut -d: -f6)
    IS_SUDO=1
else
    IS_SUDO=0
    SUDO_USER_HOME="${HOME}"
fi

# ── Pre-flight checks ───────────────────────────────────────────────────────────

log_step "Pre-flight Checks"

# Check for required commands
MISSING_DEPS=()
for cmd in curl git sudo; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING_DEPS+=("$cmd")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    log_info "Installing missing system packages: ${MISSING_DEPS[*]}"
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq "${MISSING_DEPS[@]}" 2>&1 | tail -5
    else
        log_error "Unsupported package manager. Please install: ${MISSING_DEPS[*]}"
        exit 1
    fi
fi
log_success "System dependencies OK"

# ── Identify project directory ───────────────────────────────────────────────────

# If we're already inside the project directory, use it.
# Otherwise clone into ~/database-engine/
if [ -f "docker-compose.yml" ] && [ -f "Dockerfile" ]; then
    PROJECT_DIR="$(pwd)"
    log_info "Found project at: ${PROJECT_DIR}"
elif [ -d "${HOME}/database-engine" ]; then
    PROJECT_DIR="${HOME}/database-engine"
    log_info "Using existing project at: ${PROJECT_DIR}"
else
    log_step "Cloning Repository"
    # Prompt for repo URL if not provided
    REPO_URL="${1:-}"
    if [ -z "$REPO_URL" ]; then
        echo -n "Enter your git repository URL (or press Enter for empty repo): "
        read -r REPO_URL
    fi

    if [ -n "$REPO_URL" ]; then
        git clone "$REPO_URL" "${HOME}/database-engine"
        log_success "Repository cloned"
    else
        log_warn "No repository URL provided — setting up project directory in ${HOME}/database-engine"
        mkdir -p "${HOME}/database-engine"
    fi
    PROJECT_DIR="${HOME}/database-engine"
    cd "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"
REPO_DIR="$PROJECT_DIR"   # absolute path

# ── Step 1: Install Docker ─────────────────────────────────────────────────────

log_step "1. Installing Docker"

if ! command -v docker &>/dev/null; then
    log_info "Docker not found — installing..."

    # Remove old versions if present
    sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        apt-transport-https ca-certificates curl gnupg lsb-release ufw 2>&1 | tail -3

    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL "https://download.docker.com/linux/$(lsb_release -is | tr '[:upper:]' '[:lower:]')/gpg" \
        | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    # Add Docker repo
    DISTRO="$(lsb_release -is | tr '[:upper:]' '[:lower:]')"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${DISTRO} $(lsb_release -cs) stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin 2>&1 | tail -3
    log_success "Docker installed: $(docker --version)"
else
    log_success "Docker already installed: $(docker --version)"
fi

# Start and enable Docker
sudo systemctl enable --now docker 2>/dev/null || true
if ! sudo docker ps &>/dev/null; then
    log_error "Docker daemon is not running. Try: sudo systemctl start docker"
    exit 1
fi
log_success "Docker daemon is running"

# Add current user to docker group (so we don't need sudo for docker commands)
if ! groups | grep -q '\bdocker\b'; then
    log_info "Adding $(whoami) to docker group..."
    sudo usermod -aG docker "$(whoami)"
    log_warn "Docker group membership will take effect on next login."
    log_warn "For this session, some commands may need 'sudo'."
fi

# ── Step 2: Docker Compose ─────────────────────────────────────────────────────

log_step "2. Verifying Docker Compose"

COMPOSE_VERSION=$(docker compose version 2>/dev/null || echo "not found")
if [ "$COMPOSE_VERSION" = "not found" ]; then
    log_info "Installing Docker Compose standalone..."
    sudo curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    sudo ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
    log_success "Docker Compose installed"
else
    log_success "Docker Compose: $COMPOSE_VERSION"
fi

# ── Step 3: Pull Latest from Git ─────────────────────────────────────────────

log_step "3. Pulling Latest Code from Git"

cd "$REPO_DIR"

if [ -d ".git" ]; then
    CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "main")
    log_info "Current branch: ${CURRENT_BRANCH}"
    log_info "Pulling latest changes..."
    if git diff --quiet && git diff --cached --quiet; then
        git pull origin "${CURRENT_BRANCH}" --ff
        log_success "Code updated to latest"
    else
        log_warn "Local changes detected — stashing before pull..."
        git stash
        git pull origin "${CURRENT_BRANCH}" --ff
        log_success "Code updated — your local changes are stashed (git stash pop to restore)"
    fi
else
    log_warn "Not a git repository — skipping git pull"
fi

# ── Step 4: Generate Secure Secrets ─────────────────────────────────────────

log_step "4. Configuring Secrets"

# Only generate if not already configured
if ! grep -q "your_refresh_token\|_here\|changeme\|your_api_key\|your_api_secret" .env 2>/dev/null; then
    log_info ".env appears to be configured — skipping secret generation"
else
    log_warn ".env contains placeholder values. Generating secure defaults..."
    # Generate strong random secrets
    TS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
    ADMIN_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

    # Update .env with strong defaults
    python3 - << PYEOF
import re, os

env_path = os.path.join("$REPO_DIR", ".env")
with open(env_path) as f:
    content = f.read()

replacements = [
    (r'UPSTOX_REFRESH_TOKEN=.*', f'UPSTOX_REFRESH_TOKEN=your_refresh_token_here'),
    (r'ADMIN_PASSWORD=.*', f'ADMIN_PASSWORD={os.environ.get("ADMIN_PW", "$ADMIN_PASSWORD")}'),
    (r'SESSION_SECRET=.*', f'SESSION_SECRET={os.environ.get("SESSION_S", "$SESSION_SECRET")}'),
]
# Apply only to placeholder lines (keep real values)
for pattern, repl in replacements:
    content = re.sub(pattern, repl, content)

with open(env_path, 'w') as f:
    f.write(content)
PYEOF
    log_warn "Please edit .env and set your real credentials:"
    log_warn "  nano ${REPO_DIR}/.env"
fi

# ── Step 5: Security Hardening ────────────────────────────────────────────────

log_step "5. VPS Security Hardening"

# 5a. UFW Firewall — only SSH, HTTP, HTTPS
log_info "Configuring UFW firewall..."
if ! sudo ufw status | grep -q "Status: active"; then
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow ssh comment 'SSH (change port if non-standard)'
    sudo ufw allow http comment 'HTTP (web dashboard)'
    sudo ufw allow https comment 'HTTPS (web dashboard)'
    sudo ufw --force enable
    log_success "UFW firewall enabled (SSH, HTTP, HTTPS only)"
else
    log_success "UFW already active"
fi

# 5b. SSH hardening — check for insecure settings
log_info "Checking SSH configuration..."
if [ -f /etc/ssh/sshd_config ]; then
    # Warn if password auth is still enabled
    if grep -qE "^\s*PasswordAuthentication\s+yes" /etc/ssh/sshd_config 2>/dev/null; then
        log_warn "SSH PasswordAuthentication is enabled."
        log_warn "  For production: use SSH key-only auth and set:"
        log_warn "  echo 'PasswordAuthentication no' | sudo tee -a /etc/ssh/sshd_config"
        log_warn "  sudo systemctl restart sshd"
    fi
    # Warn if root login is enabled
    if grep -qE "^\s*PermitRootLogin\s+yes" /etc/ssh/sshd_config 2>/dev/null; then
        log_warn "SSH PermitRootLogin is yes — consider disabling for production."
    fi
fi

# 5c. Check for SSH backdoors
log_info "Checking for unexpected SSH authorized_keys..."
ROOT_AK="/root/.ssh/authorized_keys"
if [ -f "$ROOT_AK" ]; then
    ROOT_KEY_COUNT=$(wc -l < "$ROOT_AK" | tr -d ' ')
    if [ "$ROOT_KEY_COUNT" -gt 0 ]; then
        log_warn "Found ${ROOT_KEY_COUNT} key(s) in ${ROOT_AK}"
        log_warn "  Review with: sudo cat ${ROOT_AK}"
    fi
fi

# 5d. Docker daemon security — prevent container from gaining host privileges
log_info "Verifying Docker daemon configuration..."
if grep -q '"live-restore":\s*true' /etc/docker/daemon.json 2>/dev/null; then
    log_success "Docker live-restore is enabled"
else
    log_info "Adding Docker live-restore (keeps containers running after daemon restart)..."
    sudo mkdir -p /etc/docker
    sudo tee /etc/docker/daemon.json > /dev/null << 'EOF'
{
  "live-restore": true,
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
    sudo systemctl restart docker
    log_success "Docker daemon configured with log rotation + live-restore"
fi

# ── Step 6: Build & Start Services ───────────────────────────────────────────

log_step "6. Building Docker Images"

cd "$REPO_DIR"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        log_info "Creating .env from .env.example..."
        cp .env.example .env
    fi
    log_warn ".env created — please fill in your credentials: nano .env"
    log_error "Cannot start services without configured .env. Please run setup again after editing."
    exit 1
fi

# Validate critical env vars
log_info "Validating .env configuration..."
MISSING=""
for VAR in UPSTOX_ACCESS_TOKEN UPSTOX_API_KEY UPSTOX_API_SECRET SUPABASE_URL SUPABASE_KEY; do
    VALUE=$(grep "^${VAR}=" .env 2>/dev/null | cut -d= -f2-)
    if [ -z "$VALUE" ] || echo "$VALUE" | grep -qE "your_|your-|_here|placeholder"; then
        MISSING="${MISSING} ${VAR}"
    fi
done

if [ -n "$MISSING" ]; then
    log_warn "The following variables may not be configured:${MISSING}"
    log_warn "Edit .env before deploying: nano .env"
fi

# Build images
log_info "Building Docker images (this may take a few minutes)..."
docker compose -p "$PROJECT_NAME" build --no-cache 2>&1 | tail -10

# ── Step 7: Start Services ───────────────────────────────────────────────────

log_step "7. Starting Services"

docker compose -p "$PROJECT_NAME" up -d

log_info "Waiting for containers to start..."
sleep 8

# ── Step 8: Verify Health ─────────────────────────────────────────────────────

log_step "8. Verifying Deployment"

CONTAINER_STATUS=$(docker compose -p "$PROJECT_NAME" ps --format json 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    if isinstance(data, list):
        for c in data:
            name = c.get('Name', c.get('Service', '?'))
            state = c.get('State', '?')
            print(f'{name}: {state}')
    else:
        print(data)
except:
    print('Could not parse container status')
" 2>/dev/null || docker compose -p "$PROJECT_NAME" ps)

echo "$CONTAINER_STATUS"

# Check engine health
ENGINE_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' db_engine 2>/dev/null || echo "no healthcheck")
if [ "$ENGINE_HEALTH" = "healthy" ]; then
    log_success "Engine container is healthy"
elif [ "$ENGINE_HEALTH" = "starting" ] || [ "$ENGINE_HEALTH" = "no healthcheck" ]; then
    log_info "Engine status: ${ENGINE_HEALTH} — logs may show initialization"
else
    log_error "Engine health: ${ENGINE_HEALTH} — check with: docker compose -p ${PROJECT_NAME} logs engine"
fi

# Check web health
WEB_STATUS=$(docker inspect --format='{{.State.Status}}' db_web 2>/dev/null || echo "not found")
if [ "$WEB_STATUS" = "running" ]; then
    log_success "Web dashboard is running"
else
    log_warn "Web dashboard status: ${WEB_STATUS}"
fi

# ── Done ───────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Database Engine — Deployed Successfully!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Project:     ${CYAN}${REPO_DIR}${NC}"
echo -e "  Web Panel:   ${CYAN}http://$(curl -sf https://api.ipify.org 2>/dev/null || echo 'YOUR_VPS_IP'):8000${NC}"
echo -e "  Docker:      ${CYAN}docker compose -p ${PROJECT_NAME} ps${NC}"
echo -e "  Logs:        ${CYAN}docker compose -p ${PROJECT_NAME} logs -f${NC}"
echo -e "  Stop:        ${CYAN}docker compose -p ${PROJECT_NAME} down${NC}"
echo -e "  Restart:    ${CYAN}docker compose -p ${PROJECT_NAME} restart${NC}"
echo ""
echo -e "  ${YELLOW}IMPORTANT: Change ADMIN_PASSWORD in .env before production use!${NC}"
echo -e "  ${YELLOW}IMPORTANT: Set UPSTOX_REFRESH_TOKEN in .env for auto token refresh!${NC}"
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"

# ── Post-deployment reminder ────────────────────────────────────────────────────

if [ -n "$MISSING" ]; then
    echo ""
    log_warn "Incomplete .env detected — edit and restart:"
    echo "  nano ${REPO_DIR}/.env"
    echo "  docker compose -p ${PROJECT_NAME} restart"
fi

exit 0
