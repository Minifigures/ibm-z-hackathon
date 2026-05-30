# Deploy: Disease Outflow Forecaster

## Current target: IBM Cloud Code Engine (scale-to-zero, free tier)

The live demo runs on **IBM Cloud Code Engine** in `us-south`, project `pandexis`.

| Component | URL |
| --- | --- |
| Frontend (custom domain) | https://pandexis.marcoayuste.com |
| Frontend (Code Engine) | https://frontend.29vrap7vinsk.us-south.codeengine.appdomain.cloud |
| Backend (Code Engine) | https://backend.29vrap7vinsk.us-south.codeengine.appdomain.cloud |

Both apps scale to zero when idle (first request after idleness has a ~5-10s cold start, then sub-second). Effective cost: **CA$0/month** within the free monthly allowances.

### CI/CD

`.github/workflows/deploy.yml` ("Deploy to Code Engine") fires on every push to `main` that touches `backend/`, `frontend/`, or the workflow itself. It does:

1. Install the IBM Cloud CLI + `code-engine` plugin on the GitHub runner.
2. Login with `IBMCLOUD_API_KEY` (repo secret) and select the `pandexis` project.
3. Detect which app(s) changed in the diff (or honour the manual `app` input).
4. Run `ibmcloud ce app update --build-source <repo-url> ...` for the changed app(s). Code Engine pulls the source, builds the Dockerfile inside a buildrun, and rolls a new revision. This stays inside Code Engine, so no IBM Container Registry namespace, no Docker push, no pull-secret.
5. Health-check the resulting URLs (with cold-start retries).

### Required GitHub repo secret

- `IBMCLOUD_API_KEY`: IAM API key with access to the `pandexis` Code Engine project. Generate at https://cloud.ibm.com/iam/apikeys.

### Optional GitHub repo variables (defaults match the live setup)

- `IBMCLOUD_REGION` (default `us-south`)
- `IBMCLOUD_RESOURCE_GROUP` (default `Default`)
- `CE_PROJECT` (default `pandexis`)

### Custom domain (pandexis.marcoayuste.com)

DNS lives on Cloudflare: `CNAME pandexis -> custom.29vrap7vinsk.us-south.codeengine.appdomain.cloud` (proxy off / DNS-only, because IBM does Let's Encrypt validation that fails behind Cloudflare's proxy). The IBM-side TLS secret is `pandexis-tls`, generated with `acme.sh` DNS-01 manual mode; cert expires ~90 days after issue and is renewed by re-running `acme.sh --renew` plus `ibmcloud ce secret update --name pandexis-tls --cert-chain-file ... --private-key-file ...`.

### Manual deploy (when CI is broken or you want to bypass it)

From IBM Cloud Shell (https://cloud.ibm.com/shell):

```bash
ibmcloud target -r us-south -g Default
ibmcloud ce project select --name pandexis
ibmcloud ce app update --name backend \
  --build-source https://github.com/Minifigures/ibm-z-hackathon \
  --build-context-dir backend --build-dockerfile Dockerfile
ibmcloud ce app update --name frontend \
  --build-source https://github.com/Minifigures/ibm-z-hackathon \
  --build-context-dir frontend --build-dockerfile Dockerfile
```

---

## RETIRED: IBM Cloud VPC VSI in Toronto

The original deploy target was a 2 vCPU / 4 GB Ubuntu VSI at `163.66.95.111` (ca-tor-1), torn down on **2026-05-15** in favour of Code Engine's scale-to-zero pricing. The instance, floating IP, public gateway, subnet, VPC, and SSH key have all been deleted. The sections below are kept for posterity (and in case anyone wants to spin up a VSI deploy on a fresh box) but the current live demo no longer uses any of this.

## 1. Target (retired)

- Host: `163.66.95.111` (ca-tor-1, 2 vCPU / 4 GB) **[DELETED]**
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
