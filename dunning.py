"""
Collections and Dunning Automation Module

Handles:
- Identifying overdue invoices
- Sending automated dunning notices at 15, 30, 60, 90 days
- Stopping dunning when payment is received
- Collections reporting
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from api_client import MyCaseClient, get_client, MyCaseAPIError
from database import Database, get_db
from templates import TemplateManager
from config import DUNNING_INTERVALS


@dataclass
class OverdueInvoice:
    """Represents an overdue invoice with relevant details."""
    invoice_id: int
    invoice_number: str
    contact_id: int
    contact_name: str
    contact_email: str
    case_id: Optional[int]
    case_name: Optional[str]
    invoice_date: date
    due_date: date
    total_amount: float
    amount_paid: float
    balance_due: float
    days_overdue: int
    last_dunning_level: int


@dataclass
class DunningAction:
    """Represents a dunning action to be taken."""
    invoice: OverdueInvoice
    action_level: int
    template_name: str
    should_send: bool
    reason: str


class CollectionsManager:
    """
    Manages collections automation including:
    - Identifying overdue invoices
    - Determining appropriate dunning actions
    - Sending dunning notices
    - Tracking payment to stop dunning
    """

    def __init__(
        self,
        client: MyCaseClient = None,
        db: Database = None,
        template_manager: TemplateManager = None,
    ):
        self.client = client or get_client()
        self.db = db or get_db()
        self.templates = template_manager or TemplateManager()
        self.dunning_intervals = DUNNING_INTERVALS  # [15, 30, 60, 90]

    def get_overdue_invoices(self) -> List[OverdueInvoice]:
        """
        Fetch all overdue invoices from MyCase and enrich with local data.

        Returns:
            List of OverdueInvoice objects
        """
        overdue_invoices = []
        today = date.today()

        # Caches for case and contact lookups
        case_cache: Dict[int, Dict] = {}
        contact_cache: Dict[int, Dict] = {}

        try:
            # Fetch ALL invoices - the API status filter is unreliable
            # We filter locally for overdue invoices with balance > 0
            print("Fetching all invoices...")
            all_invoices_raw = self.client.get_all_pages(
                self.client.get_invoices,
            )

            # Filter to only invoices with outstanding balance
            # (status "overdue" or "partial" with balance > 0)
            all_invoices = []
            for inv in all_invoices_raw:
                status = inv.get("status", "")
                if status not in ("overdue", "partial"):
                    continue
                total = float(inv.get("total_amount", 0))
                paid = float(inv.get("paid_amount", 0))
                if total - paid > 0:
                    all_invoices.append(inv)

            print(f"Found {len(all_invoices)} invoices with outstanding balances...")
            processed = 0

            for invoice in all_invoices:
                # Parse invoice data
                invoice_id = invoice.get("id")
                due_date_str = invoice.get("due_date")

                if not due_date_str:
                    continue

                due_date = datetime.fromisoformat(due_date_str.replace("Z", "")).date()
                if due_date >= today:
                    continue  # Not overdue yet

                days_overdue = (today - due_date).days

                # Get case info if linked
                case = invoice.get("case", {})
                case_id = case.get("id") if case else None
                case_name = None
                contact_id = None
                contact_name = "Unknown"
                contact_email = ""

                # Fetch case details to get name and client info (with caching)
                if case_id:
                    # Check cache first
                    if case_id in case_cache:
                        case_detail = case_cache[case_id]
                    else:
                        try:
                            case_detail = self.client.get_case(case_id)
                            case_cache[case_id] = case_detail
                        except Exception:
                            case_detail = {}
                            case_cache[case_id] = case_detail

                    case_name = case_detail.get("name")
                    # Get first client from case
                    clients = case_detail.get("clients", [])
                    if clients:
                        client_id = clients[0].get("id") if isinstance(clients[0], dict) else clients[0]
                        contact_id = client_id

                        # Check contact cache
                        if client_id in contact_cache:
                            contact_detail = contact_cache[client_id]
                        else:
                            try:
                                contact_detail = self.client.get_contact(client_id)
                                contact_cache[client_id] = contact_detail
                            except Exception:
                                contact_detail = {}
                                contact_cache[client_id] = contact_detail

                        contact_name = contact_detail.get("name", "Unknown")
                        contact_email = contact_detail.get("email", "")

                # Financial details - API uses total_amount and paid_amount
                total_amount = float(invoice.get("total_amount", invoice.get("total", 0)))
                amount_paid = float(invoice.get("paid_amount", invoice.get("amount_paid", 0)))
                balance_due = total_amount - amount_paid

                # Get last dunning level from our database
                last_dunning_level = self.db.get_last_dunning_level(invoice_id)

                overdue_invoice = OverdueInvoice(
                    invoice_id=invoice_id,
                    invoice_number=invoice.get("invoice_number", invoice.get("number", f"INV-{invoice_id}")),
                    contact_id=contact_id,
                    contact_name=contact_name,
                    contact_email=contact_email,
                    case_id=case_id,
                    case_name=case_name,
                    invoice_date=datetime.fromisoformat(
                        invoice.get("invoice_date", due_date_str).replace("Z", "")
                    ).date(),
                    due_date=due_date,
                    total_amount=total_amount,
                    amount_paid=amount_paid,
                    balance_due=balance_due,
                    days_overdue=days_overdue,
                    last_dunning_level=last_dunning_level,
                )

                overdue_invoices.append(overdue_invoice)
                processed += 1
                if processed % 100 == 0:
                    print(f"  Processed {processed}/{len(all_invoices)} invoices (cache: {len(case_cache)} cases, {len(contact_cache)} contacts)")

            print(f"Done. Processed {len(overdue_invoices)} overdue invoices.")
            print(f"Cache stats: {len(case_cache)} cases, {len(contact_cache)} contacts")

        except MyCaseAPIError as e:
            print(f"Error fetching invoices: {e}")

        return overdue_invoices

    def determine_dunning_action(self, invoice: OverdueInvoice) -> DunningAction:
        """
        Determine what dunning action should be taken for an invoice.

        Args:
            invoice: OverdueInvoice object

        Returns:
            DunningAction with recommendation
        """
        # Check if payment received since last dunning
        if self.db.has_payment_since_dunning(invoice.invoice_id):
            return DunningAction(
                invoice=invoice,
                action_level=0,
                template_name="",
                should_send=False,
                reason="Payment received since last notice",
            )

        # Determine which dunning level applies
        current_level = 0
        for i, days in enumerate(self.dunning_intervals):
            if invoice.days_overdue >= days:
                current_level = i + 1

        if current_level == 0:
            return DunningAction(
                invoice=invoice,
                action_level=0,
                template_name="",
                should_send=False,
                reason=f"Not yet {self.dunning_intervals[0]} days overdue",
            )

        # Check if we've already sent this level
        if invoice.last_dunning_level >= current_level:
            return DunningAction(
                invoice=invoice,
                action_level=current_level,
                template_name="",
                should_send=False,
                reason=f"Level {current_level} notice already sent",
            )

        # Map level to template
        template_map = {
            1: "dunning_15_day",
            2: "dunning_30_day",
            3: "dunning_60_day",
            4: "dunning_90_day",
        }
        template_name = template_map.get(current_level, "dunning_90_day")

        return DunningAction(
            invoice=invoice,
            action_level=current_level,
            template_name=template_name,
            should_send=True,
            reason=f"Due for level {current_level} notice ({self.dunning_intervals[current_level-1]} days)",
        )

    def generate_dunning_notice(
        self,
        action: DunningAction,
        firm_info: Dict = None,
    ) -> Optional[str]:
        """
        Generate the dunning notice content from template.

        Args:
            action: DunningAction object
            firm_info: Firm information dict

        Returns:
            Rendered notice text or None
        """
        if not action.should_send:
            return None

        firm_info = firm_info or {}
        invoice = action.invoice

        context = {
            "client_name": invoice.contact_name,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date,
            "invoice_amount": invoice.total_amount,
            "case_name": invoice.case_name or "N/A",
            "due_date": invoice.due_date,
            "balance_due": invoice.balance_due,
            "days_overdue": invoice.days_overdue,
            "firm_name": firm_info.get("name", ""),
            "firm_phone": firm_info.get("phone", ""),
            "firm_email": firm_info.get("email", ""),
        }

        return self.templates.render_template(action.template_name, context)

    def send_dunning_notice(
        self,
        action: DunningAction,
        notice_content: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Send a dunning notice and record it.

        Args:
            action: DunningAction object
            notice_content: Rendered notice text
            dry_run: If True, don't actually send, just simulate

        Returns:
            True if sent/recorded successfully
        """
        invoice = action.invoice

        if dry_run:
            print(f"[DRY RUN] Would send level {action.action_level} notice to {invoice.contact_email}")
            print(f"  Invoice: {invoice.invoice_number}")
            print(f"  Amount: ${invoice.balance_due:,.2f}")
            print(f"  Days Overdue: {invoice.days_overdue}")
            return True

        try:
            # In production, this would integrate with email service or MyCase messaging
            # For now, we'll record the notice as sent

            # Record in database
            self.db.record_dunning_notice(
                invoice_id=invoice.invoice_id,
                contact_id=invoice.contact_id,
                days_overdue=invoice.days_overdue,
                notice_level=action.action_level,
                amount_due=invoice.balance_due,
                invoice_number=invoice.invoice_number,
                case_id=invoice.case_id,
                template_used=action.template_name,
            )

            print(f"Recorded dunning notice level {action.action_level} for {invoice.invoice_number}")
            return True

        except Exception as e:
            print(f"Error sending dunning notice: {e}")
            return False

    def run_dunning_cycle(
        self,
        dry_run: bool = True,
        firm_info: Dict = None,
    ) -> Dict:
        """
        Run a complete dunning cycle.

        Args:
            dry_run: If True, simulate without sending
            firm_info: Firm information for templates

        Returns:
            Summary of actions taken
        """
        summary = {
            "total_overdue": 0,
            "notices_sent": 0,
            "skipped_already_sent": 0,
            "skipped_payment_received": 0,
            "skipped_not_due": 0,
            "errors": 0,
            "total_balance_due": 0.0,
            "details": [],
        }

        overdue_invoices = self.get_overdue_invoices()
        summary["total_overdue"] = len(overdue_invoices)

        for invoice in overdue_invoices:
            summary["total_balance_due"] += invoice.balance_due

            action = self.determine_dunning_action(invoice)

            detail = {
                "invoice_number": invoice.invoice_number,
                "contact_name": invoice.contact_name,
                "days_overdue": invoice.days_overdue,
                "balance_due": invoice.balance_due,
                "action": action.reason,
                "sent": False,
            }

            if action.should_send:
                notice_content = self.generate_dunning_notice(action, firm_info)
                if notice_content:
                    success = self.send_dunning_notice(action, notice_content, dry_run)
                    if success:
                        summary["notices_sent"] += 1
                        detail["sent"] = True
                    else:
                        summary["errors"] += 1
            else:
                if "already sent" in action.reason.lower():
                    summary["skipped_already_sent"] += 1
                elif "payment" in action.reason.lower():
                    summary["skipped_payment_received"] += 1
                else:
                    summary["skipped_not_due"] += 1

            summary["details"].append(detail)

        return summary

    def sync_payments(self) -> int:
        """
        Sync payments from MyCase to local database.

        Returns:
            Number of new payments recorded
        """
        new_payments = 0

        try:
            payments = self.client.get_all_pages(self.client.get_payments)

            for payment in payments:
                payment_id = payment.get("id")
                invoice_id = payment.get("invoice_id")
                amount = float(payment.get("amount", 0))
                payment_date_str = payment.get("payment_date")

                if not payment_date_str:
                    continue

                payment_date = datetime.fromisoformat(
                    payment_date_str.replace("Z", "")
                ).date()

                # Get additional context
                invoice = payment.get("invoice", {})
                case = invoice.get("case", {})
                contact = invoice.get("contact", {})

                try:
                    self.db.record_payment(
                        mycase_payment_id=payment_id,
                        invoice_id=invoice_id,
                        amount=amount,
                        payment_date=payment_date,
                        contact_id=contact.get("id"),
                        case_id=case.get("id"),
                        case_name=case.get("name"),
                    )
                    new_payments += 1
                except Exception:
                    # Already recorded
                    pass

        except MyCaseAPIError as e:
            print(f"Error syncing payments: {e}")

        return new_payments

    def get_collections_report(self) -> Dict:
        """
        Generate a collections report with aging analysis.

        Returns:
            Collections report dictionary
        """
        overdue_invoices = self.get_overdue_invoices()

        report = {
            "generated_at": datetime.now().isoformat(),
            "total_invoices": len(overdue_invoices),
            "total_balance_due": sum(inv.balance_due for inv in overdue_invoices),
            "aging": {
                "1-15_days": {"count": 0, "amount": 0.0},
                "16-30_days": {"count": 0, "amount": 0.0},
                "31-60_days": {"count": 0, "amount": 0.0},
                "61-90_days": {"count": 0, "amount": 0.0},
                "90+_days": {"count": 0, "amount": 0.0},
            },
            "by_contact": {},
            "by_case": {},
            "invoices": [],
        }

        for inv in overdue_invoices:
            # Aging buckets
            if inv.days_overdue <= 15:
                bucket = "1-15_days"
            elif inv.days_overdue <= 30:
                bucket = "16-30_days"
            elif inv.days_overdue <= 60:
                bucket = "31-60_days"
            elif inv.days_overdue <= 90:
                bucket = "61-90_days"
            else:
                bucket = "90+_days"

            report["aging"][bucket]["count"] += 1
            report["aging"][bucket]["amount"] += inv.balance_due

            # By contact
            if inv.contact_name not in report["by_contact"]:
                report["by_contact"][inv.contact_name] = {
                    "count": 0,
                    "amount": 0.0,
                    "email": inv.contact_email,
                }
            report["by_contact"][inv.contact_name]["count"] += 1
            report["by_contact"][inv.contact_name]["amount"] += inv.balance_due

            # By case
            case_key = inv.case_name or "Unassigned"
            if case_key not in report["by_case"]:
                report["by_case"][case_key] = {"count": 0, "amount": 0.0}
            report["by_case"][case_key]["count"] += 1
            report["by_case"][case_key]["amount"] += inv.balance_due

            # Invoice details
            report["invoices"].append({
                "invoice_number": inv.invoice_number,
                "contact_name": inv.contact_name,
                "case_name": inv.case_name,
                "balance_due": inv.balance_due,
                "days_overdue": inv.days_overdue,
                "last_dunning_level": inv.last_dunning_level,
            })

        # Sort invoices by days overdue (most overdue first)
        report["invoices"].sort(key=lambda x: x["days_overdue"], reverse=True)

        return report


if __name__ == "__main__":
    # Test collections manager
    from templates import create_default_templates

    # Ensure templates exist
    create_default_templates()

    manager = CollectionsManager()

    print("=== Collections Report ===")
    print("(Note: Requires valid API authentication)")

    try:
        # Run dunning cycle in dry run mode
        summary = manager.run_dunning_cycle(dry_run=True)
        print(f"\nDunning Cycle Summary:")
        print(f"  Total Overdue Invoices: {summary['total_overdue']}")
        print(f"  Notices to Send: {summary['notices_sent']}")
        print(f"  Already Sent: {summary['skipped_already_sent']}")
        print(f"  Payment Received: {summary['skipped_payment_received']}")
        print(f"  Total Balance Due: ${summary['total_balance_due']:,.2f}")
    except Exception as e:
        print(f"Error running collections: {e}")
        print("Make sure you've authenticated with: python auth.py")
