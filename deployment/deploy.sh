#!/bin/bash
# JCS MyCase Automation - Quick Deploy Script
# Run from local machine to deploy updates to server

set -e

# Configuration - UPDATE THESE
SERVER_IP="167.99.112.107"
SERVER_USER="root"
APP_USER="mycase"
APP_DIR="/opt/jcs-mycase"

echo "Deploying to $SERVER_IP..."

# SSH into server and pull latest code
ssh $SERVER_USER@$SERVER_IP << EOF
    cd $APP_DIR
    sudo -u $APP_USER git pull origin main
    sudo -u $APP_USER .venv/bin/pip install -r requirements.txt
    systemctl restart mycase-dashboard
    
    # Restart Celery services (if installed)
    if systemctl is-enabled celery-worker 2>/dev/null; then
        echo "Restarting Celery worker..."
        systemctl restart celery-worker
        systemctl restart celery-beat
        sleep 2
        systemctl is-active --quiet celery-worker && echo "  ✓ celery-worker running" || echo "  ✗ celery-worker failed"
        systemctl is-active --quiet celery-beat && echo "  ✓ celery-beat running" || echo "  ✗ celery-beat failed"
    fi
    
    echo "Deploy complete!"
    systemctl status mycase-dashboard --no-pager
EOF

echo "Deployment finished!"
