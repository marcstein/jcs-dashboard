"""
phone/lookup.py — Client Lookup by Phone Number

Given a normalized phone number and firm_id, find the matching client
and their active cases, last payment, and balance due.
"""
import logging
from typing import Optional

from db.connection import get_connection
from phone.normalize import normalize_phone, format_display
from phone.events import ScreenPopPayload

logger = logging.getLogger(__name__)


def lookup_client_by_phone(firm_id: str, phone_normalized: str) -> Optional[dict]:
    """
    Find a client by normalized phone number.

    Searches across all three normalized phone columns:
    cell_phone_normalized, work_phone_normalized, home_phone_normalized.

    Returns dict with client info or None if no match.
    """
    if not phone_normalized:
        return None

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, first_name, last_name,
                   COALESCE(first_name || ' ' || last_name, first_name, last_name) as name,
                   email, cell_phone, work_phone, home_phone
            FROM cached_clients
            WHERE firm_id = %s
              AND (
                  cell_phone_normalized = %s
                  OR work_phone_normalized = %s
                  OR home_phone_normalized = %s
                  OR phone_normalized = %s
              )
            LIMIT 1
        """, (firm_id, phone_normalized, phone_normalized,
              phone_normalized, phone_normalized))
        row = cur.fetchone()
        return dict(row) if row else None


def get_client_active_cases(firm_id: str, client_id: int) -> list:
    """
    Get active cases for a client.

    Uses the billing_contact JSONB path in cached_cases to match
    client ID (since cached_invoices.contact_id is NULL).
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                c.id,
                c.name,
                c.case_number,
                c.practice_area,
                c.status,
                c.lead_attorney_name,
                cph.current_phase
            FROM cached_cases c
            LEFT JOIN (
                SELECT DISTINCT ON (case_id, firm_id)
                    case_id, firm_id, phase_name as current_phase
                FROM case_phase_history
                WHERE exited_at IS NULL
                ORDER BY case_id, firm_id, entered_at DESC
            ) cph ON c.id = cph.case_id AND c.firm_id = cph.firm_id
            WHERE c.firm_id = %s
              AND c.status = 'open'
              AND (
                  c.data_json::jsonb -> 'billing_contact' ->> 'id' = %s
                  OR c.data_json::jsonb -> 'clients' @> %s::jsonb
              )
            ORDER BY c.created_at DESC
        """, (firm_id, str(client_id),
              __import__('json').dumps([{"id": client_id}])))
        return [dict(r) for r in cur.fetchall()]


def get_client_last_payment(firm_id: str, client_id: int) -> Optional[dict]:
    """Get the most recent payment for a client."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.amount, p.created_at as payment_date
            FROM cached_payments p
            JOIN cached_invoices i ON p.invoice_id = i.id AND p.firm_id = i.firm_id
            JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
            WHERE p.firm_id = %s
              AND (
                  c.data_json::jsonb -> 'billing_contact' ->> 'id' = %s
                  OR c.data_json::jsonb -> 'clients' @> %s::jsonb
              )
            ORDER BY p.created_at DESC
            LIMIT 1
        """, (firm_id, str(client_id),
              __import__('json').dumps([{"id": client_id}])))
        row = cur.fetchone()
        if row:
            return {
                "amount": float(row['amount']) if row['amount'] else 0,
                "date": row['payment_date'].strftime('%b %d, %Y') if row['payment_date'] else None,
            }
        return None


def get_client_balance_due(firm_id: str, client_id: int) -> float:
    """Get total outstanding balance for a client across all open invoices."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(SUM(i.balance_due), 0) as total_balance
            FROM cached_invoices i
            JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
            WHERE i.firm_id = %s
              AND i.balance_due > 0
              AND (
                  c.data_json::jsonb -> 'billing_contact' ->> 'id' = %s
                  OR c.data_json::jsonb -> 'clients' @> %s::jsonb
              )
        """, (firm_id, str(client_id),
              __import__('json').dumps([{"id": client_id}])))
        row = cur.fetchone()
        return float(row['total_balance']) if row else 0.0


def build_screen_pop(
    firm_id: str,
    caller_number: str,
    caller_number_normalized: str,
    call_event_id: int,
    target_username: str = None,
) -> ScreenPopPayload:
    """
    Build a complete screen pop payload for an incoming call.

    This is the main entry point — called after a webhook is received
    and the call event is logged.
    """
    from datetime import datetime

    # Look up client
    client = lookup_client_by_phone(firm_id, caller_number_normalized)

    if not client:
        logger.info("No client match for %s at firm %s", caller_number_normalized, firm_id)
        return ScreenPopPayload(
            firm_id=firm_id,
            call_event_id=call_event_id,
            caller_number=format_display(caller_number_normalized),
            caller_number_normalized=caller_number_normalized,
            matched=False,
            target_username=target_username,
            timestamp=datetime.utcnow().isoformat(),
        )

    client_id = client['id']
    client_name = client.get('name') or f"{client.get('first_name', '')} {client.get('last_name', '')}".strip()

    # Get active cases
    cases = get_client_active_cases(firm_id, client_id)

    # Get last payment
    last_payment = get_client_last_payment(firm_id, client_id)

    # Get total balance
    balance_due = get_client_balance_due(firm_id, client_id)

    logger.info(
        "Screen pop: %s (%s) → %s, %d cases, balance $%.2f",
        caller_number_normalized, client_name, firm_id, len(cases), balance_due,
    )

    return ScreenPopPayload(
        firm_id=firm_id,
        call_event_id=call_event_id,
        caller_number=format_display(caller_number_normalized),
        caller_number_normalized=caller_number_normalized,
        matched=True,
        client_id=client_id,
        client_name=client_name,
        client_email=client.get('email'),
        cases=[{
            "id": c['id'],
            "name": c['name'],
            "case_number": c['case_number'],
            "practice_area": c['practice_area'],
            "lead_attorney": c['lead_attorney_name'],
            "phase": c.get('current_phase', 'Unknown'),
        } for c in cases],
        last_payment=last_payment,
        balance_due=balance_due,
        target_username=target_username,
        timestamp=datetime.utcnow().isoformat(),
    )
