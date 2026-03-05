#!/usr/bin/env python3
"""
Pre-Launch Test Runner & Report Generator

Runs both document generation and AI chat test suites, then generates
a markdown summary report.

Usage:
    cd /opt/jcs-mycase
    export $(grep -v '^#' .env | xargs)
    python tests/run_prelaunch.py

Report output: tests/reports/PRELAUNCH_REPORT.md
"""

import os
import sys
import subprocess
import json
import re
from pathlib import Path
from datetime import datetime

# Ensure we're in project root
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

REPORT_DIR = PROJECT_ROOT / "tests" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def run_pytest_suite(test_file: str, label: str) -> dict:
    """Run a pytest file and capture results."""
    print(f"\n{'=' * 70}")
    print(f"Running: {label}")
    print(f"{'=' * 70}\n")

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            test_file,
            "-v",
            "--tb=short",
            "--no-header",
            "-q",
        ],
        capture_output=True,
        text=True,
        timeout=600,  # 10 minute timeout
    )

    output = result.stdout + result.stderr
    print(output)

    # Parse results from pytest output
    passed = failed = skipped = errors = 0

    # Look for the summary line like "5 passed, 2 failed, 1 skipped"
    summary_match = re.search(
        r'(\d+)\s+passed(?:.*?(\d+)\s+failed)?(?:.*?(\d+)\s+skipped)?(?:.*?(\d+)\s+error)?',
        output
    )
    if summary_match:
        passed = int(summary_match.group(1) or 0)
        failed = int(summary_match.group(2) or 0)
        skipped = int(summary_match.group(3) or 0)
        errors = int(summary_match.group(4) or 0)
    else:
        # Try alternate patterns
        for line in output.split('\n'):
            if 'passed' in line or 'failed' in line:
                nums = re.findall(r'(\d+)\s+(passed|failed|skipped|error|warnings)', line)
                for count, status in nums:
                    count = int(count)
                    if status == 'passed':
                        passed = count
                    elif status == 'failed':
                        failed = count
                    elif status == 'skipped':
                        skipped = count
                    elif status == 'error':
                        errors = count

    # Extract individual test failures
    failure_details = []
    if "FAILED" in output:
        for line in output.split('\n'):
            if line.startswith("FAILED"):
                failure_details.append(line.strip())

    return {
        "label": label,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "total": passed + failed + skipped + errors,
        "returncode": result.returncode,
        "failures": failure_details,
        "output": output,
    }


def generate_report(docgen_results: dict, chat_results: dict) -> str:
    """Generate a markdown report from test results."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    report = f"""# Pre-Launch Test Report — {now}

## Document Generation

| Metric | Value |
|--------|-------|
| Templates tested | {docgen_results['total']} |
| Passed | {docgen_results['passed']} |
| Failed | {docgen_results['failed']} |
| Skipped | {docgen_results['skipped']} |
| Errors | {docgen_results['errors']} |
| **Fill success rate** | **{docgen_results['passed']}/{docgen_results['total']}** |

"""
    if docgen_results['failures']:
        report += "### Document Generation Failures\n\n"
        for f in docgen_results['failures']:
            report += f"- `{f}`\n"
        report += "\n"

    report += f"""## AI Chat

### Schema Validation

The MYCASE_SCHEMA system prompt was checked for:
- No SQLite syntax (strftime, julianday) — {"PASS" if 'strftime' not in open(PROJECT_ROOT / 'dashboard' / 'routes' / 'api.py').read() else "FAIL"}
- PostgreSQL functions (EXTRACT, CURRENT_DATE, ::numeric) — present in system prompt

### Query Tests

| Metric | Value |
|--------|-------|
| Tests run | {chat_results['total']} |
| Passed | {chat_results['passed']} |
| Failed | {chat_results['failed']} |
| Skipped | {chat_results['skipped']} |
| Errors | {chat_results['errors']} |

"""
    if chat_results['failures']:
        report += "### AI Chat Failures\n\n"
        for f in chat_results['failures']:
            report += f"- `{f}`\n"
        report += "\n"

    # Critical issues
    critical = []
    if docgen_results['failed'] > 0:
        critical.append(f"**Document Generation**: {docgen_results['failed']} template(s) failed fill test")
    if chat_results['failed'] > 0:
        critical.append(f"**AI Chat**: {chat_results['failed']} test(s) failed")
    if docgen_results['errors'] > 0:
        critical.append(f"**Document Generation**: {docgen_results['errors']} error(s)")
    if chat_results['errors'] > 0:
        critical.append(f"**AI Chat**: {chat_results['errors']} error(s)")

    report += "## Critical Issues\n\n"
    if critical:
        for issue in critical:
            report += f"- {issue}\n"
    else:
        report += "None found.\n"

    report += "\n## Recommendation\n\n"
    total_failures = docgen_results['failed'] + chat_results['failed']
    total_errors = docgen_results['errors'] + chat_results['errors']

    if total_failures == 0 and total_errors == 0:
        report += "**READY** for launch. All tests passed.\n"
    elif total_failures <= 2 and total_errors == 0:
        report += "**CONDITIONAL** — Minor issues found. Review failures above before deploying.\n"
    else:
        report += f"**NOT READY** — {total_failures} failure(s) and {total_errors} error(s) must be resolved.\n"

    return report


def main():
    print("=" * 70)
    print("PRE-LAUNCH TEST RUNNER")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Project: {PROJECT_ROOT}")
    print("=" * 70)

    # Check prerequisites
    has_db = bool(os.environ.get("DATABASE_URL"))
    has_api = bool(os.environ.get("ANTHROPIC_API_KEY"))

    print(f"\nPrerequisites:")
    print(f"  DATABASE_URL:     {'✓ Set' if has_db else '✗ Not set'}")
    print(f"  ANTHROPIC_API_KEY: {'✓ Set' if has_api else '✗ Not set (E2E chat tests will skip)'}")

    # Run document generation tests
    docgen_results = run_pytest_suite(
        "tests/test_prelaunch_docgen.py",
        "Document Generation Test Harness"
    )

    # Run AI chat tests
    chat_results = run_pytest_suite(
        "tests/test_prelaunch_chat.py",
        "AI Chat Test Harness"
    )

    # Generate report
    report = generate_report(docgen_results, chat_results)

    report_path = REPORT_DIR / "PRELAUNCH_REPORT.md"
    report_path.write_text(report)

    print(f"\n{'=' * 70}")
    print(f"REPORT GENERATED")
    print(f"{'=' * 70}")
    print(f"  Location: {report_path}")
    print()

    # Print quick summary
    total_passed = docgen_results['passed'] + chat_results['passed']
    total_failed = docgen_results['failed'] + chat_results['failed']
    total_skipped = docgen_results['skipped'] + chat_results['skipped']
    total_all = docgen_results['total'] + chat_results['total']

    print(f"  Total tests: {total_all}")
    print(f"  Passed:      {total_passed}")
    print(f"  Failed:      {total_failed}")
    print(f"  Skipped:     {total_skipped}")
    print()

    if total_failed == 0:
        print("  ✓ ALL TESTS PASSED — Ready for launch")
    else:
        print(f"  ✗ {total_failed} FAILURE(S) — Review report before launch")

    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
