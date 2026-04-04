"""
FastAPI Dashboard Routes Package

Routes are organized by domain:
- main: Home page, staff pages, login/logout
- ar: A/R dashboard, collections, dunning
- attorneys: Attorney productivity
- phases: Case phases
- trends: KPI trends
- noiw: NOIW pipeline
- api: JSON API endpoints (chat, docket, documents, sync)
"""

from fastapi import FastAPI


def register_routes(app: FastAPI):
    """Register all route blueprints with the FastAPI app."""
    from .main import router as main_router
    from .ar import router as ar_router
    from .attorneys import router as attorneys_router
    from .phases import router as phases_router
    from .trends import router as trends_router
    from .noiw import router as noiw_router
    from .promises import router as promises_router
    from .payments import router as payments_router
    from .api import router as api_router
    from .firms import router as firms_router
    from .trust import router as trust_router
    from .phone import router as phone_router

    app.include_router(main_router)
    app.include_router(ar_router)
    app.include_router(attorneys_router)
    app.include_router(phases_router)
    app.include_router(trends_router)
    app.include_router(noiw_router)
    app.include_router(promises_router)
    app.include_router(payments_router)
    app.include_router(api_router)
    app.include_router(firms_router)
    app.include_router(trust_router)
    app.include_router(phone_router)
