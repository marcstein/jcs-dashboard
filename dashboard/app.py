"""
FastAPI Dashboard Application
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

# Load .env file before importing routes (which uses ANTHROPIC_API_KEY)
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import dashboard.config as config
from dashboard.routes import register_routes
from sync_routes import router as sync_router

# Create FastAPI app
app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
)

# Session middleware for login state
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    max_age=config.PERMANENT_SESSION_LIFETIME,
    same_site="lax",
    https_only=False,
    path="/",
)

# Static files and templates
DASHBOARD_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=DASHBOARD_DIR / "static"), name="static")

# Register domain-specific route groups
register_routes(app)
app.include_router(sync_router, prefix="/api/sync")


def run_server(host: str = "127.0.0.1", port: int = 8000, reload: bool = False):
    """Run the dashboard server."""
    import uvicorn
    uvicorn.run(
        "dashboard.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    run_server(reload=True)
