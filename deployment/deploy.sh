#!/bin/bash
# JCS MyCase Automation - Quick Deploy Script
# Run from local machine to deploy updates to server

set -e

# Configuration - UPDATE THESE
SERVER_IP="YOUR_SERVER_IP"
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
    echo "Deploy complete!"
    systemctl status mycase-dashboard --no-pager
EOF

echo "Deployment finished!"
