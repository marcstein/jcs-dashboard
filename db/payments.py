"""
db/payments.py — Online Payment Database Layer (LawPay Integration)

Tables:
- payment_links: Per-invoice payment link tracking (LawPay payment requests)
- online_payments: Completed online payment records (from webhooks)

All tables scoped by firm_id for multi-tenant isolation.
Payment links are created when dunning emails are sent (if LawPay is enabled).
Online payments are recorded when LawPay sends webhook confirmations.
"""
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List

from db.connection import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_payment_tables():
    """Create online payment tables if they don't exist."""
    with get_connection() as conn:
        cur = conn.cursor()

        # Payment links — tracks LawPay payment request URLs sent in dunning emails
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payment_links (
                id SERIAL PRIMARY KEY,
                firm_id VARCHAR(36) NOT NULL,
                invoice_id INTEGER NOT NULL,
                dunning_stage INTEGER NOT NULL DEFAULT 1,
                lawpay_request_id VARCHAR(100),
                payment_url TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                expires_at TIMESTAMP,
                clicked_at TIMESTAMP,
                paid_at TIMESTAMP,
                paid_amount_cents INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(firm_id, invoice_id, dunning_stage)
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_payment_links_firm
            ON payment_links(firm_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_payment_links_invoice
            ON payment_links(firm_id, invoice_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_payment_links_request_id
            ON payment_links(lawpay_request_id)
            WHERE lawpay_request_id IS NOT NULL
        """)

        # Online payments — records completed payments from LawPay webhooks
        cur.execute("""
            CREATE TABLE IF NOT EXISTS online_payments (
                id SERIAL PRIMARY KEY,
                firm_id VARCHAR(36) NOT NULL,
                invoice_number VARCHAR(50),
                amount_cents INTEGER NOT NULL,
                payment_method VARCHAR(20) DEFAULT 'card',
                lawpay_transaction_id VARCHAR(100),
                status VARCHAR(30) DEFAULT 'completed',
                raw_event JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(firm_id, lawpay_transaction_id)
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_online_payments_firm
            ON online_payments(firm_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_online_payments_invoice
            ON online_payments(firm_id, invoice_number)
        """)

        conn.commit()
        logger.info("Payment tables ensured")


# ---------------------------------------------------------------------------
# Payment Links — CRUD
# ---------------------------------------------------------------------------

def save_payment_link(
    firm_id: str,
    invoice_id: int,
    dunning_stage: int,
    lawpay_request_id: str,
    payment_url: str,
    amount_cents: int,
    expires_at: datetime,
):
    """Save a payment link to the database (upsert by firm_id + invoice_id + stage)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO payment_links
                (firm_id, invoice_id, dunning_stage, lawpay_request_id,
                 payment_url, amount_cents, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (firm_id, invoice_id, dunning_stage) DO UPDATE SET
                lawpay_request_id = EXCLUDED.lawpay_request_id,
                payment_url = EXCLUDED.payment_url,
                amount_cents = EXCLUDED.amount_cents,
                expires_at = EXCLUDED.expires_at,
                created_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (
            firm_id, invoice_id, dunning_stage, lawpay_request_id,
            payment_url, amount_cents, expires_at
        ))
        result = cur.fetchone()
        conn.commit()
        return result['id'] if result else None


def get_existing_payment_link(firm_id: str, invoice_id: int) -> Optional[Dict]:
    """Get the most recent unexpired, unpaid payment link for an invoice."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, payment_url, lawpay_request_id, expires_at, amount_cents,
                   dunning_stage, created_at
            FROM payment_links
            WHERE firm_id = %s AND invoice_id = %s AND paid_at IS NULL
              AND expires_at > NOW()
            ORDER BY created_at DESC LIMIT 1
        """, (firm_id, invoice_id))
        return cur.fetchone()


def record_link_click(firm_id: str, invoice_id: int):
    """Record that a payment link was clicked (for analytics)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE payment_links
            SET clicked_at = COALESCE(clicked_at, NOW())
            WHERE firm_id = %s AND invoice_id = %s AND paid_at IS NULL
            ORDER BY created_at DESC LIMIT 1
        """, (firm_id, invoice_id))
        conn.commit()


def mark_link_paid(firm_id: str, invoice_id: int, amount_cents: int):
    """Mark a payment link as paid (called from webhook handler)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE payment_links
            SET paid_at = NOW(), paid_amount_cents = %s
            WHERE firm_id = %s AND invoice_id = %s AND paid_at IS NULL
        """, (amount_cents, firm_id, invoice_id))
        conn.commit()


# ---------------------------------------------------------------------------
# Online Payments — CRUD
# ---------------------------------------------------------------------------

def record_online_payment(
    firm_id: str,
    invoice_number: str,
    amount_cents: int,
    payment_method: str,
    lawpay_transaction_id: str,
    status: str,
    raw_event: dict,
) -> Optional[int]:
    """
    Record an online payment from a LawPay webhook.
    Returns the payment ID, or None if it was a duplicate.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO online_payments
                (firm_id, invoice_number, amount_cents, payment_method,
                 lawpay_transaction_id, status, raw_event)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (firm_id, lawpay_transaction_id) DO NOTHING
            RETURNING id
        """, (
            firm_id, invoice_number, amount_cents, payment_method,
            lawpay_transaction_id, status, json.dumps(raw_event)
        ))
        result = cur.fetchone()
        conn.commit()
        if result:
            return result['id']
        return None


def get_online_payments(firm_id: str, limit: int = 50) -> List[Dict]:
    """Get recent online payments for a firm."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, invoice_number, amount_cents, payment_method,
                   lawpay_transaction_id, status, created_at
            FROM online_payments
            WHERE firm_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (firm_id, limit))
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def get_payment_link_stats(firm_id: str, days: int = 30) -> Dict:
    """Get payment link statistics for a firm over the last N days."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total_links,
                COUNT(*) FILTER (WHERE paid_at IS NOT NULL) as paid_links,
                COALESCE(SUM(paid_amount_cents) FILTER (WHERE paid_at IS NOT NULL), 0)
                    as total_collected_cents,
                COUNT(*) FILTER (WHERE clicked_at IS NOT NULL) as clicked_links
            FROM payment_links
            WHERE firm_id = %s
              AND created_at >= NOW() - INTERVAL '1 day' * %s
        """, (firm_id, days))
        row = cur.fetchone()

        total = row['total_links'] or 0
        clicked = row['clicked_links'] or 0
        paid = row['paid_links'] or 0
        collected = row['total_collected_cents'] or 0

        return {
            'total_links': total,
            'paid_links': paid,
            'total_collected': collected / 100,
            'clicked_links': clicked,
            'click_rate': (clicked / total * 100) if total > 0 else 0,
            'conversion_rate': (paid / clicked * 100) if clicked > 0 else 0,
        }


def get_payment_link_for_invoice(firm_id: str, invoice_number: str) -> Optional[Dict]:
    """Get payment link info by invoice number (for dashboard display)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT pl.payment_url, pl.expires_at, pl.paid_at, pl.paid_amount_cents,
                   pl.clicked_at, pl.created_at
            FROM payment_links pl
            JOIN cached_invoices ci ON ci.id = pl.invoice_id AND ci.firm_id = pl.firm_id
            WHERE pl.firm_id = %s
              AND (ci.invoice_number = %s OR ci.id::text = %s)
            ORDER BY pl.created_at DESC LIMIT 1
        """, (firm_id, invoice_number, invoice_number))
        return cur.fetchone()
