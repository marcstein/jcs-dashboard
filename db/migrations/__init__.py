"""
db/migrations/ — Database migration scripts.

Each migration is numbered (001, 002, etc.) and is idempotent (safe to re-run).
"""


def run_migration_001():
    """Run migration 001: Consolidate firms table."""
    # Import uses the actual filename (001_consolidate_firms)
    # Python module names can't start with digits, so we use importlib
    import importlib
    mod = importlib.import_module("db.migrations.001_consolidate_firms")
    return mod.run_migration()
