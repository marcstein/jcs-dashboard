"""
Multi-Tenant Firm Analytics Module — PostgreSQL Backend

Comprehensive analytics and reporting for law firms with multi-tenant support.
Each firm gets isolated analytics from their shared PostgreSQL cache.

Key changes from single-tenant:
1. Accepts firm_id parameter (or uses tenant context)
2. Gets cache connection through multi-tenant cache factory (Postgres)
3. Optional attorney filtering for role-based access control
4. All queries scoped by firm_id
"""
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from collections import defaultdict
from dataclasses import dataclass

from config import DATA_DIR
from tenant import current_tenant, get_current_firm_id
from cache_mt import get_cache


@dataclass
class RevenueByType:
    """Revenue metrics by case type."""
    case_type: str
    total_billed: float
    total_collected: float
    case_count: int
    collection_rate: float


@dataclass
class RevenueByAttorney:
    """Revenue metrics by attorney."""
    attorney_name: str
    total_billed: float
    total_collected: float
    case_count: int
    collection_rate: float


@dataclass
class MonthlyRevenue:
    """Monthly revenue for an attorney."""
    attorney_name: str
    month: str  # YYYY-MM format
    billed: float
    collected: float


@dataclass
class CaseLengthStats:
    """Case length statistics."""
    category: str  # Case type or attorney name
    avg_days: float
    min_days: int
    max_days: int
    case_count: int


@dataclass
class FeeStats:
    """Fee statistics by case type."""
    case_type: str
    avg_fee_charged: float
    avg_fee_collected: float
    total_cases: int


@dataclass
class NewCasesMonth:
    """New cases per month."""
    month: str
    attorney_name: str
    case_count: int


class FirmAnalytics:
    """
    Analytics engine for law firms with multi-tenant support.

    Uses cached MyCase data in PostgreSQL to generate comprehensive reports.
    Each instance is bound to a specific firm via firm_id.
    
    Optional attorney filtering for role-based access control:
    - Admins see all data
    - Attorneys see only their own cases
    - Staff see aggregate data (no individual attorney breakdown)
    """

    def __init__(self, firm_id: str = None, attorney_id: int = None, cache_path: Path = None):
        """
        Initialize analytics for a specific firm.
        
        Args:
            firm_id: The firm ID. If None, uses current tenant context.
            attorney_id: If set, filter all queries to this attorney's cases only.
            cache_path: Ignored (kept for API compatibility). Postgres only.
        """
        self.firm_id = firm_id or current_tenant.get()
        self.attorney_id = attorney_id
        self._cache = None

    @property
    def cache(self):
        if self._cache is None:
            self._cache = get_cache(self.firm_id)
        return self._cache

    def __enter__(self):
        """Support context manager usage."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up on context exit."""
        return False

    def _get_connection(self):
        """Get Postgres connection from cache (context manager)."""
        return self.cache._get_connection()

    def _get_attorney_filter(self) -> str:
        """Get SQL WHERE clause for attorney filtering."""
        if self.attorney_id:
            return f"AND c.lead_attorney_id = {self.attorney_id}"
        return ""
    
    def _get_attorney_filter_invoices(self) -> str:
        """Get SQL WHERE clause for attorney filtering on invoice queries."""
        if self.attorney_id:
            return f"AND c.lead_attorney_id = {self.attorney_id}"
        return ""

    # =========================================================================
    # 1. Revenue per Case Type
    # =========================================================================
    def get_revenue_by_case_type(self) -> List[RevenueByType]:
        """Get total revenue (billed and collected) by case type/practice area."""
        attorney_filter = self._get_attorney_filter()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT
                    COALESCE(c.practice_area, 'Unknown') as case_type,
                    COUNT(DISTINCT c.id) as case_count,
                    SUM(i.total_amount) as total_billed,
                    SUM(i.paid_amount) as total_collected
                FROM cached_cases c
                LEFT JOIN cached_invoices i ON i.case_id = c.id AND i.firm_id = c.firm_id
                WHERE c.firm_id = %s {attorney_filter}
                GROUP BY COALESCE(c.practice_area, 'Unknown')
                ORDER BY total_billed DESC
            """, (self.firm_id,))

            results = []
            for row in cursor.fetchall():
                billed = row['total_billed'] or 0
                collected = row['total_collected'] or 0
                rate = (collected / billed * 100) if billed > 0 else 0

                results.append(RevenueByType(
                    case_type=row['case_type'],
                    total_billed=billed,
                    total_collected=collected,
                    case_count=row['case_count'],
                    collection_rate=rate
                ))

            return results

    # =========================================================================
    # 2. Revenue per Attorney
    # =========================================================================
    def get_revenue_by_attorney(self) -> List[RevenueByAttorney]:
        """Get total revenue by lead attorney."""
        attorney_filter = self._get_attorney_filter()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT
                    COALESCE(c.lead_attorney_name, 'Unassigned') as attorney_name,
                    COUNT(DISTINCT c.id) as case_count,
                    SUM(i.total_amount) as total_billed,
                    SUM(i.paid_amount) as total_collected
                FROM cached_cases c
                LEFT JOIN cached_invoices i ON i.case_id = c.id AND i.firm_id = c.firm_id
                WHERE c.firm_id = %s {attorney_filter}
                GROUP BY COALESCE(c.lead_attorney_name, 'Unassigned')
                ORDER BY total_billed DESC
            """, (self.firm_id,))

            results = []
            for row in cursor.fetchall():
                billed = row['total_billed'] or 0
                collected = row['total_collected'] or 0
                rate = (collected / billed * 100) if billed > 0 else 0

                results.append(RevenueByAttorney(
                    attorney_name=row['attorney_name'],
                    total_billed=billed,
                    total_collected=collected,
                    case_count=row['case_count'],
                    collection_rate=rate
                ))

            return results

    # =========================================================================
    # 3. Revenue per Attorney per Month (12 months)
    # =========================================================================
    def get_revenue_by_attorney_monthly(self, months: int = 12) -> List[MonthlyRevenue]:
        """Get revenue per attorney per month for the past N months."""
        cutoff_date = (datetime.now() - timedelta(days=months * 30)).strftime('%Y-%m-%d')
        attorney_filter = self._get_attorney_filter()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT
                    COALESCE(c.lead_attorney_name, 'Unassigned') as attorney_name,
                    to_char(i.invoice_date, 'YYYY-MM') as month,
                    SUM(i.total_amount) as billed,
                    SUM(i.paid_amount) as collected
                FROM cached_invoices i
                JOIN cached_cases c ON c.id = i.case_id AND c.firm_id = i.firm_id
                WHERE i.firm_id = %s AND i.invoice_date >= %s {attorney_filter}
                GROUP BY c.lead_attorney_name, to_char(i.invoice_date, 'YYYY-MM')
                ORDER BY month DESC, attorney_name
            """, (self.firm_id, cutoff_date))

            results = []
            for row in cursor.fetchall():
                results.append(MonthlyRevenue(
                    attorney_name=row['attorney_name'],
                    month=row['month'] or 'Unknown',
                    billed=row['billed'] or 0,
                    collected=row['collected'] or 0
                ))

            return results

    # =========================================================================
    # 4. Average Case Length per Case Type
    # =========================================================================
    def get_avg_case_length_by_type(self) -> List[CaseLengthStats]:
        """Get average case length (days from open to close) by case type."""
        attorney_filter = self._get_attorney_filter()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT
                    COALESCE(practice_area, 'Unknown') as case_type,
                    AVG(date_closed::date - date_opened::date) as avg_days,
                    MIN(date_closed::date - date_opened::date) as min_days,
                    MAX(date_closed::date - date_opened::date) as max_days,
                    COUNT(*) as case_count
                FROM cached_cases c
                WHERE c.firm_id = %s
                AND status = 'closed'
                AND date_opened IS NOT NULL
                AND date_closed IS NOT NULL
                AND date_closed > date_opened
                {attorney_filter}
                GROUP BY COALESCE(practice_area, 'Unknown')
                ORDER BY avg_days DESC
            """, (self.firm_id,))

            results = []
            for row in cursor.fetchall():
                results.append(CaseLengthStats(
                    category=row['case_type'],
                    avg_days=float(row['avg_days'] or 0),
                    min_days=int(row['min_days'] or 0),
                    max_days=int(row['max_days'] or 0),
                    case_count=row['case_count']
                ))

            return results

    # =========================================================================
    # 5. Average Case Length per Case Type per Attorney
    # =========================================================================
    def get_avg_case_length_by_type_attorney(self) -> Dict[str, List[CaseLengthStats]]:
        """Get average case length by case type, grouped by attorney."""
        attorney_filter = self._get_attorney_filter()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT
                    COALESCE(lead_attorney_name, 'Unassigned') as attorney_name,
                    COALESCE(practice_area, 'Unknown') as case_type,
                    AVG(date_closed::date - date_opened::date) as avg_days,
                    MIN(date_closed::date - date_opened::date) as min_days,
                    MAX(date_closed::date - date_opened::date) as max_days,
                    COUNT(*) as case_count
                FROM cached_cases c
                WHERE c.firm_id = %s
                AND status = 'closed'
                AND date_opened IS NOT NULL
                AND date_closed IS NOT NULL
                AND date_closed > date_opened
                {attorney_filter}
                GROUP BY lead_attorney_name, COALESCE(practice_area, 'Unknown')
                ORDER BY attorney_name, avg_days DESC
            """, (self.firm_id,))

            results = defaultdict(list)
            for row in cursor.fetchall():
                results[row['attorney_name']].append(CaseLengthStats(
                    category=row['case_type'],
                    avg_days=float(row['avg_days'] or 0),
                    min_days=int(row['min_days'] or 0),
                    max_days=int(row['max_days'] or 0),
                    case_count=row['case_count']
                ))

            return dict(results)

    # =========================================================================
    # 6. Average Fee Charged per Case Type
    # =========================================================================
    def get_avg_fee_charged_by_type(self) -> List[FeeStats]:
        """Get average fee charged (total invoice amount) per case type."""
        attorney_filter = self._get_attorney_filter()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT
                    COALESCE(c.practice_area, 'Unknown') as case_type,
                    AVG(case_total.total_billed) as avg_fee_charged,
                    AVG(case_total.total_collected) as avg_fee_collected,
                    COUNT(*) as total_cases
                FROM cached_cases c
                JOIN (
                    SELECT
                        case_id, firm_id,
                        SUM(total_amount) as total_billed,
                        SUM(paid_amount) as total_collected
                    FROM cached_invoices
                    WHERE firm_id = %s
                    GROUP BY case_id, firm_id
                ) case_total ON case_total.case_id = c.id AND case_total.firm_id = c.firm_id
                WHERE c.firm_id = %s {attorney_filter}
                GROUP BY COALESCE(c.practice_area, 'Unknown')
                ORDER BY avg_fee_charged DESC
            """, (self.firm_id, self.firm_id))

            results = []
            for row in cursor.fetchall():
                results.append(FeeStats(
                    case_type=row['case_type'],
                    avg_fee_charged=float(row['avg_fee_charged'] or 0),
                    avg_fee_collected=float(row['avg_fee_collected'] or 0),
                    total_cases=row['total_cases']
                ))

            return results

    # =========================================================================
    # 7. Average Fee Collected per Case Type
    # =========================================================================
    def get_avg_fee_collected_by_type(self) -> List[FeeStats]:
        """Get average fee collected per case type."""
        return self.get_avg_fee_charged_by_type()

    # =========================================================================
    # 8. New Cases in Past 12 Months
    # =========================================================================
    def get_new_cases_past_12_months(self) -> Dict[str, int]:
        """Get count of new cases opened in the past 12 months."""
        cutoff_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        attorney_filter = self._get_attorney_filter()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total count
            cursor.execute(f"""
                SELECT COUNT(*) as total
                FROM cached_cases c
                WHERE c.firm_id = %s
                AND (date_opened >= %s OR
                    (date_opened IS NULL AND created_at >= %s))
                {attorney_filter}
            """, (self.firm_id, cutoff_date, cutoff_date))
            total = cursor.fetchone()['total']

            # Monthly breakdown
            cursor.execute(f"""
                SELECT
                    to_char(COALESCE(date_opened, created_at), 'YYYY-MM') as month,
                    COUNT(*) as count
                FROM cached_cases c
                WHERE c.firm_id = %s
                AND (date_opened >= %s OR
                    (date_opened IS NULL AND created_at >= %s))
                {attorney_filter}
                GROUP BY to_char(COALESCE(date_opened, created_at), 'YYYY-MM')
                ORDER BY month
            """, (self.firm_id, cutoff_date, cutoff_date))

            monthly = {row['month']: row['count'] for row in cursor.fetchall()}

            return {'total': total, 'monthly': monthly}

    # =========================================================================
    # 9. New Cases Since Date (e.g., Ty Start)
    # =========================================================================
    def get_new_cases_since_date(self, start_date: str) -> Dict[str, Any]:
        """Get new cases since a specific date."""
        attorney_filter = self._get_attorney_filter()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total count
            cursor.execute(f"""
                SELECT COUNT(*) as total
                FROM cached_cases c
                WHERE c.firm_id = %s
                AND (date_opened >= %s OR
                    (date_opened IS NULL AND created_at >= %s))
                {attorney_filter}
            """, (self.firm_id, start_date, start_date))
            total = cursor.fetchone()['total']

            # By case type
            cursor.execute(f"""
                SELECT
                    COALESCE(practice_area, 'Unknown') as case_type,
                    COUNT(*) as count
                FROM cached_cases c
                WHERE c.firm_id = %s
                AND (date_opened >= %s OR
                    (date_opened IS NULL AND created_at >= %s))
                {attorney_filter}
                GROUP BY COALESCE(practice_area, 'Unknown')
                ORDER BY count DESC
            """, (self.firm_id, start_date, start_date))

            by_type = {row['case_type']: row['count'] for row in cursor.fetchall()}

            return {'total': total, 'since_date': start_date, 'by_case_type': by_type}

    def get_new_cases_since_august(self, year: int = 2025) -> Dict[str, Any]:
        """Get new cases since August (legacy method for JCS)."""
        return self.get_new_cases_since_date(f"{year}-08-01")

    # =========================================================================
    # 10. Average Fee Comparison: Period vs Prior
    # =========================================================================
    def get_fee_comparison(self, period_start: str, prior_start: str, prior_end: str) -> Dict[str, Any]:
        """Compare average fees between two periods."""
        attorney_filter = self._get_attorney_filter()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Current period
            cursor.execute(f"""
                SELECT
                    COALESCE(c.practice_area, 'Unknown') as case_type,
                    AVG(case_total.total_billed) as avg_fee,
                    COUNT(*) as case_count
                FROM cached_cases c
                JOIN (
                    SELECT case_id, firm_id, SUM(total_amount) as total_billed
                    FROM cached_invoices
                    WHERE firm_id = %s
                    GROUP BY case_id, firm_id
                ) case_total ON case_total.case_id = c.id AND case_total.firm_id = c.firm_id
                WHERE c.firm_id = %s
                AND (c.date_opened >= %s OR
                    (c.date_opened IS NULL AND c.created_at >= %s))
                {attorney_filter}
                GROUP BY COALESCE(c.practice_area, 'Unknown')
            """, (self.firm_id, self.firm_id, period_start, period_start))

            current_period = {row['case_type']: {
                'avg_fee': float(row['avg_fee'] or 0),
                'case_count': row['case_count']
            } for row in cursor.fetchall()}

            # Prior period
            cursor.execute(f"""
                SELECT
                    COALESCE(c.practice_area, 'Unknown') as case_type,
                    AVG(case_total.total_billed) as avg_fee,
                    COUNT(*) as case_count
                FROM cached_cases c
                JOIN (
                    SELECT case_id, firm_id, SUM(total_amount) as total_billed
                    FROM cached_invoices
                    WHERE firm_id = %s
                    GROUP BY case_id, firm_id
                ) case_total ON case_total.case_id = c.id AND case_total.firm_id = c.firm_id
                WHERE c.firm_id = %s
                AND ((c.date_opened >= %s AND c.date_opened <= %s) OR
                    (c.date_opened IS NULL AND c.created_at >= %s AND c.created_at <= %s))
                {attorney_filter}
                GROUP BY COALESCE(c.practice_area, 'Unknown')
            """, (self.firm_id, self.firm_id, prior_start, prior_end, prior_start, prior_end))

            prior_period = {row['case_type']: {
                'avg_fee': float(row['avg_fee'] or 0),
                'case_count': row['case_count']
            } for row in cursor.fetchall()}

            # Build comparison
            all_types = set(current_period.keys()) | set(prior_period.keys())
            comparison = {}

            for case_type in all_types:
                curr = current_period.get(case_type, {'avg_fee': 0, 'case_count': 0})
                prior = prior_period.get(case_type, {'avg_fee': 0, 'case_count': 0})

                change = 0
                if prior['avg_fee'] > 0:
                    change = ((curr['avg_fee'] - prior['avg_fee']) / prior['avg_fee']) * 100

                comparison[case_type] = {
                    'current_period': curr,
                    'prior_period': prior,
                    'change_percent': change
                }

            return {
                'current_period_start': period_start,
                'prior_period': f"{prior_start} to {prior_end}",
                'comparison': comparison
            }

    def get_fee_comparison_august_vs_prior(self, year: int = 2025) -> Dict[str, Any]:
        """Compare average fees since August vs the preceding 12 months (JCS legacy)."""
        august_start = f"{year}-08-01"
        prior_start = f"{year - 1}-08-01"
        prior_end = f"{year}-07-31"
        
        result = self.get_fee_comparison(august_start, prior_start, prior_end)
        result['period_since_august'] = august_start
        return result

    # =========================================================================
    # 11. Client Count by Zip Code (Heat Map Data)
    # =========================================================================
    def get_clients_by_zip_code(self) -> Dict[str, int]:
        """Get client count by zip code from cached_clients table."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    SUBSTRING(zip_code, 1, 5) as zip,
                    COUNT(*) as client_count
                FROM cached_clients
                WHERE firm_id = %s AND zip_code IS NOT NULL AND zip_code != ''
                GROUP BY SUBSTRING(zip_code, 1, 5)
                ORDER BY client_count DESC
            """, (self.firm_id,))

            return {row['zip']: row['client_count'] for row in cursor.fetchall()}

    # =========================================================================
    # 12. Revenue by Zip Code (Heat Map Data)
    # =========================================================================
    def get_revenue_by_zip_code(self) -> Dict[str, Dict[str, Any]]:
        """Get revenue by client zip code."""
        attorney_filter = self._get_attorney_filter()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Build client_id -> zip_code mapping
            cursor.execute("""
                SELECT id, SUBSTRING(zip_code, 1, 5) as zip
                FROM cached_clients
                WHERE firm_id = %s AND zip_code IS NOT NULL AND zip_code != ''
            """, (self.firm_id,))
            client_zips = {row['id']: row['zip'] for row in cursor.fetchall()}

            # Get case-client relationships and revenue
            cursor.execute(f"""
                SELECT
                    c.id as case_id,
                    c.data_json,
                    COALESCE(SUM(i.total_amount), 0) as billed,
                    COALESCE(SUM(i.paid_amount), 0) as collected
                FROM cached_cases c
                LEFT JOIN cached_invoices i ON i.case_id = c.id AND i.firm_id = c.firm_id
                WHERE c.firm_id = %s {attorney_filter}
                GROUP BY c.id, c.data_json
            """, (self.firm_id,))

            zip_revenue = defaultdict(lambda: {'clients': set(), 'cases': 0, 'billed': 0, 'collected': 0})

            for row in cursor.fetchall():
                try:
                    case_data = json.loads(row['data_json']) if row['data_json'] else {}
                    clients = case_data.get('clients', [])
                    billing_contact = case_data.get('billing_contact', {})

                    case_zips = set()
                    for client in clients:
                        client_id = client.get('id') if isinstance(client, dict) else client
                        if client_id in client_zips:
                            case_zips.add(client_zips[client_id])

                    if billing_contact:
                        bc_id = billing_contact.get('id') if isinstance(billing_contact, dict) else billing_contact
                        if bc_id in client_zips:
                            case_zips.add(client_zips[bc_id])

                    if case_zips:
                        split_billed = (row['billed'] or 0) / len(case_zips)
                        split_collected = (row['collected'] or 0) / len(case_zips)

                        for zip_code in case_zips:
                            zip_revenue[zip_code]['cases'] += 1
                            zip_revenue[zip_code]['billed'] += split_billed
                            zip_revenue[zip_code]['collected'] += split_collected
                            for client in clients:
                                client_id = client.get('id') if isinstance(client, dict) else client
                                if client_id in client_zips and client_zips[client_id] == zip_code:
                                    zip_revenue[zip_code]['clients'].add(client_id)

                except (json.JSONDecodeError, TypeError):
                    continue

            # Convert sets to counts and add collection rate
            result = {}
            for zip_code, data in sorted(
                zip_revenue.items(),
                key=lambda x: x[1]['billed'],
                reverse=True
            ):
                rate = (data['collected'] / data['billed'] * 100) if data['billed'] > 0 else 0
                result[zip_code] = {
                    'clients': len(data['clients']),
                    'cases': data['cases'],
                    'billed': data['billed'],
                    'collected': data['collected'],
                    'collection_rate': rate
                }

            return result

    # =========================================================================
    # 13. New Cases per Month per Attorney
    # =========================================================================
    def get_new_cases_per_month_per_attorney(self, months: int = 12) -> List[NewCasesMonth]:
        """Get new cases per month for each attorney."""
        cutoff_date = (datetime.now() - timedelta(days=months * 30)).strftime('%Y-%m-%d')
        attorney_filter = self._get_attorney_filter()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT
                    to_char(COALESCE(date_opened, created_at), 'YYYY-MM') as month,
                    COALESCE(lead_attorney_name, 'Unassigned') as attorney_name,
                    COUNT(*) as case_count
                FROM cached_cases c
                WHERE c.firm_id = %s
                AND (date_opened >= %s OR
                    (date_opened IS NULL AND created_at >= %s))
                {attorney_filter}
                GROUP BY to_char(COALESCE(date_opened, created_at), 'YYYY-MM'), lead_attorney_name
                ORDER BY month DESC, case_count DESC
            """, (self.firm_id, cutoff_date, cutoff_date))

            results = []
            for row in cursor.fetchall():
                results.append(NewCasesMonth(
                    month=row['month'] or 'Unknown',
                    attorney_name=row['attorney_name'],
                    case_count=row['case_count']
                ))

            return results

    # =========================================================================
    # 14. Jurisdiction Analysis (from case names)
    # =========================================================================
    def _extract_jurisdiction(self, case_name: str) -> str:
        """Extract jurisdiction from case name."""
        if not case_name:
            return 'Unknown'

        # Counties (customize per firm's market)
        county_patterns = [
            ('St. Louis County', 'St. Louis County'),
            ('St. Charles County', 'St. Charles County'),
            ('Jefferson County', 'Jefferson County'),
            ('Franklin County', 'Franklin County'),
            ('Lincoln County', 'Lincoln County'),
            ('Warren County', 'Warren County'),
            ('Crawford County', 'Crawford County'),
            ('Phelps County', 'Phelps County'),
            ('Gasconade County', 'Gasconade County'),
            ('Cole County', 'Cole County'),
            ('Boone County', 'Boone County'),
            ('Washington County', 'Washington County'),
            ('Osage County', 'Osage County'),
            ('Madison County', 'Madison County (IL)'),
            ('St. Clair County', 'St. Clair County (IL)'),
        ]

        for pattern, jurisdiction in county_patterns:
            if pattern in case_name:
                return jurisdiction

        # St. Louis City
        if 'St. Louis City' in case_name or 'STL City' in case_name:
            return 'St. Louis City'

        # Federal
        if 'EDMO' in case_name:
            return 'Federal (EDMO)'
        if '-Federal' in case_name or ' Federal' in case_name:
            return 'Federal Court'

        return 'Other/Unknown'

    def get_cases_by_jurisdiction(self) -> Dict[str, int]:
        """Get case count by jurisdiction."""
        attorney_filter = self._get_attorney_filter()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT name FROM cached_cases c WHERE c.firm_id = %s {attorney_filter}",
                           (self.firm_id,))

            jurisdiction_counts = defaultdict(int)
            for row in cursor.fetchall():
                jurisdiction = self._extract_jurisdiction(row['name'])
                jurisdiction_counts[jurisdiction] += 1

            return dict(sorted(
                jurisdiction_counts.items(),
                key=lambda x: x[1],
                reverse=True
            ))

    def get_revenue_by_jurisdiction(self) -> Dict[str, Dict[str, float]]:
        """Get revenue by jurisdiction."""
        attorney_filter = self._get_attorney_filter()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT
                    c.name as case_name,
                    COALESCE(SUM(i.total_amount), 0) as billed,
                    COALESCE(SUM(i.paid_amount), 0) as collected
                FROM cached_cases c
                LEFT JOIN cached_invoices i ON i.case_id = c.id AND i.firm_id = c.firm_id
                WHERE c.firm_id = %s {attorney_filter}
                GROUP BY c.id, c.name
            """, (self.firm_id,))

            jurisdiction_revenue = defaultdict(lambda: {'cases': 0, 'billed': 0, 'collected': 0})

            for row in cursor.fetchall():
                jurisdiction = self._extract_jurisdiction(row['case_name'])
                jurisdiction_revenue[jurisdiction]['cases'] += 1
                jurisdiction_revenue[jurisdiction]['billed'] += row['billed'] or 0
                jurisdiction_revenue[jurisdiction]['collected'] += row['collected'] or 0

            result = {}
            for jurisdiction, data in sorted(
                jurisdiction_revenue.items(),
                key=lambda x: x[1]['billed'],
                reverse=True
            ):
                rate = (data['collected'] / data['billed'] * 100) if data['billed'] > 0 else 0
                result[jurisdiction] = {
                    'cases': data['cases'],
                    'billed': data['billed'],
                    'collected': data['collected'],
                    'collection_rate': rate
                }

            return result

    # =========================================================================
    # Full Report Generation
    # =========================================================================
    def generate_full_report(self) -> Dict[str, Any]:
        """Generate a comprehensive analytics report."""
        return {
            'generated_at': datetime.now().isoformat(),
            'firm_id': self.firm_id,
            'attorney_filter': self.attorney_id,
            'revenue_by_case_type': [vars(r) for r in self.get_revenue_by_case_type()],
            'revenue_by_attorney': [vars(r) for r in self.get_revenue_by_attorney()],
            'revenue_by_attorney_monthly': [vars(r) for r in self.get_revenue_by_attorney_monthly()],
            'avg_case_length_by_type': [vars(r) for r in self.get_avg_case_length_by_type()],
            'avg_case_length_by_type_attorney': {
                atty: [vars(s) for s in stats]
                for atty, stats in self.get_avg_case_length_by_type_attorney().items()
            },
            'avg_fee_by_type': [vars(r) for r in self.get_avg_fee_charged_by_type()],
            'new_cases_12_months': self.get_new_cases_past_12_months(),
            'cases_by_jurisdiction': self.get_cases_by_jurisdiction(),
            'revenue_by_jurisdiction': self.get_revenue_by_jurisdiction(),
            'clients_by_zip_code': self.get_clients_by_zip_code(),
            'revenue_by_zip_code': self.get_revenue_by_zip_code(),
            'new_cases_per_month_per_attorney': [vars(r) for r in self.get_new_cases_per_month_per_attorney()],
        }


# =============================================================================
# Formatting Utilities
# =============================================================================
def format_currency(amount: float) -> str:
    """Format as currency."""
    return f"${amount:,.2f}"


def format_percent(value: float) -> str:
    """Format as percentage."""
    return f"{value:.1f}%"


# =============================================================================
# Factory Function
# =============================================================================
def get_analytics(firm_id: str = None, attorney_id: int = None) -> FirmAnalytics:
    """
    Get an analytics instance for a firm.
    
    Args:
        firm_id: The firm ID. If None, uses current tenant context.
        attorney_id: If set, filter to this attorney's cases only.
        
    Returns:
        FirmAnalytics instance
    """
    return FirmAnalytics(firm_id=firm_id, attorney_id=attorney_id)


if __name__ == "__main__":
    # Test run
    import sys
    firm_id = sys.argv[1] if len(sys.argv) > 1 else None
    
    analytics = FirmAnalytics(firm_id=firm_id)
    print(f"Analytics initialized for firm: {analytics.firm_id}")
    
    # Quick test
    revenue = analytics.get_revenue_by_case_type()
    print(f"\nTop 5 case types by revenue:")
    for r in revenue[:5]:
        print(f"  {r.case_type}: {format_currency(r.total_billed)}")
