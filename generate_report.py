#!/usr/bin/env python
"""Generate markdown analytics report."""

from firm_analytics import FirmAnalytics, format_currency, format_percent
from datetime import datetime
from pathlib import Path


def generate_markdown_report(output_path: str = None) -> str:
    """Generate a comprehensive markdown analytics report."""

    analytics = FirmAnalytics()

    md = []
    md.append('# JCS Law Firm - Comprehensive Analytics Report')
    md.append(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    md.append('')

    # 1. Revenue by Case Type
    md.append('## 1. Revenue by Case Type')
    md.append('')
    md.append('| Case Type | Cases | Billed | Collected | Rate |')
    md.append('|-----------|------:|-------:|----------:|-----:|')
    for r in analytics.get_revenue_by_case_type():
        md.append(f'| {r.case_type} | {r.case_count} | {format_currency(r.total_billed)} | {format_currency(r.total_collected)} | {format_percent(r.collection_rate)} |')
    md.append('')

    # 2. Revenue by Attorney
    md.append('## 2. Revenue by Attorney')
    md.append('')
    md.append('| Attorney | Cases | Billed | Collected | Rate |')
    md.append('|----------|------:|-------:|----------:|-----:|')
    for r in analytics.get_revenue_by_attorney():
        md.append(f'| {r.attorney_name} | {r.case_count} | {format_currency(r.total_billed)} | {format_currency(r.total_collected)} | {format_percent(r.collection_rate)} |')
    md.append('')

    # 3. Revenue by Attorney Monthly
    md.append('## 3. Revenue by Attorney (Last 12 Months)')
    md.append('')
    md.append('| Month | Attorney | Billed | Collected |')
    md.append('|-------|----------|-------:|----------:|')
    for r in analytics.get_revenue_by_attorney_monthly(12):
        md.append(f'| {r.month} | {r.attorney_name} | {format_currency(r.billed)} | {format_currency(r.collected)} |')
    md.append('')

    # 4. Average Case Length
    md.append('## 4. Average Case Length by Type')
    md.append('')
    results = analytics.get_avg_case_length_by_type()
    if results:
        md.append('| Case Type | Avg Days | Min | Max | Cases |')
        md.append('|-----------|:--------:|----:|----:|------:|')
        for r in results:
            md.append(f'| {r.category} | {r.avg_days:.1f} | {r.min_days} | {r.max_days} | {r.case_count} |')
    else:
        md.append('*Limited data - most cases still open or missing close dates.*')
    md.append('')

    # 5. Average Fees
    md.append('## 5. Average Fee by Case Type')
    md.append('')
    md.append('| Case Type | Cases | Avg Charged | Avg Collected |')
    md.append('|-----------|------:|------------:|--------------:|')
    for r in analytics.get_avg_fee_charged_by_type():
        md.append(f'| {r.case_type} | {r.total_cases} | {format_currency(r.avg_fee_charged)} | {format_currency(r.avg_fee_collected)} |')
    md.append('')

    # 6. New Cases Past 12 Months
    md.append('## 6. New Cases - Past 12 Months')
    md.append('')
    new_cases = analytics.get_new_cases_past_12_months()
    md.append(f'**Total New Cases:** {new_cases["total"]}')
    md.append('')
    md.append('| Month | Cases |')
    md.append('|-------|------:|')
    for month, count in sorted(new_cases['monthly'].items()):
        md.append(f'| {month} | {count} |')
    md.append('')

    # 7. New Cases Since August
    md.append('## 7. New Cases Since August (Ty Start)')
    md.append('')
    aug_cases = analytics.get_new_cases_since_august()
    md.append(f'**Since:** {aug_cases["since_date"]}')
    md.append(f'**Total:** {aug_cases["total"]} cases')
    md.append('')
    md.append('| Case Type | Cases |')
    md.append('|-----------|------:|')
    for ct, count in aug_cases['by_case_type'].items():
        md.append(f'| {ct} | {count} |')
    md.append('')

    # 8. Fee Comparison
    md.append('## 8. Fee Comparison: Since August vs Prior 12 Months')
    md.append('')
    comp = analytics.get_fee_comparison_august_vs_prior()
    md.append(f'- **Since August:** {comp["period_since_august"]}')
    md.append(f'- **Prior Period:** {comp["prior_period"]}')
    md.append('')
    md.append('| Case Type | Since Aug | Prior | Change |')
    md.append('|-----------|----------:|------:|-------:|')
    for ct, data in comp['comparison'].items():
        aug_fee = data['since_august']['avg_fee']
        prior_fee = data['prior_12_months']['avg_fee']
        change = data['change_percent']
        if change != 0:
            change_str = f'{change:+.1f}%'
        else:
            change_str = 'N/A'
        md.append(f'| {ct} | {format_currency(aug_fee)} | {format_currency(prior_fee)} | {change_str} |')
    md.append('')

    # 9. Cases by Jurisdiction
    md.append('## 9. Cases by Jurisdiction')
    md.append('')
    md.append('| Jurisdiction | Cases |')
    md.append('|--------------|------:|')
    for jurisdiction, count in list(analytics.get_cases_by_jurisdiction().items())[:25]:
        md.append(f'| {jurisdiction} | {count} |')
    md.append('')

    # 10. Revenue by Jurisdiction
    md.append('## 10. Revenue by Jurisdiction')
    md.append('')
    md.append('| Jurisdiction | Cases | Billed | Collected | Rate |')
    md.append('|--------------|------:|-------:|----------:|-----:|')
    for jurisdiction, data in list(analytics.get_revenue_by_jurisdiction().items())[:20]:
        md.append(f'| {jurisdiction} | {data["cases"]} | {format_currency(data["billed"])} | {format_currency(data["collected"])} | {format_percent(data["collection_rate"])} |')
    md.append('')

    # 11. Clients by Zip Code
    md.append('## 11. Clients by Zip Code (Heat Map Data)')
    md.append('')
    zip_clients = analytics.get_clients_by_zip_code()
    md.append(f'**Total Zip Codes:** {len(zip_clients)}')
    md.append('')
    md.append('| Zip Code | Clients |')
    md.append('|----------|--------:|')
    for zip_code, count in list(zip_clients.items())[:30]:
        md.append(f'| {zip_code} | {count} |')
    md.append('')

    # 12. Revenue by Zip Code
    md.append('## 12. Revenue by Zip Code (Heat Map Data)')
    md.append('')
    md.append('| Zip Code | Clients | Cases | Billed | Collected | Rate |')
    md.append('|----------|--------:|------:|-------:|----------:|-----:|')
    for zip_code, data in list(analytics.get_revenue_by_zip_code().items())[:25]:
        md.append(f'| {zip_code} | {data["clients"]} | {data["cases"]} | {format_currency(data["billed"])} | {format_currency(data["collected"])} | {format_percent(data["collection_rate"])} |')
    md.append('')

    # 13. New Cases per Month per Attorney
    md.append('## 13. New Cases per Month per Attorney')
    md.append('')
    md.append('| Month | Attorney | Cases |')
    md.append('|-------|----------|------:|')
    for r in analytics.get_new_cases_per_month_per_attorney(6):
        md.append(f'| {r.month} | {r.attorney_name} | {r.case_count} |')
    md.append('')

    # 14. Positive Reviews
    md.append('## 14. Positive Reviews - Staff Analysis')
    md.append('')
    md.append('> **Note:** Review data is not available in MyCase. Reviews are typically on external platforms (Google, Avvo). To analyze: export review client names, match to cases, then identify staff from case assignments.')
    md.append('')

    # Join and write
    report_content = '\n'.join(md)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(report_content)
        print(f'Report saved to {output_path}')

    return report_content


if __name__ == '__main__':
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else 'reports/analytics_report.md'
    generate_markdown_report(output)
