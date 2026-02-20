"""
Shared pytest fixtures for JCS Law Firm MyCase Automation tests.

Provides:
- Mock firm_id fixture
- Mock connection context manager
- Mock cursor with database methods
- Database isolation for testing
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
from contextlib import contextmanager


@pytest.fixture
def mock_firm_id():
    """Fixture providing a test firm ID."""
    return "test_firm"


@pytest.fixture
def mock_cursor():
    """
    Fixture providing a mock cursor with database methods.

    Supports:
    - execute(sql, params)
    - fetchone()
    - fetchall()
    - Works as context manager
    """
    cursor = MagicMock()
    cursor.fetchone = MagicMock(return_value=None)
    cursor.fetchall = MagicMock(return_value=[])
    cursor.execute = MagicMock(return_value=None)
    cursor.rowcount = 0
    return cursor


@pytest.fixture
def mock_connection(mock_cursor):
    """
    Fixture providing a mock PostgreSQL connection.

    Returns a mock connection that:
    - Creates a mock cursor via cursor() method
    - Works as a context manager
    - Supports commit() and rollback() calls
    """
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=mock_cursor)
    conn.commit = MagicMock()
    conn.rollback = MagicMock()
    conn.autocommit = False

    # Make connection itself a context manager
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)

    return conn


@pytest.fixture
def mock_get_connection(mock_connection):
    """
    Fixture that patches db.connection.get_connection to return mock connection.

    Returns a context manager that yields the mock connection.
    Patches the module-level get_connection function.
    """
    @contextmanager
    def get_connection_mock(autocommit=False):
        mock_connection.autocommit = autocommit
        yield mock_connection

    with patch('db.connection.get_connection', side_effect=get_connection_mock):
        yield get_connection_mock


@pytest.fixture
def mock_db_state():
    """
    Fixture providing mock database state for tests.

    Returns a dict that can simulate database records:
    {
        'promises': [...],
        'holds': [...],
        'noiw_cases': [...],
        'phases': [...],
        'cases': [...],
    }
    """
    return {
        'promises': [],
        'holds': [],
        'outreach_logs': [],
        'noiw_cases': [],
        'phases': [],
        'cases': [],
        'templates': [],
        'contacts': [],
    }


@pytest.fixture
def assert_sql_contains():
    """
    Helper fixture for asserting SQL content in mocked execute calls.

    Usage:
        cursor.execute("SELECT * FROM foo WHERE id = %s", (1,))
        assert_sql_contains(cursor, "SELECT", "FROM foo")
    """
    def _assert(cursor, *keywords):
        """Assert that all keywords appear in any execute call."""
        assert cursor.execute.called, "execute() was not called"
        for call in cursor.execute.call_args_list:
            sql = call[0][0]  # First positional arg is SQL
            if all(kw in sql for kw in keywords):
                return True
        raise AssertionError(
            f"SQL containing all of {keywords} not found in execute calls: "
            f"{[str(c) for c in cursor.execute.call_args_list]}"
        )
    return _assert


@pytest.fixture
def sample_promise_data():
    """Sample promise data for testing."""
    return {
        'id': 1,
        'firm_id': 'test_firm',
        'contact_id': 123,
        'contact_name': 'John Doe',
        'case_id': 456,
        'case_name': 'v. State',
        'invoice_id': 789,
        'promised_amount': 500.0,
        'promised_date': '2026-02-28',
        'actual_amount': None,
        'actual_date': None,
        'status': 'pending',
        'notes': 'Client promised payment',
        'recorded_by': 'melissa',
        'recorded_at': '2026-02-20T10:00:00',
        'updated_at': '2026-02-20T10:00:00',
    }


@pytest.fixture
def sample_noiw_case():
    """Sample NOIW case data for testing."""
    return {
        'id': 1,
        'firm_id': 'test_firm',
        'case_id': 100,
        'case_name': 'State v. Smith',
        'contact_id': 200,
        'contact_name': 'John Smith',
        'invoice_id': 300,
        'balance_due': 1500.00,
        'days_delinquent': 65,
        'status': 'pending',
        'warning_sent_date': None,
        'final_notice_date': None,
        'attorney_review_date': None,
        'resolution_date': None,
        'resolution_notes': None,
        'assigned_to': 'melissa',
        'notes': '60+ days delinquent',
        'created_at': '2026-02-20T10:00:00',
        'updated_at': '2026-02-20T10:00:00',
    }


@pytest.fixture
def sample_phase_data():
    """Sample case phase data for testing."""
    return {
        'id': 1,
        'firm_id': 'test_firm',
        'case_id': 100,
        'case_name': 'State v. Smith',
        'case_type': 'DWI',
        'phase_code': 'discovery',
        'phase_name': 'Discovery & Investigation',
        'mycase_stage_id': 5,
        'mycase_stage_name': 'Discovery',
        'entered_at': '2026-01-15T10:00:00',
        'exited_at': None,
        'duration_days': None,
        'notes': 'Ongoing discovery',
    }


@pytest.fixture
def sample_template_data():
    """Sample template data for testing."""
    return {
        'id': 1,
        'firm_id': 'test_firm',
        'name': 'Motion to Dismiss',
        'original_filename': 'motion_to_dismiss.docx',
        'category': 'Motions',
        'subcategory': 'Dismissal',
        'court_type': 'Circuit Court',
        'jurisdiction': 'Missouri',
        'case_types': 'Criminal,DWI',
        'variables': ['defendant_name', 'case_number', 'county'],
        'tags': 'motion,dismissal,criminal',
        'file_size': 25600,
        'usage_count': 15,
        'is_active': True,
        'upload_date': '2026-01-01T10:00:00',
        'last_used': '2026-02-20T10:00:00',
    }
