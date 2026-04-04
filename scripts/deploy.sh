#!/bin/bash
# Deploy OpenClaw Dashboard to VPS

set -e

VPS_USER=${VPS_USER:-ubuntu}
VPS_HOST=${VPS_HOST:-43.134.111.55}
VPS_PASS=${VPS_PASS}

if [ -z "$VPS_PASS" ]; then
    echo "Error: Set VPS_PASS environment variable"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSETS_DIR="$SCRIPT_DIR/../assets"

echo "=== Deploying OpenClaw Dashboard to $VPS_HOST ==="

# Install sshpass if needed
if ! command -v sshpass &> /dev/null; then
    echo "Installing sshpass..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install sshpass
    else
        sudo apt-get install -y sshpass
    fi
fi

# Create remote directory structure
echo "Setting up remote directories..."
sshpass -p "$VPS_PASS" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST "
    sudo mkdir -p /opt/openclaw-dashboard/templates/pages
    sudo mkdir -p /opt/openclaw-dashboard/static/css
    sudo mkdir -p /opt/openclaw-dashboard/static/js
    sudo chown -R \$USER:\$USER /opt/openclaw-dashboard
"

# Copy files
echo "Copying dashboard files..."
sshpass -p "$VPS_PASS" scp -o StrictHostKeyChecking=no -r \
    "$ASSETS_DIR"/* "$VPS_USER@$VPS_HOST:/opt/openclaw-dashboard/"

# Install dependencies
echo "Installing dependencies..."
sshpass -p "$VPS_PASS" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST "
    sudo apt-get update
    sudo apt-get install -y python3-pip python3-venv nginx
    
    if [ ! -d /opt/openclaw-dashboard/venv ]; then
        python3 -m venv /opt/openclaw-dashboard/venv
    fi
    
    source /opt/openclaw-dashboard/venv/bin/activate
    pip install flask
"

# Setup systemd service
echo "Setting up systemd service..."
sshpass -p "$VPS_PASS" scp -o StrictHostKeyChecking=no \
    "$SCRIPT_DIR/openclaw-dashboard.service" \
    "$VPS_USER@$VPS_HOST:/tmp/openclaw-dashboard.service"

sshpass -p "$VPS_PASS" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST "
    sudo mv /tmp/openclaw-dashboard.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable openclaw-dashboard
    sudo systemctl restart openclaw-dashboard
"

# Setup nginx
echo "Setting up nginx..."
sshpass -p "$VPS_PASS" scp -o StrictHostKeyChecking=no \
    "$SCRIPT_DIR/nginx.conf" \
    "$VPS_USER@$VPS_HOST:/tmp/nginx-openclaw.conf"

sshpass -p "$VPS_PASS" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST "
    sudo mv /tmp/nginx-openclaw.conf /etc/nginx/sites-available/openclaw-dashboard
    sudo ln -sf /etc/nginx/sites-available/openclaw-dashboard /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo nginx -t && sudo systemctl reload nginx
"

# Open firewall
echo "Configuring firewall..."
sshpass -p "$VPS_PASS" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST "
    sudo ufw allow 8088/tcp || true
    sudo ufw allow 80/tcp || true
"

echo ""
echo "=== Deployment Complete ==="
echo "Dashboard URL: http://$VPS_HOST:8088"
echo ""
echo "To check status:"
echo "  ssh $VPS_USER@$VPS_HOST 'sudo systemctl status openclaw-dashboard'"
