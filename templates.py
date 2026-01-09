"""
Template Management System

Manages notice templates for client and attorney communications.
Uses Jinja2 for template rendering with MyCase data.
"""
import json
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape, Template

from config import TEMPLATES_DIR


class TemplateManager:
    """
    Manages notice templates stored locally.

    Templates are stored as .txt or .html files in the templates directory.
    Template metadata is stored in templates.json.
    """

    def __init__(self, templates_dir: Path = TEMPLATES_DIR):
        self.templates_dir = templates_dir
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = templates_dir / "templates.json"
        self._init_metadata()
        self._init_jinja_env()

    def _init_metadata(self):
        """Initialize or load templates metadata."""
        if not self.metadata_file.exists():
            self._save_metadata({})

    def _load_metadata(self) -> Dict:
        """Load templates metadata from JSON file."""
        with open(self.metadata_file, "r") as f:
            return json.load(f)

    def _save_metadata(self, metadata: Dict):
        """Save templates metadata to JSON file."""
        with open(self.metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

    def _init_jinja_env(self):
        """Initialize Jinja2 environment."""
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Add custom filters
        self.env.filters["currency"] = lambda x: f"${x:,.2f}" if x else "$0.00"
        self.env.filters["date"] = lambda x: x.strftime("%B %d, %Y") if x else ""
        self.env.filters["short_date"] = lambda x: x.strftime("%m/%d/%Y") if x else ""

    def create_template(
        self,
        name: str,
        content: str,
        template_type: str,
        description: str = "",
        variables: List[str] = None,
    ) -> dict:
        """
        Create a new template.

        Args:
            name: Template name (used as filename without extension)
            content: Template content with Jinja2 variables
            template_type: Type of template (client_notice, attorney_notice, dunning, etc.)
            description: Human-readable description
            variables: List of expected template variables

        Returns:
            Template metadata dict
        """
        filename = f"{name}.txt"
        filepath = self.templates_dir / filename

        # Save template content
        with open(filepath, "w") as f:
            f.write(content)

        # Update metadata
        metadata = self._load_metadata()
        metadata[name] = {
            "filename": filename,
            "type": template_type,
            "description": description,
            "variables": variables or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._save_metadata(metadata)

        return metadata[name]

    def get_template(self, name: str) -> Optional[Template]:
        """Get a template by name."""
        metadata = self._load_metadata()
        if name not in metadata:
            return None

        try:
            return self.env.get_template(metadata[name]["filename"])
        except Exception:
            return None

    def render_template(self, name: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Render a template with the given context.

        Args:
            name: Template name
            context: Dictionary of variables to render

        Returns:
            Rendered template string or None if template not found
        """
        template = self.get_template(name)
        if not template:
            return None

        # Add common context variables
        context.setdefault("today", datetime.now())
        context.setdefault("firm_name", "")

        return template.render(**context)

    def list_templates(self, template_type: str = None) -> List[dict]:
        """
        List all templates, optionally filtered by type.

        Args:
            template_type: Filter by template type

        Returns:
            List of template metadata dicts
        """
        metadata = self._load_metadata()
        templates = []

        for name, data in metadata.items():
            if template_type is None or data.get("type") == template_type:
                templates.append({"name": name, **data})

        return templates

    def delete_template(self, name: str) -> bool:
        """Delete a template."""
        metadata = self._load_metadata()
        if name not in metadata:
            return False

        # Delete file
        filepath = self.templates_dir / metadata[name]["filename"]
        if filepath.exists():
            filepath.unlink()

        # Update metadata
        del metadata[name]
        self._save_metadata(metadata)

        return True

    def update_template(self, name: str, content: str = None, **kwargs) -> Optional[dict]:
        """
        Update an existing template.

        Args:
            name: Template name
            content: New template content (optional)
            **kwargs: Other metadata fields to update

        Returns:
            Updated template metadata or None if not found
        """
        metadata = self._load_metadata()
        if name not in metadata:
            return None

        # Update content if provided
        if content is not None:
            filepath = self.templates_dir / metadata[name]["filename"]
            with open(filepath, "w") as f:
                f.write(content)

        # Update metadata
        for key, value in kwargs.items():
            if key in ["type", "description", "variables"]:
                metadata[name][key] = value

        metadata[name]["updated_at"] = datetime.now().isoformat()
        self._save_metadata(metadata)

        return metadata[name]


def create_default_templates():
    """Create default notice templates."""
    manager = TemplateManager()

    # Dunning notice templates
    dunning_templates = [
        {
            "name": "dunning_15_day",
            "type": "dunning",
            "description": "First reminder - 15 days past due",
            "content": """Dear {{ client_name }},

This is a friendly reminder that Invoice #{{ invoice_number }} dated {{ invoice_date | date }}
for {{ invoice_amount | currency }} is now 15 days past due.

Case: {{ case_name }}
Original Due Date: {{ due_date | date }}
Amount Due: {{ balance_due | currency }}

Please remit payment at your earliest convenience. If you have already sent payment,
please disregard this notice.

If you have any questions about this invoice, please don't hesitate to contact our office.

Sincerely,
{{ firm_name }}
{{ firm_phone }}
""",
            "variables": ["client_name", "invoice_number", "invoice_date", "invoice_amount",
                         "case_name", "due_date", "balance_due", "firm_name", "firm_phone"],
        },
        {
            "name": "dunning_30_day",
            "type": "dunning",
            "description": "Second reminder - 30 days past due",
            "content": """Dear {{ client_name }},

Our records indicate that Invoice #{{ invoice_number }} for {{ invoice_amount | currency }}
is now 30 days past due.

Case: {{ case_name }}
Original Due Date: {{ due_date | date }}
Current Balance Due: {{ balance_due | currency }}

We kindly request that you submit payment within the next 7 days to avoid any
further collection activity.

If you are experiencing financial difficulties, please contact our office to discuss
payment arrangements.

Sincerely,
{{ firm_name }}
{{ firm_phone }}
""",
            "variables": ["client_name", "invoice_number", "invoice_amount",
                         "case_name", "due_date", "balance_due", "firm_name", "firm_phone"],
        },
        {
            "name": "dunning_60_day",
            "type": "dunning",
            "description": "Third reminder - 60 days past due",
            "content": """URGENT: Payment Required

Dear {{ client_name }},

This is a formal notice that Invoice #{{ invoice_number }} remains unpaid and is now
60 days past due.

Case: {{ case_name }}
Original Invoice Amount: {{ invoice_amount | currency }}
Current Balance Due: {{ balance_due | currency }}
Days Past Due: 60

Immediate payment is required to avoid further collection action. Please remit
payment within 10 days of this notice.

If you wish to discuss payment options, please contact our office immediately.

{{ firm_name }}
{{ firm_phone }}
{{ firm_email }}
""",
            "variables": ["client_name", "invoice_number", "case_name",
                         "invoice_amount", "balance_due", "firm_name", "firm_phone", "firm_email"],
        },
        {
            "name": "dunning_90_day",
            "type": "dunning",
            "description": "Final notice - 90 days past due",
            "content": """FINAL NOTICE - IMMEDIATE ACTION REQUIRED

Dear {{ client_name }},

Despite our previous communications, Invoice #{{ invoice_number }} remains unpaid
and is now 90 days past due.

Case: {{ case_name }}
Total Amount Due: {{ balance_due | currency }}

This is our final notice before we pursue additional collection measures, which may
include referral to a collection agency and potential legal action.

To avoid these actions, please submit full payment within 5 business days of this notice,
or contact our office immediately to make payment arrangements.

{{ firm_name }}
{{ firm_phone }}
{{ firm_email }}
""",
            "variables": ["client_name", "invoice_number", "case_name",
                         "balance_due", "firm_name", "firm_phone", "firm_email"],
        },
    ]

    # Attorney deadline notice template
    attorney_templates = [
        {
            "name": "attorney_deadline_reminder",
            "type": "attorney_notice",
            "description": "Reminder to attorney about upcoming case deadline",
            "content": """CASE DEADLINE REMINDER

Attorney: {{ attorney_name }}
Case: {{ case_name }} ({{ case_number }})
Client: {{ client_name }}

Upcoming Deadline: {{ deadline_name }}
Date: {{ deadline_date | date }}
Days Until Due: {{ days_until_due }}

{% if deadline_description %}
Details: {{ deadline_description }}
{% endif %}

{% if related_tasks %}
Related Tasks:
{% for task in related_tasks %}
  - {{ task.name }} ({{ task.status }})
{% endfor %}
{% endif %}

This is an automated reminder from the MyCase automation system.
""",
            "variables": ["attorney_name", "case_name", "case_number", "client_name",
                         "deadline_name", "deadline_date", "days_until_due",
                         "deadline_description", "related_tasks"],
        },
        {
            "name": "attorney_overdue_alert",
            "type": "attorney_notice",
            "description": "Alert for overdue tasks or missed deadlines",
            "content": """OVERDUE ALERT

Attorney: {{ attorney_name }}

The following items are OVERDUE and require immediate attention:

{% for item in overdue_items %}
Case: {{ item.case_name }}
Item: {{ item.name }}
Due Date: {{ item.due_date | date }}
Days Overdue: {{ item.days_overdue }}
---
{% endfor %}

Please update the status of these items as soon as possible.

This is an automated alert from the MyCase automation system.
""",
            "variables": ["attorney_name", "overdue_items"],
        },
    ]

    # Client notice templates
    client_templates = [
        {
            "name": "client_case_update",
            "type": "client_notice",
            "description": "General case status update for client",
            "content": """Dear {{ client_name }},

We wanted to provide you with an update on your case.

Case: {{ case_name }}
Case Number: {{ case_number }}
Status: {{ case_status }}

{{ update_message }}

{% if next_steps %}
Next Steps:
{% for step in next_steps %}
  - {{ step }}
{% endfor %}
{% endif %}

{% if upcoming_dates %}
Important Upcoming Dates:
{% for date_item in upcoming_dates %}
  - {{ date_item.name }}: {{ date_item.date | date }}
{% endfor %}
{% endif %}

If you have any questions, please don't hesitate to contact our office.

Sincerely,
{{ attorney_name }}
{{ firm_name }}
{{ firm_phone }}
""",
            "variables": ["client_name", "case_name", "case_number", "case_status",
                         "update_message", "next_steps", "upcoming_dates",
                         "attorney_name", "firm_name", "firm_phone"],
        },
    ]

    # Create all templates
    all_templates = dunning_templates + attorney_templates + client_templates

    for template in all_templates:
        existing = manager.get_template(template["name"])
        if not existing:
            manager.create_template(
                name=template["name"],
                content=template["content"],
                template_type=template["type"],
                description=template["description"],
                variables=template["variables"],
            )
            print(f"Created template: {template['name']}")
        else:
            print(f"Template already exists: {template['name']}")

    return manager


if __name__ == "__main__":
    # Create default templates
    manager = create_default_templates()

    # List all templates
    print("\n=== All Templates ===")
    for template in manager.list_templates():
        print(f"  - {template['name']} ({template['type']}): {template['description']}")

    # Test rendering
    print("\n=== Test Render ===")
    rendered = manager.render_template("dunning_15_day", {
        "client_name": "John Smith",
        "invoice_number": "INV-2024-001",
        "invoice_date": datetime.now(),
        "invoice_amount": 1500.00,
        "case_name": "Smith v. Jones",
        "due_date": datetime.now(),
        "balance_due": 1500.00,
        "firm_name": "Acme Law Firm",
        "firm_phone": "(555) 123-4567",
    })
    print(rendered)
