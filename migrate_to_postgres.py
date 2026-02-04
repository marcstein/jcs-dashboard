#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script for LawMetrics.ai

Migrates data from local SQLite databases to Digital Ocean PostgreSQL.

Usage:
    python migrate_to_postgres.py --init     # Initialize PostgreSQL schema only
    python migrate_to_postgres.py --migrate  # Migrate all data
    python migrate_to_postgres.py --verify   # Verify migration counts
    python migrate_to_postgres.py --all      # Do all of the above
"""

import os
import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# Set up environment from .env file
from dotenv import load_dotenv
load_dotenv()

# Ensure psycopg2 is available
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

from config import DATA_DIR


# PostgreSQL connection settings
PG_CONFIG = {
    'host': os.getenv('PG_HOST', 'db-postgresql-nyc3-57744-do-user-127223-0.j.db.ondigitalocean.com'),
    'port': os.getenv('PG_PORT', '25060'),
    'database': os.getenv('PG_DATABASE', 'defaultdb'),
    'user': os.getenv('PG_USER', 'doadmin'),
    'password': os.getenv('PG_PASSWORD', ''),
    'sslmode': os.getenv('PG_SSLMODE', 'require')
}

# SQLite source paths
SQLITE_TEMPLATES = DATA_DIR / "document_engine.db"
SQLITE_ATTORNEYS = DATA_DIR / "attorney_profiles.db"


def get_pg_connection():
    """Get PostgreSQL connection."""
    conn_string = (
        f"host={PG_CONFIG['host']} "
        f"port={PG_CONFIG['port']} "
        f"dbname={PG_CONFIG['database']} "
        f"user={PG_CONFIG['user']} "
        f"password={PG_CONFIG['password']} "
        f"sslmode={PG_CONFIG['sslmode']}"
    )
    return psycopg2.connect(conn_string)


def init_postgres_schema(conn):
    """Initialize PostgreSQL schema."""
    print("Initializing PostgreSQL schema...")
    
    schema_sql = """
    -- Drop existing tables if starting fresh (comment out to preserve data)
    -- DROP TABLE IF EXISTS generated_documents CASCADE;
    -- DROP TABLE IF EXISTS attorneys CASCADE;
    -- DROP TABLE IF EXISTS templates CASCADE;
    -- DROP TABLE IF EXISTS firms CASCADE;

    -- Firms table
    CREATE TABLE IF NOT EXISTS firms (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        settings JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Templates table
    CREATE TABLE IF NOT EXISTS templates (
        id SERIAL PRIMARY KEY,
        firm_id TEXT NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        original_filename TEXT,
        category TEXT,
        subcategory TEXT,
        court_type TEXT,
        jurisdiction TEXT,
        case_types TEXT,
        variables JSONB DEFAULT '[]',
        variable_mappings JSONB DEFAULT '{}',
        tags TEXT,
        file_content BYTEA,
        file_hash TEXT,
        file_size INTEGER,
        is_active BOOLEAN DEFAULT TRUE,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP,
        usage_count INTEGER DEFAULT 0
    );
    
    -- Create unique constraint for firm_id + name (upsert support)
    CREATE UNIQUE INDEX IF NOT EXISTS idx_templates_firm_name ON templates(firm_id, name);

    -- Generated documents history
    CREATE TABLE IF NOT EXISTS generated_documents (
        id SERIAL PRIMARY KEY,
        firm_id TEXT NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
        template_id INTEGER REFERENCES templates(id),
        template_name TEXT,
        case_id TEXT,
        client_name TEXT,
        variables_used JSONB DEFAULT '{}',
        generated_by TEXT,
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        output_filename TEXT
    );

    -- Attorney profiles
    CREATE TABLE IF NOT EXISTS attorneys (
        id SERIAL PRIMARY KEY,
        firm_id TEXT NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
        attorney_name TEXT NOT NULL,
        bar_number TEXT,
        email TEXT,
        phone TEXT,
        fax TEXT,
        firm_name TEXT,
        firm_address TEXT,
        firm_city TEXT,
        firm_state TEXT,
        firm_zip TEXT,
        is_primary BOOLEAN DEFAULT FALSE,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Create unique constraint for firm_id + bar_number
    CREATE UNIQUE INDEX IF NOT EXISTS idx_attorneys_firm_bar ON attorneys(firm_id, bar_number);

    -- Indexes for performance
    CREATE INDEX IF NOT EXISTS idx_templates_firm ON templates(firm_id);
    CREATE INDEX IF NOT EXISTS idx_templates_category ON templates(firm_id, category);
    CREATE INDEX IF NOT EXISTS idx_templates_active ON templates(firm_id, is_active);
    CREATE INDEX IF NOT EXISTS idx_attorneys_firm ON attorneys(firm_id);
    CREATE INDEX IF NOT EXISTS idx_generated_docs_firm ON generated_documents(firm_id);
    CREATE INDEX IF NOT EXISTS idx_generated_docs_case ON generated_documents(case_id);
    
    -- Full-text search index
    CREATE INDEX IF NOT EXISTS idx_templates_fts ON templates 
    USING GIN (to_tsvector('english', name || ' ' || COALESCE(category, '') || ' ' || COALESCE(tags, '')));
    """
    
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
    print("✓ Schema initialized successfully")


def migrate_firms(pg_conn, sqlite_conn):
    """Migrate firms from SQLite to PostgreSQL."""
    print("\nMigrating firms...")
    
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT id, name, settings, created_at FROM firms")
    firms = sqlite_cur.fetchall()
    
    if not firms:
        print("  No firms found in SQLite")
        return 0
    
    with pg_conn.cursor() as pg_cur:
        for firm in firms:
            try:
                pg_cur.execute("""
                    INSERT INTO firms (id, name, settings, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        settings = EXCLUDED.settings
                """, firm)
            except Exception as e:
                print(f"  Warning: Error inserting firm {firm[0]}: {e}")
    
    pg_conn.commit()
    print(f"✓ Migrated {len(firms)} firms")
    return len(firms)


def migrate_templates(pg_conn, sqlite_conn, batch_size=100):
    """Migrate templates from SQLite to PostgreSQL."""
    print("\nMigrating templates...")
    
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT COUNT(*) FROM templates")
    total = sqlite_cur.fetchone()[0]
    print(f"  Total templates to migrate: {total}")
    
    sqlite_cur.execute("""
        SELECT id, firm_id, name, original_filename, category, subcategory,
               court_type, jurisdiction, case_types, variables, variable_mappings,
               tags, file_content, file_hash, file_size, is_active, upload_date,
               last_used, usage_count
        FROM templates
    """)
    
    migrated = 0
    errors = 0
    
    with pg_conn.cursor() as pg_cur:
        while True:
            rows = sqlite_cur.fetchmany(batch_size)
            if not rows:
                break
            
            for row in rows:
                try:
                    # Convert variables and variable_mappings to proper JSON
                    variables = row[9] if row[9] else '[]'
                    var_mappings = row[10] if row[10] else '{}'

                    # Convert SQLite integer (1/0) to PostgreSQL boolean
                    is_active = bool(row[15]) if row[15] is not None else True

                    pg_cur.execute("""
                        INSERT INTO templates (
                            firm_id, name, original_filename, category, subcategory,
                            court_type, jurisdiction, case_types, variables, variable_mappings,
                            tags, file_content, file_hash, file_size, is_active, upload_date,
                            last_used, usage_count
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (firm_id, name) DO UPDATE SET
                            original_filename = EXCLUDED.original_filename,
                            category = EXCLUDED.category,
                            file_content = EXCLUDED.file_content,
                            file_hash = EXCLUDED.file_hash,
                            file_size = EXCLUDED.file_size,
                            usage_count = EXCLUDED.usage_count
                    """, (
                        row[1], row[2], row[3], row[4], row[5],
                        row[6], row[7], row[8], variables, var_mappings,
                        row[11], psycopg2.Binary(row[12]) if row[12] else None,
                        row[13], row[14], is_active, row[16], row[17], row[18]
                    ))
                    migrated += 1
                except Exception as e:
                    pg_conn.rollback()  # Reset transaction after error
                    errors += 1
                    if errors <= 5:
                        print(f"  Error migrating template '{row[2]}': {e}")
            
            pg_conn.commit()
            print(f"  Progress: {migrated}/{total} ({100*migrated/total:.1f}%)", end='\r')
    
    print(f"\n✓ Migrated {migrated} templates ({errors} errors)")
    return migrated


def migrate_attorneys(pg_conn, sqlite_conn):
    """Migrate attorney profiles from SQLite to PostgreSQL."""
    print("\nMigrating attorney profiles...")
    
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("""
        SELECT firm_id, attorney_name, bar_number, email, phone, fax,
               firm_name, firm_address, firm_city, firm_state, firm_zip,
               is_primary, is_active, created_at, updated_at
        FROM attorneys
    """)
    attorneys = sqlite_cur.fetchall()
    
    if not attorneys:
        print("  No attorneys found in SQLite")
        return 0
    
    with pg_conn.cursor() as pg_cur:
        for att in attorneys:
            try:
                # Convert SQLite integers (1/0) to PostgreSQL booleans
                # att[11] = is_primary, att[12] = is_active
                is_primary = bool(att[11]) if att[11] is not None else False
                is_active = bool(att[12]) if att[12] is not None else True

                pg_cur.execute("""
                    INSERT INTO attorneys (
                        firm_id, attorney_name, bar_number, email, phone, fax,
                        firm_name, firm_address, firm_city, firm_state, firm_zip,
                        is_primary, is_active, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (firm_id, bar_number) DO UPDATE SET
                        attorney_name = EXCLUDED.attorney_name,
                        email = EXCLUDED.email,
                        phone = EXCLUDED.phone,
                        firm_name = EXCLUDED.firm_name,
                        firm_address = EXCLUDED.firm_address,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    att[0], att[1], att[2], att[3], att[4], att[5],
                    att[6], att[7], att[8], att[9], att[10],
                    is_primary, is_active, att[13], att[14]
                ))
            except Exception as e:
                pg_conn.rollback()
                print(f"  Warning: Error inserting attorney: {e}")

    pg_conn.commit()
    print(f"✓ Migrated {len(attorneys)} attorneys")
    return len(attorneys)


def migrate_generated_documents(pg_conn, sqlite_conn):
    """Migrate generated document history from SQLite to PostgreSQL."""
    print("\nMigrating generated documents history...")
    
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("""
        SELECT firm_id, template_id, template_name, case_id, client_name,
               variables_used, generated_by, generated_at, output_filename
        FROM generated_documents
    """)
    docs = sqlite_cur.fetchall()
    
    if not docs:
        print("  No generated documents found")
        return 0
    
    with pg_conn.cursor() as pg_cur:
        for doc in docs:
            try:
                variables_used = doc[5] if doc[5] else '{}'
                pg_cur.execute("""
                    INSERT INTO generated_documents (
                        firm_id, template_id, template_name, case_id, client_name,
                        variables_used, generated_by, generated_at, output_filename
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (doc[0], doc[1], doc[2], doc[3], doc[4], 
                      variables_used, doc[6], doc[7], doc[8]))
            except Exception as e:
                print(f"  Warning: Error inserting generated doc: {e}")
    
    pg_conn.commit()
    print(f"✓ Migrated {len(docs)} generated documents")
    return len(docs)


def verify_migration(pg_conn, sqlite_templates, sqlite_attorneys):
    """Verify migration counts."""
    print("\nVerifying migration...")
    
    with pg_conn.cursor() as pg_cur:
        pg_cur.execute("SELECT COUNT(*) FROM firms")
        pg_firms = pg_cur.fetchone()[0]
        
        pg_cur.execute("SELECT COUNT(*) FROM templates")
        pg_templates = pg_cur.fetchone()[0]
        
        pg_cur.execute("SELECT COUNT(*) FROM attorneys")
        pg_attorneys = pg_cur.fetchone()[0]
    
    # SQLite counts
    sqlite_conn = sqlite3.connect(sqlite_templates)
    cur = sqlite_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM firms")
    sq_firms = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM templates")
    sq_templates = cur.fetchone()[0]
    sqlite_conn.close()
    
    sqlite_conn = sqlite3.connect(sqlite_attorneys)
    cur = sqlite_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM attorneys")
    sq_attorneys = cur.fetchone()[0]
    sqlite_conn.close()
    
    print(f"\n{'Table':<20} {'SQLite':<12} {'PostgreSQL':<12} {'Status'}")
    print("-" * 56)
    print(f"{'Firms':<20} {sq_firms:<12} {pg_firms:<12} {'✓' if pg_firms >= sq_firms else '✗'}")
    print(f"{'Templates':<20} {sq_templates:<12} {pg_templates:<12} {'✓' if pg_templates >= sq_templates else '✗'}")
    print(f"{'Attorneys':<20} {sq_attorneys:<12} {pg_attorneys:<12} {'✓' if pg_attorneys >= sq_attorneys else '✗'}")
    
    return pg_templates >= sq_templates and pg_attorneys >= sq_attorneys


def main():
    parser = argparse.ArgumentParser(description="Migrate LawMetrics data to PostgreSQL")
    parser.add_argument('--init', action='store_true', help='Initialize PostgreSQL schema only')
    parser.add_argument('--migrate', action='store_true', help='Migrate all data')
    parser.add_argument('--verify', action='store_true', help='Verify migration counts')
    parser.add_argument('--all', action='store_true', help='Do init, migrate, and verify')
    args = parser.parse_args()
    
    if not any([args.init, args.migrate, args.verify, args.all]):
        parser.print_help()
        return
    
    print("=" * 60)
    print("LawMetrics SQLite to PostgreSQL Migration")
    print("=" * 60)
    print(f"\nPostgreSQL: {PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['database']}")
    print(f"SQLite Templates: {SQLITE_TEMPLATES}")
    print(f"SQLite Attorneys: {SQLITE_ATTORNEYS}")
    
    try:
        pg_conn = get_pg_connection()
        print("\n✓ Connected to PostgreSQL")
    except Exception as e:
        print(f"\n✗ Failed to connect to PostgreSQL: {e}")
        return
    
    try:
        if args.init or args.all:
            init_postgres_schema(pg_conn)
        
        if args.migrate or args.all:
            # Open SQLite connections
            sqlite_templates = sqlite3.connect(SQLITE_TEMPLATES)
            sqlite_attorneys = sqlite3.connect(SQLITE_ATTORNEYS)
            
            # Migrate in order (firms first due to foreign keys)
            migrate_firms(pg_conn, sqlite_templates)
            migrate_templates(pg_conn, sqlite_templates)
            migrate_attorneys(pg_conn, sqlite_attorneys)
            migrate_generated_documents(pg_conn, sqlite_templates)
            
            sqlite_templates.close()
            sqlite_attorneys.close()
        
        if args.verify or args.all:
            verify_migration(pg_conn, SQLITE_TEMPLATES, SQLITE_ATTORNEYS)
        
        print("\n" + "=" * 60)
        print("Migration complete!")
        print("=" * 60)
        
    finally:
        pg_conn.close()


if __name__ == "__main__":
    main()
