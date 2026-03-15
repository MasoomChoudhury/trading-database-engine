#!/bin/bash

# =================================================================
# Database Engine One-Click Setup Script
# Target OS: Ubuntu / Debian
# =================================================================

set -e

echo "🚀 Starting Database Engine Setup..."

# 1. Update System
echo "🔄 Updating system packages..."
sudo apt-get update -y

# 2. Check & Install Git
if ! command -v git &> /dev/null; then
    echo "📦 Installing Git..."
    sudo apt-get install git -y
else
    echo "✅ Git is already installed."
fi

# 3. Check & Install Python3 & Venv
if ! command -v python3 &> /dev/null; then
    echo "📦 Installing Python3..."
    sudo apt-get install python3 python3-pip python3-venv -y
else
    echo "✅ Python3 is already installed."
fi

# 4. Check & Install Docker
if ! command -v docker &> /dev/null; then
    echo "📦 Installing Docker..."
    sudo apt-get install apt-transport-https ca-certificates curl software-properties-common -y
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
    sudo apt-get update -y
    sudo apt-get install docker-ce -y
    sudo systemctl start docker
    sudo systemctl enable docker
    # Add current user to docker group (requires logout to take effect, but we use sudo for now)
    sudo usermod -aG docker $USER
else
    echo "✅ Docker is already installed."
fi

# 5. Check & Install Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "📦 Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
else
    echo "✅ Docker Compose is already installed."
fi

# 6. Check & Install Node.js & PM2
if ! command -v pm2 &> /dev/null; then
    echo "📦 Installing Node.js and PM2..."
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
    sudo apt-get install -y nodejs
    sudo npm install pm2 -g
else
    echo "✅ PM2 is already installed."
fi

# 7. Project Initialization
echo "📂 Setting up Python Virtual Environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
echo "📥 Installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# 8. Environment Setup
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo "‼️  IMPORTANT: Please edit the .env file with your Upstox and Supabase credentials!"
    echo "   ALSO set SESSION_SECRET and ADMIN_PASSWORD for the web panel."
fi

# 9. Launch Database
echo "🐘 Starting TimescaleDB container..."
sudo docker-compose up -d

# 10. Summary
echo "====================================================="
echo "✅ Setup Complete!"
echo "====================================================="
echo "1. EDIT YOUR .ENV: nano .env"
echo "2. START ENGINE: pm2 start src/main.py --name 'db-engine' --interpreter ./venv/bin/python"
echo "3. START ADMIN PANEL: pm2 start src/main_web.py --name 'db-admin' --interpreter ./venv/bin/python"
echo "4. VIEW LOGS: pm2 logs"
echo "====================================================="
