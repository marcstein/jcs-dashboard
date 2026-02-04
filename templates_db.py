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

import sqlite3
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum

from config import DATA_DIR


# Database location
TEMPLATES_DB = DATA_DIR / "templates.db"


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
    """SQLite database for template management."""

    def __init__(self, db_path: Path = TEMPLATES_DB):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Master template records
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    court_type TEXT,
                    case_types TEXT,  -- JSON array
                    jurisdiction TEXT,
                    status TEXT DEFAULT 'active',
                    file_path TEXT,
                    content_hash TEXT,
                    variables TEXT,  -- JSON array of variable names
                    tags TEXT,  -- JSON array
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 1,
                    usage_count INTEGER DEFAULT 0,
                    UNIQUE(name, category, jurisdiction)
                )
            """)

            # Template version history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS template_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    file_path TEXT,
                    content_hash TEXT,
                    variables TEXT,
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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL,
                    variable_name TEXT NOT NULL,
                    variable_type TEXT DEFAULT 'text',  -- text, date, number, choice, case_field
                    description TEXT,
                    default_value TEXT,
                    required BOOLEAN DEFAULT TRUE,
                    choices TEXT,  -- JSON array for choice type
                    case_field_mapping TEXT,  -- Maps to MyCase field if case_field type
                    FOREIGN KEY (template_id) REFERENCES templates(id),
                    UNIQUE(template_id, variable_name)
                )
            """)

            # Generated document history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS generated_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL,
                    template_name TEXT,
                    case_id INTEGER,
                    case_name TEXT,
                    client_id INTEGER,
                    client_name TEXT,
                    court TEXT,
                    purpose TEXT,
                    variables_used TEXT,  -- JSON object
                    output_path TEXT,
                    generated_by TEXT,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (template_id) REFERENCES templates(id)
                )
            """)

            # Full-text search index for templates
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS templates_fts USING fts5(
                    name, description, tags, court_type, jurisdiction,
                    content='templates',
                    content_rowid='id'
                )
            """)

            # Triggers to keep FTS in sync
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS templates_ai AFTER INSERT ON templates BEGIN
                    INSERT INTO templates_fts(rowid, name, description, tags, court_type, jurisdiction)
                    VALUES (new.id, new.name, new.description, new.tags, new.court_type, new.jurisdiction);
                END
            """)

            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS templates_ad AFTER DELETE ON templates BEGIN
                    INSERT INTO templates_fts(templates_fts, rowid, name, description, tags, court_type, jurisdiction)
                    VALUES ('delete', old.id, old.name, old.description, old.tags, old.court_type, old.jurisdiction);
                END
            """)

            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS templates_au AFTER UPDATE ON templates BEGIN
                    INSERT INTO templates_fts(templates_fts, rowid, name, description, tags, court_type, jurisdiction)
                    VALUES ('delete', old.id, old.name, old.description, old.tags, old.court_type, old.jurisdiction);
                    INSERT INTO templates_fts(rowid, name, description, tags, court_type, jurisdiction)
                    VALUES (new.id, new.name, new.description, new.tags, new.court_type, new.jurisdiction);
                END
            """)

            conn.commit()

    # =========================================================================
    # Template CRUD Operations
    # =========================================================================

    def add_template(self, template: Template, file_content: Optional[bytes] = None) -> int:
        """Add a new template to the database."""
        if file_content:
            template.content_hash = hashlib.sha256(file_content).hexdigest()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO templates (
                    name, category, description, court_type, case_types,
                    jurisdiction, status, file_path, content_hash, variables,
                    tags, created_by, version, usage_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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

            template_id = cursor.lastrowid

            # Add initial version
            cursor.execute("""
                INSERT INTO template_versions (
                    template_id, version, file_path, content_hash, variables,
                    change_notes, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                template_id,
                1,
                template.file_path,
                template.content_hash,
                json.dumps(template.variables),
                "Initial version",
                template.created_by,
            ))

            return template_id

    def get_template(self, template_id: int) -> Optional[Template]:
        """Get a template by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_template(row)

    def get_template_by_name(self, name: str, category: Optional[str] = None) -> Optional[Template]:
        """Get a template by name and optionally category."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if category:
                cursor.execute(
                    "SELECT * FROM templates WHERE name = ? AND category = ? AND status = 'active'",
                    (name, category)
                )
            else:
                cursor.execute(
                    "SELECT * FROM templates WHERE name = ? AND status = 'active'",
                    (name,)
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
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM templates WHERE status = ?"
            params = [status]

            if category:
                query += " AND category = ?"
                params.append(category)

            if court_type:
                query += " AND court_type = ?"
                params.append(court_type)

            if jurisdiction:
                query += " AND jurisdiction = ?"
                params.append(jurisdiction)

            if case_type:
                query += " AND case_types LIKE ?"
                params.append(f'%"{case_type}"%')

            query += " ORDER BY usage_count DESC, name ASC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            return [self._row_to_template(row) for row in cursor.fetchall()]

    def search_templates(self, query: str, limit: int = 20) -> List[Template]:
        """Full-text search for templates."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT t.* FROM templates t
                JOIN templates_fts fts ON t.id = fts.rowid
                WHERE templates_fts MATCH ?
                AND t.status = 'active'
                ORDER BY rank
                LIMIT ?
            """, (query, limit))

            return [self._row_to_template(row) for row in cursor.fetchall()]

    def update_template(self, template_id: int, updates: dict, file_content: Optional[bytes] = None) -> bool:
        """Update a template and create a new version."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Get current version
            cursor.execute("SELECT version FROM templates WHERE id = ?", (template_id,))
            row = cursor.fetchone()
            if not row:
                return False

            new_version = row["version"] + 1

            # Update hash if new content
            if file_content:
                updates["content_hash"] = hashlib.sha256(file_content).hexdigest()

            # Build update query
            set_clauses = []
            params = []
            for key, value in updates.items():
                if key in ("case_types", "variables", "tags"):
                    value = json.dumps(value)
                set_clauses.append(f"{key} = ?")
                params.append(value)

            set_clauses.append("version = ?")
            params.append(new_version)
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")

            params.append(template_id)

            cursor.execute(
                f"UPDATE templates SET {', '.join(set_clauses)} WHERE id = ?",
                params
            )

            # Add version record
            cursor.execute("""
                INSERT INTO template_versions (
                    template_id, version, file_path, content_hash, variables,
                    change_notes, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                template_id,
                new_version,
                updates.get("file_path"),
                updates.get("content_hash"),
                json.dumps(updates.get("variables", [])),
                updates.get("change_notes", "Updated"),
                updates.get("updated_by"),
            ))

            return True

    def increment_usage(self, template_id: int) -> None:
        """Increment the usage count for a template."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE templates SET usage_count = usage_count + 1 WHERE id = ?",
                (template_id,)
            )

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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO template_variables (
                    template_id, variable_name, variable_type, description,
                    default_value, required, choices, case_field_mapping
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                template_id,
                variable_name,
                variable_type,
                description,
                default_value,
                required,
                json.dumps(choices) if choices else None,
                case_field_mapping,
            ))
            return cursor.lastrowid

    def get_variables(self, template_id: int) -> List[dict]:
        """Get all variable definitions for a template."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM template_variables WHERE template_id = ?",
                (template_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # Generated Document Tracking
    # =========================================================================

    def log_generation(self, doc: GeneratedDocument) -> int:
        """Log a document generation event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO generated_documents (
                    template_id, template_name, case_id, case_name,
                    client_id, client_name, court, purpose,
                    variables_used, output_path, generated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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

            # Increment template usage
            self.increment_usage(doc.template_id)

            return cursor.lastrowid

    def get_generation_history(
        self,
        template_id: Optional[int] = None,
        case_id: Optional[int] = None,
        limit: int = 50
    ) -> List[dict]:
        """Get document generation history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM generated_documents WHERE 1=1"
            params = []

            if template_id:
                query += " AND template_id = ?"
                params.append(template_id)

            if case_id:
                query += " AND case_id = ?"
                params.append(case_id)

            query += " ORDER BY generated_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # Helpers
    # =========================================================================

    def _row_to_template(self, row: sqlite3.Row) -> Template:
        """Convert a database row to a Template object."""
        return Template(
            id=row["id"],
            name=row["name"],
            category=TemplateCategory(row["category"]),
            description=row["description"] or "",
            court_type=row["court_type"],
            case_types=json.loads(row["case_types"] or "[]"),
            jurisdiction=row["jurisdiction"],
            status=TemplateStatus(row["status"]),
            file_path=row["file_path"],
            content_hash=row["content_hash"],
            variables=json.loads(row["variables"] or "[]"),
            tags=json.loads(row["tags"] or "[]"),
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=row["version"],
            usage_count=row["usage_count"],
        )


def get_templates_db() -> TemplatesDatabase:
    """Get a TemplatesDatabase instance."""
    return TemplatesDatabase()
