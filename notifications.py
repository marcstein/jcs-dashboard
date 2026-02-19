"""
Notifications Module

Handles multi-channel notifications:
- Slack webhook integration
- Email via SendGrid
- SMS via Twilio
- Notification preferences and routing
"""
import os
import json
import hashlib
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from config import DATA_DIR


class NotificationChannel(Enum):
    """Available notification channels."""
    SLACK = "slack"
    EMAIL = "email"
    SMS = "sms"
    CONSOLE = "console"  # For testing/dry-run


class NotificationPriority(Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Notification:
    """Represents a notification to be sent."""
    title: str
    message: str
    channel: NotificationChannel
    priority: NotificationPriority = NotificationPriority.NORMAL
    recipient: Optional[str] = None  # email, phone, or slack channel
    metadata: Dict = field(default_factory=dict)
    sent_at: Optional[datetime] = None
    delivery_id: Optional[str] = None


@dataclass
class SlackConfig:
    """Slack webhook configuration."""
    webhook_url: str
    default_channel: str = "#mycase-alerts"
    username: str = "MyCase Bot"
    icon_emoji: str = ":scales:"


@dataclass
class EmailConfig:
    """SendGrid email configuration."""
    api_key: str
    from_email: str = "mycase@jcslaw.com"
    from_name: str = "JCS Law Firm - MyCase"


@dataclass
class SMTPConfig:
    """Gmail SMTP configuration."""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""  # App password for Gmail
    from_email: str = ""
    from_name: str = "JCS Law Firm - MyCase"


@dataclass
class SMSConfig:
    """Twilio SMS configuration."""
    account_sid: str
    auth_token: str
    from_number: str


class NotificationManager:
    """
    Manages multi-channel notifications for the MyCase automation system.

    Supports:
    - Slack webhooks for team alerts
    - SendGrid for email notifications
    - Twilio for SMS alerts
    - Dry-run mode for testing
    """

    def __init__(self):
        self.config_file = DATA_DIR / "notifications_config.json"
        self.log_file = DATA_DIR / "notifications_log.json"
        self._config = self._load_config()
        self._dry_run = self._config.get("dry_run", True)

    def _load_config(self) -> Dict:
        """Load notification configuration."""
        if self.config_file.exists():
            with open(self.config_file) as f:
                return json.load(f)

        # Default config
        return {
            "dry_run": True,
            "enabled_channels": ["console"],
            "slack": {
                "webhook_url": os.getenv("SLACK_WEBHOOK_URL", ""),
                "default_channel": "#mycase-alerts",
                "username": "MyCase Bot",
                "icon_emoji": ":scales:",
            },
            "email": {
                "api_key": os.getenv("SENDGRID_API_KEY", ""),
                "from_email": "mycase@jcslaw.com",
                "from_name": "JCS Law Firm - MyCase",
            },
            "smtp": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": os.getenv("SMTP_USERNAME", ""),
                "password": os.getenv("SMTP_PASSWORD", ""),
                "from_email": os.getenv("SMTP_FROM_EMAIL", ""),
                "from_name": "JCS Law Firm - MyCase",
            },
            "sms": {
                "account_sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
                "auth_token": os.getenv("TWILIO_AUTH_TOKEN", ""),
                "from_number": os.getenv("TWILIO_FROM_NUMBER", ""),
            },
            "routing": {
                # Route notifications by type to channels
                "critical_alerts": ["slack", "email"],
                "daily_reports": ["slack"],
                "deadline_reminders": ["email"],
                "payment_reminders": ["email", "sms"],
            },
            "recipients": {
                # Staff notification preferences
                "melissa": {"email": "", "slack": "@melissa", "sms": ""},
                "ty": {"email": "", "slack": "@ty", "sms": ""},
                "tiffany": {"email": "", "slack": "@tiffany", "sms": ""},
                "alison": {"email": "", "slack": "@alison", "sms": ""},
                "cole": {"email": "", "slack": "@cole", "sms": ""},
            },
        }

    def save_config(self, config: Dict):
        """Save notification configuration."""
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)
        self._config = config

    def _log_notification(self, notification: Notification, success: bool, error: str = None):
        """Log a notification attempt."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "title": notification.title,
            "channel": notification.channel.value,
            "priority": notification.priority.value,
            "recipient": notification.recipient,
            "success": success,
            "error": error,
            "delivery_id": notification.delivery_id,
        }

        # Append to log file
        logs = []
        if self.log_file.exists():
            with open(self.log_file) as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    logs = []

        logs.append(log_entry)

        # Keep last 1000 entries
        logs = logs[-1000:]

        with open(self.log_file, "w") as f:
            json.dump(logs, f, indent=2)

    # ========== Slack Integration ==========

    def send_slack(
        self,
        message: str,
        channel: str = None,
        title: str = None,
        color: str = None,
        fields: List[Dict] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> bool:
        """
        Send a message to Slack via webhook.

        Args:
            message: Main message text
            channel: Override default channel
            title: Optional title for attachment
            color: Attachment color (good, warning, danger, or hex)
            fields: List of {title, value, short} dicts
            priority: Message priority level

        Returns:
            True if sent successfully
        """
        slack_config = self._config.get("slack", {})
        webhook_url = slack_config.get("webhook_url")

        if not webhook_url:
            print("[SLACK] No webhook URL configured")
            return False

        notification = Notification(
            title=title or "MyCase Alert",
            message=message,
            channel=NotificationChannel.SLACK,
            priority=priority,
            recipient=channel or slack_config.get("default_channel"),
        )

        if self._dry_run:
            print(f"[SLACK DRY-RUN] Would send to {notification.recipient}:")
            print(f"  Title: {title}")
            print(f"  Message: {message[:100]}...")
            self._log_notification(notification, True)
            return True

        try:
            import httpx

            # Build payload
            payload = {
                "channel": notification.recipient,
                "username": slack_config.get("username", "MyCase Bot"),
                "icon_emoji": slack_config.get("icon_emoji", ":scales:"),
            }

            # Use attachment for rich formatting
            if title or fields or color:
                # Map priority to color
                if not color:
                    color_map = {
                        NotificationPriority.LOW: "#36a64f",
                        NotificationPriority.NORMAL: "#439FE0",
                        NotificationPriority.HIGH: "#ff9800",
                        NotificationPriority.CRITICAL: "#d00000",
                    }
                    color = color_map.get(priority, "#439FE0")

                attachment = {
                    "color": color,
                    "title": title,
                    "text": message,
                    "ts": int(datetime.now().timestamp()),
                }

                if fields:
                    attachment["fields"] = fields

                payload["attachments"] = [attachment]
            else:
                payload["text"] = message

            response = httpx.post(webhook_url, json=payload, timeout=10)
            success = response.status_code == 200

            notification.sent_at = datetime.now()
            self._log_notification(notification, success,
                                   None if success else f"HTTP {response.status_code}")

            return success

        except Exception as e:
            self._log_notification(notification, False, str(e))
            print(f"[SLACK ERROR] {e}")
            return False

    def send_slack_report(
        self,
        report_type: str,
        summary: Dict,
        details: List[Dict] = None,
    ) -> bool:
        """
        Send a formatted report to Slack.

        Args:
            report_type: Type of report (e.g., "daily_ar", "intake_weekly")
            summary: Summary metrics dict
            details: Optional list of detail items

        Returns:
            True if sent successfully
        """
        # Format based on report type
        if report_type == "daily_ar":
            title = f":moneybag: Daily A/R Report - {date.today()}"
            color = "warning" if summary.get("over_60_pct", 0) > 25 else "good"

            message = f"*Total AR:* ${summary.get('total_ar', 0):,.2f}\n"
            message += f"*Over 60 Days:* {summary.get('over_60_pct', 0):.1f}%\n"
            message += f"*Compliance Rate:* {summary.get('compliance_rate', 0):.1f}%"

            fields = [
                {"title": "NOIW Pipeline", "value": str(summary.get('noiw_count', 0)), "short": True},
                {"title": "Delinquent", "value": str(summary.get('delinquent', 0)), "short": True},
            ]

        elif report_type == "intake_weekly":
            title = f":new: Weekly Intake Report - {date.today()}"
            color = "good"

            message = f"*New Cases:* {summary.get('new_cases', 0)}\n"
            message += f"*Contact Rate:* {summary.get('contact_rate', 0):.1f}%"

            fields = [
                {"title": "DWI", "value": str(summary.get('dwi_count', 0)), "short": True},
                {"title": "Traffic", "value": str(summary.get('traffic_count', 0)), "short": True},
            ]

        elif report_type == "overdue_tasks":
            title = f":warning: Overdue Tasks Alert"
            color = "danger"

            message = f"*{summary.get('count', 0)} overdue tasks* require attention"

            fields = []
            if details:
                for item in details[:5]:
                    fields.append({
                        "title": item.get("assignee", "Unknown"),
                        "value": f"{item.get('count', 0)} tasks",
                        "short": True,
                    })

        elif report_type == "license_deadline":
            title = f":rotating_light: Critical License Deadline Alert"
            color = "danger"

            total = summary.get("total", 0)
            overdue = summary.get("overdue", 0)
            critical = summary.get("critical", 0)

            message = f"*{total} critical license deadlines*\n"
            if overdue > 0:
                message += f":red_circle: *{overdue} OVERDUE*\n"
            if critical > 0:
                message += f":warning: *{critical} due within 3 days*\n"

            fields = []
            cases = summary.get("cases", [])
            for case in cases[:8]:
                days = case.get("days", 0)
                if days < 0:
                    status = f":red_circle: {abs(days)}d overdue"
                else:
                    status = f"{days}d left"
                fields.append({
                    "title": f"{case.get('client', 'Unknown')} ({case.get('type', '')})",
                    "value": f"{status} - {case.get('assignee', '')}",
                    "short": True,
                })

        elif report_type == "noiw_daily":
            # Daily NOIW pipeline summary
            title = f":warning: NOIW Pipeline Report - {date.today()}"
            total_cases = summary.get('total_cases', 0)
            total_balance = summary.get('total_balance', 0)
            critical = summary.get('critical_count', 0)

            color = "danger" if critical > 20 else "warning" if total_cases > 50 else "#439FE0"

            message = f"*{total_cases} cases* in NOIW pipeline\n"
            message += f"*Total Balance:* ${total_balance:,.2f}\n"
            message += f"*Critical (60+ days):* {critical}"

            fields = [
                {"title": "30-60 days", "value": str(summary.get('bucket_30_60', 0)), "short": True},
                {"title": "60-90 days", "value": str(summary.get('bucket_60_90', 0)), "short": True},
                {"title": "90-180 days", "value": str(summary.get('bucket_90_180', 0)), "short": True},
                {"title": "180+ days", "value": str(summary.get('bucket_180_plus', 0)), "short": True},
            ]

        elif report_type == "noiw_critical":
            # Critical NOIW escalation alert
            title = f":rotating_light: CRITICAL NOIW Alert"
            color = "danger"

            case_count = summary.get('case_count', 0)
            total_balance = summary.get('total_balance', 0)

            message = f"*{case_count} cases* require immediate attention!\n"
            message += f"*Balance at Risk:* ${total_balance:,.2f}\n\n"

            # Add top cases if provided
            if details:
                message += "*Top Cases:*\n"
                for case in details[:5]:
                    message += f"• {case.get('contact_name', 'Unknown')}: ${case.get('balance_due', 0):,.2f} ({case.get('days_delinquent', 0)} days)\n"

            fields = None

        elif report_type == "noiw_workflow":
            # NOIW workflow status update
            title = f":clipboard: NOIW Workflow Status"
            color = "#439FE0"

            message = f"*Total Tracked:* {summary.get('total_tracked', 0)} cases\n"
            message += f"*Total Balance:* ${summary.get('total_balance', 0):,.2f}"

            fields = []
            by_status = summary.get('by_status', {})
            for status, data in by_status.items():
                if data.get('count', 0) > 0:
                    fields.append({
                        "title": status.replace('_', ' ').title(),
                        "value": f"{data['count']} (${data.get('total_balance', 0):,.0f})",
                        "short": True,
                    })

        elif report_type == "stalled_cases":
            # Stalled cases by attorney alert
            total = summary.get('total_stalled', 0)
            threshold = summary.get('threshold_days', 30)

            title = f":hourglass: Stalled Cases Alert - {total} cases over {threshold} days"
            color = "danger" if total > 20 else "warning" if total > 10 else "#439FE0"

            message = f"*{total} cases* have been stalled in their current phase for over {threshold} days.\n\n"

            # Add attorney breakdown
            attorneys = summary.get('attorneys', [])
            if attorneys:
                message += "*By Attorney:*\n"
                for atty in attorneys[:8]:
                    message += f"• *{atty['name']}*: {atty['count']} cases\n"
                    for case in atty.get('cases', [])[:2]:
                        message += f"  - {case['name']} ({case['days']}d in {case['phase']})\n"

            fields = None

        else:
            title = f"MyCase Alert: {report_type}"
            color = "#439FE0"
            message = json.dumps(summary, indent=2)
            fields = None

        return self.send_slack(
            message=message,
            title=title,
            color=color,
            fields=fields,
        )

    # ========== Email Integration (SendGrid) ==========

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> bool:
        """
        Send an email via SendGrid.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body_text: Plain text body
            body_html: Optional HTML body
            priority: Email priority

        Returns:
            True if sent successfully
        """
        email_config = self._config.get("email", {})
        api_key = email_config.get("api_key")

        if not api_key:
            print("[EMAIL] No SendGrid API key configured")
            return False

        notification = Notification(
            title=subject,
            message=body_text,
            channel=NotificationChannel.EMAIL,
            priority=priority,
            recipient=to_email,
        )

        if self._dry_run:
            print(f"[EMAIL DRY-RUN] Would send to {to_email}:")
            print(f"  Subject: {subject}")
            print(f"  Body: {body_text[:100]}...")
            self._log_notification(notification, True)
            return True

        try:
            import httpx

            payload = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {
                    "email": email_config.get("from_email"),
                    "name": email_config.get("from_name"),
                },
                "subject": subject,
                "content": [{"type": "text/plain", "value": body_text}],
            }

            if body_html:
                payload["content"].append({"type": "text/html", "value": body_html})

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            response = httpx.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers=headers,
                timeout=10,
            )

            success = response.status_code in (200, 202)
            notification.sent_at = datetime.now()
            self._log_notification(notification, success,
                                   None if success else f"HTTP {response.status_code}")

            return success

        except Exception as e:
            self._log_notification(notification, False, str(e))
            print(f"[EMAIL ERROR] {e}")
            return False

    # ========== SMTP Email Integration (Gmail) ==========

    def send_email_smtp(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str = None,
        cc_email: str = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> bool:
        """
        Send an email via SMTP (Gmail).

        Args:
            to_email: Recipient email address
            subject: Email subject
            body_text: Plain text body
            body_html: Optional HTML body
            cc_email: Optional CC email address
            priority: Email priority

        Returns:
            True if sent successfully
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_config = self._config.get("smtp", {})
        username = smtp_config.get("username")
        password = smtp_config.get("password")
        from_email = smtp_config.get("from_email") or username
        from_name = smtp_config.get("from_name", "JCS Law Firm - MyCase")
        smtp_server = smtp_config.get("smtp_server", "smtp.gmail.com")
        smtp_port = smtp_config.get("smtp_port", 587)

        if not all([username, password]):
            print("[SMTP] Gmail SMTP not fully configured (need username and password)")
            return False

        recipient_str = to_email + (f", CC: {cc_email}" if cc_email else "")
        notification = Notification(
            title=subject,
            message=body_text,
            channel=NotificationChannel.EMAIL,
            priority=priority,
            recipient=recipient_str,
        )

        if self._dry_run:
            print(f"[SMTP DRY-RUN] Would send to {to_email}:")
            if cc_email:
                print(f"  CC: {cc_email}")
            print(f"  Subject: {subject}")
            print(f"  Body: {body_text[:200]}...")
            self._log_notification(notification, True)
            return True

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{from_name} <{from_email}>"
            msg["To"] = to_email
            if cc_email:
                msg["Cc"] = cc_email

            # Attach plain text
            msg.attach(MIMEText(body_text, "plain"))

            # Attach HTML if provided
            if body_html:
                msg.attach(MIMEText(body_html, "html"))

            # Build recipient list (To + CC)
            recipients = [to_email]
            if cc_email:
                recipients.append(cc_email)

            # Connect and send
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.sendmail(from_email, recipients, msg.as_string())

            notification.sent_at = datetime.now()
            self._log_notification(notification, True)
            cc_msg = f" (CC: {cc_email})" if cc_email else ""
            print(f"[SMTP] Email sent successfully to {to_email}{cc_msg}")
            return True

        except Exception as e:
            self._log_notification(notification, False, str(e))
            print(f"[SMTP ERROR] {e}")
            return False

    # ========== MailTrap Email Integration ==========

    def send_email_mailtrap(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str = None,
        cc_email: str = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> bool:
        """
        Send an email via MailTrap API.

        Uses MAILTRAP_API_TOKEN and MAILTRAP_SENDER_EMAIL env vars.
        Falls back to SMTP if MailTrap is not configured.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body_text: Plain text body
            body_html: Optional HTML body
            cc_email: Optional CC email address
            priority: Email priority

        Returns:
            True if sent successfully
        """
        api_token = os.getenv("MAILTRAP_API_TOKEN", "")
        sender_email = os.getenv("MAILTRAP_SENDER_EMAIL", "reports@lawmetrics.ai")
        sender_name = os.getenv("MAILTRAP_SENDER_NAME", "LawMetrics.ai")

        if not api_token:
            print("[MAILTRAP] No API token configured, falling back to SMTP")
            return self.send_email_smtp(
                to_email=to_email, subject=subject,
                body_text=body_text, body_html=body_html,
                cc_email=cc_email, priority=priority,
            )

        recipient_str = to_email + (f", CC: {cc_email}" if cc_email else "")
        notification = Notification(
            title=subject,
            message=body_text,
            channel=NotificationChannel.EMAIL,
            priority=priority,
            recipient=recipient_str,
        )

        if self._dry_run:
            print(f"[MAILTRAP DRY-RUN] Would send to {to_email}:")
            if cc_email:
                print(f"  CC: {cc_email}")
            print(f"  Subject: {subject}")
            print(f"  Body: {body_text[:200]}...")
            self._log_notification(notification, True)
            return True

        try:
            import httpx

            payload = {
                "from": {"email": sender_email, "name": sender_name},
                "to": [{"email": to_email}],
                "subject": subject,
                "text": body_text,
            }

            if body_html:
                payload["html"] = body_html

            if cc_email:
                payload["cc"] = [{"email": cc_email}]

            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            }

            response = httpx.post(
                "https://send.api.mailtrap.io/api/send",
                json=payload,
                headers=headers,
                timeout=15,
            )

            success = response.status_code in (200, 201, 202)

            if success:
                result = response.json()
                notification.delivery_id = str(result.get("message_ids", [""])[0])

            notification.sent_at = datetime.now()
            self._log_notification(notification, success,
                                   None if success else f"HTTP {response.status_code}: {response.text[:200]}")

            cc_msg = f" (CC: {cc_email})" if cc_email else ""
            if success:
                print(f"[MAILTRAP] Email sent to {to_email}{cc_msg}")
            else:
                print(f"[MAILTRAP ERROR] HTTP {response.status_code}: {response.text[:200]}")

            return success

        except Exception as e:
            self._log_notification(notification, False, str(e))
            print(f"[MAILTRAP ERROR] {e}")
            return False

    # ========== SMS Integration (Twilio) ==========

    def send_sms(
        self,
        to_number: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> bool:
        """
        Send an SMS via Twilio.

        Args:
            to_number: Recipient phone number (E.164 format)
            message: SMS message (max 160 chars recommended)
            priority: Message priority

        Returns:
            True if sent successfully
        """
        sms_config = self._config.get("sms", {})
        account_sid = sms_config.get("account_sid")
        auth_token = sms_config.get("auth_token")
        from_number = sms_config.get("from_number")

        if not all([account_sid, auth_token, from_number]):
            print("[SMS] Twilio not fully configured")
            return False

        notification = Notification(
            title="SMS",
            message=message,
            channel=NotificationChannel.SMS,
            priority=priority,
            recipient=to_number,
        )

        if self._dry_run:
            print(f"[SMS DRY-RUN] Would send to {to_number}:")
            print(f"  Message: {message}")
            self._log_notification(notification, True)
            return True

        try:
            import httpx

            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

            data = {
                "From": from_number,
                "To": to_number,
                "Body": message,
            }

            response = httpx.post(
                url,
                data=data,
                auth=(account_sid, auth_token),
                timeout=10,
            )

            success = response.status_code in (200, 201)

            if success:
                result = response.json()
                notification.delivery_id = result.get("sid")

            notification.sent_at = datetime.now()
            self._log_notification(notification, success,
                                   None if success else f"HTTP {response.status_code}")

            return success

        except Exception as e:
            self._log_notification(notification, False, str(e))
            print(f"[SMS ERROR] {e}")
            return False

    # ========== Convenience Methods ==========

    def notify_critical(self, title: str, message: str, details: Dict = None) -> Dict:
        """
        Send critical alert to all configured channels.

        Returns dict of {channel: success} results.
        """
        results = {}

        # Always try Slack for critical alerts
        if "slack" in self._config.get("enabled_channels", []):
            results["slack"] = self.send_slack(
                message=message,
                title=f":rotating_light: {title}",
                color="danger",
                priority=NotificationPriority.CRITICAL,
            )

        # Send email to configured critical recipients
        routing = self._config.get("routing", {})
        if "email" in routing.get("critical_alerts", []):
            for recipient, prefs in self._config.get("recipients", {}).items():
                email = prefs.get("email")
                if email:
                    results[f"email:{recipient}"] = self.send_email(
                        to_email=email,
                        subject=f"[CRITICAL] {title}",
                        body_text=message,
                        priority=NotificationPriority.CRITICAL,
                    )

        return results

    def notify_staff(
        self,
        staff_name: str,
        title: str,
        message: str,
        channels: List[str] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> Dict:
        """
        Send notification to a specific staff member.

        Args:
            staff_name: Staff member key (melissa, ty, tiffany, etc.)
            title: Notification title
            message: Notification message
            channels: Override channels (default: all configured for staff)
            priority: Notification priority

        Returns:
            Dict of {channel: success} results
        """
        recipients = self._config.get("recipients", {})
        staff_prefs = recipients.get(staff_name.lower(), {})

        if not staff_prefs:
            print(f"[NOTIFY] No preferences found for {staff_name}")
            return {}

        channels = channels or self._config.get("enabled_channels", [])
        results = {}

        if "slack" in channels and staff_prefs.get("slack"):
            results["slack"] = self.send_slack(
                message=f"<{staff_prefs['slack']}> {message}",
                title=title,
                priority=priority,
            )

        if "email" in channels and staff_prefs.get("email"):
            results["email"] = self.send_email(
                to_email=staff_prefs["email"],
                subject=title,
                body_text=message,
                priority=priority,
            )

        if "sms" in channels and staff_prefs.get("sms"):
            # SMS only for high/critical priority
            if priority in (NotificationPriority.HIGH, NotificationPriority.CRITICAL):
                results["sms"] = self.send_sms(
                    to_number=staff_prefs["sms"],
                    message=f"{title}: {message[:100]}",
                    priority=priority,
                )

        return results

    def get_notification_log(self, limit: int = 100) -> List[Dict]:
        """Get recent notification log entries."""
        if not self.log_file.exists():
            return []

        with open(self.log_file) as f:
            try:
                logs = json.load(f)
                return logs[-limit:]
            except json.JSONDecodeError:
                return []

    def get_status(self) -> Dict:
        """Get notification system status."""
        enabled = self._config.get("enabled_channels", [])

        return {
            "dry_run": self._dry_run,
            "enabled_channels": enabled,
            "slack_configured": bool(self._config.get("slack", {}).get("webhook_url")),
            "email_configured": bool(self._config.get("email", {}).get("api_key")),
            "smtp_configured": bool(self._config.get("smtp", {}).get("username") and self._config.get("smtp", {}).get("password")),
            "sms_configured": bool(self._config.get("sms", {}).get("account_sid")),
            "recent_notifications": len(self.get_notification_log(100)),
        }


# Convenience function for quick Slack messages
def slack_alert(message: str, title: str = None, priority: str = "normal") -> bool:
    """Quick function to send a Slack alert."""
    manager = NotificationManager()
    priority_map = {
        "low": NotificationPriority.LOW,
        "normal": NotificationPriority.NORMAL,
        "high": NotificationPriority.HIGH,
        "critical": NotificationPriority.CRITICAL,
    }
    return manager.send_slack(
        message=message,
        title=title,
        priority=priority_map.get(priority, NotificationPriority.NORMAL),
    )


if __name__ == "__main__":
    # Test notifications
    manager = NotificationManager()

    print("Notification System Status:")
    status = manager.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")

    print("\nTesting Slack notification (dry-run)...")
    manager.send_slack(
        message="This is a test message from the MyCase automation system.",
        title="Test Alert",
        color="good",
    )

    print("\nTesting report notification...")
    manager.send_slack_report(
        report_type="daily_ar",
        summary={
            "total_ar": 1450000,
            "over_60_pct": 82.2,
            "compliance_rate": 7.6,
            "noiw_count": 14,
            "delinquent": 45,
        },
    )
