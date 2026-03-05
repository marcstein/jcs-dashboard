"""
Pre-Launch Test Harness: AI Chat System

Part A: Unit tests for format_query_results() with synthetic data.
Part B: Integration tests that send real questions to Claude, execute
        generated SQL against PostgreSQL, and validate formatted output.

Usage:
    cd /opt/jcs-mycase  (or project root)
    export $(grep -v '^#' .env | xargs)

    # Unit tests only (no DB or API needed):
    python -m pytest tests/test_prelaunch_chat.py::TestFormatQueryResults -v

    # Schema validation (reads code, no DB):
    python -m pytest tests/test_prelaunch_chat.py::TestSchemaValidation -v

    # Full E2E (requires DATABASE_URL + ANTHROPIC_API_KEY):
    python -m pytest tests/test_prelaunch_chat.py::TestChatE2E -v
"""

import os
import re
import sys
import json
import pytest
from pathlib import Path
from decimal import Decimal
from typing import List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from dashboard.routes.api import format_query_results, MYCASE_SCHEMA, CHAT_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _can_connect_to_db() -> bool:
    if not os.environ.get("DATABASE_URL"):
        return False
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        conn.close()
        return True
    except Exception:
        return False


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


needs_db = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason="DATABASE_URL not set or DB unreachable"
)

needs_api = pytest.mark.skipif(
    not _has_api_key(),
    reason="ANTHROPIC_API_KEY not set"
)


# ===========================================================================
# Part A: format_query_results() Unit Tests
# ===========================================================================
class TestFormatQueryResults:
    """Test the format_query_results() function with synthetic data."""

    def test_currency_columns_dollar_format(self):
        """Currency columns should be formatted as $X,XXX.XX."""
        rows = [{"lead_attorney_name": "Smith", "total_billed": 1234.56}]
        result = format_query_results(rows, "Billing")
        assert "$1,234.56" in result

    def test_percentage_columns_pct_format(self):
        """Rate/pct columns should be formatted with %."""
        rows = [{"lead_attorney_name": "Smith", "collection_rate": 82.5}]
        result = format_query_results(rows, "Rates")
        assert "82.5%" in result

    def test_year_columns_integer_format(self):
        """Year columns should display as integer, not float."""
        rows = [{"year": 2025.0, "case_count": 50}]
        result = format_query_results(rows, "By year")
        assert "2025" in result
        assert "2025.0" not in result
        assert "2,025" not in result  # Should not be comma-formatted

    def test_count_columns_not_currency(self):
        """Count columns should NOT get $ prefix."""
        rows = [{"lead_attorney_name": "Smith", "case_count": 15}]
        result = format_query_results(rows, "Counts")
        assert "$15" not in result
        assert "15" in result

    def test_null_values_dash(self):
        """NULL values should display as '-'."""
        rows = [{"name": "Test", "balance_due": None}]
        result = format_query_results(rows, "Nulls")
        assert "| - |" in result or "|-|" in result or "| -" in result

    def test_decimal_to_float_conversion(self):
        """Decimal values from PostgreSQL should format correctly."""
        rows = [{"lead_attorney_name": "Smith", "total_billed": Decimal("1234.56")}]
        result = format_query_results(rows, "Decimals")
        assert "$1,234.56" in result

    def test_whole_float_as_integer(self):
        """Whole-number floats (42.0) should display as integer."""
        rows = [{"name": "Test", "task_count": 42.0}]
        result = format_query_results(rows, "Whole floats")
        assert "42" in result
        assert "42.0" not in result

    def test_empty_results_message(self):
        """Empty results should return 'No results found.'."""
        result = format_query_results([], "Empty")
        assert "No results found" in result

    def test_twenty_row_limit_note(self):
        """When exactly 20 rows returned, show limit note."""
        rows = [{"name": f"Item {i}", "value": i} for i in range(20)]
        result = format_query_results(rows, "Limited")
        assert "Results limited to 20 rows" in result

    def test_under_twenty_rows_no_limit_note(self):
        """When less than 20 rows, no limit note."""
        rows = [{"name": f"Item {i}", "value": i} for i in range(5)]
        result = format_query_results(rows, "Not limited")
        assert "Results limited" not in result

    def test_markdown_table_structure(self):
        """Output should be a valid markdown table with header, separator, data."""
        rows = [
            {"attorney": "Smith", "cases": 10},
            {"attorney": "Jones", "cases": 5},
        ]
        result = format_query_results(rows, "Table test")
        lines = result.strip().split('\n')

        # Header row
        assert '| attorney | cases |' in lines[0]
        # Separator row
        assert '| --- | --- |' in lines[1]
        # Data rows
        assert len(lines) >= 4  # header + separator + 2 data rows

    def test_negative_amounts(self):
        """Negative currency amounts should be formatted correctly."""
        rows = [{"name": "Refund", "total_billed": -500.0}]
        result = format_query_results(rows, "Negatives")
        assert "-$500.00" in result

    def test_large_numbers(self):
        """Large currency amounts should have comma separators."""
        rows = [{"firm": "Test", "total_billed": 1234567.89}]
        result = format_query_results(rows, "Large")
        assert "$1,234,567.89" in result

    def test_zero_values(self):
        """Zero values should be formatted correctly for each type."""
        rows = [{
            "name": "Zero",
            "total_billed": 0.0,
            "case_count": 0,
            "collection_rate": 0.0,
        }]
        result = format_query_results(rows, "Zeros")
        assert "$0.00" in result
        assert "0.0%" in result

    def test_integer_currency(self):
        """Integer values in currency columns should get $ prefix."""
        rows = [{"name": "Test", "balance_due": 5000}]
        result = format_query_results(rows, "Int currency")
        assert "$5,000" in result

    def test_multiple_rows_formatting(self):
        """Multiple rows should all be properly formatted."""
        rows = [
            {"lead_attorney_name": "Heidi Leopold", "total_billed": 50000.00, "collection_rate": 75.5},
            {"lead_attorney_name": "Anthony Muhlenkamp", "total_billed": 45000.00, "collection_rate": 82.3},
        ]
        result = format_query_results(rows, "Multi-row")
        assert "Heidi Leopold" in result
        assert "Anthony Muhlenkamp" in result
        assert "$50,000.00" in result
        assert "$45,000.00" in result
        assert "75.5%" in result
        assert "82.3%" in result

    def test_month_column_integer(self):
        """Month column extracted as float should display as integer."""
        rows = [{"month": 3.0, "total_billed": 10000.00}]
        result = format_query_results(rows, "Months")
        # Month values 1-12 are within 1900-2100 range check but context matters
        # The function checks 'month' in header name and 1900 <= val <= 2100
        # Month 3.0 is not in that range, so it should just be integer
        assert "3" in result
        assert "3.0" not in result


# ===========================================================================
# Part B-1: Schema Validation (no DB/API needed)
# ===========================================================================
class TestSchemaValidation:
    """Validate the AI chat system prompt has correct PostgreSQL syntax."""

    def test_schema_no_sqlite_strftime(self):
        """MYCASE_SCHEMA should not contain SQLite strftime()."""
        assert 'strftime' not in MYCASE_SCHEMA, \
            "MYCASE_SCHEMA contains SQLite strftime() — should use EXTRACT()"

    def test_schema_no_sqlite_julianday(self):
        """MYCASE_SCHEMA should not contain SQLite julianday()."""
        assert 'julianday' not in MYCASE_SCHEMA, \
            "MYCASE_SCHEMA contains SQLite julianday() — should use CURRENT_DATE"

    def test_schema_mentions_extract(self):
        """MYCASE_SCHEMA should mention EXTRACT for date filtering."""
        assert 'EXTRACT' in MYCASE_SCHEMA, \
            "MYCASE_SCHEMA should use EXTRACT(YEAR FROM ...) for PostgreSQL"

    def test_schema_mentions_current_date(self):
        """MYCASE_SCHEMA should mention CURRENT_DATE for DPD calculations."""
        assert 'CURRENT_DATE' in MYCASE_SCHEMA, \
            "MYCASE_SCHEMA should use CURRENT_DATE for PostgreSQL DPD calculation"

    def test_system_prompt_mentions_postgresql(self):
        """System prompt should instruct to use PostgreSQL syntax."""
        assert 'PostgreSQL' in CHAT_SYSTEM_PROMPT or 'postgresql' in CHAT_SYSTEM_PROMPT.lower(), \
            "System prompt should mention PostgreSQL"

    def test_system_prompt_mentions_numeric_cast(self):
        """System prompt should warn about ::numeric cast for ROUND()."""
        assert '::numeric' in CHAT_SYSTEM_PROMPT, \
            "System prompt should mention ::numeric cast for PostgreSQL ROUND()"

    def test_schema_has_key_tables(self):
        """MYCASE_SCHEMA should reference all key tables."""
        required_tables = [
            'cached_cases', 'cached_invoices', 'cached_tasks',
            'cached_staff', 'cached_contacts',
        ]
        for table in required_tables:
            assert table in MYCASE_SCHEMA, \
                f"MYCASE_SCHEMA missing table reference: {table}"

    def test_schema_has_key_columns(self):
        """MYCASE_SCHEMA should reference important columns."""
        required_columns = [
            'lead_attorney_name', 'balance_due', 'total_amount',
            'paid_amount', 'case_number', 'practice_area',
        ]
        for col in required_columns:
            assert col in MYCASE_SCHEMA, \
                f"MYCASE_SCHEMA missing column reference: {col}"


# ===========================================================================
# Part B-2: End-to-End Chat Integration Tests
# ===========================================================================
CHAT_TEST_CASES = [
    # Basic counts
    ("How many open cases do we have?", ["count"]),
    ("How many cases by practice area?", ["practice_area", "count"]),
    ("How many cases does each attorney have?", ["lead_attorney_name", "count"]),

    # A/R & Billing
    ("What is our total accounts receivable?", ["total"]),
    ("Show billing by attorney for 2025", ["lead_attorney_name", "total"]),
    ("What is the collection rate by attorney?", ["lead_attorney_name", "rate"]),
    ("Show invoices over 90 days past due with balance", ["balance"]),
    ("What is the average invoice amount?", ["avg"]),
    ("Show unpaid invoices over $5000", ["balance"]),

    # Tasks
    ("Which staff have overdue tasks?", ["name"]),
    ("How many tasks are overdue?", ["count"]),
    ("Show task completion by staff member", ["name"]),

    # Time-based
    ("How many cases opened this year?", ["count"]),
    ("Show monthly invoice totals for 2025", ["month"]),
    ("Cases closed in the last 30 days", ["case"]),

    # Attorney performance
    ("Compare Heidi and Anthony billing", ["lead_attorney_name", "total"]),
    ("Which attorney has the most open cases?", ["lead_attorney_name", "count"]),
    ("Show attorney workload breakdown", ["lead_attorney_name"]),

    # Aggregates & calculations
    ("What is the average balance due per case?", ["avg"]),
    ("Total collected vs total billed", ["total"]),

    # Edge cases
    ("Show me everything", []),  # Should still work, limited to 20 rows
    ("What cases are in the felony category?", ["case"]),
]


@needs_db
@needs_api
class TestChatE2E:
    """End-to-end tests: question → Claude → SQL → PostgreSQL → formatted result."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Set up Anthropic client."""
        import anthropic
        self.client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )

    def _ask_chat(self, question: str) -> dict:
        """Send a question through the full chat pipeline.
        Returns dict with keys: type, sql, explanation, rows, error, formatted
        """
        from dashboard.routes.api import execute_chat_query, format_query_results, CHAT_SYSTEM_PROMPT

        # Call Claude
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=CHAT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}],
        )
        assistant_text = response.content[0].text

        # Parse JSON
        json_str = assistant_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        try:
            parsed = json.loads(json_str.strip())
        except json.JSONDecodeError:
            return {
                "type": "error",
                "error": f"Failed to parse JSON from Claude response: {assistant_text[:200]}",
                "raw": assistant_text,
            }

        if parsed.get("type") == "query":
            sql = parsed.get("sql", "")
            explanation = parsed.get("explanation", "")
            rows, error = execute_chat_query(sql)
            formatted = format_query_results(rows, explanation) if not error else None
            return {
                "type": "query",
                "sql": sql,
                "explanation": explanation,
                "rows": rows,
                "error": error,
                "formatted": formatted,
            }
        else:
            return {
                "type": "text",
                "response": parsed.get("response", assistant_text),
            }

    @pytest.mark.parametrize(
        "question,expected_columns",
        CHAT_TEST_CASES,
        ids=[q[:50] for q, _ in CHAT_TEST_CASES],
    )
    def test_chat_query_executes_without_error(self, question, expected_columns):
        """Question should produce valid SQL that executes without error."""
        result = self._ask_chat(question)

        if result["type"] == "text":
            # Some questions might get text responses — that's okay
            return

        assert result["type"] == "query", \
            f"Unexpected response type: {result.get('type')}"
        assert result.get("error") is None, \
            f"SQL error for '{question}':\n  SQL: {result.get('sql', 'N/A')}\n  Error: {result['error']}"

    @pytest.mark.parametrize(
        "question,expected_columns",
        CHAT_TEST_CASES,
        ids=[q[:50] for q, _ in CHAT_TEST_CASES],
    )
    def test_chat_query_returns_formatted_table(self, question, expected_columns):
        """Query results should be formatted as a markdown table."""
        result = self._ask_chat(question)

        if result["type"] == "text":
            return

        formatted = result.get("formatted", "")
        assert formatted, f"No formatted output for '{question}'"

        # Check it's a markdown table (has | separators)
        if "No results found" not in formatted:
            assert "|" in formatted, \
                f"Expected markdown table for '{question}', got: {formatted[:200]}"
            # Check header separator exists
            assert "---" in formatted, \
                f"Missing header separator for '{question}'"

    @pytest.mark.parametrize(
        "question,expected_columns",
        [(q, c) for q, c in CHAT_TEST_CASES if c],  # Only those with expected columns
        ids=[q[:50] for q, c in CHAT_TEST_CASES if c],
    )
    def test_chat_expected_columns_present(self, question, expected_columns):
        """Response should contain columns relevant to the question."""
        result = self._ask_chat(question)

        if result["type"] == "text":
            return
        if result.get("error"):
            pytest.skip(f"SQL error: {result['error']}")

        rows = result.get("rows", [])
        if not rows:
            pytest.skip("No results returned")

        actual_columns = list(rows[0].keys())

        # Check that at least one expected column concept appears
        # AI may use different aliases (e.g., 'open_cases' vs 'case_count')
        # Use broad substring and synonym matching since Claude picks its own aliases
        SYNONYMS = {
            'count': {'count', 'total', 'num', 'number'},
            'total': {'total', 'sum', 'amount', 'billed', 'collected'},
            'avg': {'avg', 'average', 'mean'},
            'rate': {'rate', 'pct', 'percent', 'percentage', 'ratio'},
            'balance': {'balance', 'due', 'amount', 'owed', 'outstanding'},
            'name': {'name', 'staff', 'assignee', 'attorney', 'member'},
            'case': {'case', 'number', 'cases'},
            'month': {'month', 'period', 'date'},
        }

        def matches_expected(expected: str, actual_cols: list) -> bool:
            """Check if any actual column matches the expected concept."""
            exp_lower = expected.lower()
            # Get synonym set for this expected keyword
            synonyms = SYNONYMS.get(exp_lower, {exp_lower})
            for actual in actual_cols:
                actual_lower = actual.lower()
                # Direct substring match
                if exp_lower in actual_lower or actual_lower in exp_lower:
                    return True
                # Synonym match: any synonym appears in the column name
                for syn in synonyms:
                    if syn in actual_lower:
                        return True
                # Keyword overlap
                actual_parts = set(re.split(r'[_\s]+', actual_lower))
                if actual_parts & synonyms:
                    return True
            return False

        found_any = False
        for expected in expected_columns:
            if matches_expected(expected, actual_columns):
                found_any = True
                break

        assert found_any, \
            f"Expected columns containing {expected_columns} but got {actual_columns} " \
            f"for: '{question}'"


# ===========================================================================
# Part B-3: SQL Execution Tests (DB only, no API)
# ===========================================================================
@needs_db
class TestSQLExecution:
    """Test that common SQL patterns execute correctly on PostgreSQL."""

    def _execute(self, sql: str) -> Tuple[list, Optional[str]]:
        from dashboard.routes.api import execute_chat_query
        return execute_chat_query(sql)

    def test_basic_count(self):
        """Basic COUNT query should work."""
        rows, error = self._execute(
            "SELECT COUNT(*) as case_count FROM cached_cases WHERE status = 'open'"
        )
        assert error is None, f"SQL error: {error}"
        assert len(rows) == 1
        assert 'case_count' in rows[0]

    def test_group_by_attorney(self):
        """GROUP BY with lead_attorney_name should work."""
        rows, error = self._execute(
            "SELECT lead_attorney_name, COUNT(*) as case_count "
            "FROM cached_cases WHERE status = 'open' "
            "GROUP BY lead_attorney_name ORDER BY case_count DESC LIMIT 5"
        )
        assert error is None, f"SQL error: {error}"
        assert len(rows) > 0

    def test_extract_year(self):
        """EXTRACT(YEAR FROM ...) should work (PostgreSQL syntax)."""
        rows, error = self._execute(
            "SELECT EXTRACT(YEAR FROM created_at) as year, COUNT(*) as case_count "
            "FROM cached_cases "
            "GROUP BY EXTRACT(YEAR FROM created_at) ORDER BY year DESC LIMIT 5"
        )
        assert error is None, f"SQL error: {error}"

    def test_current_date_dpd(self):
        """CURRENT_DATE - date::date should work for DPD calculation."""
        rows, error = self._execute(
            "SELECT invoice_number, balance_due, "
            "CURRENT_DATE - due_date::date as days_past_due "
            "FROM cached_invoices WHERE balance_due > 0 "
            "ORDER BY days_past_due DESC LIMIT 5"
        )
        assert error is None, f"SQL error: {error}"

    def test_round_numeric_cast(self):
        """ROUND(x::numeric, 2) should work in PostgreSQL."""
        rows, error = self._execute(
            "SELECT lead_attorney_name, "
            "ROUND((SUM(paid_amount) / NULLIF(SUM(total_amount), 0) * 100)::numeric, 1) as collection_rate "
            "FROM cached_invoices i JOIN cached_cases c ON i.case_id = c.id "
            "GROUP BY lead_attorney_name ORDER BY collection_rate DESC LIMIT 5"
        )
        assert error is None, f"SQL error: {error}"

    def test_invoice_join_cases(self):
        """Invoice-to-cases join should work."""
        rows, error = self._execute(
            "SELECT c.lead_attorney_name, COUNT(*) as invoice_count, "
            "SUM(i.total_amount) as total_billed "
            "FROM cached_invoices i "
            "JOIN cached_cases c ON i.case_id = c.id "
            "GROUP BY c.lead_attorney_name "
            "ORDER BY total_billed DESC LIMIT 5"
        )
        assert error is None, f"SQL error: {error}"
        assert len(rows) > 0

    def test_task_overdue_query(self):
        """Task overdue query should work (completed is boolean in PostgreSQL)."""
        rows, error = self._execute(
            "SELECT assignee_name, COUNT(*) as overdue_count "
            "FROM cached_tasks "
            "WHERE completed = false AND due_date < CURRENT_DATE "
            "GROUP BY assignee_name ORDER BY overdue_count DESC LIMIT 10"
        )
        assert error is None, f"SQL error: {error}"


# ===========================================================================
# Summary
# ===========================================================================
@pytest.fixture(scope="session", autouse=True)
def print_summary(request):
    """Print a summary after all tests complete."""
    yield
    terminal_reporter = request.config.pluginmanager.getplugin("terminalreporter")
    if terminal_reporter:
        passed = len(terminal_reporter.stats.get("passed", []))
        failed = len(terminal_reporter.stats.get("failed", []))
        skipped = len(terminal_reporter.stats.get("skipped", []))
        errors = len(terminal_reporter.stats.get("error", []))
        total = passed + failed + skipped + errors
        print(f"\n{'=' * 70}")
        print(f"AI CHAT PRE-LAUNCH SUMMARY")
        print(f"{'=' * 70}")
        print(f"  Total:   {total}")
        print(f"  Passed:  {passed}")
        print(f"  Failed:  {failed}")
        print(f"  Skipped: {skipped}")
        print(f"  Errors:  {errors}")
        print(f"{'=' * 70}")
