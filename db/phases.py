"""
Case Phase Tracking — PostgreSQL Multi-Tenant

Universal 7-phase framework with MyCase stage mappings,
case-type workflows, and phase/workflow history.
"""
import logging
from typing import List, Dict, Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)


PHASES_SCHEMA = """
CREATE TABLE IF NOT EXISTS phases (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    short_name TEXT,
    display_order INTEGER NOT NULL,
    description TEXT,
    primary_responsibility TEXT,
    typical_duration_min_days INTEGER DEFAULT 1,
    typical_duration_max_days INTEGER DEFAULT 30,
    is_terminal BOOLEAN DEFAULT FALSE,
    color TEXT DEFAULT '#6B7280',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, code)
);

CREATE TABLE IF NOT EXISTS mycase_stages (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stage_phase_mappings (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    mycase_stage_id INTEGER,
    mycase_stage_name TEXT NOT NULL,
    phase_code TEXT NOT NULL,
    case_type_filter TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, mycase_stage_name)
);

CREATE TABLE IF NOT EXISTS case_type_workflows (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    case_type_patterns TEXT,
    stages_json TEXT,
    applies_alongside_phases BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, code)
);

CREATE TABLE IF NOT EXISTS case_phase_history (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    case_id INTEGER NOT NULL,
    case_name TEXT,
    case_type TEXT,
    phase_code TEXT NOT NULL,
    phase_name TEXT,
    mycase_stage_id INTEGER,
    mycase_stage_name TEXT,
    entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exited_at TIMESTAMP,
    duration_days REAL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_cph_firm_case ON case_phase_history(firm_id, case_id);
CREATE INDEX IF NOT EXISTS idx_cph_phase ON case_phase_history(firm_id, phase_code);
CREATE INDEX IF NOT EXISTS idx_cph_entered ON case_phase_history(firm_id, entered_at);

CREATE TABLE IF NOT EXISTS case_workflow_history (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    case_id INTEGER NOT NULL,
    workflow_code TEXT NOT NULL,
    stage_code TEXT NOT NULL,
    stage_name TEXT,
    entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exited_at TIMESTAMP,
    duration_days REAL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_cwh_firm_case ON case_workflow_history(firm_id, case_id);
"""


def ensure_phases_tables():
    """Create phase tracking tables if they don't exist."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(PHASES_SCHEMA)
    logger.info("Phase tables ensured")


# ============================================================
# Phase Definitions
# ============================================================

def get_phases(firm_id: str) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM phases WHERE firm_id = %s ORDER BY display_order",
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def upsert_phase(firm_id: str, code: str, name: str, **kwargs) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO phases (firm_id, code, name, short_name, display_order,
                description, primary_responsibility, typical_duration_min_days,
                typical_duration_max_days, is_terminal, color)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (firm_id, code) DO UPDATE SET
                name = EXCLUDED.name,
                short_name = EXCLUDED.short_name,
                display_order = EXCLUDED.display_order,
                description = EXCLUDED.description,
                primary_responsibility = EXCLUDED.primary_responsibility,
                typical_duration_min_days = EXCLUDED.typical_duration_min_days,
                typical_duration_max_days = EXCLUDED.typical_duration_max_days,
                is_terminal = EXCLUDED.is_terminal,
                color = EXCLUDED.color,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (firm_id, code, name,
             kwargs.get("short_name"), kwargs.get("display_order", 0),
             kwargs.get("description"), kwargs.get("primary_responsibility"),
             kwargs.get("typical_duration_min_days", 1),
             kwargs.get("typical_duration_max_days", 30),
             kwargs.get("is_terminal", False),
             kwargs.get("color", "#6B7280")),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


# ============================================================
# Stage → Phase Mappings
# ============================================================

def get_stage_mappings(firm_id: str) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM stage_phase_mappings WHERE firm_id = %s ORDER BY phase_code",
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def upsert_stage_mapping(firm_id: str, stage_name: str, phase_code: str, **kwargs) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO stage_phase_mappings
                (firm_id, mycase_stage_id, mycase_stage_name, phase_code, case_type_filter, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (firm_id, mycase_stage_name) DO UPDATE SET
                phase_code = EXCLUDED.phase_code,
                case_type_filter = EXCLUDED.case_type_filter,
                notes = EXCLUDED.notes
            RETURNING id
            """,
            (firm_id, kwargs.get("stage_id"), stage_name, phase_code,
             kwargs.get("case_type_filter"), kwargs.get("notes")),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


# ============================================================
# Phase History
# ============================================================

def record_phase_entry(
    firm_id: str, case_id: int, phase_code: str,
    case_name: str = None, case_type: str = None,
    phase_name: str = None, mycase_stage_id: int = None,
    mycase_stage_name: str = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO case_phase_history
                (firm_id, case_id, case_name, case_type, phase_code, phase_name,
                 mycase_stage_id, mycase_stage_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (firm_id, case_id, case_name, case_type, phase_code, phase_name,
             mycase_stage_id, mycase_stage_name),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_case_phase_history(firm_id: str, case_id: int) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM case_phase_history WHERE firm_id = %s AND case_id = %s ORDER BY entered_at",
            (firm_id, case_id),
        )
        return [dict(r) for r in cur.fetchall()]


def get_current_phase_distribution(firm_id: str) -> List[Dict]:
    """Get count of cases in each phase (most recent phase per case)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            WITH latest_phase AS (
                SELECT DISTINCT ON (case_id) case_id, phase_code, phase_name, entered_at
                FROM case_phase_history
                WHERE firm_id = %s
                ORDER BY case_id, entered_at DESC
            )
            SELECT phase_code, phase_name, COUNT(*) as case_count
            FROM latest_phase
            GROUP BY phase_code, phase_name
            ORDER BY phase_code
            """,
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_stalled_cases(firm_id: str, max_days: int = 30) -> List[Dict]:
    """Get cases that have been in the same phase for more than max_days."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            WITH latest_phase AS (
                SELECT DISTINCT ON (case_id) case_id, case_name, case_type,
                    phase_code, phase_name, entered_at
                FROM case_phase_history
                WHERE firm_id = %s
                ORDER BY case_id, entered_at DESC
            )
            SELECT *, EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - entered_at)) / 86400.0 as days_in_phase
            FROM latest_phase
            WHERE EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - entered_at)) / 86400.0 > %s
            ORDER BY entered_at ASC
            """,
            (firm_id, max_days),
        )
        return [dict(r) for r in cur.fetchall()]
