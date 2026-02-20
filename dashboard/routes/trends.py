"""
KPI trends routes
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated
from dashboard.models import DashboardData

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
data = DashboardData()


@router.get("/trends", response_class=HTMLResponse)
async def trends_dashboard(request: Request, metric: str = None):
    """Historical KPI trends dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    summary = data.get_trends_summary()

    # If a specific metric is selected, get detailed comparison
    metric_detail = None
    metric_history = []
    if metric:
        metric_detail = data.get_metric_comparison(metric)
        metric_history = data.get_trend_data(metric, days_back=30)

    return templates.TemplateResponse("trends.html", {
        "request": request,
        "summary": summary,
        "current_metric": metric,
        "metric_detail": metric_detail,
        "metric_history": metric_history,
        "username": request.session.get("username"),
    })
