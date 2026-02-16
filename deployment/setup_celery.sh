#!/bin/bash
# LawMetrics.ai - Celery + Redis Setup Script
# Run this AFTER the base setup.sh on the Digital Ocean droplet
#
# Prerequisites:
#   - Base setup.sh has been run
#   - PostgreSQL is configured and accessible
#   - .env file is in place

set -e

APP_USER="mycase"
APP_DIR="/opt/jcs-mycase"

echo "=================================================="
echo "LawMetrics - Celery + Redis Setup"
echo "=================================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./setup_celery.sh)"
    exit 1
fi

# -------------------------------------------------------------------
# 1. Install Redis
# -------------------------------------------------------------------
echo "[1/6] Installing Redis..."
apt-get install -y redis-server

# Configure Redis for production (modify main config)
REDIS_CONF="/etc/redis/redis.conf"
if [ -f "$REDIS_CONF" ]; then
    # Set memory limit
    sed -i 's/^# maxmemory .*/maxmemory 256mb/' $REDIS_CONF
    sed -i 's/^maxmemory .*/maxmemory 256mb/' $REDIS_CONF
    grep -q "^maxmemory " $REDIS_CONF || echo "maxmemory 256mb" >> $REDIS_CONF

    # Set eviction policy
    sed -i 's/^# maxmemory-policy .*/maxmemory-policy allkeys-lru/' $REDIS_CONF
    sed -i 's/^maxmemory-policy .*/maxmemory-policy allkeys-lru/' $REDIS_CONF
    grep -q "^maxmemory-policy " $REDIS_CONF || echo "maxmemory-policy allkeys-lru" >> $REDIS_CONF

    echo "  Redis config updated: 256MB limit, allkeys-lru eviction"
else
    echo "  Warning: Redis config not found at $REDIS_CONF"
fi

systemctl enable redis-server
systemctl restart redis-server
echo "  Redis installed and running"

# -------------------------------------------------------------------
# 2. Install Python dependencies
# -------------------------------------------------------------------
echo "[2/6] Installing Celery + Redis dependencies..."
cd $APP_DIR
sudo -u $APP_USER .venv/bin/pip install \
    "celery[redis]>=5.3.0" \
    "redis>=5.0.0"
echo "  Celery dependencies installed"

# -------------------------------------------------------------------
# 3. Add Redis URL to .env if not present
# -------------------------------------------------------------------
echo "[3/6] Configuring environment..."
if ! grep -q "REDIS_URL" $APP_DIR/.env 2>/dev/null; then
    cat >> $APP_DIR/.env << 'EOF'

# ============================================================================
# Celery + Redis (Auto-Sync Infrastructure)
# ============================================================================
REDIS_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_CONCURRENCY=3
EOF
    echo "  Added Redis config to .env"
else
    echo "  Redis config already in .env"
fi

# -------------------------------------------------------------------
# 4. Install systemd services
# -------------------------------------------------------------------
echo "[4/6] Installing systemd services..."
cp $APP_DIR/deployment/celery-worker.service /etc/systemd/system/
cp $APP_DIR/deployment/celery-beat.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable celery-worker
systemctl enable celery-beat
echo "  Systemd services installed and enabled"

# -------------------------------------------------------------------
# 5. Run database migration for sync tables
# -------------------------------------------------------------------
echo "[5/6] Running sync schema migration..."
cd $APP_DIR
# Source .env so DATABASE_URL and other vars are available
set -a; source $APP_DIR/.env 2>/dev/null; set +a
.venv/bin/python migrate_sync_tables.py
echo "  Database migration complete"

# -------------------------------------------------------------------
# 6. Start services
# -------------------------------------------------------------------
echo "[6/6] Starting Celery services..."
systemctl start celery-worker
systemctl start celery-beat

sleep 3

echo ""
echo "=================================================="
echo "Setup complete!"
echo "=================================================="
echo ""
echo "Service status:"
systemctl is-active --quiet celery-worker && echo "  ✓ celery-worker is running" || echo "  ✗ celery-worker failed to start"
systemctl is-active --quiet celery-beat && echo "  ✓ celery-beat is running" || echo "  ✗ celery-beat failed to start"
systemctl is-active --quiet redis-server && echo "  ✓ redis-server is running" || echo "  ✗ redis-server is not running"
echo ""
echo "Useful commands:"
echo "  journalctl -u celery-worker -f     # Watch worker logs"
echo "  journalctl -u celery-beat -f       # Watch scheduler logs"
echo "  cat $APP_DIR/logs/celery-worker.log # Worker log file"
echo "  redis-cli ping                     # Test Redis connection"
echo ""
