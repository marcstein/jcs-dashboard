"""
Dashboard Data Access — Intake & CRM Pipeline Mixin

Provides intake pipeline data access for the dashboard:
- Pipeline board (Kanban view)
- Lead management
- Intake metrics and funnel stats
- Consultation scheduling
"""
from typing import Dict, List, Optional

from db.intake import (
    get_pipeline_board,
    get_leads_list,
    get_lead,
    create_lead,
    update_lead,
    archive_lead,
    get_lead_activities,
    get_recent_activities,
    get_intake_metrics,
    get_intake_trend,
    get_pipeline_stages,
    get_upcoming_consultations,
    get_available_slots,
    book_consultation,
    get_firm_forms,
    create_form,
    get_follow_up_rules,
    log_activity,
    seed_pipeline_stages,
    seed_default_follow_up_rules,
    ensure_intake_tables,
)


class IntakeDataMixin:
    """Intake pipeline data access for the dashboard."""

    def get_intake_board(self, include_archived: bool = False) -> Dict:
        """Get the full pipeline board (Kanban view)."""
        return get_pipeline_board(self.firm_id, include_archived)

    def get_intake_leads(self, stage: str = None, source: str = None,
                         assigned_to: str = None, search: str = None,
                         limit: int = 100) -> List[Dict]:
        """Get filtered leads list."""
        return get_leads_list(
            self.firm_id, stage=stage, source=source,
            assigned_to=assigned_to, search=search, limit=limit
        )

    def get_intake_lead(self, lead_id: int) -> Optional[Dict]:
        """Get a single lead with details."""
        return get_lead(self.firm_id, lead_id)

    def create_intake_lead(self, **kwargs) -> int:
        """Create a new lead."""
        return create_lead(self.firm_id, **kwargs)

    def update_intake_lead(self, lead_id: int, updated_by: str = "system",
                           **kwargs) -> bool:
        """Update a lead."""
        return update_lead(self.firm_id, lead_id, updated_by=updated_by, **kwargs)

    def archive_intake_lead(self, lead_id: int) -> bool:
        """Archive a lead."""
        return archive_lead(self.firm_id, lead_id)

    def get_intake_lead_activities(self, lead_id: int) -> List[Dict]:
        """Get activity history for a lead."""
        return get_lead_activities(self.firm_id, lead_id)

    def get_intake_recent_activities(self, limit: int = 30) -> List[Dict]:
        """Get recent activities across all leads."""
        return get_recent_activities(self.firm_id, limit)

    def get_intake_metrics(self, days: int = 30) -> Dict:
        """Get intake funnel metrics."""
        return get_intake_metrics(self.firm_id, days)

    def get_intake_trend(self, weeks: int = 12) -> List[Dict]:
        """Get weekly intake trend."""
        return get_intake_trend(self.firm_id, weeks)

    def get_intake_stages(self) -> List[Dict]:
        """Get pipeline stages."""
        return get_pipeline_stages(self.firm_id)

    def get_intake_consultations(self, days: int = 7) -> List[Dict]:
        """Get upcoming consultations."""
        return get_upcoming_consultations(self.firm_id, days)

    def get_intake_forms(self) -> List[Dict]:
        """Get all intake forms for the firm."""
        return get_firm_forms(self.firm_id)

    def get_intake_follow_up_rules(self) -> List[Dict]:
        """Get follow-up automation rules."""
        return get_follow_up_rules(self.firm_id)

    def ensure_intake_setup(self):
        """Ensure intake tables and default data exist."""
        ensure_intake_tables()
        stages = get_pipeline_stages(self.firm_id)
        if not stages:
            seed_pipeline_stages(self.firm_id)
            seed_default_follow_up_rules(self.firm_id)
