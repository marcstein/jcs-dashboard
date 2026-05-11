"""
LawPay Integration — Payment Link Generation for Dunning Emails

Creates per-invoice payment links via the LawPay (8am) Payment Gateway API.
All payments are routed to the firm's IOLTA trust account (deferred retainer fees).
Processing fees are automatically charged to the operating account by LawPay.

Requires:
  - LawPay API credentials stored in firms.notification_config JSONB:
      lawpay_public_key, lawpay_secret_key, lawpay_trust_account_id
  - OAuth 2.0 access token for the firm's LawPay account

API Reference: https://developers.8am.com/reference/api.html
"""

import json
import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

import httpx

from db.connection import get_connection

logger = logging.getLogger(__name__)

# LawPay (8am) API base URL
LAWPAY_API_BASE = "https://api.affinipay.com"

# Payment link expiry (days)
PAYMENT_LINK_EXPIRY_DAYS = 30


@dataclass
class PaymentLinkResult:
    """Result of creating a payment link."""
    success: bool
    payment_url: Optional[str] = None
    lawpay_request_id: Optional[str] = None
    error: Optional[str] = None
    expires_at: Optional[datetime] = None


def _get_lawpay_config(firm_id: str) -> Dict:
    """
    Load LawPay config from firms.notification_config JSONB.

    Expected keys:
      - lawpay_public_key: Public API key
      - lawpay_secret_key: Secret API key (for server-side calls)
      - lawpay_trust_account_id: Trust/IOLTA account ID for deposits
      - lawpay_operating_account_id: Operating account (fees charged here)
      - lawpay_webhook_secret: Webhook signature verification key
      - lawpay_enabled: Boolean flag to enable/disable payment links
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT notification_config FROM firms WHERE id = %s",
                (firm_id,)
            )
            row = cur.fetchone()
            if not row:
                return {}
            config = row['notification_config'] or {}
            if isinstance(config, str):
                config = json.loads(config)
            return config


def is_lawpay_enabled(firm_id: str) -> bool:
    """Check if LawPay payment links are enabled for this firm."""
    config = _get_lawpay_config(firm_id)
    return bool(
        config.get('lawpay_enabled')
        and config.get('lawpay_secret_key')
        and config.get('lawpay_trust_account_id')
    )


def create_payment_link(
    firm_id: str,
    invoice_id: int,
    invoice_number: str,
    amount_cents: int,
    client_name: str,
    client_email: str,
    case_name: str = "",
    dunning_stage: int = 1,
) -> PaymentLinkResult:
    """
    Create a LawPay payment request (payment link) for an invoice.

    The payment request creates a hosted payment page where the client can
    pay via credit card, debit card, or eCheck. Funds are deposited to the
    firm's IOLTA trust account.

    Args:
        firm_id: Firm identifier
        invoice_id: Internal invoice ID
        invoice_number: Display invoice number
        amount_cents: Amount in cents (e.g., 250000 for $2,500.00)
        client_name: Client's full name
        client_email: Client's email address
        case_name: Case name for reference
        dunning_stage: Which dunning stage triggered this link (1-4)

    Returns:
        PaymentLinkResult with payment URL or error
    """
    config = _get_lawpay_config(firm_id)

    secret_key = config.get('lawpay_secret_key')
    trust_account_id = config.get('lawpay_trust_account_id')

    if not secret_key or not trust_account_id:
        return PaymentLinkResult(
            success=False,
            error="LawPay not configured: missing secret_key or trust_account_id"
        )

    # Check for existing unexpired link for this invoice
    from db.payments import get_existing_payment_link, save_payment_link
    existing = get_existing_payment_link(firm_id, invoice_id)
    if existing and existing['expires_at'] > datetime.utcnow():
        return PaymentLinkResult(
            success=True,
            payment_url=existing['payment_url'],
            lawpay_request_id=existing['lawpay_request_id'],
            expires_at=existing['expires_at'],
        )

    # Create payment request via LawPay API
    expires_at = datetime.utcnow() + timedelta(days=PAYMENT_LINK_EXPIRY_DAYS)

    payload = {
        "amount": amount_cents,
        "currency": "USD",
        "account_id": trust_account_id,
        "reference": f"INV-{invoice_number}",
        "description": f"Payment for {case_name or f'Invoice #{invoice_number}'}",
        "email": client_email,
        "name": client_name,
        "allow_partial_payment": True,
        "payment_methods": ["card", "echeck"],
    }

    try:
        response = httpx.post(
            f"{LAWPAY_API_BASE}/v1/payment-requests",
            json=payload,
            auth=(secret_key, ""),
            timeout=30,
        )

        if response.status_code in (200, 201):
            data = response.json()
            payment_url = data.get("payment_url") or data.get("url", "")
            request_id = data.get("id", "")

            # Record the payment link in our database
            save_payment_link(
                firm_id=firm_id,
                invoice_id=invoice_id,
                dunning_stage=dunning_stage,
                lawpay_request_id=request_id,
                payment_url=payment_url,
                amount_cents=amount_cents,
                expires_at=expires_at,
            )

            logger.info(
                "Created payment link for invoice %s (firm=%s, amount=$%.2f)",
                invoice_number, firm_id, amount_cents / 100
            )

            return PaymentLinkResult(
                success=True,
                payment_url=payment_url,
                lawpay_request_id=request_id,
                expires_at=expires_at,
            )
        else:
            error_msg = f"LawPay API error {response.status_code}: {response.text}"
            logger.error(error_msg)
            return PaymentLinkResult(success=False, error=error_msg)

    except Exception as e:
        error_msg = f"LawPay API connection error: {str(e)}"
        logger.error(error_msg)
        return PaymentLinkResult(success=False, error=error_msg)


def verify_webhook_signature(payload: bytes, signature: str, firm_id: str) -> bool:
    """
    Verify a LawPay webhook signature using HMAC-SHA256.

    Args:
        payload: Raw request body bytes
        signature: Signature from X-Affinipay-Signature header
        firm_id: Firm to look up webhook secret for

    Returns:
        True if signature is valid
    """
    config = _get_lawpay_config(firm_id)
    webhook_secret = config.get('lawpay_webhook_secret', '')
    if not webhook_secret:
        logger.warning("No webhook secret configured for firm %s", firm_id)
        return False

    expected = hmac.new(
        webhook_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def process_payment_webhook(firm_id: str, event_data: Dict) -> Tuple[bool, str]:
    """
    Process a LawPay payment webhook event.

    Records the payment in online_payments and updates the payment_links
    table via the centralized db/payments.py functions.

    Args:
        firm_id: Firm identifier
        event_data: Parsed webhook JSON body

    Returns:
        (success, message) tuple
    """
    from db.payments import record_online_payment, mark_link_paid

    transaction = event_data.get("data", {})

    transaction_id = transaction.get("id", "")
    status = transaction.get("status", "")
    amount_cents = transaction.get("amount", 0)
    reference = transaction.get("reference", "")
    method_type = "card"
    method_info = transaction.get("method", {})
    if method_info:
        method_type = method_info.get("type", "card")

    if status not in ("COMPLETED", "AUTHORIZED"):
        logger.info("Ignoring webhook event with status=%s", status)
        return True, f"Ignored: status={status}"

    # Find the invoice from the reference (format: INV-xxxxx)
    invoice_number = reference.replace("INV-", "") if reference.startswith("INV-") else reference

    # Record the online payment (deduplication via UNIQUE constraint)
    payment_id = record_online_payment(
        firm_id=firm_id,
        invoice_number=invoice_number,
        amount_cents=amount_cents,
        payment_method=method_type,
        lawpay_transaction_id=transaction_id,
        status=status,
        raw_event=event_data,
    )

    if payment_id is None:
        return True, f"Duplicate webhook for transaction {transaction_id}"

    # Try to find and mark the matching payment link as paid
    # Look up invoice_id from cached_invoices by invoice_number
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM cached_invoices
                    WHERE firm_id = %s
                      AND (invoice_number = %s OR id::text = %s)
                    LIMIT 1
                """, (firm_id, invoice_number, invoice_number))
                row = cur.fetchone()
                if row:
                    mark_link_paid(firm_id, row['id'], amount_cents)
    except Exception as e:
        logger.warning("Could not update payment link status: %s", str(e))

    logger.info(
        "Recorded payment: $%.2f via %s for invoice %s (firm=%s)",
        amount_cents / 100, method_type, invoice_number, firm_id
    )

    return True, f"Payment recorded: ${amount_cents / 100:,.2f} for invoice {invoice_number}"
