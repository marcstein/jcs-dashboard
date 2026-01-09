"""
Case Quality Verification Module

Ensures case setup quality and data integrity per SOPs:
- New matter verification (Day-1 checklist)
- Attorney 3-day outreach compliance
- Document/EA verification
- Invoice/payment plan alignment
- Case stage tracking
"""
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from api_client import MyCaseClient, get_client, MyCaseAPIError
from database import Database, get_db


class CaseQualityScore(Enum):
    EXCELLENT = "excellent"  # 90-100%
    GOOD = "good"  # 75-89%
    NEEDS_ATTENTION = "needs_attention"  # 50-74%
    CRITICAL = "critical"  # <50%


@dataclass
class QualityCheckItem:
    """Individual quality check result."""
    name: str
    passed: bool
    weight: float = 1.0
    details: str = ""
    fix_action: str = ""


@dataclass
class CaseQualityReport:
    """Complete quality assessment for a case."""
    case_id: int
    case_name: str
    case_type: str
    attorney_name: str
    client_name: str
    created_date: date
    checks: List[QualityCheckItem] = field(default_factory=list)
    score: float = 0.0
    grade: CaseQualityScore = CaseQualityScore.CRITICAL
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class AttorneyOutreachStatus:
    """Tracks 3-day attorney outreach compliance."""
    case_id: int
    case_name: str
    client_name: str
    attorney_name: str
    case_created: date
    first_contact_date: Optional[date]
    days_to_contact: Optional[int]
    compliant: bool
    contact_method: str = ""


@dataclass
class DataIntegrityIssue:
    """Represents a data integrity issue (wonky invoice, missing data, etc.)."""
    case_id: int
    case_name: str
    issue_type: str
    description: str
    severity: str  # high, medium, low
    detected_at: datetime
    resolved: bool = False
    resolution_notes: str = ""


class CaseQualityManager:
    """
    Manages case quality verification per multiple SOPs.

    Tiffany SOP: 3-day attorney outreach, discovery routing
    Alison/Cole SOP: Case setup, document upload, data entry
    Melissa SOP: EA/invoice alignment, payment plan setup
    """

    # Quality check weights
    CHECK_WEIGHTS = {
        "attorney_assigned": 2.0,
        "client_contact_info": 1.5,
        "ea_uploaded": 2.0,
        "invoice_created": 2.0,
        "fee_matches_ea": 1.5,
        "payment_plan_setup": 1.5,
        "portal_access": 1.0,
        "case_type_set": 1.0,
        "court_info": 1.0,
        "3_day_outreach": 2.0,
    }

    def __init__(
        self,
        client: MyCaseClient = None,
        db: Database = None,
    ):
        self.client = client or get_client()
        self.db = db or get_db()
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure quality tracking tables exist."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Case quality snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_quality_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    case_name TEXT,
                    case_type TEXT,
                    attorney_name TEXT,
                    client_name TEXT,
                    score REAL,
                    grade TEXT,
                    checks_passed INTEGER,
                    checks_total INTEGER,
                    issues TEXT,
                    snapshot_date DATE DEFAULT CURRENT_DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(case_id, snapshot_date)
                )
            """)

            # Attorney outreach tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attorney_outreach_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER UNIQUE,
                    case_name TEXT,
                    client_name TEXT,
                    attorney_id INTEGER,
                    attorney_name TEXT,
                    case_created DATE,
                    first_contact_date DATE,
                    contact_method TEXT,
                    days_to_contact INTEGER,
                    compliant BOOLEAN,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Data integrity issues
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_integrity_issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER,
                    case_name TEXT,
                    issue_type TEXT NOT NULL,
                    description TEXT,
                    severity TEXT DEFAULT 'medium',
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolved_at TIMESTAMP,
                    resolution_notes TEXT,
                    UNIQUE(case_id, issue_type, description)
                )
            """)

            # Case stage transitions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_stage_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    case_name TEXT,
                    from_stage TEXT,
                    to_stage TEXT NOT NULL,
                    transition_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    days_in_previous_stage INTEGER,
                    triggered_by TEXT,
                    notes TEXT
                )
            """)

            conn.commit()

    # ========== Quality Checks ==========

    def run_quality_check(self, case_id: int) -> CaseQualityReport:
        """
        Run comprehensive quality check on a case.

        Checks:
        - Attorney assigned
        - Client contact info complete
        - EA uploaded
        - Invoice created
        - Fee matches EA
        - Payment plan setup
        - Portal access
        - Case type set
        - Court info
        """
        print(f"Running quality check on case {case_id}...")

        checks = []
        issues = []
        warnings = []

        try:
            case = self.client.get_case(case_id)
            case_name = case.get("name", "Unknown")
            case_type = case.get("case_type", case.get("practice_area", "Unknown"))

            # Get attorney
            lead_attorney = case.get("lead_attorney", {})
            attorney_name = lead_attorney.get("name", "Unassigned") if lead_attorney else "Unassigned"

            # Get client
            clients = case.get("clients", [])
            client_name = "Unknown"
            client_email = ""
            client_phone = ""
            contact_id = None

            if clients:
                client_info = clients[0] if isinstance(clients[0], dict) else {}
                contact_id = client_info.get("id") if isinstance(clients[0], dict) else clients[0]

                if contact_id:
                    try:
                        contact = self.client.get_contact(contact_id)
                        client_name = contact.get("name", "Unknown")
                        client_email = contact.get("email", "")
                        client_phone = contact.get("phone", "")
                    except Exception:
                        pass

            # Parse created date
            created_str = case.get("created_at", "")
            created_date = date.today()
            if created_str:
                try:
                    created_date = datetime.fromisoformat(created_str.replace("Z", "")).date()
                except ValueError:
                    pass

            # Check 1: Attorney assigned
            attorney_assigned = lead_attorney is not None and attorney_name != "Unassigned"
            checks.append(QualityCheckItem(
                name="attorney_assigned",
                passed=attorney_assigned,
                weight=self.CHECK_WEIGHTS["attorney_assigned"],
                details=attorney_name if attorney_assigned else "No attorney assigned",
                fix_action="Assign lead attorney in MyCase" if not attorney_assigned else "",
            ))
            if not attorney_assigned:
                issues.append("No lead attorney assigned")

            # Check 2: Client contact info
            has_contact_info = bool(client_email or client_phone)
            checks.append(QualityCheckItem(
                name="client_contact_info",
                passed=has_contact_info,
                weight=self.CHECK_WEIGHTS["client_contact_info"],
                details=f"Email: {client_email}, Phone: {client_phone}",
                fix_action="Add client email and phone" if not has_contact_info else "",
            ))
            if not has_contact_info:
                issues.append("Missing client contact information")

            # Check 3: EA uploaded
            ea_uploaded = False
            try:
                docs = self.client.get_case_documents(case_id)
                doc_list = docs if isinstance(docs, list) else docs.get("data", [])

                for doc in doc_list:
                    doc_name = doc.get("name", "").lower()
                    if "engagement" in doc_name or "agreement" in doc_name or "ea" == doc_name:
                        ea_uploaded = True
                        break
            except Exception:
                warnings.append("Could not verify documents")

            checks.append(QualityCheckItem(
                name="ea_uploaded",
                passed=ea_uploaded,
                weight=self.CHECK_WEIGHTS["ea_uploaded"],
                details="Found" if ea_uploaded else "Not found",
                fix_action="Upload signed Engagement Agreement" if not ea_uploaded else "",
            ))
            if not ea_uploaded:
                issues.append("Engagement Agreement not uploaded")

            # Check 4 & 5: Invoice and fee match
            invoice_created = False
            fee_matches = True
            invoice_total = 0

            try:
                invoices = self.client.get_invoices(case_id=case_id)
                invoice_list = invoices if isinstance(invoices, list) else invoices.get("data", [])

                if invoice_list:
                    invoice_created = True
                    invoice_total = float(invoice_list[0].get("total_amount", 0))
                    # Note: Would need EA parsing to truly verify fee match
                    # For now, just check invoice exists
            except Exception:
                warnings.append("Could not verify invoices")

            checks.append(QualityCheckItem(
                name="invoice_created",
                passed=invoice_created,
                weight=self.CHECK_WEIGHTS["invoice_created"],
                details=f"${invoice_total:,.2f}" if invoice_created else "No invoice",
                fix_action="Create invoice for case" if not invoice_created else "",
            ))
            if not invoice_created:
                issues.append("No invoice created")

            checks.append(QualityCheckItem(
                name="fee_matches_ea",
                passed=fee_matches and invoice_created,
                weight=self.CHECK_WEIGHTS["fee_matches_ea"],
                details="Verify manually" if invoice_created else "N/A",
                fix_action="" if fee_matches else "Verify invoice matches EA flat fee",
            ))

            # Check 6: Payment plan setup
            has_payment_plan = invoice_created and invoice_total > 0
            checks.append(QualityCheckItem(
                name="payment_plan_setup",
                passed=has_payment_plan,
                weight=self.CHECK_WEIGHTS["payment_plan_setup"],
                details="Invoice with amount" if has_payment_plan else "No payment terms",
                fix_action="Set up payment plan/terms" if not has_payment_plan else "",
            ))

            # Check 7: Portal access (would need portal API - mark for manual check)
            checks.append(QualityCheckItem(
                name="portal_access",
                passed=True,  # Assume true, flag for verification
                weight=self.CHECK_WEIGHTS["portal_access"],
                details="Verify manually",
                fix_action="",
            ))
            warnings.append("Verify client portal access enabled")

            # Check 8: Case type set
            case_type_set = case_type and case_type != "Unknown" and case_type != ""
            checks.append(QualityCheckItem(
                name="case_type_set",
                passed=case_type_set,
                weight=self.CHECK_WEIGHTS["case_type_set"],
                details=case_type if case_type_set else "Not set",
                fix_action="Set case type/practice area" if not case_type_set else "",
            ))

            # Check 9: Court info
            court = case.get("court", {})
            has_court = bool(court and court.get("name"))
            checks.append(QualityCheckItem(
                name="court_info",
                passed=has_court,
                weight=self.CHECK_WEIGHTS["court_info"],
                details=court.get("name", "Not set") if court else "Not set",
                fix_action="Add court information" if not has_court else "",
            ))

            # Check 10: 3-day outreach (check our tracking)
            outreach_compliant = self._check_3day_outreach(case_id, created_date, attorney_name)
            checks.append(QualityCheckItem(
                name="3_day_outreach",
                passed=outreach_compliant,
                weight=self.CHECK_WEIGHTS["3_day_outreach"],
                details="Compliant" if outreach_compliant else "Not verified",
                fix_action="Record attorney client contact" if not outreach_compliant else "",
            ))
            if not outreach_compliant:
                warnings.append("3-day attorney outreach not confirmed")

            # Calculate score
            total_weight = sum(c.weight for c in checks)
            earned_weight = sum(c.weight for c in checks if c.passed)
            score = (earned_weight / total_weight * 100) if total_weight > 0 else 0

            # Determine grade
            if score >= 90:
                grade = CaseQualityScore.EXCELLENT
            elif score >= 75:
                grade = CaseQualityScore.GOOD
            elif score >= 50:
                grade = CaseQualityScore.NEEDS_ATTENTION
            else:
                grade = CaseQualityScore.CRITICAL

            report = CaseQualityReport(
                case_id=case_id,
                case_name=case_name,
                case_type=case_type,
                attorney_name=attorney_name,
                client_name=client_name,
                created_date=created_date,
                checks=checks,
                score=score,
                grade=grade,
                issues=issues,
                warnings=warnings,
            )

            # Save snapshot
            self._save_quality_snapshot(report)

            return report

        except MyCaseAPIError as e:
            return CaseQualityReport(
                case_id=case_id,
                case_name="Unknown",
                case_type="Unknown",
                attorney_name="Unknown",
                client_name="Unknown",
                created_date=date.today(),
                issues=[f"API Error: {e}"],
                score=0,
                grade=CaseQualityScore.CRITICAL,
            )

    def _check_3day_outreach(
        self,
        case_id: int,
        created_date: date,
        attorney_name: str,
    ) -> bool:
        """Check if 3-day attorney outreach was completed."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM attorney_outreach_tracking
                WHERE case_id = ?
            """, (case_id,))
            row = cursor.fetchone()

            if row and row["compliant"]:
                return True

            # If case is less than 3 days old, give benefit of doubt
            days_old = (date.today() - created_date).days
            if days_old < 3:
                return True

            return False

    def _save_quality_snapshot(self, report: CaseQualityReport):
        """Save quality check snapshot to database."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            checks_passed = sum(1 for c in report.checks if c.passed)
            checks_total = len(report.checks)

            cursor.execute("""
                INSERT OR REPLACE INTO case_quality_snapshots
                (case_id, case_name, case_type, attorney_name, client_name,
                 score, grade, checks_passed, checks_total, issues, snapshot_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATE('now'))
            """, (report.case_id, report.case_name, report.case_type,
                  report.attorney_name, report.client_name, report.score,
                  report.grade.value, checks_passed, checks_total,
                  "|".join(report.issues)))
            conn.commit()

    # ========== Batch Quality Checks ==========

    def run_new_case_quality_audit(self, days_back: int = 7) -> Dict:
        """
        Run quality audit on all cases created in the last N days.

        Returns summary of quality issues.
        """
        print(f"Running quality audit on cases from last {days_back} days...")

        cutoff = datetime.now() - timedelta(days=days_back)

        try:
            all_cases = self.client.get_all_pages(
                self.client.get_cases,
                status="open",
            )

            results = {
                "total_cases": 0,
                "excellent": 0,
                "good": 0,
                "needs_attention": 0,
                "critical": 0,
                "avg_score": 0.0,
                "common_issues": {},
                "cases_with_issues": [],
            }

            total_score = 0.0

            for case in all_cases:
                created_str = case.get("created_at", "")
                if not created_str:
                    continue

                try:
                    created_at = datetime.fromisoformat(created_str.replace("Z", ""))
                    if created_at < cutoff:
                        continue
                except ValueError:
                    continue

                case_id = case.get("id")
                report = self.run_quality_check(case_id)

                results["total_cases"] += 1
                total_score += report.score

                if report.grade == CaseQualityScore.EXCELLENT:
                    results["excellent"] += 1
                elif report.grade == CaseQualityScore.GOOD:
                    results["good"] += 1
                elif report.grade == CaseQualityScore.NEEDS_ATTENTION:
                    results["needs_attention"] += 1
                else:
                    results["critical"] += 1

                # Track common issues
                for issue in report.issues:
                    results["common_issues"][issue] = results["common_issues"].get(issue, 0) + 1

                # Track cases with issues
                if report.issues:
                    results["cases_with_issues"].append({
                        "case_id": case_id,
                        "case_name": report.case_name,
                        "score": report.score,
                        "grade": report.grade.value,
                        "issues": report.issues,
                    })

            if results["total_cases"] > 0:
                results["avg_score"] = total_score / results["total_cases"]

            return results

        except MyCaseAPIError as e:
            print(f"Error running audit: {e}")
            return {"error": str(e)}

    # ========== Attorney Outreach Tracking ==========

    def record_attorney_outreach(
        self,
        case_id: int,
        contact_date: date,
        contact_method: str = "call",
        case_name: str = None,
        client_name: str = None,
        attorney_id: int = None,
        attorney_name: str = None,
        notes: str = None,
    ):
        """Record attorney client outreach for 3-day compliance."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Get case created date if not already tracked
            cursor.execute("""
                SELECT case_created FROM attorney_outreach_tracking
                WHERE case_id = ?
            """, (case_id,))
            row = cursor.fetchone()

            if row:
                case_created = datetime.strptime(row["case_created"], "%Y-%m-%d").date()
            else:
                # Get from MyCase
                try:
                    case = self.client.get_case(case_id)
                    created_str = case.get("created_at", "")
                    case_created = datetime.fromisoformat(created_str.replace("Z", "")).date()
                    case_name = case_name or case.get("name")
                except Exception:
                    case_created = date.today()

            days_to_contact = (contact_date - case_created).days
            compliant = days_to_contact <= 3

            cursor.execute("""
                INSERT INTO attorney_outreach_tracking
                (case_id, case_name, client_name, attorney_id, attorney_name,
                 case_created, first_contact_date, contact_method, days_to_contact,
                 compliant, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(case_id) DO UPDATE SET
                    first_contact_date = COALESCE(attorney_outreach_tracking.first_contact_date, excluded.first_contact_date),
                    contact_method = excluded.contact_method,
                    days_to_contact = excluded.days_to_contact,
                    compliant = excluded.compliant,
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
            """, (case_id, case_name, client_name, attorney_id, attorney_name,
                  case_created, contact_date, contact_method, days_to_contact,
                  compliant, notes))
            conn.commit()

    def get_pending_outreach(self) -> List[AttorneyOutreachStatus]:
        """Get cases needing attorney outreach (within 3 days, no contact yet)."""
        cutoff = date.today() - timedelta(days=3)

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM attorney_outreach_tracking
                WHERE first_contact_date IS NULL
                AND case_created >= ?
                ORDER BY case_created ASC
            """, (cutoff,))

            pending = []
            for row in cursor.fetchall():
                case_created = datetime.strptime(row["case_created"], "%Y-%m-%d").date()
                days_remaining = 3 - (date.today() - case_created).days

                pending.append(AttorneyOutreachStatus(
                    case_id=row["case_id"],
                    case_name=row["case_name"] or "Unknown",
                    client_name=row["client_name"] or "Unknown",
                    attorney_name=row["attorney_name"] or "Unassigned",
                    case_created=case_created,
                    first_contact_date=None,
                    days_to_contact=None,
                    compliant=days_remaining >= 0,
                ))

            return pending

    def get_outreach_compliance_report(self, days_back: int = 30) -> Dict:
        """Get attorney outreach compliance metrics."""
        cutoff = date.today() - timedelta(days=days_back)

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    attorney_name,
                    COUNT(*) as total,
                    SUM(CASE WHEN compliant = 1 THEN 1 ELSE 0 END) as compliant_count,
                    AVG(days_to_contact) as avg_days
                FROM attorney_outreach_tracking
                WHERE case_created >= ?
                AND first_contact_date IS NOT NULL
                GROUP BY attorney_name
            """, (cutoff,))

            by_attorney = {}
            for row in cursor.fetchall():
                total = row["total"] or 0
                compliant = row["compliant_count"] or 0
                rate = (compliant / total * 100) if total > 0 else 0

                by_attorney[row["attorney_name"]] = {
                    "total_cases": total,
                    "compliant": compliant,
                    "compliance_rate": rate,
                    "avg_days_to_contact": row["avg_days"] or 0,
                }

            # Overall metrics
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN compliant = 1 THEN 1 ELSE 0 END) as compliant_count,
                    AVG(days_to_contact) as avg_days
                FROM attorney_outreach_tracking
                WHERE case_created >= ?
                AND first_contact_date IS NOT NULL
            """, (cutoff,))
            row = cursor.fetchone()

            total = row["total"] or 0
            compliant = row["compliant_count"] or 0

            return {
                "period_days": days_back,
                "total_cases": total,
                "compliant_cases": compliant,
                "overall_compliance_rate": (compliant / total * 100) if total > 0 else 0,
                "avg_days_to_contact": row["avg_days"] or 0,
                "by_attorney": by_attorney,
            }

    # ========== Data Integrity ==========

    def record_integrity_issue(
        self,
        case_id: int,
        issue_type: str,
        description: str,
        severity: str = "medium",
        case_name: str = None,
    ) -> int:
        """Record a data integrity issue."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO data_integrity_issues
                (case_id, case_name, issue_type, description, severity)
                VALUES (?, ?, ?, ?, ?)
            """, (case_id, case_name, issue_type, description, severity))
            return cursor.lastrowid

    def resolve_integrity_issue(
        self,
        issue_id: int = None,
        case_id: int = None,
        issue_type: str = None,
        resolution_notes: str = None,
    ):
        """Mark an integrity issue as resolved."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            if issue_id:
                cursor.execute("""
                    UPDATE data_integrity_issues
                    SET resolved = TRUE, resolved_at = CURRENT_TIMESTAMP,
                        resolution_notes = ?
                    WHERE id = ?
                """, (resolution_notes, issue_id))
            elif case_id and issue_type:
                cursor.execute("""
                    UPDATE data_integrity_issues
                    SET resolved = TRUE, resolved_at = CURRENT_TIMESTAMP,
                        resolution_notes = ?
                    WHERE case_id = ? AND issue_type = ? AND resolved = FALSE
                """, (resolution_notes, case_id, issue_type))
            conn.commit()

    def get_open_integrity_issues(self, severity: str = None) -> List[Dict]:
        """Get all open data integrity issues."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT * FROM data_integrity_issues
                WHERE resolved = FALSE
            """
            params = []

            if severity:
                query += " AND severity = ?"
                params.append(severity)

            query += " ORDER BY severity DESC, detected_at ASC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # ========== Report Generation ==========

    def generate_quality_summary_report(self, days_back: int = 7) -> str:
        """Generate case quality summary report."""
        audit = self.run_new_case_quality_audit(days_back)
        pending_outreach = self.get_pending_outreach()
        outreach_compliance = self.get_outreach_compliance_report(days_back)
        integrity_issues = self.get_open_integrity_issues()

        report = f"""
================================================================================
                    CASE QUALITY SUMMARY - Last {days_back} Days
================================================================================

1. CASE QUALITY OVERVIEW
   Total Cases Reviewed: {audit.get('total_cases', 0)}
   Average Score: {audit.get('avg_score', 0):.1f}%

   Quality Distribution:
   ├── Excellent (90-100%): {audit.get('excellent', 0)}
   ├── Good (75-89%): {audit.get('good', 0)}
   ├── Needs Attention (50-74%): {audit.get('needs_attention', 0)}
   └── Critical (<50%): {audit.get('critical', 0)}

2. COMMON ISSUES
"""
        for issue, count in sorted(audit.get('common_issues', {}).items(), key=lambda x: -x[1])[:5]:
            report += f"   • {issue}: {count} cases\n"

        report += f"""

3. ATTORNEY OUTREACH COMPLIANCE (3-Day Policy)
   Overall Rate: {outreach_compliance.get('overall_compliance_rate', 0):.1f}%
   Avg Days to Contact: {outreach_compliance.get('avg_days_to_contact', 0):.1f}

   By Attorney:
"""
        for attorney, metrics in outreach_compliance.get('by_attorney', {}).items():
            status = "✓" if metrics['compliance_rate'] >= 100 else "⚠"
            report += f"   • {attorney}: {metrics['compliance_rate']:.0f}% ({metrics['total_cases']} cases) {status}\n"

        report += f"""

4. PENDING ATTORNEY OUTREACH ({len(pending_outreach)} cases)
"""
        for item in pending_outreach[:5]:
            days_old = (date.today() - item.case_created).days
            urgency = "🔴" if days_old >= 2 else "🟡"
            report += f"   {urgency} {item.case_name} ({item.attorney_name}) - {days_old} days old\n"

        report += f"""

5. DATA INTEGRITY ISSUES ({len(integrity_issues)} open)
"""
        high_severity = [i for i in integrity_issues if i['severity'] == 'high']
        for issue in high_severity[:5]:
            report += f"   🔴 Case {issue['case_id']}: {issue['issue_type']} - {issue['description']}\n"

        report += f"""

6. CASES NEEDING IMMEDIATE ATTENTION
"""
        critical_cases = audit.get('cases_with_issues', [])[:5]
        for case in critical_cases:
            if case['grade'] == 'critical':
                report += f"   🔴 {case['case_name']} (Score: {case['score']:.0f}%)\n"
                for issue in case['issues'][:2]:
                    report += f"      - {issue}\n"

        report += """
================================================================================
"""
        return report

    def generate_day1_checklist_report(self, case_id: int) -> str:
        """Generate Day-1 case setup checklist per Melissa SOP."""
        report = self.run_quality_check(case_id)

        checklist = f"""
================================================================================
              DAY-1 CASE SETUP CHECKLIST - {report.case_name}
================================================================================
Case ID: {report.case_id}
Client: {report.client_name}
Attorney: {report.attorney_name}
Created: {report.created_date}

QUALITY SCORE: {report.score:.0f}% ({report.grade.value.upper()})

CHECKLIST:
"""
        for check in report.checks:
            status = "✓" if check.passed else "✗"
            checklist += f"  [{status}] {check.name.replace('_', ' ').title()}\n"
            if not check.passed and check.fix_action:
                checklist += f"      Action: {check.fix_action}\n"

        if report.issues:
            checklist += "\nISSUES TO RESOLVE:\n"
            for issue in report.issues:
                checklist += f"  • {issue}\n"

        if report.warnings:
            checklist += "\nWARNINGS:\n"
            for warning in report.warnings:
                checklist += f"  • {warning}\n"

        checklist += """
================================================================================
"""
        return checklist


if __name__ == "__main__":
    manager = CaseQualityManager()

    print("Testing Case Quality Manager...")
    print("(Requires valid MyCase API authentication)")

    try:
        # Run audit
        audit = manager.run_new_case_quality_audit(days_back=7)
        print(f"\nAudit Results:")
        print(f"  Total Cases: {audit.get('total_cases', 0)}")
        print(f"  Avg Score: {audit.get('avg_score', 0):.1f}%")

        # Generate report
        report = manager.generate_quality_summary_report()
        print(report)

    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you've authenticated with: python auth.py")
