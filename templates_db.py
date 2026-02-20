"""
Legal Document Template Management System

Stores and manages firm-specific document templates (pleas, NDAs, contracts, motions)
parallel to MyCase. Enables AI-powered document generation customized for specific
courts, clients, and purposes.

Database Schema:
- templates: Master template records with metadata
- template_versions: Version history for each template
- template_variables: Defined variables/placeholders in templates
- template_usage: Audit log of document generations
- generated_documents: History of generated documents
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum

from db.connection import get_connection


class TemplateCategory(Enum):
    """Categories of legal document templates."""
    PLEA = "plea"
    MOTION = "motion"
    NDA = "nda"
    CONTRACT = "contract"
    LETTER = "letter"
    BRIEF = "brief"
    DISCOVERY = "discovery"
    FILING = "filing"
    AGREEMENT = "agreement"
    NOTICE = "notice"
    OTHER = "other"


class TemplateStatus(Enum):
    """Status of a template."""
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"


@dataclass
class Template:
    """Represents a document template."""
    id: Optional[int] = None
    firm_id: Optional[str] = None
    name: str = ""
    category: TemplateCategory = TemplateCategory.OTHER
    description: str = ""
    court_type: Optional[str] = None  # e.g., "Municipal", "District", "Federal"
    case_types: List[str] = field(default_factory=list)  # e.g., ["DWI", "Traffic"]
    jurisdiction: Optional[str] = None  # e.g., "Ohio", "Hamilton County"
    status: TemplateStatus = TemplateStatus.ACTIVE
    file_path: Optional[str] = None  # Path to original .docx template
    content_hash: Optional[str] = None
    variables: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    version: int = 1
    usage_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "firm_id": self.firm_id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "court_type": self.court_type,
            "case_types": self.case_types,
            "jurisdiction": self.jurisdiction,
            "status": self.status.value,
            "file_path": self.file_path,
            "variables": self.variables,
            "tags": self.tags,
            "version": self.version,
            "usage_count": self.usage_count,
        }


@dataclass
class GeneratedDocument:
    """Represents a generated document from a template."""
    id: Optional[int] = None
    firm_id: Optional[str] = None
    template_id: int = 0
    template_name: str = ""
    case_id: Optional[int] = None
    case_name: Optional[str] = None
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    court: Optional[str] = None
    purpose: str = ""
    variables_used: Dict[str, Any] = field(default_factory=dict)
    output_path: Optional[str] = None
    generated_by: Optional[str] = None
    generated_at: Optional[datetime] = None


class TemplatesDatabase:
    """PostgreSQL database for template management (multi-tenant via firm_id)."""

    def __init__(self, firm_id: Optional[str] = None):
        self.firm_id = firm_id
        self._init_tables()

    def _init_tables(self):
        """Initialize database tables."""
        with get_connection() as conn:
            with conn.cursor() as cursor:

                # Master template records
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS templates (
                        id SERIAL PRIMARY KEY,
                        firm_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        description TEXT,
                        court_type TEXT,
                        case_types JSONB,
                        jurisdiction TEXT,
                        status TEXT DEFAULT 'active',
                        file_path TEXT,
                        content_hash TEXT,
                        variables JSONB,
                        tags JSONB,
                        created_by TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        version INTEGER DEFAULT 1,
                        usage_count INTEGER DEFAULT 0,
                        UNIQUE(firm_id, name, category, jurisdiction)
                    )
                """)

                # Template version history
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS template_versions (
                        id SERIAL PRIMARY KEY,
                        firm_id TEXT NOT NULL,
                        template_id INTEGER NOT NULL,
                        version INTEGER NOT NULL,
                        file_path TEXT,
                        content_hash TEXT,
                        variables JSONB,
                        change_notes TEXT,
                        created_by TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (template_id) REFERENCES templates(id),
                        UNIQUE(template_id, version)
                    )
                """)

                # Template variable definitions
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS template_variables (
                        id SERIAL PRIMARY KEY,
                        firm_id TEXT NOT NULL,
                        template_id INTEGER NOT NULL,
                        variable_name TEXT NOT NULL,
                        variable_type TEXT DEFAULT 'text',
                        description TEXT,
                        default_value TEXT,
                        required BOOLEAN DEFAULT TRUE,
                        choices JSONB,
                        case_field_mapping TEXT,
                        FOREIGN KEY (template_id) REFERENCES templates(id),
                        UNIQUE(template_id, variable_name)
                    )
                """)

                # Generated document history
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS generated_documents (
                        id SERIAL PRIMARY KEY,
                        firm_id TEXT NOT NULL,
                        template_id INTEGER NOT NULL,
                        template_name TEXT,
                        case_id INTEGER,
                        case_name TEXT,
                        client_id INTEGER,
                        client_name TEXT,
                        court TEXT,
                        purpose TEXT,
                        variables_used JSONB,
                        output_path TEXT,
                        generated_by TEXT,
                        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (template_id) REFERENCES templates(id)
                    )
                """)

                # Full-text search vector for templates
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS templates_fts (
                        id SERIAL PRIMARY KEY,
                        template_id INTEGER UNIQUE NOT NULL,
                        firm_id TEXT NOT NULL,
                        search_vector tsvector,
                        FOREIGN KEY (template_id) REFERENCES templates(id)
                    )
                """)

                # Create indexes for performance
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_templates_firm_id
                    ON templates(firm_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_templates_status
                    ON templates(firm_id, status)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_templates_fts_search
                    ON templates_fts USING GIN(search_vector)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_generated_docs_firm
                    ON generated_documents(firm_id)
                """)

            conn.commit()

    # =========================================================================
    # Template CRUD Operations
    # =========================================================================

    def add_template(self, template: Template, file_content: Optional[bytes] = None) -> int:
        """Add a new template to the database."""
        if file_content:
            template.content_hash = hashlib.sha256(file_content).hexdigest()

        with get_connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    INSERT INTO templates (
                        firm_id, name, category, description, court_type, case_types,
                        jurisdiction, status, file_path, content_hash, variables,
                        tags, created_by, version, usage_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    template.firm_id,
                    template.name,
                    template.category.value,
                    template.description,
                    template.court_type,
                    json.dumps(template.case_types),
                    template.jurisdiction,
                    template.status.value,
                    template.file_path,
                    template.content_hash,
                    json.dumps(template.variables),
                    json.dumps(template.tags),
                    template.created_by,
                    template.version,
                    template.usage_count,
                ))

                template_id = cursor.fetchone()[0]

                # Add initial version
                cursor.execute("""
                    INSERT INTO template_versions (
                        firm_id, template_id, version, file_path, content_hash, variables,
                        change_notes, created_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    template.firm_id,
                    template_id,
                    1,
                    template.file_path,
                    template.content_hash,
                    json.dumps(template.variables),
                    "Initial version",
                    template.created_by,
                ))

            conn.commit()
            return template_id

    def get_template(self, template_id: int) -> Optional[Template]:
        """Get a template by ID."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM templates WHERE id = %s AND firm_id = %s",
                    (template_id, self.firm_id)
                )
                row = cursor.fetchone()

                if not row:
                    return None

                return self._row_to_template(row)

    def get_template_by_name(self, name: str, category: Optional[str] = None) -> Optional[Template]:
        """Get a template by name and optionally category."""
        with get_connection() as conn:
            with conn.cursor() as cursor:

                if category:
                    cursor.execute(
                        "SELECT * FROM templates WHERE name = %s AND category = %s AND status = 'active' AND firm_id = %s",
                        (name, category, self.firm_id)
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM templates WHERE name = %s AND status = 'active' AND firm_id = %s",
                        (name, self.firm_id)
                    )

                row = cursor.fetchone()
                return self._row_to_template(row) if row else None

    def list_templates(
        self,
        category: Optional[str] = None,
        court_type: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        case_type: Optional[str] = None,
        status: str = "active",
        limit: int = 100
    ) -> List[Template]:
        """List templates with optional filters."""
        with get_connection() as conn:
            with conn.cursor() as cursor:

                query = "SELECT * FROM templates WHERE status = %s AND firm_id = %s"
                params = [status, self.firm_id]

                if category:
                    query += " AND category = %s"
                    params.append(category)

                if court_type:
                    query += " AND court_type = %s"
                    params.append(court_type)

                if jurisdiction:
                    query += " AND jurisdiction = %s"
                    params.append(jurisdiction)

                if case_type:
                    query += " AND case_types @> %s"
                    params.append(json.dumps([case_type]))

                query += " ORDER BY usage_count DESC, name ASC LIMIT %s"
                params.append(limit)

                cursor.execute(query, params)
                return [self._row_to_template(row) for row in cursor.fetchall()]

    def search_templates(self, query: str, limit: int = 20) -> List[Template]:
        """Full-text search for templates."""
        with get_connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT t.* FROM templates t
                    JOIN templates_fts fts ON t.id = fts.template_id
                    WHERE fts.search_vector @@ websearch_to_tsquery(%s)
                    AND t.status = 'active'
                    AND t.firm_id = %s
                    ORDER BY ts_rank(fts.search_vector, websearch_to_tsquery(%s)) DESC
                    LIMIT %s
                """, (query, self.firm_id, query, limit))

                return [self._row_to_template(row) for row in cursor.fetchall()]

    def update_template(self, template_id: int, updates: dict, file_content: Optional[bytes] = None) -> bool:
        """Update a template and create a new version."""
        with get_connection() as conn:
            with conn.cursor() as cursor:

                # Get current version
                cursor.execute(
                    "SELECT version FROM templates WHERE id = %s AND firm_id = %s",
                    (template_id, self.firm_id)
                )
                row = cursor.fetchone()
                if not row:
                    return False

                new_version = row[0] + 1

                # Update hash if new content
                if file_content:
                    updates["content_hash"] = hashlib.sha256(file_content).hexdigest()

                # Build update query
                set_clauses = []
                params = []
                for key, value in updates.items():
                    if key in ("case_types", "variables", "tags"):
                        value = json.dumps(value)
                    set_clauses.append(f"{key} = %s")
                    params.append(value)

                set_clauses.append("version = %s")
                params.append(new_version)
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")

                params.append(template_id)
                params.append(self.firm_id)

                cursor.execute(
                    f"UPDATE templates SET {', '.join(set_clauses)} WHERE id = %s AND firm_id = %s",
                    params
                )

                # Add version record
                cursor.execute("""
                    INSERT INTO template_versions (
                        firm_id, template_id, version, file_path, content_hash, variables,
                        change_notes, created_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    self.firm_id,
                    template_id,
                    new_version,
                    updates.get("file_path"),
                    updates.get("content_hash"),
                    json.dumps(updates.get("variables", [])),
                    updates.get("change_notes", "Updated"),
                    updates.get("updated_by"),
                ))

            conn.commit()
            return True

    def increment_usage(self, template_id: int) -> None:
        """Increment the usage count for a template."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE templates SET usage_count = usage_count + 1 WHERE id = %s AND firm_id = %s",
                    (template_id, self.firm_id)
                )
            conn.commit()

    # =========================================================================
    # Variable Management
    # =========================================================================

    def add_variable(
        self,
        template_id: int,
        variable_name: str,
        variable_type: str = "text",
        description: str = "",
        default_value: str = "",
        required: bool = True,
        choices: Optional[List[str]] = None,
        case_field_mapping: Optional[str] = None
    ) -> int:
        """Add a variable definition to a template."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO template_variables (
                        firm_id, template_id, variable_name, variable_type, description,
                        default_value, required, choices, case_field_mapping
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    self.firm_id,
                    template_id,
                    variable_name,
                    variable_type,
                    description,
                    default_value,
                    required,
                    json.dumps(choices) if choices else None,
                    case_field_mapping,
                ))
                var_id = cursor.fetchone()[0]
            conn.commit()
            return var_id

    def get_variables(self, template_id: int) -> List[dict]:
        """Get all variable definitions for a template."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM template_variables WHERE template_id = %s AND firm_id = %s",
                    (template_id, self.firm_id)
                )
                rows = cursor.fetchall()
                # Convert psycopg2 rows to dicts
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]

    # =========================================================================
    # Generated Document Tracking
    # =========================================================================

    def log_generation(self, doc: GeneratedDocument) -> int:
        """Log a document generation event."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO generated_documents (
                        firm_id, template_id, template_name, case_id, case_name,
                        client_id, client_name, court, purpose,
                        variables_used, output_path, generated_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    doc.firm_id,
                    doc.template_id,
                    doc.template_name,
                    doc.case_id,
                    doc.case_name,
                    doc.client_id,
                    doc.client_name,
                    doc.court,
                    doc.purpose,
                    json.dumps(doc.variables_used),
                    doc.output_path,
                    doc.generated_by,
                ))

                doc_id = cursor.fetchone()[0]

                # Increment template usage
                self.increment_usage(doc.template_id)

            conn.commit()
            return doc_id

    def get_generation_history(
        self,
        template_id: Optional[int] = None,
        case_id: Optional[int] = None,
        limit: int = 50
    ) -> List[dict]:
        """Get document generation history."""
        with get_connection() as conn:
            with conn.cursor() as cursor:

                query = "SELECT * FROM generated_documents WHERE firm_id = %s"
                params = [self.firm_id]

                if template_id:
                    query += " AND template_id = %s"
                    params.append(template_id)

                if case_id:
                    query += " AND case_id = %s"
                    params.append(case_id)

                query += " ORDER BY generated_at DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]

    # =========================================================================
    # Helpers
    # =========================================================================

    def _row_to_template(self, row) -> Template:
        """Convert a database row to a Template object."""
        columns = [desc[0] for desc in row.cursor.description] if hasattr(row, 'cursor') else None
        if columns:
            row_dict = dict(zip(columns, row))
        else:
            # Assume row is already a dict-like object from cursor
            row_dict = dict(row) if hasattr(row, '__iter__') else row

        return Template(
            id=row_dict.get("id"),
            firm_id=row_dict.get("firm_id"),
            name=row_dict.get("name", ""),
            category=TemplateCategory(row_dict.get("category", "other")),
            description=row_dict.get("description") or "",
            court_type=row_dict.get("court_type"),
            case_types=json.loads(row_dict.get("case_types") or "[]"),
            jurisdiction=row_dict.get("jurisdiction"),
            status=TemplateStatus(row_dict.get("status", "active")),
            file_path=row_dict.get("file_path"),
            content_hash=row_dict.get("content_hash"),
            variables=json.loads(row_dict.get("variables") or "[]"),
            tags=json.loads(row_dict.get("tags") or "[]"),
            created_by=row_dict.get("created_by"),
            created_at=row_dict.get("created_at"),
            updated_at=row_dict.get("updated_at"),
            version=row_dict.get("version", 1),
            usage_count=row_dict.get("usage_count", 0),
        )


def get_templates_db(firm_id: Optional[str] = None) -> TemplatesDatabase:
    """Get a TemplatesDatabase instance."""
    return TemplatesDatabase(firm_id=firm_id)
