# JCS Law Firm MyCase Automation - Test Suite

A comprehensive pytest test suite for the JCS Law Firm MyCase automation project. All tests use PostgreSQL mock connections to avoid requiring a real database during testing.

## Overview

**Total Test Files:** 8
**Total Test Functions:** ~140
**Coverage Areas:** Database layer, business logic, collections, promises, case phases, documents, dunning, and dashboards

## Test Files

### 1. `conftest.py` (Shared Fixtures)
Core pytest fixtures used across all test modules.

**Key Fixtures:**
- `mock_firm_id` - Test firm ID ("test_firm")
- `mock_cursor` - Mock database cursor with `execute()`, `fetchone()`, `fetchall()`
- `mock_connection` - Mock PostgreSQL connection context manager
- `mock_get_connection` - Patches `db.connection.get_connection` for testing
- `mock_db_state` - Simulated database state (dictionary)
- `assert_sql_contains` - Helper for asserting SQL patterns in mocked calls

**Sample Data Fixtures:**
- `sample_promise_data` - Complete promise record
- `sample_noiw_case` - NOIW case data
- `sample_phase_data` - Case phase history record
- `sample_template_data` - Document template record

### 2. `test_promises.py` (Payment Promise Tracking)
Tests for `db.promises` module. Validates promise recording, status transitions, and overdue detection.

**Test Classes:**
- `TestAddPromise` (3 tests) - Promise creation
- `TestPromiseStatusTransitions` (4 tests) - Kept/broken transitions
- `TestListPromises` (3 tests) - Query filtering
- `TestOverdueDetection` (3 tests) - Due today/overdue queries
- `TestPromiseStats` (3 tests) - Statistics and keep rate calculation

**Total: 16 tests**

### 3. `test_collections.py` (NOIW & Collections)
Tests for `db.collections` module. Covers NOIW pipeline, holds, and outreach logging.

**Test Classes:**
- `TestNOIWTracking` (4 tests) - NOIW case upsert and retrieval
- `TestNOIWStatusTransitions` (5 tests) - Status progression (pending → resolved)
- `TestCollectionsHolds` (5 tests) - Adding/releasing holds
- `TestOutreachLogging` (4 tests) - Contact history tracking
- `TestNOIWSummary` (2 tests) - Summary statistics

**Total: 20 tests**

### 4. `test_phases.py` (Case Phase Tracking)
Tests for `db.phases` module. Validates phase definitions, history, and stalled case detection.

**Test Classes:**
- `TestPhaseDefinitions` (2 tests) - Phase retrieval and upsert
- `TestPhaseHistory` (2 tests) - Recording phase entries
- `TestPhaseDistribution` (3 tests) - Phase distribution aggregation
- `TestStalledCases` (4 tests) - Stalled case detection with thresholds
- `TestStageToPhaseMapping` (3 tests) - MyCase stage mappings
- `TestMultiTenantIsolation` (2 tests) - Firm-specific queries

**Total: 16 tests**

### 5. `test_cache.py` (MyCase API Cache)
Tests for `db.cache` module. Validates batch operations and multi-tenant isolation.

**Test Classes:**
- `TestCacheBatchOperations` (3 tests) - Bulk upsert logic
- `TestCaseCaching` (2 tests) - Case cache structure
- `TestContactCaching` (2 tests) - Contact cache operations
- `TestInvoiceCaching` (3 tests) - Invoice structure and aging
- `TestTaskCaching` (2 tests) - Task cache and overdue detection
- `TestCacheSyncMetadata` (2 tests) - Sync tracking
- `TestCacheUpsertLogic` (2 tests) - ON CONFLICT behavior
- `TestMultiTenantCacheIsolation` (2 tests) - Firm isolation

**Total: 18 tests**

### 6. `test_documents.py` (Document Engine)
Tests for `db.documents` module. Covers template search with synonyms, stop word removal, and FTS fallback.

**Test Classes:**
- `TestTemplateSearch` (3 tests) - Basic search, synonyms, FTS queries
- `TestSynonymExpansion` (3 tests) - Abbreviation expansion (MTD→motion dismiss)
- `TestStopWordRemoval` (3 tests) - English stop word filtering
- `TestFTSFallback` (3 tests) - Fallback to ILIKE when FTS fails
- `TestTemplateMetadata` (3 tests) - Jurisdiction and case type filtering
- `TestTemplateVariables` (3 tests) - Variable extraction and handling
- `TestMultiTenantTemplateIsolation` (2 tests) - Firm-specific templates

**Total: 20 tests**

### 7. `test_dunning.py` (Dunning Notice Logic)
Tests for dunning stage classification and email template selection.

**Test Classes:**
- `TestDunningStageClassification` (6 tests) - Stage boundaries (5-14, 15-29, etc.)
- `TestDunningEmailTemplate` (5 tests) - Template selection per stage
- `TestDunningProgression` (4 tests) - Progression through stages
- `TestDunningStopConditions` (4 tests) - Conditions that pause dunning
- `TestDunningMetrics` (3 tests) - Aging bucket distribution
- `TestDunningNoticeContent` (4 tests) - Tone escalation
- `TestDunningExclusions` (3 tests) - Excluding from dunning

**Total: 29 tests**

### 8. `test_dashboard.py` (Dashboard Models)
Tests for dashboard data retrieval and SQL patterns.

**Test Classes:**
- `TestDashboardInitialization` (2 tests) - Dashboard setup
- `TestARDashboard` (3 tests) - A/R balance and aging buckets
- `TestTasksDashboard` (2 tests) - Task aggregation by assignee
- `TestQualityDashboard` (2 tests) - Quality score distribution
- `TestPhasesDashboard` (2 tests) - Phase distribution queries
- `TestCollectionsDashboard` (2 tests) - NOIW and hold summaries
- `TestAttorneyProductivityDashboard` (3 tests) - Attorney metrics
- `TestMultiTenantDashboardIsolation` (2 tests) - Firm isolation

**Total: 18 tests**

## Running the Tests

### Prerequisites
```bash
pip install pytest pytest-mock psycopg2-binary
```

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/test_promises.py -v
```

### Run Specific Test Class
```bash
pytest tests/test_promises.py::TestAddPromise -v
```

### Run Specific Test Function
```bash
pytest tests/test_promises.py::TestAddPromise::test_add_promise_success -v
```

### Run with Coverage
```bash
pytest tests/ --cov=db --cov=commands --cov=dashboard --cov-report=html
```

## Test Design Principles

### 1. Mock Database Connections
All tests use mocked PostgreSQL connections via `mock_get_connection` fixture. This eliminates the need for:
- Real database instance
- Test database setup
- Cleanup between tests
- Multi-tenant isolation complexity

### 2. Multi-Tenant Isolation Testing
Every test validates that queries include `firm_id` in WHERE clauses:
```python
def test_get_promises_filters_by_firm(self, mock_get_connection, mock_cursor):
    with mock_get_connection:
        promises.get_promises(firm_id='firm_a')

    params = mock_cursor.execute.call_args[0][1]
    assert params[0] == 'firm_a'
```

### 3. SQL Pattern Matching
Tests verify SQL structure without executing:
```python
def test_upsert_uses_on_conflict(self, mock_get_connection, mock_cursor):
    with mock_get_connection:
        promises.add_promise(...)

    sql = mock_cursor.execute.call_args[0][0]
    assert 'ON CONFLICT' in sql
```

### 4. Fixture Reusability
All fixtures are defined in `conftest.py` and automatically available to all test modules:
- `mock_firm_id` - Test tenant ID
- `mock_cursor` - Database cursor mock
- `sample_*_data` - Realistic test data

## Coverage Summary

| Module | Tests | Coverage |
|--------|-------|----------|
| db/promises.py | 16 | Promise lifecycle, stats |
| db/collections.py | 20 | NOIW pipeline, holds, outreach |
| db/phases.py | 16 | Phase definitions, stalled cases |
| db/cache.py | 18 | Batch ops, multi-tenant isolation |
| db/documents.py | 20 | Template search, FTS, fallback |
| Dunning Logic | 29 | Stage classification, email selection |
| Dashboard | 18 | Data aggregation, joins |
| **TOTAL** | **137** | Comprehensive coverage |

## Key Testing Patterns

### Pattern 1: Fixture Injection
```python
def test_something(self, mock_get_connection, mock_firm_id, sample_promise_data):
    with mock_get_connection:
        result = some_function(firm_id=mock_firm_id)
```

### Pattern 2: SQL Verification
```python
def test_query_structure(self, mock_get_connection, mock_cursor):
    with mock_get_connection:
        db_function(firm_id='test')

    sql = mock_cursor.execute.call_args[0][0]
    assert 'WHERE firm_id = %s' in sql
```

### Pattern 3: Status Transitions
```python
def test_status_change(self, mock_get_connection, mock_cursor):
    with mock_get_connection:
        collections.update_noiw_status(
            firm_id='test',
            case_id=100,
            status='final_notice'
        )

    sql = mock_cursor.execute.call_args[0][0]
    assert "final_notice_date = CURRENT_DATE" in sql
```

### Pattern 4: Multi-Tenant Validation
```python
def test_firm_isolation(self, mock_get_connection, mock_cursor):
    with mock_get_connection:
        phases.get_phases(firm_id='firm_a')

    params = mock_cursor.execute.call_args[0][1]
    assert params[0] == 'firm_a'
```

## Test Data

### Sample Records
All sample data fixtures in `conftest.py` mirror real database schema:
- Complete field coverage
- Realistic values
- Proper data types
- Multi-tenant isolation

### Mock Connection Behavior
The `mock_get_connection` fixture:
1. Patches `db.connection.get_connection`
2. Returns a context manager
3. Provides mock cursor with `execute()`, `fetchone()`, `fetchall()`
4. Supports assertions on SQL parameters
5. Tracks all database calls

## Extending the Test Suite

### Adding a New Test
1. Choose appropriate test file or create new one
2. Import fixtures from `conftest.py`
3. Use `mock_get_connection` for all database operations
4. Verify SQL patterns with `mock_cursor.execute.call_args`
5. Add docstrings explaining what's being tested

### Adding a New Fixture
1. Add to `conftest.py`
2. Use `@pytest.fixture` decorator
3. Follow naming convention: `mock_*` or `sample_*_data`
4. Document in README

## Notes

- Tests do NOT require PostgreSQL installation
- Tests do NOT require real API connections
- Tests run in isolation (no shared state)
- All tests follow pytest conventions
- Fixtures are reusable across modules
- Mock cursors track all SQL calls for verification

## CI/CD Integration

These tests are suitable for:
- GitHub Actions
- GitLab CI
- Jenkins
- Any Python-based CI system

Minimal requirements:
```bash
pip install pytest pytest-mock
pytest tests/
```
