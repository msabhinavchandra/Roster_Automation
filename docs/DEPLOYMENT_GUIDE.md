# Deployment Guide - Enterprise Roster Automation System

## 1. Overview & Architecture

The Enterprise Roster Automation System is a self-contained, high-performance operations scheduling application. It combines:
- **Backend:** Python 3.11+ with Google OR-Tools CP-SAT (Constraint Programming - Satisfiability).
- **Frontend:** Streamlit multi-page interface.
- **Data Layer:** openpyxl and Pandas for Excel ingestion and formatted multi-tab publication.
- **Storage:** File-system based (stateless with persistent volume mount for output Excel deliverables).

Because it uses pure mathematical constraint satisfaction rather than external databases or cloud LLM APIs, it requires no external API keys, database servers, or GPU hardware.

---

## 2. Prerequisites

- Python 3.10, 3.11, 3.12, or 3.13.
- `pip` package manager.
- 2 GB RAM minimum (4 GB recommended for large employee pools).
- 2 CPU cores minimum.

---

## 3. Local Workstation Deployment

### Step 1: Clone or Navigate to Directory
```bash
cd D:\DBS\Roster_Automation
```

### Step 2: Create and Activate Virtual Environment (Recommended)
**On Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```
**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Run Application
```bash
streamlit run app.py
```
The application will launch automatically in your default browser at `http://localhost:8501`.

---

## 4. Virtual Machine (VM) Deployment (Linux / Windows Server)

### Systemd Service Configuration (Linux VM)
Create a systemd unit file at `/etc/systemd/system/roster-automation.service`:

```ini
[Unit]
Description=Enterprise Roster Automation Streamlit Service
After=network.target

[Service]
User=rosterapp
Group=rosterapp
WorkingDirectory=/opt/roster-automation
Environment="PATH=/opt/roster-automation/venv/bin"
Environment="STREAMLIT_SERVER_PORT=8501"
Environment="STREAMLIT_SERVER_ADDRESS=0.0.0.0"
Environment="STREAMLIT_SERVER_HEADLESS=true"
ExecStart=/opt/roster-automation/venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable roster-automation
sudo systemctl start roster-automation
sudo systemctl status roster-automation
```

### Nginx Reverse Proxy Configuration
To expose the application on standard port 80/443 with SSL termination and WebSocket support:

```nginx
server {
    listen 80;
    server_name roster.company.internal;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

---

## 5. Docker Deployment

### Build the Docker Image
```bash
docker build -t roster-automation:1.0.0 .
```

### Run the Docker Container
```bash
docker run -d \
  --name roster-automation-app \
  -p 8501:8501 \
  -v $(pwd)/output:/app/output \
  --restart unless-stopped \
  roster-automation:1.0.0
```

### Accessing the Container
Navigate to `http://<host-ip>:8501`.

---

## 6. Kubernetes Production Deployment

The project provides production-ready manifests in `deployment/`:
- `deployment/kubernetes-deployment.yaml`: Deployment spec with resource limits, liveness and readiness probes, and PVC volume mount.
- `deployment/kubernetes-service.yaml`: ClusterIP service and 2Gi PersistentVolumeClaim.

### Apply Manifests
```bash
kubectl apply -f deployment/kubernetes-service.yaml
kubectl apply -f deployment/kubernetes-deployment.yaml
```

### Check Rollout Status
```bash
kubectl rollout status deployment/roster-automation-deployment
kubectl get pods -l app=roster-automation
```

### Persistent Volume Requirements
> [!IMPORTANT]
> The `/app/output` directory is mounted to a PersistentVolumeClaim (`roster-output-pvc`). This ensures that generated rosters exported to the server disk persist across pod restarts, upgrades, and scaling events.

---

## 7. Writable Output Directory & Excel Downloads

The system supports two complementary delivery modes:
1. **In-Browser Direct Download:** Users can click "Download Excel Workbook" directly in the Streamlit UI to download `.xlsx` files straight to their local browser downloads folder.
2. **Server-Side File Persistence:** Approved rosters are simultaneously saved to the server's `output/` directory (configurable in UI, defaulting to `output/roster_generated.xlsx`).

---

## 8. Verification and Health Checks

The container and Kubernetes manifests include a native health endpoint:
```bash
curl -f http://localhost:8501/_stcore/health
```
A return code of `200 OK` indicates the Streamlit server is active and healthy.
