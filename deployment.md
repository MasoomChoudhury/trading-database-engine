## Recommended VPS (Hetzner)

For a stable and responsive Data Engine, I recommend the following Hetzner Cloud configurations:

| Use Case | Tier | Specs | Est. Price |
| :--- | :--- | :--- | :--- |
| **Minimum** | CX22 | 2 vCPU, 4GB RAM, 40GB NVMe | ~€5 / mo |
| **Recommended** | **CPX31** | **4 vCPU**, **8GB RAM**, 160GB NVMe | ~€14 / mo |

> [!TIP]
> **CPX31** is the sweet spot. It provides AMD EPYC performance which is excellent for the heavy nested loops and indicators in the `indicator_engine`, and handles the TimescaleDB write-load effortlessly.

---

## ⚡ One-Click Auto-Setup (Recommended)

I have included a `setup.sh` script that automates the entire process (Docker, Python, PM2, Git).

1. **Upload or Clone** the project onto your fresh VPS.
2. **Run the script**:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
3. Follow the onscreen instructions to edit your `.env` and start the engine with PM2.

---

## 🛠 Manual Installation
If you prefer to install manually, follow these steps:

### 1. Prerequisites
Ensure your VPS has:
- **Docker & Docker Compose**: To run the TimescaleDB instance.
- **Python 3.10+**: To run the core logic.
- **Git**: To clone the repository.
- **PM2** (Recommended): To keep the Python process running 24/7.

### Install Docker (Ubuntu)
```bash
sudo apt update
sudo apt install docker.io docker-compose -y
sudo systemctl start docker
sudo systemctl enable docker
```

### Install PM2
```bash
sudo apt install nodejs npm -y
sudo npm install pm2 -g
```

---

## 2. Project Setup

1. **Clone the Project**:
   ```bash
   git clone <your-repo-url>
   cd "Database Engine"
   ```

2. **Configure Environment**:
   Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in your:
   - `UPSTOX_ACCESS_TOKEN`
   - `SUPABASE_URL` & `SUPABASE_KEY`
   - `POSTGRES_USER`/`PASSWORD` (Match with docker-compose.yml)

3. **Install Python Dependencies**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

---

## 3. Database Deployment

Start the local TimescaleDB container:
```bash
docker-compose up -d
```
Verify it's running:
```bash
docker ps
```

---

## 4. Run the Engine

### Option A: Manual Launch (For Testing)
```bash
source venv/bin/activate
python src/main.py
```

### Option B: PM2 Deployment (Production)
PM2 will automatically restart the script if it crashes and handles logs.
```bash
pm2 start src/main.py --name "db-engine" --interpreter ./venv/bin/python
pm2 save
pm2 startup
```

---

## 🔄 Daily Token Refresh (Upstox)

Upstox access tokens usually expire at 3:30 AM every day. To refresh it without manually editing the `.env` file:

1. **Run the Auth Script**:
   ```bash
   source venv/bin/activate
   python upstox_auth.py
   ```
2. **Follow the Prompts**:
   - Open the provided URL in your browser.
   - Log in with your Upstox credentials.
   - Copy the `code` from the browser's address bar.
   - Paste it back into the terminal.
3. **Restart the Engine**:
   The script will automatically update your `.env`. You just need to restart PM2:
   ```bash
   pm2 restart db-engine
   ```

---

## 🌐 Web Admin Panel (Manual)

If you installed manually, you can launch the dashboard as follows:

1. **Start with PM2**:
   ```bash
   pm2 start src/main_web.py --name 'db-admin' --interpreter ./venv/bin/python
   ```
2. **Access**:
   The dashboard runs on port `8000` by default. 
   - Local: `http://your-vps-ip:8000`
   - Production: Use my domain instructions (Nginx + SSL) to map your domain to this port.

---

## 🌐 Domain & SSL Setup (Production)

To use `https://www.database.masoomchoudhury.com` with your VPS (IP: `94.136.186.15`), follow these steps:

### 1. DNS Configuration
In your domain registrar (GoDaddy, Namecheap, etc.), add an **A Record**:
- **Name**: `www.database` (or `@` if you want the root)
- **Value**: `94.136.186.15`

### 2. Upstox Dashboard Update
Login to [Upstox Developer Console](https://developer.upstox.com/) and change your **Redirect URL** to:
`https://www.database.masoomchoudhury.com/auth/upstox-callback`

### 3. Nginx Reverse Proxy
Install Nginx and configure it to point to FastAPI:
```bash
sudo apt install nginx -y
sudo nano /etc/nginx/sites-available/trading-engine
```
Paste this config:
```nginx
server {
    listen 80;
    server_name www.database.masoomchoudhury.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
Enable and restart:
```bash
sudo ln -s /etc/nginx/sites-available/trading-engine /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 4. Install SSL (Let's Encrypt)
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d www.database.masoomchoudhury.com
```

---

## 5. Monitoring & Maintenance

- **View Logs**: `pm2 logs db-engine`
- **Check Status**: `pm2 status`
- **Restart**: `pm2 restart db-engine`
- **Database Logs**: `docker-compose logs -f timescaledb`

## Important Checklist
- [ ] **Upstox Token**: Ensure your token is fresh. Upstox access tokens usually expire daily or weekly depending on your app type.
- [ ] **Firewall**: Ensure port `5432` is NOT open to the public if you only need local access (Docker handles this internally by default).
- [ ] **Supabase Table**: Ensure the `market_data` table exists in Supabase with the correct schema before starting the sync.
- [ ] **TimescaleDB Health**: If the container restarts, the data is persisted in the `timescaledb_data` volume.
