"""
Intake & CRM Pipeline — PostgreSQL Multi-Tenant

Lead management, intake pipeline stages, activity tracking,
embeddable forms, follow-up automation, and consultation scheduling.

Equivalent to Clio Grow functionality, purpose-built for
DUI and criminal defense firms.
"""
import json
import logging
import uuid
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)


# ============================================================
# Schema
# ============================================================

INTAKE_SCHEMA = """
-- Pipeline stage definitions per firm
CREATE TABLE IF NOT EXISTS intake_pipeline_stages (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    stage_name TEXT NOT NULL,
    stage_order INTEGER NOT NULL DEFAULT 0,
    color VARCHAR(7) DEFAULT '#4472C4',
    is_terminal BOOLEAN DEFAULT FALSE,
    auto_follow_up_hours INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, stage_name)
);
CREATE INDEX IF NOT EXISTS idx_intake_stages_firm
    ON intake_pipeline_stages(firm_id);

-- Lead / prospect records
CREATE TABLE IF NOT EXISTS intake_leads (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    external_id TEXT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    phone_alt TEXT,
    source TEXT DEFAULT 'website',
    source_detail TEXT,
    case_type TEXT,
    practice_area TEXT,
    stage_id INTEGER REFERENCES intake_pipeline_stages(id),
    stage_name TEXT NOT NULL DEFAULT 'New',
    assigned_to TEXT,
    priority TEXT DEFAULT 'normal',
    referral_source TEXT,
    notes TEXT,
    consultation_date TIMESTAMP,
    consultation_type TEXT,
    retained_date DATE,
    declined_date DATE,
    declined_reason TEXT,
    estimated_value NUMERIC(12, 2),
    custom_fields JSONB DEFAULT '{}',
    archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_contacted_at TIMESTAMP,
    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_intake_leads_firm
    ON intake_leads(firm_id);
CREATE INDEX IF NOT EXISTS idx_intake_leads_stage
    ON intake_leads(firm_id, stage_name);
CREATE INDEX IF NOT EXISTS idx_intake_leads_assigned
    ON intake_leads(firm_id, assigned_to);
CREATE INDEX IF NOT EXISTS idx_intake_leads_email
    ON intake_leads(firm_id, email);
CREATE INDEX IF NOT EXISTS idx_intake_leads_phone
    ON intake_leads(firm_id, phone);
CREATE INDEX IF NOT EXISTS idx_intake_leads_created
    ON intake_leads(firm_id, created_at DESC);

-- Activity log (calls, emails, notes, stage changes)
CREATE TABLE IF NOT EXISTS intake_activities (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    lead_id INTEGER NOT NULL REFERENCES intake_leads(id) ON DELETE CASCADE,
    activity_type TEXT NOT NULL,
    description TEXT,
    performed_by TEXT,
    old_stage TEXT,
    new_stage TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_intake_activities_lead
    ON intake_activities(lead_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_intake_activities_firm
    ON intake_activities(firm_id, created_at DESC);

-- Embeddable form configurations
CREATE TABLE IF NOT EXISTS intake_forms (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    form_token VARCHAR(64) NOT NULL UNIQUE,
    form_name TEXT NOT NULL DEFAULT 'Contact Form',
    fields JSONB NOT NULL DEFAULT '[
        {"name": "first_name", "label": "First Name", "type": "text", "required": true},
        {"name": "last_name", "label": "Last Name", "type": "text", "required": true},
        {"name": "email", "label": "Email", "type": "email", "required": true},
        {"name": "phone", "label": "Phone", "type": "tel", "required": true},
        {"name": "case_type", "label": "Type of Case", "type": "select", "required": false,
         "options": ["DUI/DWI", "Traffic", "Criminal Defense", "Expungement", "License Reinstatement", "Other"]},
        {"name": "message", "label": "Brief Description", "type": "textarea", "required": false}
    ]',
    success_message TEXT DEFAULT 'Thank you! We will contact you shortly.',
    redirect_url TEXT,
    notification_email TEXT,
    auto_assign_to TEXT,
    styling JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    submissions_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_intake_forms_firm
    ON intake_forms(firm_id);
CREATE INDEX IF NOT EXISTS idx_intake_forms_token
    ON intake_forms(form_token);

-- Form submission log (raw submissions before lead creation)
CREATE TABLE IF NOT EXISTS intake_form_submissions (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    form_id INTEGER REFERENCES intake_forms(id),
    lead_id INTEGER REFERENCES intake_leads(id),
    submission_data JSONB NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    referrer_url TEXT,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_intake_submissions_firm
    ON intake_form_submissions(firm_id, created_at DESC);

-- Follow-up automation rules
CREATE TABLE IF NOT EXISTS intake_follow_up_rules (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    rule_name TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    trigger_stage TEXT,
    delay_hours INTEGER NOT NULL DEFAULT 24,
    email_subject TEXT NOT NULL,
    email_body TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    send_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_intake_followup_firm
    ON intake_follow_up_rules(firm_id);

-- Scheduled follow-up queue
CREATE TABLE IF NOT EXISTS intake_follow_up_queue (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    lead_id INTEGER NOT NULL REFERENCES intake_leads(id) ON DELETE CASCADE,
    rule_id INTEGER REFERENCES intake_follow_up_rules(id),
    scheduled_at TIMESTAMP NOT NULL,
    sent_at TIMESTAMP,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_intake_followup_queue_pending
    ON intake_follow_up_queue(firm_id, status, scheduled_at)
    WHERE status = 'pending';

-- Consultation availability windows
CREATE TABLE IF NOT EXISTS intake_availability (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    attorney_name TEXT,
    day_of_week INTEGER NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    slot_duration_minutes INTEGER DEFAULT 30,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_intake_availability_firm
    ON intake_availability(firm_id);

-- Booked consultations
CREATE TABLE IF NOT EXISTS intake_consultations (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    lead_id INTEGER NOT NULL REFERENCES intake_leads(id) ON DELETE CASCADE,
    attorney_name TEXT,
    consultation_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    consultation_type TEXT DEFAULT 'phone',
    location TEXT,
    meeting_url TEXT,
    status TEXT DEFAULT 'scheduled',
    notes TEXT,
    confirmed_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    completed_at TIMESTAMP,
    outcome TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_intake_consultations_firm
    ON intake_consultations(firm_id, consultation_date);
CREATE INDEX IF NOT EXISTS idx_intake_consultations_lead
    ON intake_consultations(lead_id);

-- Consultation reminders (email + SMS)
CREATE TABLE IF NOT EXISTS intake_consultation_reminders (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    consultation_id INTEGER NOT NULL REFERENCES intake_consultations(id) ON DELETE CASCADE,
    lead_id INTEGER NOT NULL REFERENCES intake_leads(id) ON DELETE CASCADE,
    reminder_type TEXT NOT NULL,  -- '24h_email', '1h_email', '24h_sms', '1h_sms'
    channel TEXT NOT NULL,        -- 'email' or 'sms'
    scheduled_at TIMESTAMP NOT NULL,
    sent_at TIMESTAMP,
    status TEXT DEFAULT 'pending',  -- pending, sent, failed, cancelled
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_intake_reminders_pending
    ON intake_consultation_reminders(firm_id, status, scheduled_at)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_intake_reminders_consult
    ON intake_consultation_reminders(consultation_id);

-- Conflict checks
CREATE TABLE IF NOT EXISTS intake_conflict_checks (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    lead_id INTEGER NOT NULL REFERENCES intake_leads(id) ON DELETE CASCADE,
    check_type TEXT NOT NULL,          -- 'name_match', 'phone_match', 'email_match'
    matched_entity_type TEXT NOT NULL, -- 'client', 'lead', 'opposing_party'
    matched_entity_id INTEGER,
    matched_name TEXT,
    matched_detail TEXT,               -- extra info (case number, role, etc.)
    similarity_score NUMERIC(5,2),     -- 0-100
    status TEXT DEFAULT 'unresolved',  -- unresolved, cleared, flagged
    resolved_by TEXT,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_intake_conflicts_lead
    ON intake_conflict_checks(lead_id);
CREATE INDEX IF NOT EXISTS idx_intake_conflicts_firm
    ON intake_conflict_checks(firm_id, status);

-- Custom field definitions per firm
CREATE TABLE IF NOT EXISTS intake_custom_fields (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    field_key TEXT NOT NULL,
    field_label TEXT NOT NULL,
    field_type TEXT NOT NULL DEFAULT 'text',  -- text, number, date, select, checkbox, textarea
    field_options JSONB DEFAULT '[]',         -- for select type
    is_required BOOLEAN DEFAULT FALSE,
    display_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    show_on_card BOOLEAN DEFAULT FALSE,       -- show on Kanban card
    show_on_form BOOLEAN DEFAULT TRUE,        -- show on public forms
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, field_key)
);
CREATE INDEX IF NOT EXISTS idx_intake_custom_fields_firm
    ON intake_custom_fields(firm_id);
"""


def ensure_intake_tables():
    """Create all intake tables if they don't exist."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(INTAKE_SCHEMA)
    logger.info("Intake tables ensured")


# ============================================================
# Default Pipeline Stages
# ============================================================

DEFAULT_STAGES = [
    ("New", 1, "#4472C4", False, 24),       # Auto-follow-up after 24 hours
    ("Contacted", 2, "#2196F3", False, 48),  # Follow up if no response in 48h
    ("Consultation Scheduled", 3, "#FF9800", False, None),
    ("Consultation Complete", 4, "#9C27B0", False, 24),
    ("Retained", 5, "#2E7D32", True, None),
    ("Declined", 6, "#C62828", True, None),
    ("Lost", 7, "#757575", True, None),
]


def seed_pipeline_stages(firm_id: str) -> int:
    """Seed default pipeline stages for a firm."""
    ensure_intake_tables()
    count = 0
    with get_connection() as conn:
        cur = conn.cursor()
        for name, order, color, terminal, follow_up in DEFAULT_STAGES:
            cur.execute("""
                INSERT INTO intake_pipeline_stages
                    (firm_id, stage_name, stage_order, color, is_terminal, auto_follow_up_hours)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (firm_id, stage_name) DO UPDATE SET
                    stage_order = EXCLUDED.stage_order,
                    color = EXCLUDED.color,
                    is_terminal = EXCLUDED.is_terminal,
                    auto_follow_up_hours = EXCLUDED.auto_follow_up_hours
            """, (firm_id, name, order, color, terminal, follow_up))
            count += 1
    logger.info(f"Seeded {count} pipeline stages for {firm_id}")
    return count


# ============================================================
# Pipeline Stage Queries
# ============================================================

def get_pipeline_stages(firm_id: str) -> List[Dict]:
    """Get all pipeline stages for a firm, ordered by stage_order."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, firm_id, stage_name, stage_order, color,
                   is_terminal, auto_follow_up_hours
            FROM intake_pipeline_stages
            WHERE firm_id = %s
            ORDER BY stage_order
        """, (firm_id,))
        return [dict(row) for row in cur.fetchall()]


# ============================================================
# Lead CRUD
# ============================================================

def create_lead(firm_id: str, **kwargs) -> int:
    """Create a new intake lead. Returns the lead ID."""
    # Determine initial stage
    stage_name = kwargs.pop("stage_name", "New")

    # Look up stage_id
    stage_id = None
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM intake_pipeline_stages
            WHERE firm_id = %s AND stage_name = %s
        """, (firm_id, stage_name))
        row = cur.fetchone()
        if row:
            stage_id = row["id"]

    fields = {
        "firm_id": firm_id,
        "first_name": kwargs.get("first_name", ""),
        "last_name": kwargs.get("last_name", ""),
        "email": kwargs.get("email"),
        "phone": kwargs.get("phone"),
        "phone_alt": kwargs.get("phone_alt"),
        "source": kwargs.get("source", "website"),
        "source_detail": kwargs.get("source_detail"),
        "case_type": kwargs.get("case_type"),
        "practice_area": kwargs.get("practice_area"),
        "stage_id": stage_id,
        "stage_name": stage_name,
        "assigned_to": kwargs.get("assigned_to"),
        "priority": kwargs.get("priority", "normal"),
        "referral_source": kwargs.get("referral_source"),
        "notes": kwargs.get("notes"),
        "estimated_value": kwargs.get("estimated_value"),
    }

    columns = ", ".join(fields.keys())
    placeholders = ", ".join(["%s"] * len(fields))

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO intake_leads ({columns})
            VALUES ({placeholders})
            RETURNING id
        """, tuple(fields.values()))
        lead_id = cur.fetchone()["id"]

        # Log the creation activity
        cur.execute("""
            INSERT INTO intake_activities
                (firm_id, lead_id, activity_type, description, performed_by)
            VALUES (%s, %s, 'lead_created', %s, %s)
        """, (firm_id, lead_id, f"Lead created from {fields['source']}", kwargs.get("created_by", "system")))

    # Auto-run conflict check
    try:
        conflicts = run_conflict_check(
            firm_id, lead_id,
            fields["first_name"], fields["last_name"],
            email=fields.get("email"),
            phone=fields.get("phone"),
        )
        if conflicts:
            log_activity(
                firm_id, lead_id, "conflict_detected",
                f"{len(conflicts)} potential conflict(s) found — review required",
                performed_by="system"
            )
    except Exception as e:
        logger.warning(f"Conflict check failed for lead {lead_id}: {e}")

    return lead_id


def get_lead(firm_id: str, lead_id: int) -> Optional[Dict]:
    """Get a single lead by ID."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT l.*, ps.color as stage_color
            FROM intake_leads l
            LEFT JOIN intake_pipeline_stages ps
                ON ps.firm_id = l.firm_id AND ps.stage_name = l.stage_name
            WHERE l.firm_id = %s AND l.id = %s
        """, (firm_id, lead_id))
        row = cur.fetchone()
        return dict(row) if row else None


def update_lead(firm_id: str, lead_id: int, updated_by: str = "system", **kwargs) -> bool:
    """Update a lead's fields. Returns True if updated."""
    if not kwargs:
        return False

    # Handle stage change specially (log activity)
    old_stage = None
    new_stage = kwargs.get("stage_name")
    if new_stage:
        lead = get_lead(firm_id, lead_id)
        if lead:
            old_stage = lead["stage_name"]

        # Look up stage_id for new stage
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id FROM intake_pipeline_stages
                WHERE firm_id = %s AND stage_name = %s
            """, (firm_id, new_stage))
            row = cur.fetchone()
            if row:
                kwargs["stage_id"] = row["id"]

        # Set terminal stage dates
        if new_stage == "Retained":
            kwargs["retained_date"] = date.today()
        elif new_stage == "Declined":
            kwargs["declined_date"] = date.today()

    kwargs["updated_at"] = datetime.now()
    kwargs["last_activity_at"] = datetime.now()

    set_clause = ", ".join([f"{k} = %s" for k in kwargs.keys()])
    values = list(kwargs.values())

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            UPDATE intake_leads SET {set_clause}
            WHERE firm_id = %s AND id = %s
        """, (*values, firm_id, lead_id))

        # Log stage change activity
        if new_stage and old_stage and old_stage != new_stage:
            cur.execute("""
                INSERT INTO intake_activities
                    (firm_id, lead_id, activity_type, description,
                     performed_by, old_stage, new_stage)
                VALUES (%s, %s, 'stage_changed', %s, %s, %s, %s)
            """, (firm_id, lead_id,
                  f"Stage changed from {old_stage} to {new_stage}",
                  updated_by, old_stage, new_stage))

    return True


def archive_lead(firm_id: str, lead_id: int) -> bool:
    """Archive a lead (soft delete)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE intake_leads SET archived = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE firm_id = %s AND id = %s
        """, (firm_id, lead_id))
        return cur.rowcount > 0


# ============================================================
# Pipeline Queries (for Kanban board)
# ============================================================

def get_pipeline_board(firm_id: str, include_archived: bool = False) -> Dict:
    """Get all leads grouped by stage for the Kanban board.

    Returns: {
        "stages": [{"name": ..., "color": ..., "leads": [...]}],
        "stats": {"total": N, "this_week": N, "conversion_rate": X}
    }
    """
    stages = get_pipeline_stages(firm_id)
    if not stages:
        seed_pipeline_stages(firm_id)
        stages = get_pipeline_stages(firm_id)

    archive_filter = "" if include_archived else "AND l.archived = FALSE"

    with get_connection() as conn:
        cur = conn.cursor()

        # Get leads per stage
        board = []
        for stage in stages:
            cur.execute(f"""
                SELECT l.id, l.first_name, l.last_name, l.email, l.phone,
                       l.case_type, l.source, l.assigned_to, l.priority,
                       l.created_at, l.last_contacted_at, l.last_activity_at,
                       l.estimated_value, l.consultation_date, l.notes
                FROM intake_leads l
                WHERE l.firm_id = %s AND l.stage_name = %s {archive_filter}
                ORDER BY l.priority DESC, l.created_at DESC
            """, (firm_id, stage["stage_name"]))
            leads = [dict(row) for row in cur.fetchall()]
            board.append({
                "id": stage["id"],
                "name": stage["stage_name"],
                "color": stage["color"],
                "order": stage["stage_order"],
                "is_terminal": stage["is_terminal"],
                "leads": leads,
                "count": len(leads),
            })

        # Stats
        cur.execute(f"""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - INTERVAL '7 days') as this_week,
                COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - INTERVAL '30 days') as this_month,
                COUNT(*) FILTER (WHERE stage_name = 'Retained') as retained,
                COUNT(*) FILTER (WHERE stage_name IN ('Declined', 'Lost')) as lost
            FROM intake_leads l
            WHERE firm_id = %s {archive_filter}
        """, (firm_id,))
        stats_row = dict(cur.fetchone())

        total_resolved = stats_row["retained"] + stats_row["lost"]
        conversion_rate = (stats_row["retained"] / total_resolved * 100) if total_resolved > 0 else 0

        stats = {
            "total": stats_row["total"],
            "this_week": stats_row["this_week"],
            "this_month": stats_row["this_month"],
            "retained": stats_row["retained"],
            "lost": stats_row["lost"],
            "conversion_rate": round(conversion_rate, 1),
        }

    return {"stages": board, "stats": stats}


def get_leads_list(
    firm_id: str,
    stage: str = None,
    source: str = None,
    assigned_to: str = None,
    search: str = None,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict]:
    """Get leads with optional filters."""
    conditions = ["l.firm_id = %s"]
    params = [firm_id]

    if not include_archived:
        conditions.append("l.archived = FALSE")
    if stage:
        conditions.append("l.stage_name = %s")
        params.append(stage)
    if source:
        conditions.append("l.source = %s")
        params.append(source)
    if assigned_to:
        conditions.append("l.assigned_to = %s")
        params.append(assigned_to)
    if search:
        conditions.append("""
            (l.first_name ILIKE %s OR l.last_name ILIKE %s
             OR l.email ILIKE %s OR l.phone ILIKE %s)
        """)
        search_param = f"%{search}%"
        params.extend([search_param] * 4)

    where = " AND ".join(conditions)

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT l.*, ps.color as stage_color
            FROM intake_leads l
            LEFT JOIN intake_pipeline_stages ps
                ON ps.firm_id = l.firm_id AND ps.stage_name = l.stage_name
            WHERE {where}
            ORDER BY l.created_at DESC
            LIMIT %s OFFSET %s
        """, (*params, limit, offset))
        return [dict(row) for row in cur.fetchall()]


# ============================================================
# Activity Log
# ============================================================

def log_activity(firm_id: str, lead_id: int, activity_type: str,
                 description: str = None, performed_by: str = None,
                 metadata: dict = None):
    """Log an activity for a lead."""
    import json
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO intake_activities
                (firm_id, lead_id, activity_type, description, performed_by, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (firm_id, lead_id, activity_type, description, performed_by,
              json.dumps(metadata) if metadata else None))

        # Update last_activity_at on lead
        cur.execute("""
            UPDATE intake_leads SET last_activity_at = CURRENT_TIMESTAMP
            WHERE firm_id = %s AND id = %s
        """, (firm_id, lead_id))

        if activity_type in ('call', 'email_sent', 'sms_sent'):
            cur.execute("""
                UPDATE intake_leads SET last_contacted_at = CURRENT_TIMESTAMP
                WHERE firm_id = %s AND id = %s
            """, (firm_id, lead_id))


def get_lead_activities(firm_id: str, lead_id: int, limit: int = 50) -> List[Dict]:
    """Get activity history for a lead."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM intake_activities
            WHERE firm_id = %s AND lead_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (firm_id, lead_id, limit))
        return [dict(row) for row in cur.fetchall()]


def get_recent_activities(firm_id: str, limit: int = 30) -> List[Dict]:
    """Get recent activities across all leads."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT a.*, l.first_name, l.last_name, l.email
            FROM intake_activities a
            JOIN intake_leads l ON l.id = a.lead_id AND l.firm_id = a.firm_id
            WHERE a.firm_id = %s
            ORDER BY a.created_at DESC
            LIMIT %s
        """, (firm_id, limit))
        return [dict(row) for row in cur.fetchall()]


# ============================================================
# Form Management
# ============================================================

def create_form(firm_id: str, form_name: str = "Contact Form", **kwargs) -> Dict:
    """Create an embeddable intake form. Returns the form record."""
    form_token = uuid.uuid4().hex[:16]

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO intake_forms
                (firm_id, form_token, form_name, notification_email,
                 auto_assign_to, success_message, redirect_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (firm_id, form_token, form_name,
              kwargs.get("notification_email"),
              kwargs.get("auto_assign_to"),
              kwargs.get("success_message", "Thank you! We will contact you shortly."),
              kwargs.get("redirect_url")))
        return dict(cur.fetchone())


def get_form_by_token(form_token: str) -> Optional[Dict]:
    """Get a form by its public token (no firm_id needed — token is unique)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM intake_forms
            WHERE form_token = %s AND is_active = TRUE
        """, (form_token,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_firm_forms(firm_id: str) -> List[Dict]:
    """Get all forms for a firm."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM intake_forms
            WHERE firm_id = %s
            ORDER BY created_at DESC
        """, (firm_id,))
        return [dict(row) for row in cur.fetchall()]


def record_form_submission(form_id: int, firm_id: str, submission_data: dict,
                           ip_address: str = None, user_agent: str = None,
                           referrer_url: str = None) -> int:
    """Record a form submission and create a lead. Returns lead_id."""
    import json

    with get_connection() as conn:
        cur = conn.cursor()

        # Get form config
        cur.execute("SELECT * FROM intake_forms WHERE id = %s", (form_id,))
        form = cur.fetchone()
        if not form:
            raise ValueError(f"Form {form_id} not found")
        form = dict(form)

        # Create the lead
        lead_id = create_lead(
            firm_id=firm_id,
            first_name=submission_data.get("first_name", ""),
            last_name=submission_data.get("last_name", ""),
            email=submission_data.get("email"),
            phone=submission_data.get("phone"),
            case_type=submission_data.get("case_type"),
            source="website_form",
            source_detail=form["form_name"],
            assigned_to=form["auto_assign_to"],
            notes=submission_data.get("message"),
            created_by="form_submission",
        )

        # Record raw submission
        cur.execute("""
            INSERT INTO intake_form_submissions
                (firm_id, form_id, lead_id, submission_data,
                 ip_address, user_agent, referrer_url, processed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            RETURNING id
        """, (firm_id, form_id, lead_id,
              json.dumps(submission_data),
              ip_address, user_agent, referrer_url))

        # Increment submission count
        cur.execute("""
            UPDATE intake_forms SET submissions_count = submissions_count + 1
            WHERE id = %s
        """, (form_id,))

    return lead_id


# ============================================================
# Consultation Scheduling
# ============================================================

def set_availability(firm_id: str, attorney_name: str, day_of_week: int,
                     start_time: str, end_time: str,
                     slot_duration: int = 30) -> int:
    """Set consultation availability for an attorney on a day of week.

    day_of_week: 0=Monday, 6=Sunday
    start_time/end_time: "HH:MM" format
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO intake_availability
                (firm_id, attorney_name, day_of_week, start_time,
                 end_time, slot_duration_minutes)
            VALUES (%s, %s, %s, %s::time, %s::time, %s)
            RETURNING id
        """, (firm_id, attorney_name, day_of_week, start_time, end_time, slot_duration))
        return cur.fetchone()["id"]


def get_availability(firm_id: str, attorney_name: str = None) -> List[Dict]:
    """Get availability windows."""
    with get_connection() as conn:
        cur = conn.cursor()
        if attorney_name:
            cur.execute("""
                SELECT * FROM intake_availability
                WHERE firm_id = %s AND attorney_name = %s AND is_active = TRUE
                ORDER BY day_of_week, start_time
            """, (firm_id, attorney_name))
        else:
            cur.execute("""
                SELECT * FROM intake_availability
                WHERE firm_id = %s AND is_active = TRUE
                ORDER BY attorney_name, day_of_week, start_time
            """, (firm_id,))
        return [dict(row) for row in cur.fetchall()]


def get_available_slots(firm_id: str, target_date: date,
                        attorney_name: str = None) -> List[Dict]:
    """Get available consultation slots for a given date.

    Checks availability windows and excludes already-booked slots.
    """
    day_of_week = target_date.weekday()  # 0=Mon

    with get_connection() as conn:
        cur = conn.cursor()

        # Get availability windows for this day
        if attorney_name:
            cur.execute("""
                SELECT * FROM intake_availability
                WHERE firm_id = %s AND day_of_week = %s
                  AND attorney_name = %s AND is_active = TRUE
            """, (firm_id, day_of_week, attorney_name))
        else:
            cur.execute("""
                SELECT * FROM intake_availability
                WHERE firm_id = %s AND day_of_week = %s AND is_active = TRUE
            """, (firm_id, day_of_week))

        windows = [dict(row) for row in cur.fetchall()]

        # Get existing bookings for this date
        cur.execute("""
            SELECT start_time, end_time, attorney_name
            FROM intake_consultations
            WHERE firm_id = %s AND consultation_date = %s
              AND status NOT IN ('cancelled')
        """, (firm_id, target_date))
        booked = [dict(row) for row in cur.fetchall()]

    # Generate time slots from windows, excluding booked ones
    slots = []
    for window in windows:
        start = window["start_time"]
        end = window["end_time"]
        duration = timedelta(minutes=window["slot_duration_minutes"])
        atty = window["attorney_name"]

        # Generate slots within window
        from datetime import datetime as dt
        slot_start = dt.combine(target_date, start)
        slot_end_limit = dt.combine(target_date, end)

        while slot_start + duration <= slot_end_limit:
            slot_time = slot_start.time()
            slot_end_time = (slot_start + duration).time()

            # Check if this slot overlaps any booking
            is_booked = any(
                b["attorney_name"] == atty
                and b["start_time"] < slot_end_time
                and b["end_time"] > slot_time
                for b in booked
            )

            if not is_booked:
                slots.append({
                    "attorney_name": atty,
                    "date": target_date.isoformat(),
                    "start_time": slot_time.strftime("%H:%M"),
                    "end_time": slot_end_time.strftime("%H:%M"),
                    "duration_minutes": window["slot_duration_minutes"],
                })

            slot_start += duration

    return slots


def book_consultation(firm_id: str, lead_id: int, attorney_name: str,
                      consultation_date: date, start_time: str,
                      end_time: str, consultation_type: str = "phone",
                      notes: str = None) -> int:
    """Book a consultation slot. Returns consultation ID."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO intake_consultations
                (firm_id, lead_id, attorney_name, consultation_date,
                 start_time, end_time, consultation_type, notes)
            VALUES (%s, %s, %s, %s, %s::time, %s::time, %s, %s)
            RETURNING id
        """, (firm_id, lead_id, attorney_name, consultation_date,
              start_time, end_time, consultation_type, notes))
        consult_id = cur.fetchone()["id"]

        # Update lead
        cur.execute("""
            UPDATE intake_leads SET
                consultation_date = %s,
                consultation_type = %s,
                stage_name = 'Consultation Scheduled',
                updated_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE firm_id = %s AND id = %s
        """, (datetime.combine(consultation_date,
                               datetime.strptime(start_time, "%H:%M").time()),
              consultation_type, firm_id, lead_id))

        # Log activity
        log_activity(firm_id, lead_id, "consultation_booked",
                     f"Consultation scheduled for {consultation_date} at {start_time} with {attorney_name}",
                     performed_by="system")

    # Schedule reminders (email + SMS) — done outside the transaction
    lead = get_lead(firm_id, lead_id)
    if lead:
        schedule_consultation_reminders(
            firm_id, consult_id, lead_id,
            consultation_date, start_time,
            lead_email=lead.get("email"),
            lead_phone=lead.get("phone"),
        )

    return consult_id


def get_upcoming_consultations(firm_id: str, days: int = 7) -> List[Dict]:
    """Get upcoming consultations."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.*, l.first_name, l.last_name, l.email, l.phone,
                   l.case_type, l.source
            FROM intake_consultations c
            JOIN intake_leads l ON l.id = c.lead_id AND l.firm_id = c.firm_id
            WHERE c.firm_id = %s
              AND c.consultation_date BETWEEN CURRENT_DATE AND CURRENT_DATE + %s
              AND c.status = 'scheduled'
            ORDER BY c.consultation_date, c.start_time
        """, (firm_id, days))
        return [dict(row) for row in cur.fetchall()]


# ============================================================
# Follow-Up Rules
# ============================================================

def get_follow_up_rules(firm_id: str) -> List[Dict]:
    """Get all follow-up rules for a firm."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM intake_follow_up_rules
            WHERE firm_id = %s
            ORDER BY trigger_stage, delay_hours
        """, (firm_id,))
        return [dict(row) for row in cur.fetchall()]


def create_follow_up_rule(firm_id: str, rule_name: str, trigger_type: str,
                          trigger_stage: str, delay_hours: int,
                          email_subject: str, email_body: str) -> int:
    """Create a follow-up automation rule."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO intake_follow_up_rules
                (firm_id, rule_name, trigger_type, trigger_stage,
                 delay_hours, email_subject, email_body)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (firm_id, rule_name, trigger_type, trigger_stage,
              delay_hours, email_subject, email_body))
        return cur.fetchone()["id"]


def seed_default_follow_up_rules(firm_id: str) -> int:
    """Seed default follow-up rules for a firm."""
    rules = [
        {
            "rule_name": "New Lead - Immediate Response",
            "trigger_type": "stage_enter",
            "trigger_stage": "New",
            "delay_hours": 1,
            "email_subject": "Thank you for contacting {firm_name}",
            "email_body": (
                "Dear {first_name},\n\n"
                "Thank you for reaching out to {firm_name}. We received your inquiry "
                "and a member of our team will contact you within 24 hours to discuss "
                "your case.\n\n"
                "If you need immediate assistance, please call us at {firm_phone}.\n\n"
                "Best regards,\n{firm_name}"
            ),
        },
        {
            "rule_name": "No Contact After 24 Hours",
            "trigger_type": "stale_lead",
            "trigger_stage": "New",
            "delay_hours": 24,
            "email_subject": "Following up on your inquiry - {firm_name}",
            "email_body": (
                "Dear {first_name},\n\n"
                "We wanted to follow up on your recent inquiry. We understand that "
                "dealing with legal matters can be stressful, and we're here to help.\n\n"
                "Would you like to schedule a free consultation? You can reply to this "
                "email or call us at {firm_phone}.\n\n"
                "Best regards,\n{firm_name}"
            ),
        },
        {
            "rule_name": "Post-Consultation Follow-Up",
            "trigger_type": "stage_enter",
            "trigger_stage": "Consultation Complete",
            "delay_hours": 24,
            "email_subject": "Thank you for meeting with us - {firm_name}",
            "email_body": (
                "Dear {first_name},\n\n"
                "Thank you for taking the time to meet with us regarding your case. "
                "We hope the consultation was helpful.\n\n"
                "If you'd like to move forward with representation, or if you have "
                "any additional questions, please don't hesitate to reach out.\n\n"
                "Best regards,\n{firm_name}"
            ),
        },
    ]

    count = 0
    for rule in rules:
        create_follow_up_rule(firm_id, **rule)
        count += 1
    return count


def get_pending_follow_ups(firm_id: str) -> List[Dict]:
    """Get follow-up emails that are due to be sent."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT q.*, l.first_name, l.last_name, l.email,
                   r.email_subject, r.email_body
            FROM intake_follow_up_queue q
            JOIN intake_leads l ON l.id = q.lead_id AND l.firm_id = q.firm_id
            JOIN intake_follow_up_rules r ON r.id = q.rule_id
            WHERE q.firm_id = %s AND q.status = 'pending'
              AND q.scheduled_at <= CURRENT_TIMESTAMP
              AND l.email IS NOT NULL
              AND l.archived = FALSE
            ORDER BY q.scheduled_at
        """, (firm_id,))
        return [dict(row) for row in cur.fetchall()]


# ============================================================
# Intake Metrics
# ============================================================

def get_intake_metrics(firm_id: str, days: int = 30) -> Dict:
    """Get intake funnel metrics for the last N days."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total_leads,
                COUNT(*) FILTER (WHERE source = 'website_form') as from_form,
                COUNT(*) FILTER (WHERE source = 'phone') as from_phone,
                COUNT(*) FILTER (WHERE source = 'referral') as from_referral,
                COUNT(*) FILTER (WHERE source = 'walk_in') as from_walkin,
                COUNT(*) FILTER (WHERE stage_name = 'Retained') as retained,
                COUNT(*) FILTER (WHERE stage_name = 'Declined') as declined,
                COUNT(*) FILTER (WHERE stage_name = 'Lost') as lost,
                COUNT(*) FILTER (WHERE consultation_date IS NOT NULL) as had_consultation,
                AVG(EXTRACT(EPOCH FROM (
                    CASE WHEN last_contacted_at IS NOT NULL
                    THEN last_contacted_at - created_at
                    END
                )) / 3600)::numeric(10,1) as avg_response_hours,
                AVG(EXTRACT(EPOCH FROM (
                    CASE WHEN retained_date IS NOT NULL
                    THEN retained_date::timestamp - created_at
                    END
                )) / 86400)::numeric(10,1) as avg_days_to_retain
            FROM intake_leads
            WHERE firm_id = %s
              AND created_at >= CURRENT_DATE - INTERVAL '%s days'
              AND archived = FALSE
        """, (firm_id, days))
        return dict(cur.fetchone())


def get_intake_trend(firm_id: str, weeks: int = 12) -> List[Dict]:
    """Get weekly intake trend data."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            WITH weeks AS (
                SELECT generate_series(
                    date_trunc('week', CURRENT_DATE - INTERVAL '%s weeks'),
                    date_trunc('week', CURRENT_DATE),
                    INTERVAL '1 week'
                )::date as week_start
            )
            SELECT
                w.week_start,
                COUNT(l.id) as new_leads,
                COUNT(l.id) FILTER (WHERE l.stage_name = 'Retained') as retained,
                COUNT(l.id) FILTER (WHERE l.stage_name IN ('Declined', 'Lost')) as lost
            FROM weeks w
            LEFT JOIN intake_leads l
                ON l.firm_id = %s
                AND date_trunc('week', l.created_at) = w.week_start
                AND l.archived = FALSE
            GROUP BY w.week_start
            ORDER BY w.week_start
        """, (weeks, firm_id))
        return [dict(row) for row in cur.fetchall()]


# ============================================================
# Consultation Reminders
# ============================================================

def schedule_consultation_reminders(firm_id: str, consultation_id: int,
                                     lead_id: int,
                                     consultation_date: date,
                                     start_time: str,
                                     lead_email: Optional[str] = None,
                                     lead_phone: Optional[str] = None) -> int:
    """Schedule email and SMS reminders for a consultation.

    Creates up to 4 reminders:
    - 24-hour email reminder
    - 1-hour email reminder
    - 24-hour SMS reminder
    - 1-hour SMS reminder
    """
    consult_dt = datetime.combine(
        consultation_date,
        datetime.strptime(start_time, "%H:%M").time()
    )
    reminders = []
    if lead_email:
        reminders.append(("24h_email", "email", consult_dt - timedelta(hours=24)))
        reminders.append(("1h_email", "email", consult_dt - timedelta(hours=1)))
    if lead_phone:
        reminders.append(("24h_sms", "sms", consult_dt - timedelta(hours=24)))
        reminders.append(("1h_sms", "sms", consult_dt - timedelta(hours=1)))

    count = 0
    now = datetime.now()
    with get_connection() as conn:
        cur = conn.cursor()
        for rtype, channel, scheduled_at in reminders:
            if scheduled_at <= now:
                continue  # Don't schedule reminders in the past
            cur.execute("""
                INSERT INTO intake_consultation_reminders
                    (firm_id, consultation_id, lead_id, reminder_type,
                     channel, scheduled_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                ON CONFLICT DO NOTHING
            """, (firm_id, consultation_id, lead_id, rtype,
                  channel, scheduled_at))
            count += 1
    return count


def get_pending_reminders(firm_id: str = None) -> List[Dict]:
    """Get all reminders that are due to be sent now.

    If firm_id is None, returns reminders across all firms (for worker).
    """
    with get_connection() as conn:
        cur = conn.cursor()
        if firm_id:
            cur.execute("""
                SELECT r.*, l.first_name, l.last_name, l.email, l.phone,
                       c.consultation_date, c.start_time, c.end_time,
                       c.consultation_type, c.attorney_name, c.location,
                       c.meeting_url, c.status as consult_status
                FROM intake_consultation_reminders r
                JOIN intake_leads l ON l.id = r.lead_id AND l.firm_id = r.firm_id
                JOIN intake_consultations c ON c.id = r.consultation_id
                    AND c.firm_id = r.firm_id
                WHERE r.firm_id = %s
                  AND r.status = 'pending'
                  AND r.scheduled_at <= CURRENT_TIMESTAMP
                  AND c.status = 'scheduled'
                ORDER BY r.scheduled_at
            """, (firm_id,))
        else:
            cur.execute("""
                SELECT r.*, l.first_name, l.last_name, l.email, l.phone,
                       c.consultation_date, c.start_time, c.end_time,
                       c.consultation_type, c.attorney_name, c.location,
                       c.meeting_url, c.status as consult_status
                FROM intake_consultation_reminders r
                JOIN intake_leads l ON l.id = r.lead_id AND l.firm_id = r.firm_id
                JOIN intake_consultations c ON c.id = r.consultation_id
                    AND c.firm_id = r.firm_id
                WHERE r.status = 'pending'
                  AND r.scheduled_at <= CURRENT_TIMESTAMP
                  AND c.status = 'scheduled'
                ORDER BY r.scheduled_at
            """)
        return [dict(row) for row in cur.fetchall()]


def mark_reminder_sent(reminder_id: int, error_message: str = None):
    """Mark a reminder as sent or failed."""
    status = "failed" if error_message else "sent"
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE intake_consultation_reminders
            SET status = %s, sent_at = CURRENT_TIMESTAMP,
                error_message = %s
            WHERE id = %s
        """, (status, error_message, reminder_id))


def cancel_consultation_reminders(consultation_id: int):
    """Cancel all pending reminders for a cancelled consultation."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE intake_consultation_reminders
            SET status = 'cancelled'
            WHERE consultation_id = %s AND status = 'pending'
        """, (consultation_id,))


def get_reminder_stats(firm_id: str, days: int = 30) -> Dict:
    """Get reminder statistics for a firm."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'sent') as sent,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled,
                COUNT(*) FILTER (WHERE channel = 'email') as email_total,
                COUNT(*) FILTER (WHERE channel = 'sms') as sms_total
            FROM intake_consultation_reminders
            WHERE firm_id = %s
              AND created_at >= CURRENT_DATE - INTERVAL '%s days'
        """, (firm_id, days))
        return dict(cur.fetchone())


# ============================================================
# Conflict of Interest Checks
# ============================================================

def run_conflict_check(firm_id: str, lead_id: int,
                       first_name: str, last_name: str,
                       email: Optional[str] = None,
                       phone: Optional[str] = None) -> List[Dict]:
    """Run conflict of interest check against existing clients and leads.

    Checks:
    1. Name matches against cached_contacts and cached_clients
    2. Name matches against other intake leads (opposing parties)
    3. Email matches
    4. Phone matches

    Returns list of potential conflicts found.
    """
    conflicts = []
    full_name = f"{first_name} {last_name}".strip()

    with get_connection() as conn:
        cur = conn.cursor()

        # 1. Name match against existing clients (case-insensitive, partial)
        cur.execute("""
            SELECT id, name, email
            FROM cached_clients
            WHERE firm_id = %s
              AND (
                  LOWER(name) = LOWER(%s)
                  OR LOWER(name) LIKE LOWER(%s)
              )
            LIMIT 20
        """, (firm_id, full_name, f"%{last_name}%"))
        for row in cur.fetchall():
            row = dict(row)
            score = 100.0 if row["name"].lower() == full_name.lower() else 70.0
            conflicts.append({
                "check_type": "name_match",
                "matched_entity_type": "client",
                "matched_entity_id": row["id"],
                "matched_name": row["name"],
                "matched_detail": f"Existing client (email: {row.get('email', 'N/A')})",
                "similarity_score": score,
            })

        # 2. Name match against cached_contacts
        cur.execute("""
            SELECT id, name
            FROM cached_contacts
            WHERE firm_id = %s
              AND (
                  LOWER(name) = LOWER(%s)
                  OR LOWER(name) LIKE LOWER(%s)
              )
            LIMIT 20
        """, (firm_id, full_name, f"%{last_name}%"))
        for row in cur.fetchall():
            row = dict(row)
            score = 100.0 if row["name"].lower() == full_name.lower() else 65.0
            conflicts.append({
                "check_type": "name_match",
                "matched_entity_type": "contact",
                "matched_entity_id": row["id"],
                "matched_name": row["name"],
                "matched_detail": "Existing contact in system",
                "similarity_score": score,
            })

        # 3. Name match against other leads (could be opposing party)
        cur.execute("""
            SELECT id, first_name, last_name, case_type, stage_name
            FROM intake_leads
            WHERE firm_id = %s AND id != %s
              AND (
                  LOWER(first_name || ' ' || last_name) = LOWER(%s)
                  OR LOWER(last_name) = LOWER(%s)
              )
              AND archived = FALSE
            LIMIT 20
        """, (firm_id, lead_id, full_name, last_name))
        for row in cur.fetchall():
            row = dict(row)
            matched = f"{row['first_name']} {row['last_name']}"
            score = 100.0 if matched.lower() == full_name.lower() else 60.0
            conflicts.append({
                "check_type": "name_match",
                "matched_entity_type": "lead",
                "matched_entity_id": row["id"],
                "matched_name": matched,
                "matched_detail": f"Intake lead — {row['case_type'] or 'Unknown'} ({row['stage_name']})",
                "similarity_score": score,
            })

        # 4. Email match
        if email:
            cur.execute("""
                SELECT id, name, email
                FROM cached_clients
                WHERE firm_id = %s AND LOWER(email) = LOWER(%s)
                LIMIT 10
            """, (firm_id, email))
            for row in cur.fetchall():
                row = dict(row)
                conflicts.append({
                    "check_type": "email_match",
                    "matched_entity_type": "client",
                    "matched_entity_id": row["id"],
                    "matched_name": row["name"],
                    "matched_detail": f"Same email: {row['email']}",
                    "similarity_score": 95.0,
                })

            cur.execute("""
                SELECT id, first_name, last_name, email
                FROM intake_leads
                WHERE firm_id = %s AND id != %s
                  AND LOWER(email) = LOWER(%s) AND archived = FALSE
                LIMIT 10
            """, (firm_id, lead_id, email))
            for row in cur.fetchall():
                row = dict(row)
                conflicts.append({
                    "check_type": "email_match",
                    "matched_entity_type": "lead",
                    "matched_entity_id": row["id"],
                    "matched_name": f"{row['first_name']} {row['last_name']}",
                    "matched_detail": f"Same email: {row['email']}",
                    "similarity_score": 95.0,
                })

        # 5. Phone match
        if phone:
            # Normalize: strip non-digits for comparison
            phone_digits = ''.join(c for c in phone if c.isdigit())
            if len(phone_digits) >= 7:
                phone_pattern = f"%{phone_digits[-10:]}"  # last 10 digits
                cur.execute("""
                    SELECT id, name, phone
                    FROM cached_clients
                    WHERE firm_id = %s
                      AND regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g')
                          LIKE %s
                    LIMIT 10
                """, (firm_id, phone_pattern))
                for row in cur.fetchall():
                    row = dict(row)
                    conflicts.append({
                        "check_type": "phone_match",
                        "matched_entity_type": "client",
                        "matched_entity_id": row["id"],
                        "matched_name": row["name"],
                        "matched_detail": f"Same phone: {row.get('phone', '')}",
                        "similarity_score": 90.0,
                    })

        # Store conflicts in DB
        for c in conflicts:
            cur.execute("""
                INSERT INTO intake_conflict_checks
                    (firm_id, lead_id, check_type, matched_entity_type,
                     matched_entity_id, matched_name, matched_detail,
                     similarity_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (firm_id, lead_id, c["check_type"], c["matched_entity_type"],
                  c.get("matched_entity_id"), c["matched_name"],
                  c.get("matched_detail"), c.get("similarity_score")))

    return conflicts


def get_lead_conflicts(firm_id: str, lead_id: int) -> List[Dict]:
    """Get all conflict check results for a lead."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM intake_conflict_checks
            WHERE firm_id = %s AND lead_id = %s
            ORDER BY similarity_score DESC, created_at DESC
        """, (firm_id, lead_id))
        return [dict(row) for row in cur.fetchall()]


def resolve_conflict(conflict_id: int, resolved_by: str,
                     status: str = "cleared",
                     notes: str = None):
    """Resolve a conflict check (clear or flag)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE intake_conflict_checks
            SET status = %s, resolved_by = %s,
                resolved_at = CURRENT_TIMESTAMP,
                resolution_notes = %s
            WHERE id = %s
        """, (status, resolved_by, notes, conflict_id))


def has_unresolved_conflicts(firm_id: str, lead_id: int) -> bool:
    """Check if a lead has any unresolved conflicts."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) as cnt FROM intake_conflict_checks
            WHERE firm_id = %s AND lead_id = %s AND status = 'unresolved'
        """, (firm_id, lead_id))
        return dict(cur.fetchone())["cnt"] > 0


# ============================================================
# Lead → MyCase Conversion
# ============================================================

def mark_lead_converted(firm_id: str, lead_id: int,
                        mycase_case_id: int = None,
                        mycase_contact_id: int = None) -> bool:
    """Mark a lead as converted to a MyCase case."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE intake_leads
            SET stage_name = 'Retained',
                retained_date = CURRENT_DATE,
                custom_fields = custom_fields || %s::jsonb,
                updated_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE firm_id = %s AND id = %s
        """, (
            json.dumps({
                "mycase_case_id": mycase_case_id,
                "mycase_contact_id": mycase_contact_id,
                "converted_at": datetime.now().isoformat(),
            }),
            firm_id, lead_id
        ))

        log_activity(
            firm_id, lead_id, "converted",
            f"Lead converted to MyCase case (case_id={mycase_case_id}, contact_id={mycase_contact_id})",
            performed_by="system"
        )
    return True


def get_conversion_data(firm_id: str, lead_id: int) -> Optional[Dict]:
    """Get lead data formatted for MyCase API case/contact creation."""
    lead = get_lead(firm_id, lead_id)
    if not lead:
        return None

    return {
        "contact": {
            "first_name": lead["first_name"],
            "last_name": lead["last_name"],
            "email": lead.get("email"),
            "phone": lead.get("phone"),
            "phone_alt": lead.get("phone_alt"),
        },
        "case": {
            "name": f"{lead['first_name']} {lead['last_name']} - {lead.get('case_type', 'General')}",
            "case_type": lead.get("case_type"),
            "practice_area": lead.get("practice_area"),
            "description": lead.get("notes", ""),
            "source": f"Intake pipeline (lead #{lead_id})",
        },
        "lead": lead,
    }


# ============================================================
# Custom Fields
# ============================================================

def get_custom_fields(firm_id: str, active_only: bool = True) -> List[Dict]:
    """Get custom field definitions for a firm."""
    with get_connection() as conn:
        cur = conn.cursor()
        active_filter = "AND is_active = TRUE" if active_only else ""
        cur.execute(f"""
            SELECT * FROM intake_custom_fields
            WHERE firm_id = %s {active_filter}
            ORDER BY display_order, id
        """, (firm_id,))
        return [dict(row) for row in cur.fetchall()]


def create_custom_field(firm_id: str, field_key: str, field_label: str,
                        field_type: str = "text",
                        field_options: List[str] = None,
                        is_required: bool = False,
                        show_on_card: bool = False,
                        show_on_form: bool = True) -> int:
    """Create a custom field definition."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO intake_custom_fields
                (firm_id, field_key, field_label, field_type,
                 field_options, is_required, show_on_card, show_on_form)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT (firm_id, field_key) DO UPDATE SET
                field_label = EXCLUDED.field_label,
                field_type = EXCLUDED.field_type,
                field_options = EXCLUDED.field_options,
                is_required = EXCLUDED.is_required,
                show_on_card = EXCLUDED.show_on_card,
                show_on_form = EXCLUDED.show_on_form,
                is_active = TRUE
            RETURNING id
        """, (firm_id, field_key, field_label, field_type,
              json.dumps(field_options or []),
              is_required, show_on_card, show_on_form))
        return cur.fetchone()["id"]


def update_custom_field(field_id: int, **kwargs):
    """Update a custom field definition."""
    allowed = {"field_label", "field_type", "field_options", "is_required",
               "display_order", "is_active", "show_on_card", "show_on_form"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return

    set_parts = []
    values = []
    for k, v in updates.items():
        if k == "field_options":
            set_parts.append(f"{k} = %s::jsonb")
            values.append(json.dumps(v))
        else:
            set_parts.append(f"{k} = %s")
            values.append(v)

    values.append(field_id)
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            UPDATE intake_custom_fields
            SET {', '.join(set_parts)}
            WHERE id = %s
        """, values)


def delete_custom_field(field_id: int):
    """Soft-delete a custom field."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE intake_custom_fields
            SET is_active = FALSE
            WHERE id = %s
        """, (field_id,))


def set_lead_custom_field(firm_id: str, lead_id: int,
                          field_key: str, value) -> bool:
    """Set a custom field value on a lead."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE intake_leads
            SET custom_fields = jsonb_set(
                COALESCE(custom_fields, '{}'),
                %s, %s::jsonb
            ),
            updated_at = CURRENT_TIMESTAMP
            WHERE firm_id = %s AND id = %s
        """, (f'{{{field_key}}}', json.dumps(value), firm_id, lead_id))
    return True
