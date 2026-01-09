#!/bin/bash
# JCS MyCase Automation - Server Setup Script
# Run this on a fresh Ubuntu 22.04+ Digital Ocean Droplet

set -e  # Exit on error

echo "=================================================="
echo "JCS MyCase Automation - Server Setup"
echo "=================================================="

# Configuration
APP_USER="mycase"
APP_DIR="/opt/jcs-mycase"
REPO_URL="https://github.com/marcstein/jcs-dashboard.git"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./setup.sh)"
    exit 1
fi

echo "[1/8] Updating system packages..."
apt-get update
apt-get upgrade -y

echo "[2/8] Installing dependencies..."
apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    nginx \
    certbot \
    python3-certbot-nginx \
    sqlite3 \
    curl \
    htop

echo "[3/8] Creating application user..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -m -d /home/$APP_USER -s /bin/bash $APP_USER
fi

echo "[4/8] Cloning repository..."
if [ -d "$APP_DIR" ]; then
    echo "Directory exists, pulling latest..."
    cd $APP_DIR
    sudo -u $APP_USER git pull
else
    git clone $REPO_URL $APP_DIR
    chown -R $APP_USER:$APP_USER $APP_DIR
fi

echo "[5/8] Setting up Python virtual environment..."
cd $APP_DIR
sudo -u $APP_USER python3.11 -m venv .venv
sudo -u $APP_USER .venv/bin/pip install --upgrade pip
sudo -u $APP_USER .venv/bin/pip install -r requirements.txt

echo "[6/8] Creating directories..."
sudo -u $APP_USER mkdir -p $APP_DIR/data $APP_DIR/logs

echo "[7/8] Setting up systemd services..."
cp $APP_DIR/deployment/mycase-dashboard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable mycase-dashboard

echo "[8/8] Setting up cron jobs..."
# Run as the mycase user
CRON_CMD="cd $APP_DIR && .venv/bin/python agent.py scheduler run-due >> $APP_DIR/logs/cron.log 2>&1"
SYNC_CMD="cd $APP_DIR && .venv/bin/python agent.py scheduler run-task sync_data >> $APP_DIR/logs/cron.log 2>&1"

# Create crontab for mycase user
cat > /tmp/mycase_crontab << EOF
# MyCase Automation Scheduler
# Run scheduler check every 15 minutes during business hours (Mon-Fri 5AM-6PM)
*/15 5-18 * * 1-5 $CRON_CMD

# Daily data sync at 5:00 AM
0 5 * * * $SYNC_CMD
EOF

crontab -u $APP_USER /tmp/mycase_crontab
rm /tmp/mycase_crontab

echo "=================================================="
echo "Setup complete!"
echo "=================================================="
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. Copy your .env file to $APP_DIR/.env:"
echo "   scp .env root@YOUR_SERVER_IP:$APP_DIR/.env"
echo ""
echo "2. Copy your tokens.json (MyCase OAuth):"
echo "   scp data/tokens.json root@YOUR_SERVER_IP:$APP_DIR/data/"
echo ""
echo "3. Create notifications config:"
echo "   scp data/notifications_config.json root@YOUR_SERVER_IP:$APP_DIR/data/"
echo ""
echo "4. Set correct permissions:"
echo "   chown -R $APP_USER:$APP_USER $APP_DIR"
echo ""
echo "5. Start the dashboard:"
echo "   systemctl start mycase-dashboard"
echo ""
echo "6. (Optional) Set up Nginx reverse proxy - see deployment/nginx.conf"
echo ""
echo "7. (Optional) Set up SSL with Let's Encrypt:"
echo "   certbot --nginx -d yourdomain.com"
echo ""
