"""
Upcoming Events Report

Generates and sends daily upcoming events report to managing partner/originating attorney.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from zoneinfo import ZoneInfo

# Firm timezone - St. Louis, MO
FIRM_TZ = ZoneInfo("America/Chicago")

from config import DATA_DIR

# Use multi-tenant cache when available (Celery tasks set tenant context).
# Falls back to single-tenant cache for standalone/local usage.
try:
    from cache_mt import get_cache
except ImportError:
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
        cursor.execute("SELECT id, name FROM cached_staff WHERE firm_id = %s", (cache.firm_id,))
        for row in cursor.fetchall():
            staff_lookup[row['id']] = row['name']

    # Use Central Time for date boundaries.
    # Events are stored in UTC, so widen the SQL window by 1 day on each
    # side to capture events near the midnight boundary, then filter
    # precisely after fetching using _event_local_date().
    now_central = datetime.now(FIRM_TZ)
    today_central = now_central.strftime("%Y-%m-%d")
    end_central = (now_central + timedelta(days=days)).strftime("%Y-%m-%d")

    query_start = (now_central - timedelta(days=1)).strftime("%Y-%m-%d")
    query_end = (now_central + timedelta(days=days + 1)).strftime("%Y-%m-%d")

    with cache._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                id, name, event_type, start_at, end_at, all_day,
                case_id, location, data_json
            FROM cached_events
            WHERE firm_id = %s
            AND start_at::text::date >= %s::date
            AND start_at::text::date <= %s::date
            ORDER BY start_at ASC
        """, (cache.firm_id, query_start, query_end))

        events = []
        for row in cursor.fetchall():
            event = dict(row)

            # Filter precisely by Central Time date
            start_at = event.get('start_at', '')
            if start_at:
                local_date = _event_local_date(start_at)
                if local_date < today_central or local_date > end_central:
                    continue  # Outside the actual Central Time window

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
    """Group events by date in Central Time."""
    by_date = defaultdict(list)

    for event in events:
        start = event.get('start_at', '')
        if start:
            date_str = _event_local_date(start)
            by_date[date_str].append(event)

    return dict(sorted(by_date.items()))


def _to_central(iso_str: str) -> datetime:
    """Parse an ISO timestamp and convert to Central Time.

    All-day events from MyCase store just a date (e.g. '2026-02-16')
    with no time or timezone. These represent a literal calendar date,
    not a UTC point-in-time, so we treat them as-is in the firm's
    local timezone rather than converting from UTC.
    """
    # Bare date (no 'T') — treat as midnight in firm timezone, not UTC
    if 'T' not in iso_str and len(iso_str) == 10:
        dt = datetime.strptime(iso_str, '%Y-%m-%d')
        return dt.replace(tzinfo=FIRM_TZ)

    dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    # If naive (no timezone), assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(FIRM_TZ)


def format_time(iso_str: str, all_day: bool = False) -> str:
    """Format ISO timestamp to readable Central Time."""
    if not iso_str or all_day:
        return "All Day"
    try:
        dt = _to_central(iso_str)
        return dt.strftime("%I:%M %p").lstrip('0')
    except:
        return iso_str


def format_date(iso_str: str) -> str:
    """Format ISO date to readable format in Central Time."""
    if not iso_str:
        return ""
    try:
        dt = _to_central(iso_str)
        return dt.strftime("%A, %B %d, %Y")
    except:
        return iso_str[:10]


def format_short_date(iso_str: str) -> str:
    """Format ISO date to short format in Central Time."""
    if not iso_str:
        return ""
    try:
        dt = _to_central(iso_str)
        return dt.strftime("%a %m/%d")
    except:
        return iso_str[:10]


def _event_local_date(iso_str: str) -> str:
    """Extract the YYYY-MM-DD date of an event in Central Time."""
    try:
        dt = _to_central(iso_str)
        return dt.strftime("%Y-%m-%d")
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


def get_staff_email_lookup() -> Dict[str, str]:
    """Get staff name -> email mapping from cache."""
    cache = get_cache()
    lookup = {}
    with cache._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, email FROM cached_staff WHERE firm_id = %s AND email IS NOT NULL AND email != ''", (cache.firm_id,))
        for row in cursor.fetchall():
            lookup[row['name']] = row['email']
    return lookup


def get_active_staff() -> List[Dict]:
    """Get all active staff members from cache."""
    cache = get_cache()
    with cache._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, email
            FROM cached_staff
            WHERE firm_id = %s
            AND active = TRUE
            AND name != 'Firm Calendar'
            ORDER BY name
        """, (cache.firm_id,))
        return [dict(row) for row in cursor.fetchall()]


def generate_individual_report_text(
    staff_name: str,
    events: List[Dict],
    days: int = 7,
) -> str:
    """
    Generate a plain text events report for a single staff member.

    Args:
        staff_name: Name of the staff member
        events: List of event dicts already filtered to this person
        days: Number of days the report covers

    Returns:
        Formatted text report
    """
    by_date = defaultdict(list)
    for event in events:
        start = event.get('start_at', '')
        if start:
            by_date[_event_local_date(start)].append(event)
    by_date = dict(sorted(by_date.items()))

    lines = []
    lines.append("=" * 60)
    lines.append(f"DAILY EVENTS REPORT - {staff_name}")
    lines.append(f"{datetime.now().strftime('%A, %B %d, %Y')}")
    lines.append(f"Next {days} Days")
    lines.append("=" * 60)
    lines.append("")

    lines.append(f"You have {len(events)} upcoming event(s).")
    lines.append("")

    # Event type breakdown
    event_types = defaultdict(int)
    for e in events:
        event_types[e.get('event_type') or 'Other'] += 1
    if event_types:
        lines.append("By Type:")
        for etype, count in sorted(event_types.items(), key=lambda x: -x[1]):
            lines.append(f"  {etype}: {count}")
        lines.append("")

    # Events by date
    for date_str, date_events in by_date.items():
        lines.append(f"--- {format_date(date_str)} ({len(date_events)} events) ---")
        lines.append("")

        for event in date_events:
            time_str = format_time(event.get('start_at'), event.get('all_day'))
            event_type = event.get('event_type') or 'Event'
            name = event.get('name', 'Unnamed')
            location = event.get('location') or ''
            # Show other staff on this event (excluding this person)
            other_staff = [s for s in event.get('staff_names', []) if s != staff_name]

            lines.append(f"  {time_str:12} [{event_type}]")
            lines.append(f"               {name[:60]}")
            if location:
                lines.append(f"               Location: {location[:50]}")
            if other_staff:
                lines.append(f"               Also attending: {', '.join(other_staff[:3])}")
            lines.append("")

    if not events:
        lines.append("No upcoming events scheduled.")

    lines.append("-" * 60)
    lines.append("JCS Law Firm - MyCase Automation System")

    return '\n'.join(lines)


def generate_individual_report_html(
    staff_name: str,
    events: List[Dict],
    days: int = 7,
) -> str:
    """
    Generate an HTML events report for a single staff member.

    Args:
        staff_name: Name of the staff member
        events: List of event dicts already filtered to this person
        days: Number of days the report covers

    Returns:
        HTML report string
    """
    by_date = defaultdict(list)
    for event in events:
        start = event.get('start_at', '')
        if start:
            by_date[_event_local_date(start)].append(event)
    by_date = dict(sorted(by_date.items()))

    # Event type counts
    event_types = defaultdict(int)
    for e in events:
        event_types[e.get('event_type') or 'Other'] += 1

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

    # Today/tomorrow highlighting (Central Time)
    now_ct = datetime.now(FIRM_TZ)
    today_str = now_ct.strftime("%Y-%m-%d")
    tomorrow_str = (now_ct + timedelta(days=1)).strftime("%Y-%m-%d")

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #333; max-width: 700px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1a365d; border-bottom: 3px solid #2b6cb0; padding-bottom: 10px; font-size: 22px; }}
        .subtitle {{ color: #718096; margin-top: -10px; font-size: 14px; }}
        .summary {{ background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin: 15px 0; }}
        .stat-row {{ display: flex; gap: 20px; flex-wrap: wrap; }}
        .stat-item {{ text-align: center; min-width: 80px; }}
        .stat-number {{ font-size: 24px; font-weight: bold; color: #2b6cb0; }}
        .stat-label {{ font-size: 11px; color: #718096; text-transform: uppercase; }}
        table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
        th {{ background: #edf2f7; text-align: left; padding: 6px 10px; font-size: 11px; text-transform: uppercase; color: #4a5568; }}
        td {{ padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }}
        tr:hover {{ background: #f7fafc; }}
        .event-type {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }}
        .event-type-court {{ background: #fed7d7; color: #c53030; }}
        .event-type-meeting {{ background: #c6f6d5; color: #276749; }}
        .event-type-deadline {{ background: #feebc8; color: #c05621; }}
        .event-type-dor {{ background: #bee3f8; color: #2b6cb0; }}
        .event-type-trial {{ background: #e9d8fd; color: #6b46c1; }}
        .event-type-other {{ background: #e2e8f0; color: #4a5568; }}
        .time {{ font-weight: 500; white-space: nowrap; }}
        .date-header {{ padding: 8px 12px; margin-top: 20px; border-radius: 6px 6px 0 0; font-weight: 600; font-size: 14px; }}
        .date-today {{ background: #2b6cb0; color: white; }}
        .date-tomorrow {{ background: #4299e1; color: white; }}
        .date-future {{ background: #718096; color: white; }}
        .date-count {{ float: right; background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: normal; }}
        .other-staff {{ font-size: 11px; color: #718096; font-style: italic; }}
        .location {{ font-size: 11px; color: #718096; }}
        footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #a0aec0; text-align: center; }}
    </style>
</head>
<body>
    <h1>Your Upcoming Events</h1>
    <p class="subtitle">Report for <strong>{staff_name}</strong> &mdash; {datetime.now().strftime('%A, %B %d, %Y')}</p>

    <div class="summary">
        <div class="stat-row">
            <div class="stat-item">
                <div class="stat-number">{len(events)}</div>
                <div class="stat-label">Events</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{len(by_date)}</div>
                <div class="stat-label">Days</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{event_types.get('Court Date', 0) + event_types.get('Court Appearance', 0)}</div>
                <div class="stat-label">Court</div>
            </div>
        </div>
    </div>
"""

    # Events by date
    for date_str, date_events in by_date.items():
        formatted_date = format_date(date_str)
        if date_str == today_str:
            date_class = "date-today"
            label = f"TODAY &mdash; {formatted_date}"
        elif date_str == tomorrow_str:
            date_class = "date-tomorrow"
            label = f"TOMORROW &mdash; {formatted_date}"
        else:
            date_class = "date-future"
            label = formatted_date

        html += f"""
    <div class="date-header {date_class}">{label} <span class="date-count">{len(date_events)} events</span></div>
    <table>
        <tr><th style="width:75px;">Time</th><th style="width:100px;">Type</th><th>Event</th></tr>
"""
        for event in date_events:
            time_str = format_time(event.get('start_at'), event.get('all_day'))
            event_type = event.get('event_type') or 'Event'
            type_class = get_event_type_class(event_type)
            name = event.get('name', 'Unnamed')
            if len(name) > 65:
                name = name[:62] + "..."
            location = event.get('location') or ''
            other_staff = [s for s in event.get('staff_names', []) if s != staff_name]

            extra = ""
            if location:
                extra += f'<br><span class="location">📍 {location[:45]}</span>'
            if other_staff:
                extra += f'<br><span class="other-staff">With: {", ".join(other_staff[:3])}</span>'

            html += f"""        <tr>
            <td class="time">{time_str}</td>
            <td><span class="event-type {type_class}">{event_type[:20]}</span></td>
            <td>{name}{extra}</td>
        </tr>
"""
        html += "    </table>\n"

    if not events:
        html += """    <p style="text-align:center; color:#718096; padding:30px;">No upcoming events scheduled.</p>\n"""

    html += """
    <footer>
        JCS Law Firm &mdash; MyCase Automation System<br>
        This report was automatically generated.
    </footer>
</body>
</html>
"""

    return html


def generate_all_individual_reports(
    days: int = 7,
    output_dir: Optional[str] = None,
    active_only: bool = True,
) -> Dict[str, Dict]:
    """
    Generate individual event reports for all staff members.

    Starts from the active staff roster so everyone gets a report,
    even if they have zero events in the window.

    Args:
        days: Number of days to include
        output_dir: Optional directory to save HTML files
        active_only: If True, only include active staff (default)

    Returns:
        Dict of staff_name -> {text, html, event_count, email}
    """
    events = get_upcoming_events(days)
    by_staff = group_events_by_staff(events)

    # Start from the full active staff roster
    staff_roster = get_active_staff()

    reports = {}

    for staff in staff_roster:
        staff_name = staff['name']
        staff_events = by_staff.get(staff_name, [])

        text = generate_individual_report_text(staff_name, staff_events, days)
        html = generate_individual_report_html(staff_name, staff_events, days)

        reports[staff_name] = {
            'text': text,
            'html': html,
            'event_count': len(staff_events),
            'email': staff.get('email'),
        }

        # Optionally save HTML to disk
        if output_dir:
            from pathlib import Path
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            safe_name = staff_name.replace(' ', '_').replace('/', '_')
            filepath = out_path / f"events_{safe_name}.html"
            with open(filepath, 'w') as f:
                f.write(html)

    return reports


def send_individual_events_reports(
    days: int = 7,
    staff_filter: Optional[List[str]] = None,
    cc_email: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, bool]:
    """
    Generate and send individual events reports to each staff member.

    Args:
        days: Number of days to include
        staff_filter: Optional list of staff names to limit sending to
        cc_email: Optional CC address (e.g., managing partner)
        dry_run: If True, don't actually send emails

    Returns:
        Dict of staff_name -> send_success
    """
    from notifications import NotificationManager

    reports = generate_all_individual_reports(days)
    manager = NotificationManager()
    if dry_run:
        manager._dry_run = True

    results = {}
    date_str = datetime.now().strftime('%m/%d/%Y')

    for staff_name, report_data in reports.items():
        # Skip if filtered
        if staff_filter and staff_name not in staff_filter:
            continue

        email = report_data.get('email')
        if not email:
            print(f"[SKIP] {staff_name}: no email address on file")
            results[staff_name] = False
            continue

        if report_data['event_count'] == 0:
            print(f"[SKIP] {staff_name}: no upcoming events")
            results[staff_name] = True  # Not a failure
            continue

        subject = f"Your Upcoming Events ({date_str}) - {report_data['event_count']} events"

        success = manager.send_email_smtp(
            to_email=email,
            subject=subject,
            body_text=report_data['text'],
            body_html=report_data['html'],
            cc_email=cc_email,
        )

        results[staff_name] = success
        status = "✓" if success else "✗"
        print(f"[{status}] {staff_name} ({email}): {report_data['event_count']} events")

    return results


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

    usage = """
Usage:
  python events_report.py                    # Print firm-wide text report
  python events_report.py preview            # Save firm-wide HTML preview
  python events_report.py individual         # Generate & print individual reports
  python events_report.py individual-preview # Save individual HTML files
  python events_report.py send-individual    # Send individual reports via email (dry-run)
  python events_report.py send-individual --live  # Actually send emails
"""

    cmd = sys.argv[1] if len(sys.argv) > 1 else None

    if cmd == "preview":
        # Preview firm-wide HTML report
        html, summary = generate_events_report_html(7)
        output_file = DATA_DIR / "events_report_preview.html"
        with open(output_file, 'w') as f:
            f.write(html)
        print(f"Preview saved to: {output_file}")
        print(f"Summary: {summary}")

    elif cmd == "individual":
        # Print individual text reports
        reports = generate_all_individual_reports(7)
        for staff_name, data in reports.items():
            print(data['text'])
            print(f"  [Email: {data.get('email') or 'NOT ON FILE'}]")
            print()

    elif cmd == "individual-preview":
        # Save individual HTML reports
        from pathlib import Path
        out_dir = Path(DATA_DIR) / "individual_events"
        reports = generate_all_individual_reports(7, output_dir=str(out_dir))
        print(f"Generated {len(reports)} individual reports in: {out_dir}")
        for staff_name, data in reports.items():
            email_str = data.get('email') or 'no email'
            print(f"  {staff_name}: {data['event_count']} events ({email_str})")

    elif cmd == "send-individual":
        # Send individual reports via email
        live = "--live" in sys.argv
        dry_run = not live
        if dry_run:
            print("DRY RUN - no emails will actually be sent. Add --live to send.")
        results = send_individual_events_reports(days=7, dry_run=dry_run)
        sent = sum(1 for v in results.values() if v)
        print(f"\nResults: {sent}/{len(results)} sent successfully")

    elif cmd == "--help" or cmd == "-h":
        print(usage)

    else:
        # Default: print firm-wide text report
        text, summary = generate_events_report_text(7)
        print(text)
        print(f"\nSummary: {summary}")
