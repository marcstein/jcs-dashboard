"""
Attorney Performance Targets — PostgreSQL Multi-Tenant

Stores attorney salary and billing target configuration per firm.
Target formula: annual_target = salary * (1 + marketing_pct) * target_multiplier
Default: salary * 1.20 * 3 = salary * 3.6
"""
import logging
from typing import Dict, List, Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)

ATTORNEY_TARGETS_SCHEMA = """
CREATE TABLE IF NOT EXISTS attorney_targets (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    attorney_name TEXT NOT NULL,
    annual_salary NUMERIC(12, 2) NOT NULL,
    marketing_pct NUMERIC(5, 2) NOT NULL DEFAULT 20.00,
    target_multiplier NUMERIC(5, 2) NOT NULL DEFAULT 3.00,
    effective_date DATE NOT NULL DEFAULT CURRENT_DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, attorney_name, effective_date)
);
CREATE INDEX IF NOT EXISTS idx_attorney_targets_firm
    ON attorney_targets(firm_id);
CREATE INDEX IF NOT EXISTS idx_attorney_targets_lookup
    ON attorney_targets(firm_id, attorney_name, effective_date DESC);
"""


def ensure_attorney_targets_tables():
    """Create the attorney_targets table if it doesn't exist."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(ATTORNEY_TARGETS_SCHEMA)
    logger.info("attorney_targets table ensured")


def get_attorney_target(firm_id: str, attorney_name: str) -> Optional[Dict]:
    """Get the most recent target for an attorney (by effective_date)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, firm_id, attorney_name, annual_salary,
                   marketing_pct, target_multiplier, effective_date, notes,
                   created_at, updated_at
            FROM attorney_targets
            WHERE firm_id = %s AND attorney_name = %s
            ORDER BY effective_date DESC
            LIMIT 1
        """, (firm_id, attorney_name))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)


def get_all_attorney_targets(firm_id: str) -> List[Dict]:
    """Get the most recent target for each attorney in the firm."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ON (attorney_name)
                   id, firm_id, attorney_name, annual_salary,
                   marketing_pct, target_multiplier, effective_date, notes,
                   created_at, updated_at
            FROM attorney_targets
            WHERE firm_id = %s
            ORDER BY attorney_name, effective_date DESC
        """, (firm_id,))
        return [dict(row) for row in cur.fetchall()]


def upsert_attorney_target(
    firm_id: str,
    attorney_name: str,
    annual_salary: float,
    marketing_pct: float = 20.0,
    target_multiplier: float = 3.0,
    effective_date: str = None,
    notes: str = None,
) -> int:
    """Insert or update an attorney's billing target.

    effective_date defaults to today if not provided.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        if effective_date is None:
            cur.execute("""
                INSERT INTO attorney_targets
                    (firm_id, attorney_name, annual_salary, marketing_pct,
                     target_multiplier, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (firm_id, attorney_name, effective_date) DO UPDATE SET
                    annual_salary = EXCLUDED.annual_salary,
                    marketing_pct = EXCLUDED.marketing_pct,
                    target_multiplier = EXCLUDED.target_multiplier,
                    notes = EXCLUDED.notes,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (firm_id, attorney_name, annual_salary, marketing_pct,
                  target_multiplier, notes))
        else:
            cur.execute("""
                INSERT INTO attorney_targets
                    (firm_id, attorney_name, annual_salary, marketing_pct,
                     target_multiplier, effective_date, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (firm_id, attorney_name, effective_date) DO UPDATE SET
                    annual_salary = EXCLUDED.annual_salary,
                    marketing_pct = EXCLUDED.marketing_pct,
                    target_multiplier = EXCLUDED.target_multiplier,
                    notes = EXCLUDED.notes,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (firm_id, attorney_name, annual_salary, marketing_pct,
                  target_multiplier, effective_date, notes))
        row = cur.fetchone()
        return row["id"] if row else 0


def delete_attorney_target(firm_id: str, attorney_name: str, effective_date: str = None):
    """Delete an attorney's target. If no effective_date, delete all."""
    with get_connection() as conn:
        cur = conn.cursor()
        if effective_date:
            cur.execute("""
                DELETE FROM attorney_targets
                WHERE firm_id = %s AND attorney_name = %s AND effective_date = %s
            """, (firm_id, attorney_name, effective_date))
        else:
            cur.execute("""
                DELETE FROM attorney_targets
                WHERE firm_id = %s AND attorney_name = %s
            """, (firm_id, attorney_name))


def compute_annual_target(target: Dict) -> float:
    """Compute the annual billing target from a target record.

    Formula: salary * (1 + marketing_pct/100) * target_multiplier
    """
    salary = float(target["annual_salary"])
    marketing = float(target["marketing_pct"]) / 100.0
    multiplier = float(target["target_multiplier"])
    return salary * (1 + marketing) * multiplier


def seed_jcs_targets(firm_id: str = "jcs_law") -> int:
    """Seed the JCS Law attorney salary targets."""
    ensure_attorney_targets_tables()

    attorneys = [
        ("Anthony Muhlenkamp", 175000),
        ("Heidi Leopold", 120000),
        ("Jen Kusmer", 115000),
        ("Leigh Hawk", 86000),
        ("Ethan Dwyer", 60000),
    ]

    count = 0
    for name, salary in attorneys:
        upsert_attorney_target(
            firm_id=firm_id,
            attorney_name=name,
            annual_salary=salary,
            marketing_pct=20.0,
            target_multiplier=3.0,
            notes="Initial seed — 3x (salary + 20% marketing)",
        )
        count += 1

    logger.info(f"Seeded {count} attorney targets for {firm_id}")
    return count
