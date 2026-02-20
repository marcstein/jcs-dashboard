"""
Dunning Email System

Sends staged collection notices based on invoice past due dates:
- Notice 1: Friendly Reminder (5-7 days past due)
- Notice 2: Formal Reminder (15-20 days past due)
- Notice 3: Urgent Notice (30 days past due)
- Notice 4: Final Notice (45-60 days past due)

Uses SendGrid for email delivery with test mode support.
Multi-tenant PostgreSQL support via firm_id parameter.
"""
import os
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from db.cache import get_invoices, get_contacts
from db.tracking import record_dunning_notice, get_last_dunning_level

# Load .env file if it exists
from config import BASE_DIR

env_file = BASE_DIR / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())


@dataclass
class DunningInvoice:
    """Invoice data for dunning notice."""
    invoice_id: int
    invoice_number: str
    case_id: int
    case_name: str
    client_name: str
    client_email: str
    total_amount: float
    paid_amount: float
    balance_due: float
    due_date: date
    days_overdue: int


@dataclass
class DunningStage:
    """Dunning stage definition."""
    stage: int
    name: str
    min_days: int
    max_days: int
    subject_template: str


# Define the 4 dunning stages based on the document
DUNNING_STAGES = [
    DunningStage(1, "Friendly Reminder", 5, 14, "Payment Reminder - {case_ref}"),
    DunningStage(2, "Formal Reminder", 15, 29, "Important: Outstanding Balance - {case_ref}"),
    DunningStage(3, "Urgent Notice", 30, 44, "URGENT: Seriously Past Due Account - {case_ref}"),
    DunningStage(4, "Final Notice", 45, 999, "FINAL NOTICE Before Collection Action - {case_ref}"),
]


def get_stage_for_days(days_overdue: int) -> Optional[DunningStage]:
    """Get the appropriate dunning stage for days overdue."""
    for stage in DUNNING_STAGES:
        if stage.min_days <= days_overdue <= stage.max_days:
            return stage
    return None


def generate_notice_1_html(inv: DunningInvoice) -> str:
    """Generate Notice 1: Friendly Reminder (5-7 days past due)."""
    return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; }}
        .header {{ background: #1a365d; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
        .payment-details {{ background: #f7fafc; border-left: 4px solid #1a365d; padding: 15px; margin: 20px 0; }}
        .payment-methods {{ background: #edf2f7; padding: 15px; margin: 20px 0; border-radius: 5px; }}
        .signature {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>JCS Law Firm</h2>
    </div>
    <div class="content">
        <p>Dear {inv.client_name},</p>

        <p>I hope this message finds you well. I'm writing regarding the payment for legal services in your case, <strong>{inv.case_name}</strong>, which was due on {inv.due_date.strftime('%B %d, %Y')}.</p>

        <p>Our records indicate that we have not yet received your payment of <strong>${inv.balance_due:,.2f}</strong>. I understand that oversights happen, and wanted to reach out as a courtesy reminder.</p>

        <p>If you have already sent payment, please disregard this notice and accept my thanks. If you are experiencing difficulty meeting this payment deadline, please contact our office at your earliest convenience so we can discuss potential payment arrangement options.</p>

        <div class="payment-details">
            <strong>Payment Details:</strong><br>
            • Amount Due: <strong>${inv.balance_due:,.2f}</strong><br>
            • Original Due Date: {inv.due_date.strftime('%B %d, %Y')}<br>
            • Invoice Number: {inv.invoice_number}
        </div>

        <div class="payment-methods">
            <strong>You may submit payment by:</strong><br>
            • Credit/Debit Card (call office)<br>
            • Check (payable to: JCS Law)<br>
            • Online payment portal
        </div>

        <p>Please feel free to contact me if you have any questions or concerns.</p>

        <div class="signature">
            <p>Best regards,</p>
            <p><strong>Melissa Scarlett</strong><br>
            Accounts Receivable Specialist<br>
            JCS Law Firm<br>
            Phone: (314) 561-9690</p>
        </div>
    </div>
</body>
</html>
"""


def generate_notice_2_html(inv: DunningInvoice) -> str:
    """Generate Notice 2: Formal Reminder (15-20 days past due)."""
    action_date = (date.today() + timedelta(days=10)).strftime('%B %d, %Y')

    return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; }}
        .header {{ background: #744210; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
        .balance-box {{ background: #fffaf0; border: 2px solid #c05621; padding: 15px; margin: 20px 0; text-align: center; }}
        .action-required {{ background: #fef3c7; border-left: 4px solid #d97706; padding: 15px; margin: 20px 0; }}
        .signature {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>JCS Law Firm - Important Notice</h2>
    </div>
    <div class="content">
        <p>Dear {inv.client_name},</p>

        <p>This letter serves as formal notice that your account remains past due. As of {date.today().strftime('%B %d, %Y')}, we have not received payment for legal services rendered in your case, <strong>{inv.case_name}</strong>.</p>

        <div class="balance-box">
            <strong style="font-size: 18px;">Outstanding Balance: ${inv.balance_due:,.2f}</strong><br>
            Original Due Date: {inv.due_date.strftime('%B %d, %Y')}<br>
            Days Overdue: {inv.days_overdue}
        </div>

        <p>Our office takes pride in providing quality legal representation while maintaining reasonable and transparent billing practices. Prompt payment allows us to continue dedicating the necessary time and resources to your case.</p>

        <div class="action-required">
            <strong>Action Required:</strong><br>
            Please remit payment within 10 days of the date of this notice (by {action_date}). If there are circumstances preventing timely payment, I urge you to contact our office immediately to discuss a payment plan or alternative arrangements.<br><br>
            <em>Failure to respond may impact our ability to continue representation in your matter and could result in additional collection efforts.</em>
        </div>

        <p>Payment can be made by check, credit card, or through our online portal. Please reference invoice #{inv.invoice_number} with your payment.</p>

        <p>Our office remains committed to resolving your legal matter successfully and hope we can quickly resolve this billing issue.</p>

        <div class="signature">
            <p>Sincerely,</p>
            <p><strong>Melissa Scarlett</strong><br>
            Accounts Receivable Specialist<br>
            JCS Law Firm<br>
            Phone: (314) 561-9690</p>
        </div>
    </div>
</body>
</html>
"""


def generate_notice_3_html(inv: DunningInvoice) -> str:
    """Generate Notice 3: Urgent Notice (30 days past due)."""
    deadline = (date.today() + timedelta(days=7)).strftime('%B %d, %Y')
    late_fee = inv.balance_due * 0.05  # Example 5% late fee
    total_with_fee = inv.balance_due + late_fee

    return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; }}
        .header {{ background: #c53030; color: white; padding: 20px; text-align: center; }}
        .urgent-banner {{ background: #fed7d7; color: #c53030; padding: 15px; text-align: center; font-weight: bold; font-size: 18px; border: 2px solid #c53030; }}
        .content {{ padding: 20px; }}
        .balance-box {{ background: #fff5f5; border: 2px solid #c53030; padding: 15px; margin: 20px 0; }}
        .warnings {{ background: #fef2f2; border-left: 4px solid #dc2626; padding: 15px; margin: 20px 0; }}
        .signature {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>JCS Law Firm - URGENT NOTICE</h2>
    </div>
    <div class="urgent-banner">
        ⚠️ ACCOUNT SERIOUSLY PAST DUE ⚠️
    </div>
    <div class="content">
        <p>Dear {inv.client_name},</p>

        <p>Despite previous correspondence, your account remains unpaid. This constitutes a serious breach of our fee agreement.</p>

        <div class="balance-box">
            <table style="width: 100%;">
                <tr><td>Current Outstanding Balance:</td><td style="text-align: right;"><strong>${inv.balance_due:,.2f}</strong></td></tr>
                <tr><td>Original Due Date:</td><td style="text-align: right;">{inv.due_date.strftime('%B %d, %Y')}</td></tr>
                <tr><td>Days Overdue:</td><td style="text-align: right; color: #c53030;"><strong>{inv.days_overdue} days</strong></td></tr>
                <tr style="border-top: 2px solid #c53030;"><td><strong>Total Amount Now Due:</strong></td><td style="text-align: right;"><strong style="font-size: 18px;">${inv.balance_due:,.2f}</strong></td></tr>
            </table>
        </div>

        <p style="background: #fef3c7; padding: 10px; border-radius: 5px;"><strong>Immediate Action Required:</strong><br>
        Payment must be received within 7 days of the date of this letter (by <strong>{deadline}</strong>).</p>

        <div class="warnings">
            <strong>Please be advised:</strong>
            <ol>
                <li>Continued non-payment may result in withdrawal from your case (subject to court approval where applicable)</li>
                <li>Outstanding balances may be referred to a collection agency</li>
                <li>Collection costs and reasonable attorney fees may be added to your balance</li>
            </ol>
        </div>

        <p><strong>Payment Arrangements:</strong><br>
        If you are unable to pay the full amount immediately, contact our office no later than {deadline} to arrange a payment plan. This is your final opportunity to resolve this matter directly with our office before additional action is taken.</p>

        <p><strong>Your Legal Representation:</strong><br>
        Please understand that unresolved billing issues affect my ability to continue providing the representation your case requires. I take my ethical obligations seriously and want to see your legal matter through to completion, but this requires mutual commitment to our agreement.</p>

        <p style="font-weight: bold; color: #c53030;">Your prompt attention is required. Please contact me immediately.</p>

        <div class="signature">
            <p>Sincerely,</p>
            <p><strong>Melissa Scarlett</strong><br>
            Accounts Receivable Specialist<br>
            JCS Law Firm<br>
            Phone: (314) 561-9690</p>
        </div>
    </div>
</body>
</html>
"""


def generate_notice_4_html(inv: DunningInvoice) -> str:
    """Generate Notice 4: Final Notice (45-60 days past due)."""
    deadline = (date.today() + timedelta(days=10)).strftime('%B %d, %Y')
    contact_deadline = (date.today() + timedelta(days=5)).strftime('%B %d, %Y')

    return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; }}
        .header {{ background: #1a1a1a; color: white; padding: 20px; text-align: center; }}
        .final-banner {{ background: #1a1a1a; color: #fbbf24; padding: 15px; text-align: center; font-weight: bold; font-size: 20px; }}
        .content {{ padding: 20px; }}
        .balance-box {{ background: #1a1a1a; color: white; padding: 20px; margin: 20px 0; text-align: center; }}
        .actions-list {{ background: #fef2f2; border: 2px solid #dc2626; padding: 20px; margin: 20px 0; }}
        .payment-options {{ background: #fefce8; border-left: 4px solid #ca8a04; padding: 15px; margin: 20px 0; }}
        .signature {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>JCS Law Firm</h2>
    </div>
    <div class="final-banner">
        ⚠️ FINAL NOTICE - IMMEDIATE ACTION REQUIRED ⚠️
    </div>
    <div class="content">
        <p>Dear {inv.client_name},</p>

        <p>This is your <strong>final notice</strong> regarding the seriously delinquent balance on your account. All previous attempts to resolve this matter have been unsuccessful.</p>

        <div class="balance-box">
            <div style="font-size: 14px; margin-bottom: 10px;">Outstanding Balance</div>
            <div style="font-size: 32px; font-weight: bold; color: #fbbf24;">${inv.balance_due:,.2f}</div>
            <div style="margin-top: 10px;">Days Overdue: <strong>{inv.days_overdue}</strong></div>
        </div>

        <p style="font-size: 16px; font-weight: bold;">This is your last opportunity to resolve this balance before the following actions are taken:</p>

        <div class="actions-list">
            <ol style="margin: 0; padding-left: 20px;">
                <li style="margin-bottom: 10px;"><strong>Withdrawal from Representation:</strong> We will file a motion to withdraw as your attorney in {inv.case_name} (subject to court approval)</li>
                <li style="margin-bottom: 10px;"><strong>Collection Referral:</strong> Your account will be referred to a collection agency within 10 days if payment is not received</li>
                <li><strong>Additional Costs:</strong> You will be responsible for all collection costs, court costs, and reasonable attorney fees incurred in collecting this debt</li>
            </ol>
        </div>

        <p style="background: #dc2626; color: white; padding: 15px; text-align: center; font-weight: bold; font-size: 16px;">
            Payment must be received by {deadline}
        </p>

        <div class="payment-options">
            <strong>Final Payment Options:</strong>
            <ul>
                <li>Pay in full immediately</li>
                <li>Contact our office by {contact_deadline} to arrange an acceptable payment plan with immediate down payment</li>
            </ul>
            <p style="margin-bottom: 0;"><em>Failure to respond or remit payment by {deadline} will result in automatic referral to collections without further notice.</em></p>
        </div>

        <p>I regret that our professional relationship has reached this point. However, I have an obligation to my practice and other clients to ensure fair compensation for services rendered.</p>

        <p>If you have any questions about this notice or wish to discuss payment arrangements, contact me immediately at <strong>(314) 561-9690</strong>. Our primary goal is still to help you.</p>

        <p style="background: #fef3c7; padding: 15px; border-radius: 5px; font-weight: bold; text-align: center;">
            This is a final attempt to collect this balance.<br>Please treat it with the urgency it requires.
        </p>

        <div class="signature">
            <p>Sincerely,</p>
            <p><strong>Melissa Scarlett</strong><br>
            Accounts Receivable Specialist<br>
            JCS Law Firm<br>
            Phone: (314) 561-9690</p>
        </div>
    </div>
</body>
</html>
"""


def generate_notice_text(stage: int, inv: DunningInvoice) -> str:
    """Generate plain text version of the notice."""
    if stage == 1:
        return f"""
JCS Law Firm - Payment Reminder

Dear {inv.client_name},

I hope this message finds you well. I'm writing regarding the payment for legal services
in your case, {inv.case_name}, which was due on {inv.due_date.strftime('%B %d, %Y')}.

Our records indicate that we have not yet received your payment of ${inv.balance_due:,.2f}.

Payment Details:
- Amount Due: ${inv.balance_due:,.2f}
- Original Due Date: {inv.due_date.strftime('%B %d, %Y')}
- Invoice Number: {inv.invoice_number}

Please contact our office if you have any questions.

Best regards,
Melissa Scarlett
Accounts Receivable Specialist
JCS Law Firm
(314) 561-9690
"""
    elif stage == 2:
        return f"""
JCS Law Firm - IMPORTANT: Outstanding Balance

Dear {inv.client_name},

This letter serves as formal notice that your account remains past due.

Outstanding Balance: ${inv.balance_due:,.2f}
Original Due Date: {inv.due_date.strftime('%B %d, %Y')}
Days Overdue: {inv.days_overdue}

Please remit payment within 10 days or contact our office to discuss payment arrangements.

Sincerely,
Melissa Scarlett
Accounts Receivable Specialist
JCS Law Firm
(314) 561-9690
"""
    elif stage == 3:
        deadline = (date.today() + timedelta(days=7)).strftime('%B %d, %Y')
        return f"""
JCS Law Firm - URGENT: Account Seriously Past Due

Dear {inv.client_name},

ACCOUNT SERIOUSLY PAST DUE

Despite previous correspondence, your account remains unpaid.

Current Outstanding Balance: ${inv.balance_due:,.2f}
Original Due Date: {inv.due_date.strftime('%B %d, %Y')}
Days Overdue: {inv.days_overdue}

Payment must be received by {deadline}.

Continued non-payment may result in withdrawal from your case and referral to collections.

Contact us immediately.

Sincerely,
Melissa Scarlett
Accounts Receivable Specialist
JCS Law Firm
(314) 561-9690
"""
    else:  # stage 4
        deadline = (date.today() + timedelta(days=10)).strftime('%B %d, %Y')
        return f"""
JCS Law Firm - FINAL NOTICE Before Collection Action

Dear {inv.client_name},

FINAL NOTICE - IMMEDIATE ACTION REQUIRED

This is your final notice regarding your seriously delinquent balance.

Outstanding Balance: ${inv.balance_due:,.2f}
Days Overdue: {inv.days_overdue}

Payment must be received by {deadline}.

Failure to respond will result in:
1. Withdrawal from Representation
2. Referral to Collection Agency
3. Additional collection costs

This is your last opportunity to resolve this matter directly.

Sincerely,
Melissa Scarlett
Accounts Receivable Specialist
JCS Law Firm
(314) 561-9690
"""


class DunningEmailManager:
    """Manages sending dunning emails. PostgreSQL multi-tenant via firm_id."""

    def __init__(self, firm_id: str, test_mode: bool = True, test_email: str = None):
        self.firm_id = firm_id
        self.test_mode = test_mode
        self.test_email = test_email or "marc.stein@gmail.com"
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY", "")
        self.from_email = "melissa@jcslawstl.com"
        self.from_name = "Melissa Scarlett - JCS Law Firm"

    def get_invoices_for_stage(self, stage: DunningStage, limit: int = 1) -> List[DunningInvoice]:
        """Get invoices that match a dunning stage from PostgreSQL."""
        # Get all invoices for this firm
        all_invoices = get_invoices(self.firm_id)

        # Get all cases and contacts for lookup
        from db.cache import get_cases, get_contacts as get_cached_contacts
        all_cases = get_cases(self.firm_id)
        all_contacts = get_cached_contacts(self.firm_id)

        # Build lookup maps
        cases_map = {c['id']: c for c in all_cases}
        contacts_map = {c['id']: c for c in all_contacts}

        # Filter invoices by balance due and days overdue
        invoices = []
        today = date.today()

        for inv in all_invoices:
            # Skip if no balance due
            if not inv.get('balance_due') or inv['balance_due'] <= 0:
                continue

            # Skip if no due date
            if not inv.get('due_date'):
                continue

            # Parse due date
            due_date = inv['due_date']
            if isinstance(due_date, str):
                due_date = datetime.strptime(due_date, '%Y-%m-%d').date()

            # Calculate days overdue
            days_overdue = (today - due_date).days

            # Check if in stage range
            if not (stage.min_days <= days_overdue <= stage.max_days):
                continue

            # Get case name
            case_id = inv.get('case_id')
            case_data = cases_map.get(case_id, {})
            case_name = case_data.get('name', 'Unknown Case')

            # Get client info from contact
            contact_id = inv.get('contact_id')
            contact_data = contacts_map.get(contact_id, {})
            client_name = f"{contact_data.get('first_name', '')} {contact_data.get('last_name', '')}".strip() or 'Client'
            client_email = contact_data.get('email', '')

            invoices.append(DunningInvoice(
                invoice_id=inv['id'],
                invoice_number=str(inv.get('invoice_number', '')),
                case_id=case_id,
                case_name=case_name,
                client_name=client_name,
                client_email=client_email,
                total_amount=float(inv.get('total_amount', 0)),
                paid_amount=float(inv.get('paid_amount', 0)),
                balance_due=float(inv.get('balance_due', 0)),
                due_date=due_date,
                days_overdue=days_overdue,
            ))

        # Return up to limit invoices, sorted by days overdue descending
        invoices.sort(key=lambda x: x.days_overdue, reverse=True)
        return invoices[:limit]

    def send_email_smtp(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str,
    ) -> Tuple[bool, str]:
        """Send email via SMTP (Gmail or other provider)."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")

        if not smtp_user or not smtp_pass:
            return False, "SMTP credentials not configured (set SMTP_USER and SMTP_PASS)"

        actual_recipient = self.test_email if self.test_mode else to_email

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{self.from_name} <{smtp_user}>"
        msg['To'] = actual_recipient

        msg.attach(MIMEText(body_text, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, actual_recipient, msg.as_string())
            return True, f"Sent to {actual_recipient} via SMTP"
        except Exception as e:
            return False, f"SMTP error: {str(e)}"

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str,
    ) -> Tuple[bool, str]:
        """Send email via SendGrid or SMTP fallback."""
        import httpx

        # Try SMTP first if configured
        smtp_user = os.getenv("SMTP_USER", "")
        if smtp_user:
            return self.send_email_smtp(to_email, subject, body_text, body_html)

        # Fall back to SendGrid
        if not self.sendgrid_api_key:
            return False, "No email provider configured (set SENDGRID_API_KEY or SMTP_USER/SMTP_PASS)"

        # In test mode, override recipient
        actual_recipient = self.test_email if self.test_mode else to_email

        payload = {
            "personalizations": [{
                "to": [{"email": actual_recipient}],
                "subject": subject,
            }],
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "content": [
                {"type": "text/plain", "value": body_text},
                {"type": "text/html", "value": body_html},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.sendgrid_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers=headers,
                timeout=30,
            )

            if response.status_code in (200, 202):
                return True, f"Sent to {actual_recipient}"
            else:
                return False, f"HTTP {response.status_code}: {response.text}"

        except Exception as e:
            return False, str(e)

    def send_dunning_notice(self, stage: int, inv: DunningInvoice) -> Tuple[bool, str]:
        """Send a dunning notice for the given stage and record to database."""
        stage_info = DUNNING_STAGES[stage - 1]

        # Generate case reference for subject
        case_ref = inv.case_name.split(':')[0] if ':' in inv.case_name else inv.invoice_number
        subject = stage_info.subject_template.format(case_ref=case_ref)

        # Add test mode indicator
        if self.test_mode:
            subject = f"[TEST] {subject}"

        # Generate content
        if stage == 1:
            html = generate_notice_1_html(inv)
        elif stage == 2:
            html = generate_notice_2_html(inv)
        elif stage == 3:
            html = generate_notice_3_html(inv)
        else:
            html = generate_notice_4_html(inv)

        text = generate_notice_text(stage, inv)

        # Determine recipient
        recipient = self.test_email if self.test_mode else (inv.client_email or self.test_email)

        # Send email
        success, message = self.send_email(recipient, subject, text, html)

        # Record to database if successful
        if success:
            record_dunning_notice(
                firm_id=self.firm_id,
                invoice_id=inv.invoice_id,
                contact_id=0,  # TODO: Get actual contact_id if available
                days_overdue=inv.days_overdue,
                notice_level=stage,
                amount_due=inv.balance_due,
                invoice_number=inv.invoice_number,
                case_id=inv.case_id,
                template_used=f"notice_{stage}",
            )

        return success, message

    def send_test_samples(self) -> Dict:
        """Send one sample of each dunning stage for testing."""
        results = {
            "sent": [],
            "failed": [],
            "skipped": [],
        }

        print(f"\n{'='*60}")
        print("DUNNING EMAIL TEST - Sending samples to:", self.test_email)
        print(f"{'='*60}\n")

        for stage in DUNNING_STAGES:
            print(f"Stage {stage.stage}: {stage.name} ({stage.min_days}-{stage.max_days} days)")

            # Get one invoice for this stage
            invoices = self.get_invoices_for_stage(stage, limit=1)

            if not invoices:
                print(f"  ⚠️  No invoices found for this stage")
                results["skipped"].append({
                    "stage": stage.stage,
                    "name": stage.name,
                    "reason": "No matching invoices",
                })
                continue

            inv = invoices[0]
            print(f"  Invoice: {inv.invoice_number}")
            print(f"  Client: {inv.client_name}")
            print(f"  Balance: ${inv.balance_due:,.2f}")
            print(f"  Days Overdue: {inv.days_overdue}")

            success, message = self.send_dunning_notice(stage.stage, inv)

            if success:
                print(f"  ✅ {message}")
                results["sent"].append({
                    "stage": stage.stage,
                    "name": stage.name,
                    "invoice": inv.invoice_number,
                    "client": inv.client_name,
                    "balance": inv.balance_due,
                    "days_overdue": inv.days_overdue,
                })
            else:
                print(f"  ❌ Failed: {message}")
                results["failed"].append({
                    "stage": stage.stage,
                    "name": stage.name,
                    "error": message,
                })

            print()

        # Summary
        print(f"{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Sent: {len(results['sent'])}")
        print(f"Failed: {len(results['failed'])}")
        print(f"Skipped: {len(results['skipped'])}")

        return results


if __name__ == "__main__":
    import sys

    # For testing, use default firm_id
    firm_id = sys.argv[1] if len(sys.argv) > 1 else "jcs_law"
    test_email = sys.argv[2] if len(sys.argv) > 2 else "marc.stein@gmail.com"

    manager = DunningEmailManager(firm_id=firm_id, test_mode=True, test_email=test_email)
    results = manager.send_test_samples()
