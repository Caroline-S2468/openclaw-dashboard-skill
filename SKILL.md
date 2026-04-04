---
name: openclaw-dashboard-deployer
description: Deploy and manage OpenClaw Dashboard on VPS with virtual office visualization, agent monitoring, and task management. Use when user needs to setup, update, or customize the OpenClaw Dashboard web interface showing agents working in a virtual office with CSS-drawn figures, beds for sleeping agents, and desks for working agents.
---

# OpenClaw Dashboard Deployer

Deploy and manage a web-based monitoring dashboard for OpenClaw agents with a virtual office visualization.

## Features

- **Virtual Office**: CSS-drawn agents at desks (working) or in beds (sleeping)
- **Agent Monitoring**: Real-time status, skills, tasks
- **Task Management**: Kanban board with status tracking
- **Performance**: 10s caching, <50ms API response
- **Responsive**: Works on desktop and mobile

## Quick Deploy

### Prerequisites

- VPS with Ubuntu 24.04 LTS
- SSH access to VPS
- OpenClaw data at `/root/.openclaw`

### First-time Setup

Use `scripts/deploy.sh`:

```bash
# Set VPS credentials
export VPS_USER=ubuntu
export VPS_HOST=43.134.111.55
export VPS_PASS=your_password

# Deploy
bash scripts/deploy.sh
```

### Manual Setup

```bash
# 1. Install dependencies
sudo apt update
sudo apt install -y python3-pip python3-venv nginx

# 2. Create directory
sudo mkdir -p /opt/openclaw-dashboard
sudo chown $USER:$USER /opt/openclaw-dashboard

# 3. Setup virtual environment
python3 -m venv /opt/openclaw-dashboard/venv
source /opt/openclaw-dashboard/venv/bin/activate
pip install flask

# 4. Copy files from assets/ to /opt/openclaw-dashboard/
cp -r assets/* /opt/openclaw-dashboard/

# 5. Create systemd service
sudo cp scripts/openclaw-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openclaw-dashboard
sudo systemctl start openclaw-dashboard

# 6. Setup nginx
sudo cp scripts/nginx.conf /etc/nginx/sites-available/openclaw-dashboard
sudo ln -sf /etc/nginx/sites-available/openclaw-dashboard /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## File Structure

```
/opt/openclaw-dashboard/
├── app.py                 # Flask app with caching
├── openclaw_monitor.py    # Data monitoring with 10s cache
├── static/
│   ├── css/
│   └── js/
└── templates/
    ├── base.html
    ├── pages/
    │   ├── office.html    # Virtual office with CSS figures
    │   ├── agents.html    # Agent cards
    │   ├── tasks.html     # Kanban board
    │   └── skills.html    # Skills list
```

## Customization

### Office Visualization

Edit `templates/pages/office.html`:

- **Working agents**: CSS-drawn standing figures at desks
  - `person-work` class: 110px height, typing animation
  - `work-desk` class: 90px height desk
  - `work-computer` class: glowing screen with `</>`
  
- **Sleeping agents**: CSS figures lying in beds
  - `person-sleep` class: horizontal figure
  - `bed` class: bed frame, mattress, pillow, blanket
  - `ps-z1/2/3` classes: floating Zzz animation

- **Gender styling**:
  - `.male::before` - short dark hair
  - `.female::before` - longer brown hair  
  - `.bald` - no hair (for 老孙)

### Performance Tuning

In `openclaw_monitor.py`:

```python
self._cache_ttl = 10  # Cache TTL in seconds
def _get_cached(self, key, fetch_func):
    # Cache data to reduce file I/O
```

### Agent Colors

Edit agent config in `templates/pages/office.html`:

```javascript
const AGENTS = {
    'Edgar':     { gender: 'male', color: '#3b82f6' },
    'Anne':      { gender: 'female', color: '#8b5cf6' },
    'Charlotte': { gender: 'female', color: '#ec4899' },
    'Danny':     { gender: 'male', color: '#10b981' },
    'Emily':     { gender: 'female', color: '#f59e0b' },
    '老孙':       { gender: 'bald', color: '#6b7280' }
};
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/agents` | Agent list with status |
| `GET /api/tasks` | Task list |
| `GET /api/skills` | Skills list |
| `GET /api/stats` | Statistics |

## Troubleshooting

### Dashboard not loading

```bash
# Check service status
sudo systemctl status openclaw-dashboard

# Check logs
sudo journalctl -u openclaw-dashboard -f

# Test locally
curl http://localhost:8088/api/health
```

### Permission denied

Dashboard must run as root to access `/root/.openclaw`:

```bash
# In systemd service
User=root
Group=root
```

### CSS not updating

Clear browser cache or restart service:

```bash
sudo systemctl restart openclaw-dashboard
```

## Update Code

To update dashboard code on VPS:

1. Edit local files in `assets/`
2. Transfer to VPS:
   ```bash
   scp -r assets/* ubuntu@VPS_IP:/opt/openclaw-dashboard/
   ```
3. Restart service:
   ```bash
   ssh ubuntu@VPS_IP "sudo systemctl restart openclaw-dashboard"
   ```
