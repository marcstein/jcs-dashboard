#!/usr/bin/env python3
"""
Trust-to-Operating Transfer Report

Generates a report showing how much of each flat-fee case's fee
should be transferred from trust to operating, based on current case phase.

Phase-based fee allocation schedules define what percentage of the total
flat fee is "earned" at each phase. The managing partner uses this report
to maintain trust and operating accounts.

Fee schedules are loaded from the database (trust_fee_schedules table)
per firm. If no DB schedules exist, falls back to hardcoded defaults.

No money is moved by this system — it produces a report only.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from db.connection import get_connection

logger = logging.getLogger(__name__)


# =============================================================================
# Hardcoded defaults — used as fallback if no DB schedules exist,
# and as seed data for new firms.
# =============================================================================

_HARDCODED_SCHEDULES = {
    "dwi_criminal": {
        "label": "DWI / Criminal",
        "case_type_patterns": ["DWI", "Criminal", "Drug", "Felony", "Misdemeanor", "Assault", "Theft", "DUI"],
        "phases": {
            "intake":           15,
            "discovery":        20,
            "motions":          25,
            "strategy":         15,
            "trial_prep":       10,
            "disposition":      10,
            "post_disposition":  5,
        }
    },
    "traffic_municipal": {
        "label": "Traffic / Municipal",
        "case_type_patterns": ["Traffic", "Municipal", "Speeding", "Moving Violation"],
        "phases": {
            "intake":           20,
            "discovery":        25,
            "motions":          20,
            "strategy":         20,
            "trial_prep":        0,
            "disposition":      10,
            "post_disposition":  5,
        }
    },
    "expungement_license": {
        "label": "Expungement / License",
        "case_type_patterns": ["Expungement", "License", "Reinstatement", "DOR"],
        "phases": {
            "intake":           25,
            "discovery":        35,
            "motions":          25,
            "strategy":         15,
            "trial_prep":        0,
            "disposition":       0,
            "post_disposition":  0,
        }
    },
}

_HARDCODED_DEFAULT = {
    "label": "Default",
    "phases": {
        "intake":           15,
        "discovery":        20,
        "motions":          25,
        "strategy":         15,
        "trial_prep":       10,
        "disposition":      10,
        "post_disposition":  5,
    }
}

# Phase display order for consistent output
PHASE_ORDER = [
    "intake", "discovery", "motions", "strategy",
    "trial_prep", "disposition", "post_disposition"
]

PHASE_LABELS = {
    "intake": "Intake",
    "discovery": "Discovery",
    "motions": "Motions",
    "strategy": "Strategy",
    "trial_prep": "Trial Prep",
    "disposition": "Disposition",
    "post_disposition": "Closing",
}


# =============================================================================
# Schedule Loading — DB first, hardcoded fallback
# =============================================================================

def load_fee_schedules(firm_id: str) -> Tuple[Dict, Dict]:
    """
    Load fee schedules for a firm.

    Returns (schedules_dict, default_schedule) where:
    - schedules_dict maps schedule_key -> {label, case_type_patterns, phases}
    - default_schedule is the fallback for unmatched case types

    Tries DB first. If no rows found, returns hardcoded defaults.
    """
    try:
        from db.trust import get_fee_schedules
        db_schedules = get_fee_schedules(firm_id)
    except Exception:
        db_schedules = []

    if not db_schedules:
        return dict(_HARDCODED_SCHEDULES), dict(_HARDCODED_DEFAULT)

    schedules = {}
    default = None

    for row in db_schedules:
        entry = {
            "label": row["label"],
            "case_type_patterns": row["case_type_patterns"] or [],
            "phases": row["phase_percentages"] or {},
        }
        if row["is_default"]:
            default = entry
        else:
            schedules[row["schedule_key"]] = entry

    if not default:
        default = dict(_HARDCODED_DEFAULT)

    return schedules, default


def get_schedule_for_case_type(case_type: str, schedules: Dict, default: Dict) -> Dict:
    """Match a case type string to its fee schedule."""
    if not case_type:
        return default

    ct = case_type.upper()
    for key, schedule in schedules.items():
        for pattern in schedule.get("case_type_patterns", []):
            if pattern.upper() in ct:
                return schedule
    return default


# Public alias for backward compat — dashboard template reads this
FEE_SCHEDULES = _HARDCODED_SCHEDULES


def cumulative_earned_pct(schedule: Dict, current_phase: str) -> int:
    """
    Calculate cumulative percentage earned up to and including current_phase.
    Phases that are skipped (0%) still count as passed-through.
    """
    phases = schedule["phases"]
    total = 0
    for phase_code in PHASE_ORDER:
        total += phases.get(phase_code, 0)
        if phase_code == current_phase:
            return total
    # Phase not found in order — return 0
    return 0


# =============================================================================
# Report Generation
# =============================================================================

@dataclass
class TrustTransferLine:
    """One line item in the trust transfer report."""
    case_id: int
    case_name: str
    case_type: str
    client_name: str
    lead_attorney: str
    current_phase: str
    phase_label: str
    total_fee: float
    earned_pct: int
    earned_amount: float
    in_operating: float  # already transferred (= paid_amount as proxy)
    recommended_transfer: float  # earned - already in operating
    remaining_in_trust: float
    schedule_label: str


def generate_trust_transfer_report(firm_id: str) -> Dict:
    """
    Generate the trust transfer report.

    Joins:
    - case_phase_history (current phase per open case)
    - cached_invoices (total fee amount per case, summed)
    - cached_cases (client name, lead attorney, status)

    Returns dict with 'lines' (list of TrustTransferLine), 'summary',
    'schedules', 'default_schedule', and 'generated_at'.
    """
    # Load schedules from DB (or hardcoded fallback)
    schedules, default_schedule = load_fee_schedules(firm_id)

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            WITH latest_phase AS (
                SELECT DISTINCT ON (case_id)
                    case_id, case_name, case_type, phase_code, phase_name, entered_at
                FROM case_phase_history
                WHERE firm_id = %s
                ORDER BY case_id, entered_at DESC
            ),
            case_fees AS (
                SELECT
                    case_id,
                    SUM(total_amount) as total_fee,
                    SUM(paid_amount) as total_paid,
                    SUM(balance_due) as total_balance
                FROM cached_invoices
                WHERE firm_id = %s AND total_amount > 0
                GROUP BY case_id
            ),
            case_info AS (
                SELECT
                    id as case_id,
                    COALESCE(
                        data_json::jsonb -> 'billing_contact' ->> 'name',
                        name
                    ) as client_name,
                    lead_attorney_name,
                    status
                FROM cached_cases
                WHERE firm_id = %s
            )
            SELECT
                lp.case_id,
                lp.case_name,
                lp.case_type,
                lp.phase_code,
                lp.phase_name,
                lp.entered_at,
                COALESCE(cf.total_fee, 0) as total_fee,
                COALESCE(cf.total_paid, 0) as total_paid,
                COALESCE(cf.total_balance, 0) as total_balance,
                COALESCE(ci.client_name, '') as client_name,
                COALESCE(ci.lead_attorney_name, '') as lead_attorney,
                COALESCE(ci.status, '') as case_status
            FROM latest_phase lp
            LEFT JOIN case_fees cf ON lp.case_id = cf.case_id
            LEFT JOIN case_info ci ON lp.case_id = ci.case_id
            WHERE COALESCE(ci.status, 'open') = 'open'
              AND COALESCE(cf.total_fee, 0) > 0
            ORDER BY lp.case_type, lp.case_name
        """, (firm_id, firm_id, firm_id))

        rows = cur.fetchall()

    lines = []
    for row in rows:
        row = dict(row)
        case_type = row["case_type"] or ""
        phase_code = row["phase_code"]
        total_fee = float(row["total_fee"])
        total_paid = float(row["total_paid"])

        schedule = get_schedule_for_case_type(case_type, schedules, default_schedule)
        earned_pct = cumulative_earned_pct(schedule, phase_code)
        earned_amount = round(total_fee * earned_pct / 100, 2)

        # total_paid is our proxy for "already in operating"
        in_operating = total_paid
        recommended_transfer = max(0, round(earned_amount - in_operating, 2))
        remaining_in_trust = max(0, round(total_fee - earned_amount, 2))

        lines.append(TrustTransferLine(
            case_id=row["case_id"],
            case_name=row["case_name"] or "",
            case_type=case_type,
            client_name=row["client_name"],
            lead_attorney=row["lead_attorney"],
            current_phase=phase_code,
            phase_label=PHASE_LABELS.get(phase_code, phase_code),
            total_fee=total_fee,
            earned_pct=earned_pct,
            earned_amount=earned_amount,
            in_operating=in_operating,
            recommended_transfer=recommended_transfer,
            remaining_in_trust=remaining_in_trust,
            schedule_label=schedule["label"],
        ))

    # Summary stats
    total_fees = sum(l.total_fee for l in lines)
    total_earned = sum(l.earned_amount for l in lines)
    total_in_operating = sum(l.in_operating for l in lines)
    total_to_transfer = sum(l.recommended_transfer for l in lines)
    total_remaining_trust = sum(l.remaining_in_trust for l in lines)

    # Breakdown by schedule type
    by_schedule = {}
    for l in lines:
        key = l.schedule_label
        if key not in by_schedule:
            by_schedule[key] = {"count": 0, "total_fee": 0, "earned": 0, "to_transfer": 0}
        by_schedule[key]["count"] += 1
        by_schedule[key]["total_fee"] += l.total_fee
        by_schedule[key]["earned"] += l.earned_amount
        by_schedule[key]["to_transfer"] += l.recommended_transfer

    # Breakdown by phase
    by_phase = {}
    for l in lines:
        key = l.phase_label
        if key not in by_phase:
            by_phase[key] = {"count": 0, "total_fee": 0, "earned": 0, "to_transfer": 0}
        by_phase[key]["count"] += 1
        by_phase[key]["total_fee"] += l.total_fee
        by_phase[key]["earned"] += l.earned_amount
        by_phase[key]["to_transfer"] += l.recommended_transfer

    return {
        "lines": lines,
        "summary": {
            "case_count": len(lines),
            "total_fees": total_fees,
            "total_earned": total_earned,
            "total_in_operating": total_in_operating,
            "total_to_transfer": total_to_transfer,
            "total_remaining_trust": total_remaining_trust,
            "earned_pct": round(total_earned / total_fees * 100, 1) if total_fees else 0,
            "by_schedule": by_schedule,
            "by_phase": by_phase,
        },
        "schedules": schedules,
        "default_schedule": default_schedule,
        "generated_at": datetime.now().isoformat(),
        "firm_id": firm_id,
    }


def export_trust_report_csv(report: Dict, filepath: str):
    """Export report lines to CSV."""
    import csv
    lines = report["lines"]
    if not lines:
        return

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Case ID", "Case Name", "Client", "Lead Attorney", "Case Type",
            "Schedule", "Current Phase", "Earned %",
            "Total Fee", "Earned Amount", "In Operating", "Recommended Transfer",
            "Remaining in Trust"
        ])
        for l in lines:
            writer.writerow([
                l.case_id, l.case_name, l.client_name, l.lead_attorney,
                l.case_type, l.schedule_label, l.phase_label, f"{l.earned_pct}%",
                f"${l.total_fee:,.2f}", f"${l.earned_amount:,.2f}",
                f"${l.in_operating:,.2f}", f"${l.recommended_transfer:,.2f}",
                f"${l.remaining_in_trust:,.2f}",
            ])
