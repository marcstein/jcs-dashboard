"""
Case phases routes
"""
from collections import defaultdict
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated
from dashboard.models import DashboardData

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
data = DashboardData()

# Map phase names to short names, codes, and sequence numbers
PHASE_META = {
    'Intake & Case Initiation': {'code': 'intake', 'short_name': 'Intake', 'sequence': 1, 'expected_days': 3},
    'Discovery & Investigation': {'code': 'discovery', 'short_name': 'Discovery', 'sequence': 2, 'expected_days': 56},
    'Legal Analysis & Motion Practice': {'code': 'motions', 'short_name': 'Motions', 'sequence': 3, 'expected_days': 70},
    'Case Strategy & Negotiation': {'code': 'strategy', 'short_name': 'Strategy', 'sequence': 4, 'expected_days': 42},
    'Trial Preparation': {'code': 'trial_prep', 'short_name': 'Trial Prep', 'sequence': 5, 'expected_days': 56},
    'Disposition & Sentencing': {'code': 'disposition', 'short_name': 'Disposition', 'sequence': 6, 'expected_days': 42},
    'Post-Disposition & Case Closure': {'code': 'post_disposition', 'short_name': 'Closing', 'sequence': 7, 'expected_days': 28},
}


def _get_phase_meta(phase_name):
    """Get metadata for a phase name, with fuzzy matching fallback."""
    if phase_name in PHASE_META:
        return PHASE_META[phase_name]
    # Fuzzy match on lowercase
    lower = (phase_name or '').lower()
    for name, meta in PHASE_META.items():
        if name.lower() in lower or lower in name.lower():
            return meta
        if meta['code'] in lower or meta['short_name'].lower() in lower:
            return meta
    return {'code': phase_name or 'unknown', 'short_name': phase_name or 'Unknown', 'sequence': 99, 'expected_days': None}


@router.get("/phases", response_class=HTMLResponse)
async def phases_dashboard(request: Request, phase: str = None):
    """Case Phases dashboard showing phase distribution and stalled cases."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    raw_summary = data.get_phases_summary()
    raw_stalled = data.get_stalled_cases(threshold_days=30)
    raw_velocity = data.get_phase_velocity()
    raw_by_case_type = data.get_phase_by_case_type()

    # Reshape summary: model returns {phases: [{phase_name, phase_number, count, percentage}]}
    # Template expects {total_cases, phases_count, distribution: [{code, short_name, case_count, percentage, sequence}]}
    distribution = []
    for p in raw_summary.get('phases', []):
        meta = _get_phase_meta(p.get('phase_name'))
        distribution.append({
            'code': meta['code'],
            'short_name': meta['short_name'],
            'sequence': meta['sequence'],
            'case_count': p.get('count', 0),
            'percentage': p.get('percentage', 0),
        })
    distribution.sort(key=lambda x: x['sequence'])
    summary = {
        'total_cases': raw_summary.get('total_cases', 0),
        'phases_count': len(distribution),
        'distribution': distribution,
    }

    # Reshape stalled: model returns {case_name, phase, entered, days_in_phase}
    # Template expects {case_name, current_phase, short_name, days_in_phase, phase_entered_at}
    stalled = []
    for s in raw_stalled:
        meta = _get_phase_meta(s.get('phase'))
        stalled.append({
            'case_name': s.get('case_name'),
            'current_phase': meta['code'],
            'short_name': meta['short_name'],
            'days_in_phase': s.get('days_in_phase', 0),
            'phase_entered_at': s.get('entered'),
        })

    # Reshape velocity: model returns {phase_name, avg_days, min_days, max_days, transitions}
    # Template expects {short_name, avg_days, expected_days, transitions}
    velocity = []
    for v in raw_velocity:
        meta = _get_phase_meta(v.get('phase_name'))
        velocity.append({
            'short_name': meta['short_name'],
            'avg_days': v.get('avg_days'),
            'expected_days': meta.get('expected_days'),
            'transitions': v.get('transitions', 0),
        })

    # Reshape by_case_type: model returns flat [{case_type, phase_name, count}]
    # Template expects [{practice_area, total, phases: {intake: N, discovery: N, ...}}]
    ct_map = defaultdict(lambda: {'total': 0, 'phases': defaultdict(int)})
    for row in raw_by_case_type:
        ct = row.get('case_type', 'Unknown')
        meta = _get_phase_meta(row.get('phase_name'))
        count = row.get('count', 0)
        ct_map[ct]['total'] += count
        ct_map[ct]['phases'][meta['code']] += count

    by_case_type = []
    for practice_area, info in sorted(ct_map.items(), key=lambda x: -x[1]['total']):
        by_case_type.append({
            'practice_area': practice_area,
            'total': info['total'],
            'phases': dict(info['phases']),
        })

    # Reshape phase_cases: model returns {case_name, entered, days_in_phase}
    # Template expects {case_name, phase_entered_at, days_in_phase}
    phase_cases = []
    if phase:
        raw_cases = data.get_cases_in_phase(phase, limit=50)
        for c in raw_cases:
            phase_cases.append({
                'case_name': c.get('case_name'),
                'phase_entered_at': c.get('entered'),
                'days_in_phase': c.get('days_in_phase', 0),
            })

    return templates.TemplateResponse("phases.html", {
        "request": request,
        "summary": summary,
        "stalled": stalled,
        "velocity": velocity,
        "by_case_type": by_case_type,
        "current_phase": phase,
        "phase_cases": phase_cases,
        "username": request.session.get("username"),
    })
