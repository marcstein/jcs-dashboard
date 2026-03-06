"""
FastAPI Dashboard Application
"""
import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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

# Configure logging so errors are visible
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

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

# Subdomain resolution — extracts firm_id from Host header (e.g. jcs.lawmetrics.ai → jcs_law)
# Registered AFTER SessionMiddleware so it runs BEFORE it in the request chain
# (Starlette middleware is LIFO — last added runs first)
from dashboard.middleware import SubdomainResolutionMiddleware
app.add_middleware(SubdomainResolutionMiddleware)

# Static files and templates
DASHBOARD_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=DASHBOARD_DIR / "static"), name="static")

# Register domain-specific route groups
register_routes(app)
app.include_router(sync_router, prefix="/api/sync")


# Global exception handler so 500 errors show tracebacks in the server log
@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    logger.error(f"500 on {request.url.path}: {exc}")
    logger.error(traceback.format_exc())
    return HTMLResponse(
        content=f"<h1>500 Internal Server Error</h1><pre>{traceback.format_exc()}</pre>",
        status_code=500,
    )


@app.get("/debug/health", response_class=HTMLResponse)
async def debug_health():
    """Debug endpoint — tests each model method and shows results/errors."""
    from dashboard.models import DashboardData
    import traceback as tb

    html = "<h1>Dashboard Health Check</h1>"
    d = DashboardData()
    html += f"<p><b>firm_id:</b> {d.firm_id}</p>"

    tests = [
        ("get_attorney_productivity_data", {}),
        ("get_attorney_invoice_aging", {}),
        ("get_promises_summary", {}),
        ("get_promises_list", {}),
        ("get_payment_analytics_summary", {}),
        ("get_time_to_payment_by_attorney", {}),
        ("get_time_to_payment_by_case_type", {}),
        ("get_dunning_summary", {}),
        ("get_dunning_queue", {}),
        ("get_dunning_history", {}),
        ("get_phases_summary", {}),
        ("get_stalled_cases", {}),
        ("get_trends_summary", {}),
    ]
    for method_name, kwargs in tests:
        html += f"<h3>{method_name}</h3>"
        try:
            method = getattr(d, method_name)
            result = method(**kwargs)
            if isinstance(result, dict):
                html += f"<p>dict with {len(result)} keys: {list(result.keys())}</p>"
                for k, v in result.items():
                    val_repr = repr(v)[:200]
                    html += f"<p>&nbsp;&nbsp;<b>{k}:</b> {val_repr}</p>"
            elif isinstance(result, list):
                html += f"<p>list with {len(result)} items</p>"
                if result:
                    html += f"<p>&nbsp;&nbsp;first: {repr(result[0])[:200]}</p>"
            else:
                html += f"<p>{repr(result)[:200]}</p>"
        except Exception as e:
            html += f"<p style='color:red'>ERROR: {e}</p>"
            html += f"<pre style='color:red'>{tb.format_exc()}</pre>"

    return HTMLResponse(content=html)


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
