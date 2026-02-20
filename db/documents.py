"""
Document Engine — PostgreSQL Multi-Tenant

Firms, templates (with full-text search via tsvector), and
generated document history.
"""
import logging
from typing import List, Dict, Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)


DOCUMENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS firms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS templates (
    id SERIAL PRIMARY KEY,
    firm_id TEXT NOT NULL REFERENCES firms(id),
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
    usage_count INTEGER DEFAULT 0,
    search_vector TSVECTOR,
    UNIQUE(firm_id, name)
);

CREATE TABLE IF NOT EXISTS generated_documents (
    id SERIAL PRIMARY KEY,
    firm_id TEXT NOT NULL REFERENCES firms(id),
    template_id INTEGER REFERENCES templates(id),
    template_name TEXT,
    case_id TEXT,
    client_name TEXT,
    variables_used JSONB DEFAULT '{}',
    generated_by TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    output_filename TEXT
);

-- Full-text search index using stored tsvector column
CREATE INDEX IF NOT EXISTS idx_templates_fts ON templates USING GIN (search_vector);

-- Trigger to keep search_vector in sync
CREATE OR REPLACE FUNCTION templates_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        to_tsvector('english', COALESCE(NEW.name, '') || ' ' ||
                                COALESCE(NEW.category, '') || ' ' ||
                                COALESCE(NEW.tags, ''));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'tsvector_update_templates'
    ) THEN
        CREATE TRIGGER tsvector_update_templates
        BEFORE INSERT OR UPDATE ON templates
        FOR EACH ROW EXECUTE FUNCTION templates_search_trigger();
    END IF;
END
$$;

-- Other indexes
CREATE INDEX IF NOT EXISTS idx_templates_firm ON templates(firm_id);
CREATE INDEX IF NOT EXISTS idx_templates_category ON templates(firm_id, category);
CREATE INDEX IF NOT EXISTS idx_generated_docs_firm ON generated_documents(firm_id);
CREATE INDEX IF NOT EXISTS idx_generated_docs_case ON generated_documents(case_id);
"""


def ensure_documents_tables():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(DOCUMENTS_SCHEMA)

        # Self-healing: add search_vector column if table existed before FTS migration.
        # CREATE TABLE IF NOT EXISTS won't add new columns to an existing table,
        # so we need this ALTER TABLE to cover tables created before the column was added.
        cur.execute("""
            ALTER TABLE templates ADD COLUMN IF NOT EXISTS search_vector TSVECTOR
        """)

        # Backfill any rows with NULL search_vector (e.g., after column was just added)
        cur.execute("""
            UPDATE templates SET search_vector =
                to_tsvector('english', COALESCE(name, '') || ' ' ||
                                        COALESCE(category, '') || ' ' ||
                                        COALESCE(tags, ''))
            WHERE search_vector IS NULL
        """)
        backfilled = cur.rowcount
        if backfilled > 0:
            logger.info("Backfilled search_vector for %d templates", backfilled)

    logger.info("Documents tables ensured")


# ── Firms ─────────────────────────────────────────────────────

def upsert_firm(firm_id: str, name: str, settings: dict = None) -> str:
    import json
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO firms (id, name, settings)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                settings = COALESCE(EXCLUDED.settings, firms.settings)
            RETURNING id
            """,
            (firm_id, name, json.dumps(settings or {})),
        )
        row = cur.fetchone()
        return row["id"] if row else firm_id


def get_firm(firm_id: str) -> Optional[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM firms WHERE id = %s", (firm_id,))
        row = cur.fetchone()
        return dict(row) if row else None


# ── Templates ─────────────────────────────────────────────────

def insert_template(
    firm_id: str,
    name: str,
    original_filename: str = None,
    category: str = None,
    subcategory: str = None,
    court_type: str = None,
    jurisdiction: str = None,
    case_types: str = None,
    variables: list = None,
    variable_mappings: dict = None,
    tags: str = None,
    file_content: bytes = None,
    file_hash: str = None,
    file_size: int = None,
) -> int:
    import json
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO templates
                (firm_id, name, original_filename, category, subcategory,
                 court_type, jurisdiction, case_types, variables,
                 variable_mappings, tags, file_content, file_hash, file_size)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (firm_id, name) DO UPDATE SET
                original_filename = EXCLUDED.original_filename,
                category = COALESCE(EXCLUDED.category, templates.category),
                subcategory = COALESCE(EXCLUDED.subcategory, templates.subcategory),
                court_type = COALESCE(EXCLUDED.court_type, templates.court_type),
                jurisdiction = COALESCE(EXCLUDED.jurisdiction, templates.jurisdiction),
                case_types = COALESCE(EXCLUDED.case_types, templates.case_types),
                variables = COALESCE(EXCLUDED.variables, templates.variables),
                variable_mappings = COALESCE(EXCLUDED.variable_mappings, templates.variable_mappings),
                tags = COALESCE(EXCLUDED.tags, templates.tags),
                file_content = COALESCE(EXCLUDED.file_content, templates.file_content),
                file_hash = COALESCE(EXCLUDED.file_hash, templates.file_hash),
                file_size = COALESCE(EXCLUDED.file_size, templates.file_size)
            RETURNING id
            """,
            (firm_id, name, original_filename, category, subcategory,
             court_type, jurisdiction, case_types,
             json.dumps(variables or []), json.dumps(variable_mappings or {}),
             tags, file_content, file_hash, file_size),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_template(template_id: int) -> Optional[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM templates WHERE id = %s", (template_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_templates(firm_id: str, category: str = None, active_only: bool = True) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        conditions = ["firm_id = %s"]
        params = [firm_id]
        if active_only:
            conditions.append("is_active = TRUE")
        if category:
            conditions.append("category = %s")
            params.append(category)
        cur.execute(
            f"""
            SELECT id, firm_id, name, original_filename, category, subcategory,
                   court_type, jurisdiction, case_types, variables, tags,
                   file_hash, file_size, is_active, upload_date, last_used, usage_count
            FROM templates
            WHERE {' AND '.join(conditions)}
            ORDER BY name
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


# Stop words to strip from search queries
_STOP_WORDS = {
    "i", "me", "my", "need", "want", "looking", "for", "please", "the", "a", "an",
    "to", "of", "in", "is", "it", "can", "you", "do", "get", "make", "create",
    "give", "find", "show", "help", "with", "this", "that",
}

# Synonym mappings for legal document search
_SYNONYMS = {
    "cash bond": "bond assignment",
    "assignment of cash bond": "bond assignment",
    "mtd": "motion to dismiss",
    "mtc": "motion to continue",
    "eoa": "entry of appearance",
    "noh": "notice of hearing",
    "rog": "interrogatories",
    "rogs": "interrogatories",
    "rfp": "request for production",
    "rfa": "request for admission",
    "nol pros": "nolle prosequi",
    "nolle pros": "nolle prosequi",
    "dor": "director of revenue",
}


def search_templates(firm_id: str, query: str, limit: int = 10) -> List[Dict]:
    """Search templates using PostgreSQL full-text search with synonym expansion."""
    # Apply synonym mappings
    q_lower = query.lower().strip()
    for alt, canonical in _SYNONYMS.items():
        if alt in q_lower:
            q_lower = canonical
            break

    # Remove stop words and build OR query
    words = [w for w in q_lower.split() if w not in _STOP_WORDS and len(w) > 1]
    if not words:
        words = q_lower.split()

    with get_connection() as conn:
        cur = conn.cursor()

        if words:
            # Try tsvector search with OR logic
            tsquery = " | ".join(words)
            cur.execute(
                """
                SELECT id, firm_id, name, original_filename, category, subcategory,
                       court_type, jurisdiction, case_types, variables, tags,
                       file_hash, file_size, is_active, upload_date, last_used, usage_count,
                       ts_rank(search_vector, to_tsquery('english', %s)) AS rank
                FROM templates
                WHERE firm_id = %s AND is_active = TRUE
                  AND search_vector @@ to_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s
                """,
                (tsquery, firm_id, tsquery, limit),
            )
            results = [dict(r) for r in cur.fetchall()]
            if results:
                return results

        # Fallback: ILIKE search on name
        cur.execute(
            """
            SELECT id, firm_id, name, original_filename, category, subcategory,
                   court_type, jurisdiction, case_types, variables, tags,
                   file_hash, file_size, is_active, upload_date, last_used, usage_count
            FROM templates
            WHERE firm_id = %s AND is_active = TRUE
              AND name ILIKE %s
            ORDER BY name
            LIMIT %s
            """,
            (firm_id, f"%{q_lower}%", limit),
        )
        return [dict(r) for r in cur.fetchall()]


def increment_template_usage(template_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE templates
            SET usage_count = usage_count + 1, last_used = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (template_id,),
        )


# ── Generated Documents ───────────────────────────────────────

def record_generated_document(
    firm_id: str,
    template_id: int = None,
    template_name: str = None,
    case_id: str = None,
    client_name: str = None,
    variables_used: dict = None,
    generated_by: str = None,
    output_filename: str = None,
) -> int:
    import json
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO generated_documents
                (firm_id, template_id, template_name, case_id, client_name,
                 variables_used, generated_by, output_filename)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (firm_id, template_id, template_name, case_id, client_name,
             json.dumps(variables_used or {}), generated_by, output_filename),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_generated_documents(firm_id: str, case_id: str = None, limit: int = 50) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        if case_id:
            cur.execute(
                """
                SELECT * FROM generated_documents
                WHERE firm_id = %s AND case_id = %s
                ORDER BY generated_at DESC
                LIMIT %s
                """,
                (firm_id, case_id, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM generated_documents
                WHERE firm_id = %s
                ORDER BY generated_at DESC
                LIMIT %s
                """,
                (firm_id, limit),
            )
        return [dict(r) for r in cur.fetchall()]
