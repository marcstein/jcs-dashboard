"""
Firm Analytics Module

Comprehensive analytics and reporting for JCS Law Firm:
1. Revenue per case type
2. Revenue per attorney
3. Revenue per attorney per month (12 months)
4. Average case length per case type
5. Average case length per case type per attorney
6. Average fee charged per case type
7. Average fee collected per case type
8. New cases in past 12 months
9. New cases since August (Ty start)
10. Average fee comparison: Since August vs preceding 12 months
11. Client zip code heat map (requires address data)
12. Revenue per zip code heat map (requires address data)
13. New cases per month per attorney
14. Positive reviews - primary staff analysis (requires review data)
"""
import sqlite3
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from collections import defaultdict
from dataclasses import dataclass

from config import DATA_DIR


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
    Analytics engine for JCS Law Firm.

    Uses cached MyCase data to generate comprehensive reports.
    """

    def __init__(self, cache_path: Path = None):
        self.cache_path = cache_path or DATA_DIR / "mycase_cache.db"

    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.cache_path)
        conn.row_factory = sqlite3.Row
        return conn

    # =========================================================================
    # 1. Revenue per Case Type
    # =========================================================================
    def get_revenue_by_case_type(self) -> List[RevenueByType]:
        """
        Get total revenue (billed and collected) by case type/practice area.

        Returns:
            List of RevenueByType objects sorted by total billed descending
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COALESCE(c.practice_area, 'Unknown') as case_type,
                    COUNT(DISTINCT c.id) as case_count,
                    SUM(i.total_amount) as total_billed,
                    SUM(i.paid_amount) as total_collected
                FROM cached_cases c
                LEFT JOIN cached_invoices i ON i.case_id = c.id
                GROUP BY COALESCE(c.practice_area, 'Unknown')
                ORDER BY total_billed DESC
            """)

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
        """
        Get total revenue by lead attorney.

        Returns:
            List of RevenueByAttorney objects sorted by total billed descending
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COALESCE(c.lead_attorney_name, 'Unassigned') as attorney_name,
                    COUNT(DISTINCT c.id) as case_count,
                    SUM(i.total_amount) as total_billed,
                    SUM(i.paid_amount) as total_collected
                FROM cached_cases c
                LEFT JOIN cached_invoices i ON i.case_id = c.id
                GROUP BY COALESCE(c.lead_attorney_name, 'Unassigned')
                ORDER BY total_billed DESC
            """)

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
        """
        Get revenue per attorney per month for the past N months.

        Args:
            months: Number of months to include (default 12)

        Returns:
            List of MonthlyRevenue objects
        """
        cutoff_date = (datetime.now() - timedelta(days=months * 30)).strftime('%Y-%m-%d')

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COALESCE(c.lead_attorney_name, 'Unassigned') as attorney_name,
                    strftime('%Y-%m', i.invoice_date) as month,
                    SUM(i.total_amount) as billed,
                    SUM(i.paid_amount) as collected
                FROM cached_invoices i
                JOIN cached_cases c ON c.id = i.case_id
                WHERE i.invoice_date >= ?
                GROUP BY c.lead_attorney_name, strftime('%Y-%m', i.invoice_date)
                ORDER BY month DESC, attorney_name
            """, (cutoff_date,))

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
        """
        Get average case length (days from open to close) by case type.
        Only includes closed cases.

        Returns:
            List of CaseLengthStats objects
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COALESCE(practice_area, 'Unknown') as case_type,
                    AVG(julianday(date_closed) - julianday(date_opened)) as avg_days,
                    MIN(julianday(date_closed) - julianday(date_opened)) as min_days,
                    MAX(julianday(date_closed) - julianday(date_opened)) as max_days,
                    COUNT(*) as case_count
                FROM cached_cases
                WHERE status = 'closed'
                AND date_opened IS NOT NULL
                AND date_closed IS NOT NULL
                AND date_closed > date_opened
                GROUP BY COALESCE(practice_area, 'Unknown')
                ORDER BY avg_days DESC
            """)

            results = []
            for row in cursor.fetchall():
                results.append(CaseLengthStats(
                    category=row['case_type'],
                    avg_days=row['avg_days'] or 0,
                    min_days=int(row['min_days'] or 0),
                    max_days=int(row['max_days'] or 0),
                    case_count=row['case_count']
                ))

            return results

    # =========================================================================
    # 5. Average Case Length per Case Type per Attorney
    # =========================================================================
    def get_avg_case_length_by_type_attorney(self) -> Dict[str, List[CaseLengthStats]]:
        """
        Get average case length by case type, grouped by attorney.

        Returns:
            Dict of attorney name -> List of CaseLengthStats
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COALESCE(lead_attorney_name, 'Unassigned') as attorney_name,
                    COALESCE(practice_area, 'Unknown') as case_type,
                    AVG(julianday(date_closed) - julianday(date_opened)) as avg_days,
                    MIN(julianday(date_closed) - julianday(date_opened)) as min_days,
                    MAX(julianday(date_closed) - julianday(date_opened)) as max_days,
                    COUNT(*) as case_count
                FROM cached_cases
                WHERE status = 'closed'
                AND date_opened IS NOT NULL
                AND date_closed IS NOT NULL
                AND date_closed > date_opened
                GROUP BY lead_attorney_name, COALESCE(practice_area, 'Unknown')
                ORDER BY attorney_name, avg_days DESC
            """)

            results = defaultdict(list)
            for row in cursor.fetchall():
                results[row['attorney_name']].append(CaseLengthStats(
                    category=row['case_type'],
                    avg_days=row['avg_days'] or 0,
                    min_days=int(row['min_days'] or 0),
                    max_days=int(row['max_days'] or 0),
                    case_count=row['case_count']
                ))

            return dict(results)

    # =========================================================================
    # 6. Average Fee Charged per Case Type
    # =========================================================================
    def get_avg_fee_charged_by_type(self) -> List[FeeStats]:
        """
        Get average fee charged (total invoice amount) per case type.

        Returns:
            List of FeeStats objects
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COALESCE(c.practice_area, 'Unknown') as case_type,
                    AVG(case_total.total_billed) as avg_fee_charged,
                    AVG(case_total.total_collected) as avg_fee_collected,
                    COUNT(*) as total_cases
                FROM cached_cases c
                JOIN (
                    SELECT
                        case_id,
                        SUM(total_amount) as total_billed,
                        SUM(paid_amount) as total_collected
                    FROM cached_invoices
                    GROUP BY case_id
                ) case_total ON case_total.case_id = c.id
                GROUP BY COALESCE(c.practice_area, 'Unknown')
                ORDER BY avg_fee_charged DESC
            """)

            results = []
            for row in cursor.fetchall():
                results.append(FeeStats(
                    case_type=row['case_type'],
                    avg_fee_charged=row['avg_fee_charged'] or 0,
                    avg_fee_collected=row['avg_fee_collected'] or 0,
                    total_cases=row['total_cases']
                ))

            return results

    # =========================================================================
    # 7. Average Fee Collected per Case Type
    # =========================================================================
    def get_avg_fee_collected_by_type(self) -> List[FeeStats]:
        """
        Get average fee collected per case type.
        (This is included in get_avg_fee_charged_by_type, but separate method for clarity)
        """
        return self.get_avg_fee_charged_by_type()

    # =========================================================================
    # 8. New Cases in Past 12 Months
    # =========================================================================
    def get_new_cases_past_12_months(self) -> Dict[str, int]:
        """
        Get count of new cases opened in the past 12 months.

        Returns:
            Dict with 'total' and monthly breakdown
        """
        cutoff_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM cached_cases
                WHERE date_opened >= ? OR
                      (date_opened IS NULL AND created_at >= ?)
            """, (cutoff_date, cutoff_date))
            total = cursor.fetchone()['total']

            # Monthly breakdown
            cursor.execute("""
                SELECT
                    strftime('%Y-%m', COALESCE(date_opened, created_at)) as month,
                    COUNT(*) as count
                FROM cached_cases
                WHERE date_opened >= ? OR
                      (date_opened IS NULL AND created_at >= ?)
                GROUP BY strftime('%Y-%m', COALESCE(date_opened, created_at))
                ORDER BY month
            """, (cutoff_date, cutoff_date))

            monthly = {row['month']: row['count'] for row in cursor.fetchall()}

            return {'total': total, 'monthly': monthly}

    # =========================================================================
    # 9. New Cases Since August (Ty Start)
    # =========================================================================
    def get_new_cases_since_august(self, year: int = 2025) -> Dict[str, Any]:
        """
        Get new cases since August (when Ty started).

        Args:
            year: The year Ty started (default 2025)

        Returns:
            Dict with total and breakdown by case type
        """
        start_date = f"{year}-08-01"

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM cached_cases
                WHERE date_opened >= ? OR
                      (date_opened IS NULL AND created_at >= ?)
            """, (start_date, start_date))
            total = cursor.fetchone()['total']

            # By case type
            cursor.execute("""
                SELECT
                    COALESCE(practice_area, 'Unknown') as case_type,
                    COUNT(*) as count
                FROM cached_cases
                WHERE date_opened >= ? OR
                      (date_opened IS NULL AND created_at >= ?)
                GROUP BY COALESCE(practice_area, 'Unknown')
                ORDER BY count DESC
            """, (start_date, start_date))

            by_type = {row['case_type']: row['count'] for row in cursor.fetchall()}

            return {'total': total, 'since_date': start_date, 'by_case_type': by_type}

    # =========================================================================
    # 10. Average Fee Comparison: Since August vs Preceding 12 Months
    # =========================================================================
    def get_fee_comparison_august_vs_prior(self, year: int = 2025) -> Dict[str, Any]:
        """
        Compare average fees charged since August vs the preceding 12 months.

        Args:
            year: The year to use for August cutoff

        Returns:
            Dict with comparison data by case type
        """
        august_start = f"{year}-08-01"
        prior_start = f"{year - 1}-08-01"
        prior_end = f"{year}-07-31"

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Since August
            cursor.execute("""
                SELECT
                    COALESCE(c.practice_area, 'Unknown') as case_type,
                    AVG(case_total.total_billed) as avg_fee,
                    COUNT(*) as case_count
                FROM cached_cases c
                JOIN (
                    SELECT case_id, SUM(total_amount) as total_billed
                    FROM cached_invoices
                    GROUP BY case_id
                ) case_total ON case_total.case_id = c.id
                WHERE c.date_opened >= ? OR
                      (c.date_opened IS NULL AND c.created_at >= ?)
                GROUP BY COALESCE(c.practice_area, 'Unknown')
            """, (august_start, august_start))

            since_august = {row['case_type']: {
                'avg_fee': row['avg_fee'] or 0,
                'case_count': row['case_count']
            } for row in cursor.fetchall()}

            # Prior 12 months
            cursor.execute("""
                SELECT
                    COALESCE(c.practice_area, 'Unknown') as case_type,
                    AVG(case_total.total_billed) as avg_fee,
                    COUNT(*) as case_count
                FROM cached_cases c
                JOIN (
                    SELECT case_id, SUM(total_amount) as total_billed
                    FROM cached_invoices
                    GROUP BY case_id
                ) case_total ON case_total.case_id = c.id
                WHERE (c.date_opened >= ? AND c.date_opened <= ?) OR
                      (c.date_opened IS NULL AND c.created_at >= ? AND c.created_at <= ?)
                GROUP BY COALESCE(c.practice_area, 'Unknown')
            """, (prior_start, prior_end, prior_start, prior_end))

            prior_period = {row['case_type']: {
                'avg_fee': row['avg_fee'] or 0,
                'case_count': row['case_count']
            } for row in cursor.fetchall()}

            # Build comparison
            all_types = set(since_august.keys()) | set(prior_period.keys())
            comparison = {}

            for case_type in all_types:
                aug = since_august.get(case_type, {'avg_fee': 0, 'case_count': 0})
                prior = prior_period.get(case_type, {'avg_fee': 0, 'case_count': 0})

                change = 0
                if prior['avg_fee'] > 0:
                    change = ((aug['avg_fee'] - prior['avg_fee']) / prior['avg_fee']) * 100

                comparison[case_type] = {
                    'since_august': aug,
                    'prior_12_months': prior,
                    'change_percent': change
                }

            return {
                'period_since_august': august_start,
                'prior_period': f"{prior_start} to {prior_end}",
                'comparison': comparison
            }

    # =========================================================================
    # 11. Cases by Jurisdiction (Alternative to Zip Code)
    # =========================================================================
    def _extract_jurisdiction(self, case_name: str) -> str:
        """Extract jurisdiction from case name."""
        if not case_name:
            return 'Unknown'

        # Counties
        if 'St. Louis County' in case_name:
            return 'St. Louis County'
        if 'St. Charles County' in case_name:
            return 'St. Charles County'
        if 'Jefferson County' in case_name:
            return 'Jefferson County'
        if 'Franklin County' in case_name:
            return 'Franklin County'
        if 'Lincoln County' in case_name:
            return 'Lincoln County'
        if 'Warren County' in case_name:
            return 'Warren County'
        if 'Crawford County' in case_name:
            return 'Crawford County'
        if 'Phelps County' in case_name:
            return 'Phelps County'
        if 'Gasconade County' in case_name:
            return 'Gasconade County'
        if 'Cole County' in case_name:
            return 'Cole County'
        if 'Boone County' in case_name:
            return 'Boone County'
        if 'Washington County' in case_name:
            return 'Washington County'
        if 'Osage County' in case_name:
            return 'Osage County'
        if 'Madison County' in case_name:
            return 'Madison County (IL)'
        if 'St. Clair County' in case_name:
            return 'St. Clair County (IL)'

        # St. Louis City variants
        if 'St. Louis City' in case_name or 'STL City' in case_name:
            return 'St. Louis City'

        # Federal
        if 'EDMO' in case_name:
            return 'Federal (EDMO)'
        if '-Federal' in case_name or ' Federal' in case_name:
            return 'Federal Court'

        # Municipalities
        municipalities = [
            'Webster Groves', 'Ballwin', 'Florissant', 'Hazelwood',
            'University City', 'Town & Country', 'Frontenac', 'Wentzville',
            'Sullivan', 'Pevely', 'Clayton', 'Creve Coeur', 'Chesterfield',
            'Maryland Heights', 'Kirkwood', 'Olivette', 'Overland',
            'Ferguson', 'Berkeley', 'Bridgeton', 'Normandy', 'Pagedale',
            'Brentwood', 'Maplewood', 'Richmond Heights', 'Rock Hill',
            'Shrewsbury', 'Des Peres', 'Manchester', 'Ellisville',
            'Eureka', 'Pacific', 'Union', 'Washington', 'O\'Fallon',
            "O'Fallon", 'St. Peters', 'Lake St. Louis', 'Cottleville'
        ]

        for muni in municipalities:
            if muni in case_name:
                return f'{muni} Muni'

        return 'Other/Unknown'

    def get_cases_by_jurisdiction(self) -> Dict[str, int]:
        """
        Get case count by jurisdiction (extracted from case names).

        Since the MyCase API doesn't provide client addresses, we extract
        jurisdiction from case names which typically include court/county info.

        Returns:
            Dict of jurisdiction -> case_count
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM cached_cases")

            jurisdiction_counts = defaultdict(int)
            for row in cursor.fetchall():
                jurisdiction = self._extract_jurisdiction(row['name'])
                jurisdiction_counts[jurisdiction] += 1

            # Sort by count descending
            return dict(sorted(
                jurisdiction_counts.items(),
                key=lambda x: x[1],
                reverse=True
            ))

    # =========================================================================
    # 12. Revenue by Jurisdiction
    # =========================================================================
    def get_revenue_by_jurisdiction(self) -> Dict[str, Dict[str, float]]:
        """
        Get revenue by jurisdiction.

        Returns:
            Dict of jurisdiction -> {cases, billed, collected, collection_rate}
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    c.name as case_name,
                    COALESCE(SUM(i.total_amount), 0) as billed,
                    COALESCE(SUM(i.paid_amount), 0) as collected
                FROM cached_cases c
                LEFT JOIN cached_invoices i ON i.case_id = c.id
                GROUP BY c.id, c.name
            """)

            jurisdiction_revenue = defaultdict(lambda: {'cases': 0, 'billed': 0, 'collected': 0})

            for row in cursor.fetchall():
                jurisdiction = self._extract_jurisdiction(row['case_name'])
                jurisdiction_revenue[jurisdiction]['cases'] += 1
                jurisdiction_revenue[jurisdiction]['billed'] += row['billed'] or 0
                jurisdiction_revenue[jurisdiction]['collected'] += row['collected'] or 0

            # Add collection rate and sort
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
    # 11b. Client Count by Zip Code (Heat Map Data)
    # =========================================================================
    def get_clients_by_zip_code(self) -> Dict[str, int]:
        """
        Get client count by zip code from cached_clients table.

        Returns:
            Dict of zip_code -> client_count, sorted by count descending
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    SUBSTR(zip_code, 1, 5) as zip,
                    COUNT(*) as client_count
                FROM cached_clients
                WHERE zip_code IS NOT NULL AND zip_code != ''
                GROUP BY SUBSTR(zip_code, 1, 5)
                ORDER BY client_count DESC
            """)

            return {row['zip']: row['client_count'] for row in cursor.fetchall()}

    # =========================================================================
    # 12b. Revenue by Zip Code (Heat Map Data)
    # =========================================================================
    def get_revenue_by_zip_code(self) -> Dict[str, Dict[str, Any]]:
        """
        Get revenue by client zip code.

        Links clients to cases via the case-client relationship in data_json,
        then aggregates invoice data.

        Returns:
            Dict of zip_code -> {clients, cases, billed, collected, collection_rate}
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # First, build a mapping of client_id -> zip_code
            cursor.execute("""
                SELECT id, SUBSTR(zip_code, 1, 5) as zip
                FROM cached_clients
                WHERE zip_code IS NOT NULL AND zip_code != ''
            """)
            client_zips = {row['id']: row['zip'] for row in cursor.fetchall()}

            # Get case-client relationships and revenue
            cursor.execute("""
                SELECT
                    c.id as case_id,
                    c.data_json,
                    COALESCE(SUM(i.total_amount), 0) as billed,
                    COALESCE(SUM(i.paid_amount), 0) as collected
                FROM cached_cases c
                LEFT JOIN cached_invoices i ON i.case_id = c.id
                GROUP BY c.id
            """)

            zip_revenue = defaultdict(lambda: {'clients': set(), 'cases': 0, 'billed': 0, 'collected': 0})

            for row in cursor.fetchall():
                try:
                    case_data = json.loads(row['data_json']) if row['data_json'] else {}
                    # Get clients from case data
                    clients = case_data.get('clients', [])
                    billing_contact = case_data.get('billing_contact', {})

                    # Find zip codes for this case's clients
                    case_zips = set()
                    for client in clients:
                        client_id = client.get('id') if isinstance(client, dict) else client
                        if client_id in client_zips:
                            case_zips.add(client_zips[client_id])

                    # Also check billing contact
                    if billing_contact:
                        bc_id = billing_contact.get('id') if isinstance(billing_contact, dict) else billing_contact
                        if bc_id in client_zips:
                            case_zips.add(client_zips[bc_id])

                    # Attribute revenue to each zip (split evenly if multiple)
                    if case_zips:
                        split_billed = (row['billed'] or 0) / len(case_zips)
                        split_collected = (row['collected'] or 0) / len(case_zips)

                        for zip_code in case_zips:
                            zip_revenue[zip_code]['cases'] += 1
                            zip_revenue[zip_code]['billed'] += split_billed
                            zip_revenue[zip_code]['collected'] += split_collected
                            # Track unique clients
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
        """
        Get new cases per month for each attorney.

        Args:
            months: Number of months to include

        Returns:
            List of NewCasesMonth objects
        """
        cutoff_date = (datetime.now() - timedelta(days=months * 30)).strftime('%Y-%m-%d')

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    strftime('%Y-%m', COALESCE(date_opened, created_at)) as month,
                    COALESCE(lead_attorney_name, 'Unassigned') as attorney_name,
                    COUNT(*) as case_count
                FROM cached_cases
                WHERE date_opened >= ? OR
                      (date_opened IS NULL AND created_at >= ?)
                GROUP BY strftime('%Y-%m', COALESCE(date_opened, created_at)), lead_attorney_name
                ORDER BY month DESC, case_count DESC
            """, (cutoff_date, cutoff_date))

            results = []
            for row in cursor.fetchall():
                results.append(NewCasesMonth(
                    month=row['month'] or 'Unknown',
                    attorney_name=row['attorney_name'],
                    case_count=row['case_count']
                ))

            return results

    # =========================================================================
    # 14. Positive Reviews - Primary Staff Analysis
    # =========================================================================
    def get_positive_reviews_staff(self) -> Dict[str, Any]:
        """
        Analyze which staff members primarily worked with clients who left positive reviews.

        NOTE: This requires review data which is typically not in MyCase.
        Reviews are usually on external platforms (Google, Avvo, etc.).
        Would need to manually link review client names to cases.

        Returns:
            Dict with note about data availability
        """
        return {
            '_note': 'Review data not available in MyCase cache. '
                     'Reviews are typically on external platforms (Google, Avvo). '
                     'To analyze: export review client names, match to cases, '
                     'then identify staff from case assignments.'
        }

    # =========================================================================
    # Full Report Generation
    # =========================================================================
    def generate_full_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive analytics report.

        Returns:
            Dict with all analytics data
        """
        return {
            'generated_at': datetime.now().isoformat(),
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
            'new_cases_since_august': self.get_new_cases_since_august(),
            'fee_comparison_august_vs_prior': self.get_fee_comparison_august_vs_prior(),
            'cases_by_jurisdiction': self.get_cases_by_jurisdiction(),
            'revenue_by_jurisdiction': self.get_revenue_by_jurisdiction(),
            'clients_by_zip_code': self.get_clients_by_zip_code(),
            'revenue_by_zip_code': self.get_revenue_by_zip_code(),
            'new_cases_per_month_per_attorney': [vars(r) for r in self.get_new_cases_per_month_per_attorney()],
            'positive_reviews_staff': self.get_positive_reviews_staff()
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
# CLI Report Printer
# =============================================================================
def print_full_report(analytics: FirmAnalytics):
    """Print a formatted analytics report to console."""

    print("\n" + "=" * 70)
    print("JCS LAW FIRM - COMPREHENSIVE ANALYTICS REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 1. Revenue by Case Type
    print("\n1. REVENUE BY CASE TYPE")
    print("-" * 50)
    print(f"{'Case Type':<25} {'Billed':>12} {'Collected':>12} {'Rate':>8}")
    print("-" * 50)
    for r in analytics.get_revenue_by_case_type()[:15]:
        print(f"{r.case_type:<25} {format_currency(r.total_billed):>12} "
              f"{format_currency(r.total_collected):>12} {format_percent(r.collection_rate):>8}")

    # 2. Revenue by Attorney
    print("\n2. REVENUE BY ATTORNEY")
    print("-" * 50)
    print(f"{'Attorney':<25} {'Billed':>12} {'Collected':>12} {'Cases':>8}")
    print("-" * 50)
    for r in analytics.get_revenue_by_attorney():
        print(f"{r.attorney_name:<25} {format_currency(r.total_billed):>12} "
              f"{format_currency(r.total_collected):>12} {r.case_count:>8}")

    # 3. Revenue by Attorney Monthly (last 3 months sample)
    print("\n3. REVENUE BY ATTORNEY (Last 3 Months)")
    print("-" * 50)
    monthly = analytics.get_revenue_by_attorney_monthly(3)
    current_month = None
    for r in monthly:
        if r.month != current_month:
            current_month = r.month
            print(f"\n  {current_month}:")
        print(f"    {r.attorney_name:<20} Billed: {format_currency(r.billed):>10} "
              f"Collected: {format_currency(r.collected):>10}")

    # 4. Average Case Length by Type
    print("\n4. AVERAGE CASE LENGTH BY CASE TYPE (Closed Cases)")
    print("-" * 50)
    print(f"{'Case Type':<25} {'Avg Days':>10} {'Min':>8} {'Max':>8} {'Count':>8}")
    print("-" * 50)
    for r in analytics.get_avg_case_length_by_type()[:15]:
        print(f"{r.category:<25} {r.avg_days:>10.1f} {r.min_days:>8} {r.max_days:>8} {r.case_count:>8}")

    # 5. Case Length by Type per Attorney (summarized)
    print("\n5. CASE LENGTH BY TYPE PER ATTORNEY (Top Attorneys)")
    print("-" * 50)
    by_atty = analytics.get_avg_case_length_by_type_attorney()
    for atty in list(by_atty.keys())[:5]:
        print(f"\n  {atty}:")
        for s in by_atty[atty][:3]:
            print(f"    {s.category:<20} Avg: {s.avg_days:.1f} days ({s.case_count} cases)")

    # 6. Average Fee by Case Type
    print("\n6. AVERAGE FEE CHARGED & COLLECTED BY CASE TYPE")
    print("-" * 50)
    print(f"{'Case Type':<25} {'Avg Charged':>12} {'Avg Collected':>14} {'Cases':>8}")
    print("-" * 50)
    for r in analytics.get_avg_fee_charged_by_type()[:15]:
        print(f"{r.case_type:<25} {format_currency(r.avg_fee_charged):>12} "
              f"{format_currency(r.avg_fee_collected):>14} {r.total_cases:>8}")

    # 8. New Cases Past 12 Months
    print("\n8. NEW CASES - PAST 12 MONTHS")
    print("-" * 50)
    new_12 = analytics.get_new_cases_past_12_months()
    print(f"  Total New Cases: {new_12['total']}")
    print("  Monthly Breakdown:")
    for month, count in sorted(new_12['monthly'].items()):
        print(f"    {month}: {count} cases")

    # 9. New Cases Since August
    print("\n9. NEW CASES SINCE AUGUST (Ty Start)")
    print("-" * 50)
    new_aug = analytics.get_new_cases_since_august()
    print(f"  Since: {new_aug['since_date']}")
    print(f"  Total: {new_aug['total']} new cases")
    print("  By Case Type:")
    for ct, count in list(new_aug['by_case_type'].items())[:10]:
        print(f"    {ct}: {count}")

    # 10. Fee Comparison
    print("\n10. AVERAGE FEE COMPARISON: Since August vs Prior 12 Months")
    print("-" * 60)
    comp = analytics.get_fee_comparison_august_vs_prior()
    print(f"  Since August: {comp['period_since_august']}")
    print(f"  Prior Period: {comp['prior_period']}")
    print(f"\n  {'Case Type':<25} {'Since Aug':>12} {'Prior':>12} {'Change':>10}")
    print("  " + "-" * 55)
    for ct, data in list(comp['comparison'].items())[:10]:
        aug_fee = data['since_august']['avg_fee']
        prior_fee = data['prior_12_months']['avg_fee']
        change = data['change_percent']
        change_str = f"{change:+.1f}%" if change != 0 else "N/A"
        print(f"  {ct:<25} {format_currency(aug_fee):>12} {format_currency(prior_fee):>12} {change_str:>10}")

    # 11. Cases by Jurisdiction
    print("\n11. CASES BY JURISDICTION")
    print("-" * 50)
    print(f"{'Jurisdiction':<30} {'Cases':>8}")
    print("-" * 50)
    for jurisdiction, count in list(analytics.get_cases_by_jurisdiction().items())[:20]:
        print(f"{jurisdiction:<30} {count:>8}")

    # 12. Revenue by Jurisdiction
    print("\n12. REVENUE BY JURISDICTION")
    print("-" * 60)
    print(f"{'Jurisdiction':<25} {'Cases':>6} {'Billed':>12} {'Collected':>12} {'Rate':>8}")
    print("-" * 60)
    for jurisdiction, data in list(analytics.get_revenue_by_jurisdiction().items())[:15]:
        print(f"{jurisdiction:<25} {data['cases']:>6} {format_currency(data['billed']):>12} "
              f"{format_currency(data['collected']):>12} {format_percent(data['collection_rate']):>8}")

    # 13. Clients by Zip Code
    print("\n13. CLIENTS BY ZIP CODE (Top 20)")
    print("-" * 30)
    print(f"{'Zip Code':<12} {'Clients':>8}")
    print("-" * 30)
    zip_clients = analytics.get_clients_by_zip_code()
    if zip_clients:
        for zip_code, count in list(zip_clients.items())[:20]:
            print(f"{zip_code:<12} {count:>8}")
    else:
        print("  No zip code data - run 'sync.py clients' first")

    # 14. Revenue by Zip Code
    print("\n14. REVENUE BY ZIP CODE (Top 15)")
    print("-" * 70)
    print(f"{'Zip Code':<10} {'Clients':>8} {'Cases':>6} {'Billed':>12} {'Collected':>12} {'Rate':>8}")
    print("-" * 70)
    zip_revenue = analytics.get_revenue_by_zip_code()
    if zip_revenue:
        for zip_code, data in list(zip_revenue.items())[:15]:
            print(f"{zip_code:<10} {data['clients']:>8} {data['cases']:>6} "
                  f"{format_currency(data['billed']):>12} {format_currency(data['collected']):>12} "
                  f"{format_percent(data['collection_rate']):>8}")
    else:
        print("  No zip code data - run 'sync.py clients' first")

    # 15. New Cases per Month per Attorney
    print("\n15. NEW CASES PER MONTH PER ATTORNEY (Last 6 Months)")
    print("-" * 50)
    cases_monthly = analytics.get_new_cases_per_month_per_attorney(6)
    current_month = None
    for r in cases_monthly:
        if r.month != current_month:
            current_month = r.month
            print(f"\n  {current_month}:")
        print(f"    {r.attorney_name:<25} {r.case_count} cases")

    # 16. Positive Reviews
    print("\n16. POSITIVE REVIEWS - STAFF ANALYSIS")
    print("-" * 50)
    reviews = analytics.get_positive_reviews_staff()
    print(f"  Note: {reviews['_note']}")

    print("\n" + "=" * 70)
    print("END OF REPORT")
    print("=" * 70)


if __name__ == "__main__":
    analytics = FirmAnalytics()
    print_full_report(analytics)
