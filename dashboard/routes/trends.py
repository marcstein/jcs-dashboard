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

# Display names and targets for known metrics
METRIC_CONFIG = {
    'ar_over_60_pct': {
        'display_name': 'A/R Over 60 Days',
        'target': '< 25%',
        'target_fn': lambda v: v < 25,
        'direction_good': 'down',
    },
    'payment_plan_compliance': {
        'display_name': 'Payment Plan Compliance',
        'target': '≥ 90%',
        'target_fn': lambda v: v >= 90,
        'direction_good': 'up',
    },
    'total_ar': {
        'display_name': 'Total A/R Balance',
        'target': None,
        'target_fn': None,
        'direction_good': 'down',
    },
    'overdue_tasks': {
        'display_name': 'Overdue Tasks',
        'target': '< 10',
        'target_fn': lambda v: v < 10,
        'direction_good': 'down',
    },
}


def _reshape_metric(m: dict) -> dict:
    """Reshape a metric dict from model format to template format."""
    name = m.get('name', '')
    value = m.get('value')
    prev = m.get('previous_value')
    raw_dir = m.get('direction', 'stable')  # up/down/stable

    config = METRIC_CONFIG.get(name, {})
    direction_good = config.get('direction_good', 'up')

    # Map raw direction to improving/declining/stable
    if raw_dir == 'up':
        direction = 'improving' if direction_good == 'up' else 'declining'
    elif raw_dir == 'down':
        direction = 'improving' if direction_good == 'down' else 'declining'
    else:
        direction = 'stable'

    # Target check
    target_fn = config.get('target_fn')
    on_target = target_fn(value) if (target_fn and value is not None) else None

    # Change percentage
    change_pct = None
    if prev is not None and prev != 0 and value is not None:
        change_pct = round((value - prev) / abs(prev) * 100, 1)

    # Fallback display name: convert snake_case to Title Case
    display_name = config.get('display_name') or name.replace('_', ' ').title()

    return {
        'name': name,
        'display_name': display_name,
        'current': value,
        'direction': direction,
        'target': config.get('target'),
        'on_target': on_target,
        'sparkline': None,
        'change_pct': change_pct,
        'insight': None,
    }


@router.get("/trends", response_class=HTMLResponse)
async def trends_dashboard(request: Request, metric: str = None):
    """Historical KPI trends dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    raw_summary = data.get_trends_summary()

    # Reshape metrics for template
    reshaped_metrics = [_reshape_metric(m) for m in raw_summary.get('metrics', [])]
    summary = {
        'metrics': reshaped_metrics,
        'total_metrics': len(reshaped_metrics),
    }

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
