# Deploy: Disease Outflow Forecaster

The project runs on **IBM Cloud Code Engine** (serverless containers, scale-to-zero).
`main` auto-deploys via `.github/workflows/deploy.yml`. The legacy IBM Cloud VSI
notes are kept below for reference but are **retired** — see the banner in §1.

## 0. Code Engine (current)

CI builds the two images on the GitHub runner, pushes them to IBM Container
Registry, and rolls the existing `backend` and `frontend` Code Engine apps to
the new images. The build runs on GitHub (free CI minutes), so it consumes no
Code Engine vCPU-seconds; only runtime does, and idle apps scale to zero.

### One-time setup

Configure these under **Settings → Secrets and variables → Actions**:

| Kind   | Name               | Value |
|--------|--------------------|-------|
| Secret | `IBMCLOUD_API_KEY` | IBM Cloud API key with access to the CE project + ICR |
| Var    | `CE_PROJECT`       | Code Engine project name hosting the `backend`/`frontend` apps |
| Var    | `ICR_NAMESPACE`    | IBM Container Registry namespace to push images to |
| Var    | `IBMCLOUD_REGION`  | optional, default `us-south` |
| Var    | `ICR_DOMAIN`       | optional, default `us.icr.io` (must match the region) |

Prerequisites that must already exist in the account (the apps are already
running, so these are typically in place):

- An ICR namespace matching `ICR_NAMESPACE` (`ibmcloud cr namespace-add <ns>`).
- The Code Engine apps `backend` (port 8000) and `frontend` (port 3000), each
  with their env vars (e.g. `WATSONX_*` on the backend) and a registry-pull
  secret for ICR. The workflow only swaps the image; it never touches env vars,
  so watsonx secrets never need to live in GitHub.

### Cost

Stays within IBM's monthly free tiers for this usage: Code Engine free
allowance + scale-to-zero means idle costs nothing, and the build runs on
GitHub. The one thing to watch is ICR's 0.5 GB free storage — the workflow
sets a retention policy (keep last 3 images per repo) to stay under it.

### Manual deploy / rollback

```bash
ibmcloud login --apikey "$IBMCLOUD_API_KEY" -r us-south
ibmcloud ce project select --name "<CE_PROJECT>"
# Roll back to a known-good image tag:
ibmcloud ce app update --name backend  --image us.icr.io/<ns>/pandexis-backend:<sha>
ibmcloud ce app update --name frontend --image us.icr.io/<ns>/pandexis-frontend:<sha>
```

---

## 1. Target (legacy VSI — RETIRED)

> **Retired.** This VSI path is no longer the deploy target; the box at
> `163.66.95.111` currently returns 503. Kept for historical reference only.
> Use the Code Engine flow in §0.

- Host: `163.66.95.111` (ca-tor-1, 2 vCPU / 4 GB)
- OS: Ubuntu 22.04 LTS
- Assumes: SSH access as a sudo-capable user. Replace `deploy` below with your user if different.

```bash
ssh deploy@163.66.95.111
```

## 2. System prereqs

Python 3.11, Node 20 (NodeSource), nginx, git. One block:

```bash
sudo apt update
sudo apt install -y software-properties-common ca-certificates curl gnupg git nginx
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.11 python3.11-venv python3.11-dev
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Verify: `python3.11 --version`, `node --version` (should be v20.x), `nginx -v`.

## 3. Clone + install

```bash
sudo mkdir -p /opt/disease-outflow
sudo chown "$USER:$USER" /opt/disease-outflow
git clone <repo-url> /opt/disease-outflow
cd /opt/disease-outflow

# Backend
cd backend
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Frontend
cd ../frontend
npm ci
npm run build
```

## 4. systemd units

### `/etc/systemd/system/disease-outflow-backend.service`

```ini
[Unit]
Description=Disease Outflow Forecaster - FastAPI backend
After=network.target

[Service]
Type=simple
User=deploy
Group=deploy
WorkingDirectory=/opt/disease-outflow/backend
EnvironmentFile=/etc/disease-outflow.env
ExecStart=/opt/disease-outflow/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/disease-outflow-frontend.service`

```ini
[Unit]
Description=Disease Outflow Forecaster - Next.js frontend
After=network.target

[Service]
Type=simple
User=deploy
Group=deploy
WorkingDirectory=/opt/disease-outflow/frontend
Environment=NODE_ENV=production
Environment=NEXT_PUBLIC_API_BASE=/api
Environment=PORT=3000
ExecStart=/usr/bin/npm start
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## 5. nginx reverse proxy

`/etc/nginx/sites-available/disease-outflow`:

```nginx
server {
    listen 80;
    server_name 163.66.95.111;
    # TODO: switch to 443 + certbot once a hostname is attached.
    # sudo apt install -y certbot python3-certbot-nginx
    # sudo certbot --nginx -d <hostname>

    client_max_body_size 2m;

    # Backend, strip /api prefix
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # Frontend
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # WebSocket upgrade (harmless in prod; needed if Next dev/HMR ever runs here)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 60s;
    }
}
```

Enable:

```bash
sudo ln -sf /etc/nginx/sites-available/disease-outflow /etc/nginx/sites-enabled/disease-outflow
sudo rm -f /etc/nginx/sites-enabled/default
```

## 6. Env file

`/etc/disease-outflow.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

```bash
sudo install -m 600 -o root -g root /dev/null /etc/disease-outflow.env
sudoedit /etc/disease-outflow.env
```

Note: the `/explain` endpoint falls back to a deterministic templated paragraph if `ANTHROPIC_API_KEY` is missing, so the demo will still function without it.

## 7. Bring it up

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now disease-outflow-backend.service
sudo systemctl enable --now disease-outflow-frontend.service
sudo nginx -t && sudo systemctl reload nginx
```

If UFW is on: `sudo ufw allow 80/tcp` (and `443/tcp` once TLS is up).

## 8. Smoke test

```bash
curl -s http://163.66.95.111/api/health
# {"status":"ok"}
```

Then open `http://163.66.95.111/` in a browser. Move a slider, confirm the map updates and the explain panel renders.

## 9. Rollback / redeploy

```bash
cd /opt/disease-outflow && git pull && sudo systemctl restart disease-outflow-backend disease-outflow-frontend
```

If `backend/requirements.txt` changed: `cd backend && .venv/bin/pip install -r requirements.txt` before restart.
If `frontend/package.json` or any frontend source changed: `cd frontend && npm ci && npm run build` before restart.

## 10. Logs

```bash
# Backend
journalctl -u disease-outflow-backend -f

# Frontend
journalctl -u disease-outflow-frontend -f

# nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```
