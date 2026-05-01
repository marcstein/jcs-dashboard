"""
Dashboard Data Access — Intake & CRM Pipeline Mixin

Provides intake pipeline data access for the dashboard:
- Pipeline board (Kanban view)
- Lead management
- Intake metrics and funnel stats
- Consultation scheduling
- Appointment reminders
- Conflict of interest checks
- Lead → MyCase conversion
- Custom fields
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
    # Reminders
    get_pending_reminders,
    get_reminder_stats,
    cancel_consultation_reminders,
    # Conflict checks
    run_conflict_check,
    get_lead_conflicts,
    resolve_conflict,
    has_unresolved_conflicts,
    # Lead conversion
    get_conversion_data,
    mark_lead_converted,
    # Custom fields
    get_custom_fields,
    create_custom_field,
    update_custom_field,
    delete_custom_field,
    set_lead_custom_field,
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

    # ---------- Reminders ----------

    def get_intake_pending_reminders(self) -> List[Dict]:
        """Get pending consultation reminders."""
        return get_pending_reminders(self.firm_id)

    def get_intake_reminder_stats(self, days: int = 30) -> Dict:
        """Get reminder send statistics."""
        return get_reminder_stats(self.firm_id, days)

    def cancel_intake_consultation_reminders(self, consultation_id: int):
        """Cancel reminders for a cancelled consultation."""
        return cancel_consultation_reminders(consultation_id)

    # ---------- Conflict Checks ----------

    def get_intake_lead_conflicts(self, lead_id: int) -> List[Dict]:
        """Get conflict check results for a lead."""
        return get_lead_conflicts(self.firm_id, lead_id)

    def resolve_intake_conflict(self, conflict_id: int, resolved_by: str,
                                status: str = "cleared", notes: str = None):
        """Resolve a conflict check."""
        return resolve_conflict(conflict_id, resolved_by, status, notes)

    def has_intake_unresolved_conflicts(self, lead_id: int) -> bool:
        """Check if lead has unresolved conflicts."""
        return has_unresolved_conflicts(self.firm_id, lead_id)

    # ---------- Lead Conversion ----------

    def get_intake_conversion_data(self, lead_id: int) -> Optional[Dict]:
        """Get lead data formatted for MyCase conversion."""
        return get_conversion_data(self.firm_id, lead_id)

    def mark_intake_lead_converted(self, lead_id: int,
                                    mycase_case_id: int = None,
                                    mycase_contact_id: int = None) -> bool:
        """Mark a lead as converted to MyCase case."""
        return mark_lead_converted(self.firm_id, lead_id,
                                    mycase_case_id, mycase_contact_id)

    # ---------- Custom Fields ----------

    def get_intake_custom_fields(self, active_only: bool = True) -> List[Dict]:
        """Get custom field definitions."""
        return get_custom_fields(self.firm_id, active_only)

    def create_intake_custom_field(self, field_key: str, field_label: str,
                                    **kwargs) -> int:
        """Create a custom field."""
        return create_custom_field(self.firm_id, field_key, field_label, **kwargs)

    def update_intake_custom_field(self, field_id: int, **kwargs):
        """Update a custom field definition."""
        return update_custom_field(field_id, **kwargs)

    def delete_intake_custom_field(self, field_id: int):
        """Soft-delete a custom field."""
        return delete_custom_field(field_id)

    def set_intake_lead_custom_field(self, lead_id: int,
                                      field_key: str, value) -> bool:
        """Set a custom field value on a lead."""
        return set_lead_custom_field(self.firm_id, lead_id, field_key, value)

    def ensure_intake_setup(self):
        """Ensure intake tables and default data exist."""
        ensure_intake_tables()
        stages = get_pipeline_stages(self.firm_id)
        if not stages:
            seed_pipeline_stages(self.firm_id)
            seed_default_follow_up_rules(self.firm_id)
