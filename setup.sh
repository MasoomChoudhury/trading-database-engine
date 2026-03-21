#!/bin/bash
# =============================================================================
# Database Engine — Master Setup Script
# =============================================================================
# ONE script to rule them all. Run this on a fresh VPS and it will:
#   1. Install Docker, Git, curl, UFW, Nginx, Certbot
#   2. Pull the latest code from git
#   3. Configure Docker daemon security
#   4. Set up the VPS firewall (only SSH, HTTP, HTTPS open)
#   5. Configure Nginx reverse proxy → port 8000
#   6. Install SSL certificate (Let's Encrypt) for your domain
#   7. Start the engine + web dashboard via Docker Compose
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

SCRIPT_VERSION="2.0.0"
PROJECT_NAME="db-engine"

# Domain configuration — change these to match your setup
DOMAIN="database.masoomchoudhury.com"
WEB_PORT="8000"          # Docker web container port
NGINX_PORT="80"           # Nginx listens here (HTTP)
NGINX_SSL_PORT="443"      # Nginx listens here (HTTPS)

# Detect if running with sudo
if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    SUDO_USER_HOME=$(getent passwd "$(logname 2>/dev/null || echo "${SUDO_USER:-$(whoami)}")" | cut -d: -f6)
    IS_SUDO=1
else
    IS_SUDO=0
    SUDO_USER_HOME="${HOME}"
fi

# ── Pre-flight checks ───────────────────────────────────────────────────────────

log_step "Pre-flight Checks"

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

if [ -f "docker-compose.yml" ] && [ -f "Dockerfile" ]; then
    PROJECT_DIR="$(pwd)"
    log_info "Found project at: ${PROJECT_DIR}"
elif [ -d "${HOME}/database-engine" ]; then
    PROJECT_DIR="${HOME}/database-engine"
    log_info "Using existing project at: ${PROJECT_DIR}"
else
    log_step "Cloning Repository"
    REPO_URL="${1:-}"
    if [ -z "$REPO_URL" ]; then
        echo -n "Enter your git repository URL (or press Enter for empty repo): "
        read -r REPO_URL
    fi

    if [ -n "$REPO_URL" ]; then
        git clone "$REPO_URL" "${HOME}/database-engine"
        log_success "Repository cloned"
    else
        log_warn "No repository URL — creating project directory"
        mkdir -p "${HOME}/database-engine"
    fi
    PROJECT_DIR="${HOME}/database-engine"
    cd "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"
REPO_DIR="$PROJECT_DIR"

# ── Step 1: Install Docker ─────────────────────────────────────────────────────

log_step "1. Installing Docker"

if ! command -v docker &>/dev/null; then
    log_info "Docker not found — installing..."
    sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        apt-transport-https ca-certificates curl gnupg lsb-release ufw 2>&1 | tail -3

    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL "https://download.docker.com/linux/$(lsb_release -is | tr '[:upper:]' '[:lower:]')/gpg" \
        | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    DISTRO="$(lsb_release -is | tr '[:upper:]' '[:lower:]')"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${DISTRO} $(lsb_release -cs) stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin 2>&1 | tail -3
    log_success "Docker installed: $(docker --version)"
else
    log_success "Docker already installed: $(docker --version)"
fi

sudo systemctl enable --now docker 2>/dev/null || true
if ! sudo docker ps &>/dev/null; then
    log_error "Docker daemon is not running. Try: sudo systemctl start docker"
    exit 1
fi
log_success "Docker daemon is running"

if ! groups | grep -q '\bdocker\b'; then
    log_info "Adding $(whoami) to docker group..."
    sudo usermod -aG docker "$(whoami)"
    log_warn "Docker group membership takes effect on next login."
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
    if git diff --quiet && git diff --cached --quiet; then
        git pull origin "${CURRENT_BRANCH}" --ff
        log_success "Code updated to latest"
    else
        log_warn "Local changes detected — stashing before pull..."
        git stash
        git pull origin "${CURRENT_BRANCH}" --ff
        log_success "Code updated — local changes stashed (git stash pop to restore)"
    fi
else
    log_warn "Not a git repository — skipping git pull"
fi

# ── Step 4: Configure .env ────────────────────────────────────────────────────

log_step "4. Configuring .env"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        log_warn ".env created from .env.example — please fill in your credentials:"
        log_warn "  nano ${REPO_DIR}/.env"
    fi
fi

# Warn about incomplete .env
if [ -f ".env" ]; then
    MISSING=""
    for VAR in UPSTOX_ACCESS_TOKEN UPSTOX_API_KEY UPSTOX_API_SECRET SUPABASE_URL SUPABASE_KEY; do
        VALUE=$(grep "^${VAR}=" .env 2>/dev/null | cut -d= -f2-)
        if [ -z "$VALUE" ] || echo "$VALUE" | grep -qE "your_|your-|_here|placeholder"; then
            MISSING="${MISSING} ${VAR}"
        fi
    done
    if [ -n "$MISSING" ]; then
        log_warn "Potentially incomplete .env:${MISSING}"
    fi
fi

# ── Step 5: Security Hardening ────────────────────────────────────────────────

log_step "5. VPS Security Hardening"

# UFW Firewall
log_info "Configuring UFW firewall..."
if ! sudo ufw status | grep -q "Status: active"; then
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow ssh comment 'SSH'
    sudo ufw allow http comment 'HTTP (Nginx)'
    sudo ufw allow https comment 'HTTPS (SSL)'
    sudo ufw --force enable
    log_success "UFW firewall enabled (SSH, HTTP, HTTPS only)"
else
    log_success "UFW already active"
fi

# SSH hardening
log_info "Checking SSH configuration..."
if [ -f /etc/ssh/sshd_config ]; then
    if grep -qE "^\s*PasswordAuthentication\s+yes" /etc/ssh/sshd_config 2>/dev/null; then
        log_warn "SSH PasswordAuthentication is enabled — recommend SSH key-only auth for production."
    fi
    if grep -qE "^\s*PermitRootLogin\s+yes" /etc/ssh/sshd_config 2>/dev/null; then
        log_warn "SSH PermitRootLogin is yes — recommend disabling for production."
    fi
fi

# SSH authorized_keys check
ROOT_AK="/root/.ssh/authorized_keys"
if [ -f "$ROOT_AK" ] && [ "$(wc -l < "$ROOT_AK" | tr -d ' ')" -gt 0 ]; then
    log_warn "Found $(wc -l < "$ROOT_AK" | tr -d ' ') key(s) in ${ROOT_AK} — review with: sudo cat ${ROOT_AK}"
fi

# Docker daemon
log_info "Verifying Docker daemon configuration..."
if grep -q '"live-restore":\s*true' /etc/docker/daemon.json 2>/dev/null; then
    log_success "Docker live-restore is enabled"
else
    log_info "Adding Docker live-restore + log rotation..."
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
    log_success "Docker daemon configured"
fi

# ── Step 6: Nginx Reverse Proxy ──────────────────────────────────────────────

log_step "6. Nginx Reverse Proxy Setup"

# Install Nginx
if ! command -v nginx &>/dev/null; then
    log_info "Installing Nginx..."
    sudo apt-get install -y -qq nginx 2>&1 | tail -3
    log_success "Nginx installed"
else
    log_success "Nginx already installed: $(nginx -v 2>&1)"
fi

# Generate Nginx config
NGINX_SITE_FILE="/etc/nginx/sites-available/${DOMAIN}"
NGINX_ENABLED_FILE="/etc/nginx/sites-enabled/${DOMAIN}"

log_info "Configuring Nginx for ${DOMAIN} → localhost:${WEB_PORT}..."

sudo tee "$NGINX_SITE_FILE" > /dev/null << NGINX_EOF
# HTTP — redirect all traffic to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    # Certbot will add challenge locations here automatically
    location / {
        return 301 https://\$host\$request_uri;
    }

    # Let's Encrypt ACME challenge — allow access without redirect
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/html;
    }
}

# HTTPS — reverse proxy to Docker web container
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name ${DOMAIN};

    # SSL certificate (Certbot will update these paths)
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Proxy to Docker web container
    location / {
        proxy_pass http://127.0.0.1:${WEB_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 75;

        # WebSocket support (if needed by the admin panel)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Block sensitive paths
    location ~ /\. { deny all; }
}
NGINX_EOF

log_success "Nginx config written to ${NGINX_SITE_FILE}"

# Disable default site if it conflicts
if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm -f /etc/nginx/sites-enabled/default
    log_info "Removed default Nginx site"
fi

# Enable our site
sudo ln -sf "$NGINX_SITE_FILE" "$NGINX_ENABLED_FILE"

# Test and reload Nginx
if sudo nginx -t 2>&1 | grep -qE "(syntax is ok|test is successful)"; then
    log_success "Nginx config syntax OK"
    sudo systemctl reload nginx
    log_success "Nginx reloaded"
else
    log_error "Nginx config test failed:"
    sudo nginx -t 2>&1
    exit 1
fi

# ── Step 7: SSL Certificate (Let's Encrypt) ─────────────────────────────────────

log_step "7. SSL Certificate — Let's Encrypt"

# Check if SSL is already configured for this domain
SSL_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
if [ -f "$SSL_CERT" ]; then
    log_success "SSL certificate already exists for ${DOMAIN}"
    SSL_STATUS="existing"
else
    log_info "No existing SSL cert for ${DOMAIN} — requesting new certificate..."

    # Verify domain resolves to this server
    DOMAIN_IP=$(dig +short "${DOMAIN}" 2>/dev/null | tail -1 || echo "")
    SERVER_IP=$(curl -sf https://api.ipify.org 2>/dev/null || echo "")

    if [ -n "$DOMAIN_IP" ] && [ -n "$SERVER_IP" ]; then
        if [ "$DOMAIN_IP" != "$SERVER_IP" ]; then
            log_warn "DNS check: ${DOMAIN} resolves to ${DOMAIN_IP}, but this server is ${SERVER_IP}"
            log_warn "Make sure DNS A record for ${DOMAIN} points to ${SERVER_IP} before continuing."
            log_warn "Skipping SSL setup. Run this script again once DNS is propagated."
            SSL_STATUS="dns_mismatch"
        else
            log_success "DNS check passed: ${DOMAIN} → ${SERVER_IP}"
            SSL_STATUS="needs_cert"
        fi
    else
        log_warn "Could not verify DNS — proceeding with SSL setup anyway"
        SSL_STATUS="needs_cert"
    fi

    if [ "$SSL_STATUS" = "needs_cert" ]; then
        # Install Certbot
        if ! command -v certbot &>/dev/null; then
            log_info "Installing Certbot..."
            sudo apt-get install -y -qq certbot python3-certbot-nginx 2>&1 | tail -3
            log_success "Certbot installed"
        else
            log_success "Certbot already installed"
        fi

        # Create ACME challenge directory
        sudo mkdir -p /var/www/html/.well-known/acme-challenge
        echo "Let's Encrypt challenge directory ready" | sudo tee /var/www/html/.well-known/acme-challenge/.placeholder > /dev/null

        # Request certificate (standalone mode — Nginx serves HTTP on port 80)
        log_info "Requesting SSL certificate for ${DOMAIN}..."
        log_info "This will verify domain ownership via Let's Encrypt."

        if sudo certbot certonly \
            --nginx \
            --non-interactive \
            --agree-tos \
            --email "noreply@${DOMAIN}" \
            --domains "${DOMAIN}" \
            --keep-until-expiring \
            2>&1 | grep -qE "(Congratulations|renewed)"; then
            log_success "SSL certificate obtained successfully!"
            SSL_STATUS="installed"
        else
            log_warn "Certbot failed — SSL will be attempted on next run."
            log_warn "Common cause: DNS not yet propagated. Run 'sudo certbot --nginx -d ${DOMAIN}' after DNS is ready."
            SSL_STATUS="failed"
        fi
    fi
fi

# If cert was installed, update Nginx to use it and reload
if [ "$SSL_STATUS" = "installed" ] && [ -f "$SSL_CERT" ]; then
    log_info "Updating Nginx with SSL certificate paths..."
    sudo certbot --nginx --deploy-hook "systemctl reload nginx" \
        --non-interactive --agree-tos \
        --domains "${DOMAIN}" \
        2>&1 | tail -5 || true

    # Ensure auto-renewal is enabled
    sudo systemctl enable certbot.timer 2>/dev/null || true
    sudo certbot renew --dry-run 2>&1 | grep -qE "(renewal|Congratulations)" && \
        log_success "SSL auto-renewal is configured" || \
        log_warn "SSL auto-renewal may need attention"
fi

# ── Step 8: Build & Start Services ───────────────────────────────────────────

log_step "8. Building Docker Images"

cd "$REPO_DIR"

if [ ! -f ".env" ]; then
    log_error ".env missing — cannot start services. Please create it first."
    exit 1
fi

log_info "Building Docker images (may take a few minutes)..."
if docker compose -p "$PROJECT_NAME" build 2>&1 | tail -5; then
    log_success "Docker images built"
else
    log_error "Docker build failed — check Dockerfile and requirements.txt"
    exit 1
fi

# ── Step 9: Start Services ───────────────────────────────────────────────────

log_step "9. Starting Services"

docker compose -p "$PROJECT_NAME" up -d

log_info "Waiting for containers to start..."
sleep 10

# ── Step 10: Verify Everything ────────────────────────────────────────────────

log_step "10. Verifying Deployment"

# Docker containers
CONTAINERS=$(docker compose -p "$PROJECT_NAME" ps 2>/dev/null)
echo "$CONTAINERS"

ENGINE_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' db_engine 2>/dev/null || echo "unknown")
WEB_RUNNING=$(docker inspect --format='{{.State.Status}}' db_web 2>/dev/null || echo "unknown")

if [ "$ENGINE_HEALTH" = "healthy" ]; then
    log_success "Engine: healthy"
elif [ "$ENGINE_HEALTH" != "unknown" ]; then
    log_info "Engine: ${ENGINE_HEALTH}"
fi

if [ "$WEB_RUNNING" = "running" ]; then
    log_success "Web dashboard: running"
else
    log_warn "Web dashboard: ${WEB_RUNNING}"
fi

# Nginx
if systemctl is-active --quiet nginx 2>/dev/null; then
    log_success "Nginx: running"
else
    log_error "Nginx is not running: sudo systemctl status nginx"
fi

# SSL
if [ -f "$SSL_CERT" ]; then
    SSL_EXPIRY=$(sudo openssl x509 -noout -enddate -in "$SSL_CERT" 2>/dev/null | cut -d= -f2 || echo "unknown")
    log_success "SSL certificate present (expires: ${SSL_EXPIRY})"
else
    log_warn "No SSL certificate found — HTTPS may not work yet"
fi

# ── Done ───────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Database Engine — Deployed Successfully!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${CYAN}HTTPS://${DOMAIN}${NC}     ← Your web dashboard"
echo -e "  ${CYAN}http://${DOMAIN}/health${NC} ← Engine health check"
echo ""
echo -e "  Project:     ${CYAN}${REPO_DIR}${NC}"
echo -e "  Docker:      ${CYAN}docker compose -p ${PROJECT_NAME} ps${NC}"
echo -e "  Engine logs: ${CYAN}docker compose -p ${PROJECT_NAME} logs -f engine${NC}"
echo -e "  All logs:    ${CYAN}docker compose -p ${PROJECT_NAME} logs -f${NC}"
echo -e "  Restart:     ${CYAN}docker compose -p ${PROJECT_NAME} restart${NC}"
echo -e "  Stop:        ${CYAN}docker compose -p ${PROJECT_NAME} down${NC}"
echo ""
echo -e "${YELLOW}  Action required: Change ADMIN_PASSWORD in .env before production use${NC}"
echo -e "${YELLOW}  Action required: Set UPSTOX_REFRESH_TOKEN in .env for auto token refresh${NC}"
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════════════${NC}"

exit 0
