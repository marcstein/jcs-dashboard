"""
Celery Application Configuration for LawMetrics.ai

Configures Celery with Redis broker for:
- Periodic firm data sync
- OAuth token refresh
- Report generation and delivery
- Retry logic with exponential backoff

Usage:
    # Start worker:
    celery -A celery_app worker --loglevel=info --concurrency=3

    # Start beat scheduler:
    celery -A celery_app beat --loglevel=info

    # Start both (development only):
    celery -A celery_app worker --beat --loglevel=info --concurrency=3
"""
import os
import logging
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    from pathlib import Path
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Broker configuration
# ---------------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

# ---------------------------------------------------------------------------
# Create Celery app
# ---------------------------------------------------------------------------
app = Celery(
    "lawmetrics",
    broker=REDIS_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["tasks"],
)

# ---------------------------------------------------------------------------
# Celery configuration
# ---------------------------------------------------------------------------
app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_track_started=True,

    # Result expiration
    result_expires=86400,

    # Concurrency
    worker_concurrency=int(os.environ.get("CELERY_CONCURRENCY", "3")),

    # Task time limits
    task_soft_time_limit=1800,
    task_time_limit=2100,

    # Retry defaults
    task_default_retry_delay=300,
    task_max_retries=3,

    # Queue routing
    task_routes={
        "tasks.sync_firm_task": {"queue": "sync"},
        "tasks.refresh_firm_tokens": {"queue": "sync"},
        "tasks.generate_firm_reports": {"queue": "reports"},
        "tasks.send_events_reports_task": {"queue": "reports"},
    },

    # Beat schedule
    beat_schedule={
        "dispatch-pending-syncs": {
            "task": "tasks.dispatch_pending_syncs",
            "schedule": 300.0,
            "options": {"queue": "default"},
        },
        "refresh-expiring-tokens": {
            "task": "tasks.refresh_expiring_tokens",
            "schedule": 1800.0,
            "options": {"queue": "sync"},
        },
        "daily-events-reports": {
            "task": "tasks.dispatch_daily_reports",
            "schedule": crontab(hour=12, minute=30),
            "options": {"queue": "reports"},
        },
        "detect-stale-syncs": {
            "task": "tasks.detect_stale_syncs",
            "schedule": 3600.0,
            "options": {"queue": "default"},
        },
        "cleanup-sync-history": {
            "task": "tasks.cleanup_sync_history",
            "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
            "options": {"queue": "default"},
        },
    },
)

app.conf.worker_hijack_root_logger = False

if __name__ == "__main__":
    app.start()
