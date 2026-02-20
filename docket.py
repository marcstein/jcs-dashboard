"""
Missouri Court Docket Parser and Manager

Parses docket text from Missouri CaseNet and stores entries in the database.
Provides notification system for upcoming attorney actions.
"""
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from db.connection import get_connection


@dataclass
class DocketEntry:
    """Represents a single docket entry."""
    entry_date: date
    entry_type: str
    entry_text: Optional[str] = None
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[str] = None
    judge: Optional[str] = None
    location: Optional[str] = None
    filed_by: Optional[str] = None
    on_behalf_of: Optional[str] = None
    document_id: Optional[str] = None
    associated_entries: Optional[str] = None
    raw_text: str = ""
    requires_action: bool = False
    action_due_date: Optional[date] = None


# Entry types that typically require attorney action
ACTION_REQUIRED_TYPES = [
    'Hearing Scheduled',
    'Plea Hearing Scheduled',
    'Trial Scheduled',
    'Show Cause Hearing Scheduled',
    'Motion Hearing Scheduled',
    'Status Hearing Scheduled',
    'Pretrial Conference Scheduled',
    'Arraignment Scheduled',
    'Sentencing Scheduled',
    'Initial Appearance',
    'Deposition Scheduled',
    'Subpoena Issued',
    'Response Due',
    'Answer Due',
    'Discovery Due',
]


class DocketParser:
    """Parses Missouri CaseNet docket text into structured entries."""

    def __init__(self):
        # Pattern for date lines like "12/31/2025"
        self.date_pattern = re.compile(r'^(\d{2}/\d{2}/\d{4})\s*$')
        # Pattern for "Scheduled For:" lines
        self.scheduled_pattern = re.compile(
            r'Scheduled For:\s*(\d{2}/\d{2}/\d{4});\s*(\d{1,2}:\d{2}\s*[AP]M);\s*([^;]+);\s*(.+?)(?:\s*$|\s{2,})'
        )
        # Pattern for "Filed By:" lines
        self.filed_by_pattern = re.compile(r'Filed By:\s*(.+?)(?:\s*$|\s{2,})')
        # Pattern for "On Behalf Of:" lines
        self.on_behalf_pattern = re.compile(r'On Behalf Of:\s*(.+?)(?:\s*$|\s{2,})')
        # Pattern for "Document ID:" lines
        self.document_id_pattern = re.compile(r'Document ID:\s*([^,\s]+)')
        # Pattern for "Associated Entries:" lines
        self.associated_pattern = re.compile(r'Associated Entries:\s*(.+?)(?:\s*$|\s{2,})')

    def parse(self, docket_text: str) -> Tuple[str, str, List[DocketEntry]]:
        """
        Parse docket text and return case info and entries.

        Args:
            docket_text: Raw docket text from CaseNet

        Returns:
            Tuple of (case_number, case_name, list of DocketEntry objects)
        """
        lines = docket_text.strip().split('\n')
        if not lines:
            return "", "", []

        # Parse header line: "250681127 - CITY OF SAINT PETERS V ALEXSANDRA DAWN MESHOTO"
        header = lines[0].strip()
        case_number, case_name = self._parse_header(header)

        entries = []
        current_date = None
        current_entry_lines = []
        current_entry_type = None

        for line in lines[1:]:
            line_stripped = line.strip()

            # Check for date line
            date_match = self.date_pattern.match(line_stripped)
            if date_match:
                # Save previous entry if exists
                if current_entry_type and current_date:
                    entry = self._parse_entry(current_date, current_entry_type, current_entry_lines)
                    if entry:
                        entries.append(entry)

                # Start new date section
                current_date = datetime.strptime(date_match.group(1), '%m/%d/%Y').date()
                current_entry_lines = []
                current_entry_type = None
                continue

            # Check if this is a new entry type (not indented, not a detail line)
            if line_stripped and not line.startswith(' ') and not line.startswith('\t'):
                # Could be an entry type or continuation
                if not any(line_stripped.startswith(p) for p in ['Scheduled For:', 'Filed By:', 'On Behalf Of:', 'Document ID:', 'Associated Entries:']):
                    # Save previous entry
                    if current_entry_type and current_date:
                        entry = self._parse_entry(current_date, current_entry_type, current_entry_lines)
                        if entry:
                            entries.append(entry)

                    current_entry_type = line_stripped
                    current_entry_lines = []
                    continue

            # Add line to current entry
            if current_entry_type:
                current_entry_lines.append(line)

        # Don't forget the last entry
        if current_entry_type and current_date:
            entry = self._parse_entry(current_date, current_entry_type, current_entry_lines)
            if entry:
                entries.append(entry)

        return case_number, case_name, entries

    def _parse_header(self, header: str) -> Tuple[str, str]:
        """Parse the header line to extract case number and name."""
        # Format: "250681127 - CITY OF SAINT PETERS V ALEXSANDRA DAWN MESHOTO"
        if ' - ' in header:
            parts = header.split(' - ', 1)
            return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
        return header.strip(), ""

    def _parse_entry(self, entry_date: date, entry_type: str, detail_lines: List[str]) -> Optional[DocketEntry]:
        """Parse a single docket entry from its type and detail lines."""
        raw_text = entry_type + '\n' + '\n'.join(detail_lines)
        full_text = ' '.join(detail_lines)

        # Extract entry text (first line of details if it's descriptive)
        entry_text = None
        for line in detail_lines:
            line_stripped = line.strip()
            if line_stripped and not any(line_stripped.startswith(p) for p in
                ['Scheduled For:', 'Filed By:', 'On Behalf Of:', 'Document ID:', 'Associated Entries:']):
                if not line_stripped.startswith('+'):
                    entry_text = line_stripped
                    break

        # Extract scheduled info
        scheduled_date = None
        scheduled_time = None
        judge = None
        location = None
        scheduled_match = self.scheduled_pattern.search(full_text)
        if scheduled_match:
            scheduled_date = datetime.strptime(scheduled_match.group(1), '%m/%d/%Y').date()
            scheduled_time = scheduled_match.group(2).strip()
            judge = scheduled_match.group(3).strip()
            location = scheduled_match.group(4).strip()

        # Extract filed by
        filed_by = None
        filed_match = self.filed_by_pattern.search(full_text)
        if filed_match:
            filed_by = filed_match.group(1).strip()

        # Extract on behalf of
        on_behalf_of = None
        behalf_match = self.on_behalf_pattern.search(full_text)
        if behalf_match:
            on_behalf_of = behalf_match.group(1).strip()

        # Extract document ID
        document_id = None
        doc_match = self.document_id_pattern.search(full_text)
        if doc_match:
            document_id = doc_match.group(1).strip()

        # Extract associated entries
        associated_entries = None
        assoc_match = self.associated_pattern.search(full_text)
        if assoc_match:
            associated_entries = assoc_match.group(1).strip()

        # Determine if action is required
        requires_action = False
        action_due_date = None
        for action_type in ACTION_REQUIRED_TYPES:
            if action_type.lower() in entry_type.lower():
                requires_action = True
                # Use scheduled date as action due date, or entry date + 7 days
                action_due_date = scheduled_date or (entry_date + timedelta(days=7))
                break

        return DocketEntry(
            entry_date=entry_date,
            entry_type=entry_type,
            entry_text=entry_text,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            judge=judge,
            location=location,
            filed_by=filed_by,
            on_behalf_of=on_behalf_of,
            document_id=document_id,
            associated_entries=associated_entries,
            raw_text=raw_text,
            requires_action=requires_action,
            action_due_date=action_due_date,
        )


class DocketManager:
    """Manages docket entries in the database (PostgreSQL multi-tenant)."""

    def __init__(self, firm_id: Optional[str] = None):
        self.firm_id = firm_id
        self.parser = DocketParser()
        self._init_table()

    def _init_table(self):
        """Ensure the docket entries table exists."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cached_docket_entries (
                        id SERIAL PRIMARY KEY,
                        firm_id TEXT NOT NULL,
                        case_number TEXT NOT NULL,
                        case_name TEXT,
                        case_id INTEGER,
                        entry_date DATE NOT NULL,
                        entry_type TEXT NOT NULL,
                        entry_text TEXT,
                        scheduled_date DATE,
                        scheduled_time TEXT,
                        judge TEXT,
                        location TEXT,
                        filed_by TEXT,
                        on_behalf_of TEXT,
                        document_id TEXT,
                        associated_entries TEXT,
                        raw_text TEXT,
                        requires_action BOOLEAN DEFAULT FALSE,
                        action_due_date DATE,
                        notification_sent BOOLEAN DEFAULT FALSE,
                        notification_sent_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(firm_id, case_number, entry_date, entry_type, entry_text)
                    )
                """)

                # Create indexes for performance
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_docket_firm_id
                    ON cached_docket_entries(firm_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_docket_case_id
                    ON cached_docket_entries(firm_id, case_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_docket_action_due
                    ON cached_docket_entries(firm_id, action_due_date)
                    WHERE requires_action = TRUE
                """)

            conn.commit()

    def import_docket(self, docket_text: str, case_id: int = None, firm_id: Optional[str] = None) -> Dict:
        """
        Import docket text and store entries in database.

        Args:
            docket_text: Raw docket text from CaseNet
            case_id: Optional MyCase case ID to link entries to
            firm_id: Firm ID for multi-tenant isolation (uses self.firm_id if not provided)

        Returns:
            Dict with import statistics
        """
        firm_id = firm_id or self.firm_id

        case_number, case_name, entries = self.parser.parse(docket_text)

        if not case_number:
            return {'error': 'Could not parse case number from docket text'}

        # Try to find case_id from case_number if not provided
        if not case_id:
            case_id = self._find_case_id(case_number, firm_id)

        with get_connection() as conn:
            with conn.cursor() as cursor:

                inserted = 0
                updated = 0

                for entry in entries:
                    try:
                        cursor.execute("""
                            INSERT INTO cached_docket_entries (
                                firm_id, case_number, case_name, case_id, entry_date, entry_type,
                                entry_text, scheduled_date, scheduled_time, judge, location,
                                filed_by, on_behalf_of, document_id, associated_entries,
                                requires_action, action_due_date, raw_text
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT(firm_id, case_number, entry_date, entry_type, entry_text)
                            DO UPDATE SET
                                scheduled_date = EXCLUDED.scheduled_date,
                                scheduled_time = EXCLUDED.scheduled_time,
                                judge = EXCLUDED.judge,
                                location = EXCLUDED.location,
                                requires_action = EXCLUDED.requires_action,
                                action_due_date = EXCLUDED.action_due_date,
                                updated_at = CURRENT_TIMESTAMP
                        """, (
                            firm_id,
                            case_number,
                            case_name,
                            case_id,
                            entry.entry_date.isoformat(),
                            entry.entry_type,
                            entry.entry_text,
                            entry.scheduled_date.isoformat() if entry.scheduled_date else None,
                            entry.scheduled_time,
                            entry.judge,
                            entry.location,
                            entry.filed_by,
                            entry.on_behalf_of,
                            entry.document_id,
                            entry.associated_entries,
                            entry.requires_action,
                            entry.action_due_date.isoformat() if entry.action_due_date else None,
                            entry.raw_text,
                        ))

                        inserted += 1

                    except Exception as e:
                        # On conflict, treat as update
                        updated += 1

            conn.commit()

        return {
            'case_number': case_number,
            'case_name': case_name,
            'case_id': case_id,
            'entries_parsed': len(entries),
            'inserted': inserted,
            'updated': updated,
        }

    def _find_case_id(self, case_number: str, firm_id: Optional[str] = None) -> Optional[int]:
        """Try to find MyCase case_id from case number."""
        firm_id = firm_id or self.firm_id

        with get_connection() as conn:
            with conn.cursor() as cursor:

                # Search in cached_cases for matching case_number
                cursor.execute("""
                    SELECT id FROM cached_cases
                    WHERE firm_id = %s AND case_number LIKE %s
                    ORDER BY created_at DESC LIMIT 1
                """, (firm_id, f'%{case_number}%'))

                row = cursor.fetchone()

        return row[0] if row else None

    def get_upcoming_actions(self, days_ahead: int = 14, firm_id: Optional[str] = None) -> List[Dict]:
        """Get docket entries requiring action in the next N days."""
        firm_id = firm_id or self.firm_id

        with get_connection() as conn:
            with conn.cursor() as cursor:

                today = date.today()
                future_date = today + timedelta(days=days_ahead)

                cursor.execute("""
                    SELECT d.*, c.lead_attorney_name, c.name as mycase_name
                    FROM cached_docket_entries d
                    LEFT JOIN cached_cases c ON d.firm_id = c.firm_id AND d.case_id = c.id
                    WHERE d.firm_id = %s
                      AND d.requires_action = TRUE
                      AND d.scheduled_date BETWEEN %s AND %s
                      AND (d.notification_sent = FALSE OR d.notification_sent IS NULL)
                    ORDER BY d.scheduled_date ASC
                """, (firm_id, today.isoformat(), future_date.isoformat()))

                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]

    def get_case_docket(self, case_number: str = None, case_id: int = None, firm_id: Optional[str] = None) -> List[Dict]:
        """Get all docket entries for a case."""
        firm_id = firm_id or self.firm_id

        with get_connection() as conn:
            with conn.cursor() as cursor:

                if case_id:
                    cursor.execute("""
                        SELECT * FROM cached_docket_entries
                        WHERE firm_id = %s AND case_id = %s
                        ORDER BY entry_date DESC, id DESC
                    """, (firm_id, case_id))
                elif case_number:
                    cursor.execute("""
                        SELECT * FROM cached_docket_entries
                        WHERE firm_id = %s AND case_number = %s
                        ORDER BY entry_date DESC, id DESC
                    """, (firm_id, case_number))
                else:
                    return []

                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]

    def mark_notification_sent(self, entry_ids: List[int], firm_id: Optional[str] = None):
        """Mark entries as having notifications sent."""
        if not entry_ids:
            return

        firm_id = firm_id or self.firm_id

        with get_connection() as conn:
            with conn.cursor() as cursor:

                placeholders = ','.join(['%s'] * len(entry_ids))
                cursor.execute(f"""
                    UPDATE cached_docket_entries
                    SET notification_sent = TRUE, notification_sent_at = CURRENT_TIMESTAMP
                    WHERE firm_id = %s AND id IN ({placeholders})
                """, [firm_id] + entry_ids)

            conn.commit()

    def send_upcoming_notifications(self, email_to: str = "marc.stein@gmail.com", days_ahead: int = 14, firm_id: Optional[str] = None) -> Dict:
        """
        Send email notifications for upcoming actions.

        Args:
            email_to: Email address to send notifications to
            days_ahead: Number of days to look ahead
            firm_id: Firm ID for multi-tenant isolation

        Returns:
            Dict with notification results
        """
        firm_id = firm_id or self.firm_id
        upcoming = self.get_upcoming_actions(days_ahead, firm_id)

        if not upcoming:
            return {'sent': 0, 'message': 'No upcoming actions requiring notification'}

        # Group by case
        by_case = {}
        for entry in upcoming:
            case_key = entry['case_number']
            if case_key not in by_case:
                by_case[case_key] = {
                    'case_name': entry['case_name'],
                    'case_id': entry['case_id'],
                    'entries': []
                }
            by_case[case_key]['entries'].append(entry)

        # Build email content
        subject = f"LawMetrics.ai: {len(upcoming)} Upcoming Court Actions"

        body_lines = [
            "The following court actions require your attention:",
            "",
        ]

        for case_number, case_info in by_case.items():
            body_lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            body_lines.append(f"Case: {case_number}")
            body_lines.append(f"      {case_info['case_name']}")
            body_lines.append("")

            for entry in case_info['entries']:
                scheduled = entry['scheduled_date']
                time_str = entry['scheduled_time'] or ''
                body_lines.append(f"  📅 {scheduled} {time_str}")
                body_lines.append(f"     {entry['entry_type']}")
                if entry['judge']:
                    body_lines.append(f"     Judge: {entry['judge']}")
                if entry['location']:
                    body_lines.append(f"     Location: {entry['location']}")
                body_lines.append("")

        body_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        body_lines.append("")
        body_lines.append("— LawMetrics.ai")

        body = '\n'.join(body_lines)

        # Send email (using existing notification system if available)
        try:
            from notifications import send_email
            success = send_email(email_to, subject, body)

            if success:
                # Mark as sent
                entry_ids = [e['id'] for e in upcoming]
                self.mark_notification_sent(entry_ids, firm_id)
                return {'sent': len(upcoming), 'email': email_to}
            else:
                return {'sent': 0, 'error': 'Email send failed'}

        except ImportError:
            # Fallback: just print the notification
            print(f"\n{'='*60}")
            print(f"TO: {email_to}")
            print(f"SUBJECT: {subject}")
            print(f"{'='*60}")
            print(body)
            print(f"{'='*60}\n")

            # Mark as sent anyway for testing
            entry_ids = [e['id'] for e in upcoming]
            self.mark_notification_sent(entry_ids, firm_id)

            return {'sent': len(upcoming), 'email': email_to, 'note': 'Printed to console (email not configured)'}


# CLI interface
if __name__ == "__main__":
    import sys

    manager = DocketManager()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python docket.py import <file.txt>  - Import docket from file")
        print("  python docket.py notify             - Send upcoming action notifications")
        print("  python docket.py upcoming [days]    - Show upcoming actions")
        print("  python docket.py case <number>      - Show docket for case")
        sys.exit(1)

    command = sys.argv[1]

    if command == "import":
        if len(sys.argv) < 3:
            print("Usage: python docket.py import <file.txt>")
            sys.exit(1)

        filepath = sys.argv[2]
        with open(filepath, 'r') as f:
            docket_text = f.read()

        result = manager.import_docket(docket_text)
        print(f"Import complete:")
        print(f"  Case: {result['case_number']} - {result['case_name']}")
        print(f"  MyCase ID: {result.get('case_id', 'Not linked')}")
        print(f"  Entries parsed: {result['entries_parsed']}")
        print(f"  Inserted: {result['inserted']}")
        print(f"  Updated: {result['updated']}")

    elif command == "notify":
        result = manager.send_upcoming_notifications()
        print(f"Notifications: {result}")

    elif command == "upcoming":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 14
        upcoming = manager.get_upcoming_actions(days)

        if not upcoming:
            print(f"No upcoming actions in the next {days} days")
        else:
            print(f"Upcoming actions ({len(upcoming)} total):")
            for entry in upcoming:
                print(f"  {entry['scheduled_date']} {entry['scheduled_time'] or ''}")
                print(f"    {entry['case_number']}: {entry['entry_type']}")
                print()

    elif command == "case":
        if len(sys.argv) < 3:
            print("Usage: python docket.py case <case_number>")
            sys.exit(1)

        case_number = sys.argv[2]
        entries = manager.get_case_docket(case_number=case_number)

        if not entries:
            print(f"No docket entries found for case {case_number}")
        else:
            print(f"Docket for {case_number} ({len(entries)} entries):")
            for entry in entries:
                print(f"\n{entry['entry_date']} - {entry['entry_type']}")
                if entry['entry_text']:
                    print(f"  {entry['entry_text']}")
                if entry['scheduled_date']:
                    print(f"  Scheduled: {entry['scheduled_date']} {entry['scheduled_time'] or ''}")
                if entry['judge']:
                    print(f"  Judge: {entry['judge']}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
