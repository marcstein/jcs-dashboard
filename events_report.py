"""
Upcoming Events Report

Generates and sends daily upcoming events report to managing partner/originating attorney.
"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from config import DATA_DIR
from cache import get_cache


def get_upcoming_events(days: int = 7) -> List[Dict]:
    """
    Get upcoming events from cache for the next N days.

    Returns list of events with staff names resolved.
    """
    cache = get_cache()

    # Get staff lookup
    staff_lookup = {}
    with cache._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM cached_staff")
        for row in cursor.fetchall():
            staff_lookup[row['id']] = row['name']

    # Get upcoming events
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    with cache._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                id, name, event_type, start_at, end_at, all_day,
                case_id, location, data_json
            FROM cached_events
            WHERE date(start_at) >= date(?)
            AND date(start_at) <= date(?)
            ORDER BY start_at ASC
        """, (today, end_date))

        events = []
        for row in cursor.fetchall():
            event = dict(row)
            # Parse data_json to get staff
            data = json.loads(event['data_json']) if event['data_json'] else {}
            staff_ids = [s.get('id') for s in data.get('staff', []) if s.get('id')]
            event['staff_names'] = [staff_lookup.get(sid, f"Unknown ({sid})") for sid in staff_ids]
            event['staff_ids'] = staff_ids
            events.append(event)

        return events


def group_events_by_staff(events: List[Dict]) -> Dict[str, List[Dict]]:
    """Group events by staff member."""
    by_staff = defaultdict(list)

    for event in events:
        for staff_name in event.get('staff_names', []):
            by_staff[staff_name].append(event)

    # Sort each staff's events by date
    for staff_name in by_staff:
        by_staff[staff_name].sort(key=lambda e: e.get('start_at', ''))

    return dict(by_staff)


def group_events_by_date(events: List[Dict]) -> Dict[str, List[Dict]]:
    """Group events by date."""
    by_date = defaultdict(list)

    for event in events:
        start = event.get('start_at', '')
        if start:
            date_str = start[:10]  # YYYY-MM-DD
            by_date[date_str].append(event)

    return dict(sorted(by_date.items()))


def format_time(iso_str: str, all_day: bool = False) -> str:
    """Format ISO timestamp to readable time."""
    if not iso_str or all_day:
        return "All Day"
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime("%I:%M %p").lstrip('0')
    except:
        return iso_str


def format_date(iso_str: str) -> str:
    """Format ISO date to readable format."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime("%A, %B %d, %Y")
    except:
        return iso_str[:10]


def format_short_date(iso_str: str) -> str:
    """Format ISO date to short format."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime("%a %m/%d")
    except:
        return iso_str[:10]


def generate_events_report_text(days: int = 7) -> Tuple[str, Dict]:
    """
    Generate plain text upcoming events report.

    Returns (text_content, summary_dict)
    """
    events = get_upcoming_events(days)
    by_date = group_events_by_date(events)
    by_staff = group_events_by_staff(events)

    lines = []
    lines.append("=" * 60)
    lines.append(f"UPCOMING EVENTS REPORT - {datetime.now().strftime('%A, %B %d, %Y')}")
    lines.append(f"Next {days} Days")
    lines.append("=" * 60)
    lines.append("")

    # Summary
    total_events = len(events)
    event_types = defaultdict(int)
    for e in events:
        event_types[e.get('event_type') or 'Other'] += 1

    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"Total Events: {total_events}")
    lines.append("")
    lines.append("By Type:")
    for etype, count in sorted(event_types.items(), key=lambda x: -x[1]):
        lines.append(f"  {etype}: {count}")
    lines.append("")
    lines.append("By Staff Member:")
    for staff, staff_events in sorted(by_staff.items(), key=lambda x: -len(x[1])):
        lines.append(f"  {staff}: {len(staff_events)} events")
    lines.append("")

    # Events by date
    lines.append("=" * 60)
    lines.append("EVENTS BY DATE")
    lines.append("=" * 60)

    for date_str, date_events in by_date.items():
        lines.append("")
        lines.append(f"--- {format_date(date_str)} ({len(date_events)} events) ---")
        lines.append("")

        for event in date_events:
            time_str = format_time(event.get('start_at'), event.get('all_day'))
            event_type = event.get('event_type') or 'Event'
            name = event.get('name', 'Unnamed')
            staff = ', '.join(event.get('staff_names', []))

            lines.append(f"  {time_str:12} [{event_type}]")
            lines.append(f"               {name[:60]}")
            if staff:
                lines.append(f"               Staff: {staff[:50]}")
            lines.append("")

    summary = {
        'total_events': total_events,
        'event_types': dict(event_types),
        'staff_counts': {k: len(v) for k, v in by_staff.items()},
        'days': days,
    }

    return '\n'.join(lines), summary


def generate_events_report_html(days: int = 7) -> Tuple[str, Dict]:
    """
    Generate HTML upcoming events report.

    Returns (html_content, summary_dict)
    """
    events = get_upcoming_events(days)
    by_date = group_events_by_date(events)
    by_staff = group_events_by_staff(events)

    # Summary stats
    total_events = len(events)
    event_types = defaultdict(int)
    for e in events:
        event_types[e.get('event_type') or 'Other'] += 1

    summary = {
        'total_events': total_events,
        'event_types': dict(event_types),
        'staff_counts': {k: len(v) for k, v in by_staff.items()},
        'days': days,
    }

    # Build HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1a365d; border-bottom: 3px solid #2b6cb0; padding-bottom: 10px; }}
        h2 {{ color: #2b6cb0; margin-top: 30px; }}
        h3 {{ color: #4a5568; margin-top: 20px; background: #edf2f7; padding: 8px 12px; border-radius: 4px; }}
        .summary {{ background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin: 20px 0; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }}
        .stat-box {{ background: white; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; text-align: center; }}
        .stat-number {{ font-size: 28px; font-weight: bold; color: #2b6cb0; }}
        .stat-label {{ font-size: 12px; color: #718096; text-transform: uppercase; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th {{ background: #edf2f7; text-align: left; padding: 8px 12px; font-size: 12px; text-transform: uppercase; color: #4a5568; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #e2e8f0; }}
        tr:hover {{ background: #f7fafc; }}
        .event-type {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }}
        .event-type-court {{ background: #fed7d7; color: #c53030; }}
        .event-type-meeting {{ background: #c6f6d5; color: #276749; }}
        .event-type-deadline {{ background: #feebc8; color: #c05621; }}
        .event-type-dor {{ background: #bee3f8; color: #2b6cb0; }}
        .event-type-trial {{ background: #e9d8fd; color: #6b46c1; }}
        .event-type-other {{ background: #e2e8f0; color: #4a5568; }}
        .staff-list {{ font-size: 12px; color: #718096; }}
        .time {{ font-weight: 500; white-space: nowrap; }}
        .date-header {{ background: #2b6cb0; color: white; padding: 10px 15px; margin-top: 25px; border-radius: 6px 6px 0 0; }}
        .date-count {{ float: right; background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 10px; font-size: 12px; }}
        footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #718096; text-align: center; }}
    </style>
</head>
<body>
    <h1>Upcoming Events Report</h1>
    <p style="color: #718096;">Generated: {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}</p>

    <div class="summary">
        <div class="summary-grid">
            <div class="stat-box">
                <div class="stat-number">{total_events}</div>
                <div class="stat-label">Total Events</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{days}</div>
                <div class="stat-label">Days Ahead</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{len(by_date)}</div>
                <div class="stat-label">Days with Events</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{len(by_staff)}</div>
                <div class="stat-label">Staff Members</div>
            </div>
        </div>
    </div>

    <h2>Events by Type</h2>
    <table>
        <tr><th>Event Type</th><th>Count</th></tr>
"""

    for etype, count in sorted(event_types.items(), key=lambda x: -x[1]):
        html += f"        <tr><td>{etype}</td><td>{count}</td></tr>\n"

    html += """    </table>

    <h2>Staff Workload</h2>
    <table>
        <tr><th>Staff Member</th><th>Events</th></tr>
"""

    for staff, staff_events in sorted(by_staff.items(), key=lambda x: -len(x[1])):
        html += f"        <tr><td>{staff}</td><td>{len(staff_events)}</td></tr>\n"

    html += """    </table>

    <h2>Events by Date</h2>
"""

    def get_event_type_class(event_type: str) -> str:
        if not event_type:
            return "event-type-other"
        et_lower = event_type.lower()
        if 'court' in et_lower:
            return "event-type-court"
        elif 'meeting' in et_lower or 'phone' in et_lower:
            return "event-type-meeting"
        elif 'deadline' in et_lower or 'filing' in et_lower or 'to do' in et_lower:
            return "event-type-deadline"
        elif 'dor' in et_lower:
            return "event-type-dor"
        elif 'trial' in et_lower:
            return "event-type-trial"
        else:
            return "event-type-other"

    for date_str, date_events in by_date.items():
        formatted_date = format_date(date_str)
        html += f"""
    <div class="date-header">{formatted_date} <span class="date-count">{len(date_events)} events</span></div>
    <table>
        <tr><th style="width:80px;">Time</th><th style="width:120px;">Type</th><th>Event</th><th>Staff</th></tr>
"""
        for event in date_events:
            time_str = format_time(event.get('start_at'), event.get('all_day'))
            event_type = event.get('event_type') or 'Event'
            type_class = get_event_type_class(event_type)
            name = event.get('name', 'Unnamed')
            # Truncate long names
            if len(name) > 70:
                name = name[:67] + "..."
            staff = ', '.join(event.get('staff_names', []))
            if len(staff) > 40:
                staff = staff[:37] + "..."

            html += f"""        <tr>
            <td class="time">{time_str}</td>
            <td><span class="event-type {type_class}">{event_type[:20]}</span></td>
            <td>{name}</td>
            <td class="staff-list">{staff}</td>
        </tr>
"""
        html += "    </table>\n"

    html += """
    <footer>
        JCS Law Firm - MyCase Automation System<br>
        This report was automatically generated.
    </footer>
</body>
</html>
"""

    return html, summary


def send_events_report(
    to_email: str,
    days: int = 7,
    cc_email: str = None,
    dry_run: bool = False
) -> bool:
    """
    Generate and send the upcoming events report via SMTP.

    Args:
        to_email: Recipient email address
        days: Number of days to include in report
        cc_email: Optional CC email address
        dry_run: If True, don't actually send the email

    Returns:
        True if sent successfully
    """
    from notifications import NotificationManager

    # Generate report
    text_content, summary = generate_events_report_text(days)
    html_content, _ = generate_events_report_html(days)

    subject = f"JCS Law Firm - Upcoming Events Report ({datetime.now().strftime('%m/%d/%Y')})"

    print(f"Generated events report: {summary['total_events']} events over {days} days")

    # Get notification manager
    manager = NotificationManager()

    # Override dry_run setting if specified
    if dry_run:
        manager._dry_run = True

    # Send via SMTP
    return manager.send_email_smtp(
        to_email=to_email,
        subject=subject,
        body_text=text_content,
        body_html=html_content,
        cc_email=cc_email,
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        # Preview HTML report
        html, summary = generate_events_report_html(7)
        output_file = DATA_DIR / "events_report_preview.html"
        with open(output_file, 'w') as f:
            f.write(html)
        print(f"Preview saved to: {output_file}")
        print(f"Summary: {summary}")
    else:
        # Print text report
        text, summary = generate_events_report_text(7)
        print(text)
        print(f"\nSummary: {summary}")
