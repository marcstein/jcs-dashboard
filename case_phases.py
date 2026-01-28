"""
Case Phases Module

Implements the 7-phase universal case management framework with:
- Universal phase definitions (configurable per firm)
- MyCase stage → phase mapping
- Case-type specific workflows (DWI, Muni, Expungement, etc.)
- Phase history tracking and analytics

The 7 Universal Phases:
1. Intake & Case Initiation
2. Discovery & Investigation
3. Legal Analysis & Motion Practice
4. Case Strategy & Negotiation
5. Trial Preparation
6. Disposition & Sentencing
7. Post-Disposition & Case Closure
"""
import sqlite3
import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from contextlib import contextmanager

from config import DATA_DIR


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Phase:
    """Universal case phase definition."""
    code: str
    name: str
    short_name: str
    display_order: int
    description: str = ""
    primary_responsibility: str = ""  # 'Intake Team', 'Paralegals', 'Attorneys', 'Admin'
    typical_duration_min_days: int = 1
    typical_duration_max_days: int = 30
    is_terminal: bool = False
    color: str = "#6B7280"  # Default gray

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class StageMapping:
    """Maps a MyCase stage to a universal phase."""
    mycase_stage_id: int
    mycase_stage_name: str
    phase_code: str
    case_type_filter: Optional[str] = None  # None = all case types
    notes: str = ""


@dataclass
class CaseTypeWorkflow:
    """Defines a case-type specific workflow with its own stage progression."""
    code: str  # 'dwi_pfr', 'expungement', 'muni', 'reinstatement'
    name: str
    description: str
    case_type_patterns: List[str]  # Patterns to match case types
    stages: List[Dict]  # Ordered list of stages specific to this workflow
    applies_alongside_phases: bool = True  # True = overlay, False = replaces phases


@dataclass
class CasePhaseInfo:
    """Current phase/stage info for a case."""
    case_id: int
    case_name: str
    case_type: str
    mycase_stage_id: Optional[int]
    mycase_stage_name: Optional[str]
    phase_code: Optional[str]
    phase_name: Optional[str]
    workflow_code: Optional[str] = None
    workflow_stage: Optional[str] = None
    phase_entered_at: Optional[datetime] = None
    days_in_phase: int = 0


# =============================================================================
# Default Phase Definitions (JCS Criminal Defense)
# =============================================================================

DEFAULT_PHASES = [
    Phase(
        code="intake",
        name="Intake & Case Initiation",
        short_name="Intake",
        display_order=1,
        description="Establish representation and understand case exposure",
        primary_responsibility="Intake Team",
        typical_duration_min_days=1,
        typical_duration_max_days=3,
        color="#10B981"  # Green
    ),
    Phase(
        code="discovery",
        name="Discovery & Investigation",
        short_name="Discovery",
        display_order=2,
        description="Comprehensive information gathering and fact development",
        primary_responsibility="Paralegals",
        typical_duration_min_days=14,
        typical_duration_max_days=56,
        color="#3B82F6"  # Blue
    ),
    Phase(
        code="motions",
        name="Legal Analysis & Motion Practice",
        short_name="Motions",
        display_order=3,
        description="Identify and pursue legal advantages through pretrial litigation",
        primary_responsibility="Attorneys",
        typical_duration_min_days=21,
        typical_duration_max_days=70,
        color="#8B5CF6"  # Purple
    ),
    Phase(
        code="strategy",
        name="Case Strategy & Negotiation",
        short_name="Strategy",
        display_order=4,
        description="Develop comprehensive case theory and pursue optimal resolution",
        primary_responsibility="Attorneys",
        typical_duration_min_days=14,
        typical_duration_max_days=42,
        color="#F59E0B"  # Amber
    ),
    Phase(
        code="trial_prep",
        name="Trial Preparation",
        short_name="Trial Prep",
        display_order=5,
        description="Complete readiness for trial or finalize negotiated resolution",
        primary_responsibility="Attorneys",
        typical_duration_min_days=14,
        typical_duration_max_days=56,
        color="#EF4444"  # Red
    ),
    Phase(
        code="disposition",
        name="Disposition & Sentencing",
        short_name="Disposition",
        display_order=6,
        description="Final adjudication and sentencing",
        primary_responsibility="Attorneys",
        typical_duration_min_days=1,
        typical_duration_max_days=42,
        color="#EC4899"  # Pink
    ),
    Phase(
        code="post_disposition",
        name="Post-Disposition & Case Closure",
        short_name="Closing",
        display_order=7,
        description="Complete client service, ensure compliance, and close file",
        primary_responsibility="Admin",
        typical_duration_min_days=7,
        typical_duration_max_days=28,
        is_terminal=True,
        color="#6B7280"  # Gray
    ),
]


# =============================================================================
# Default Stage Mappings (JCS MyCase Stages → Phases)
# =============================================================================

DEFAULT_STAGE_MAPPINGS = [
    # Phase 2: Discovery
    {"stage_name": "Awaiting Discovery", "phase_code": "discovery"},
    {"stage_name": "Discovery Review", "phase_code": "discovery"},
    {"stage_name": "Depositions", "phase_code": "discovery"},

    # Phase 3: Motions
    {"stage_name": "Arraignment", "phase_code": "motions"},
    {"stage_name": "Preliminary Hearing", "phase_code": "motions"},
    {"stage_name": "CaseNet Checklist", "phase_code": "motions"},
    {"stage_name": "OOP Hearing Scheduled", "phase_code": "motions"},

    # Phase 4: Strategy & Negotiation
    {"stage_name": "Plea Negotiations", "phase_code": "strategy"},
    {"stage_name": "Ready to Plea", "phase_code": "strategy"},

    # Phase 5: Trial Prep
    {"stage_name": "Set for Bench Trial", "phase_code": "trial_prep"},
    {"stage_name": "Set for Jury Trial", "phase_code": "trial_prep"},
    {"stage_name": "Trial Prep", "phase_code": "trial_prep"},

    # Phase 6: Disposition
    {"stage_name": "Sentencing", "phase_code": "disposition"},
    {"stage_name": "In TC Awaiting Graduation/Final Disposition", "phase_code": "disposition"},

    # Special statuses (map to appropriate phase based on context)
    {"stage_name": "In Jail - Awaiting Bond Reduction", "phase_code": "intake"},
    {"stage_name": "In Warrant - FTA", "phase_code": "post_disposition"},

    # === Additional Mappings (unmapped stages) ===

    # Admin/License Hearings (criminal case closed, admin pending)
    {"stage_name": "Admin Hearing Pending (Criminal Case Closed)", "phase_code": "post_disposition"},
    {"stage_name": "PFR - Awaiting Confession Eligibility (Criminal Case Closed)", "phase_code": "post_disposition"},
    {"stage_name": "PFR - Awaiting Final Judgment", "phase_code": "disposition"},

    # Municipal/Traffic workflow stages
    {"stage_name": "Awaiting Recommendation", "phase_code": "strategy"},
    {"stage_name": "Muni - Awaiting Rec", "phase_code": "strategy"},
    {"stage_name": "Muni - Client Rec Requirements Needed", "phase_code": "strategy"},
    {"stage_name": "Muni - Disposition Letter Mailed", "phase_code": "post_disposition"},
    {"stage_name": "Muni - In Warrant (Client Needs to Pay Fines)", "phase_code": "post_disposition"},

    # Expungement workflow stages
    {"stage_name": "Expungement - Awaiting Client's Fingerprints", "phase_code": "discovery"},

    # Intake/Pre-charge stages
    {"stage_name": "In Warrant - Initial Case Filing", "phase_code": "intake"},
    {"stage_name": "Initial Petition Needs to Be Filed", "phase_code": "intake"},
    {"stage_name": "Pre-charge Discussions w/LEOs", "phase_code": "intake"},

    # Motion/Hearing stages
    {"stage_name": "Waiting for Hearing to be Scheduled", "phase_code": "motions"},
    {"stage_name": "PCR - Reviewing Case File for Appeal", "phase_code": "motions"},

    # === Phase-Named Stages (new naming convention) ===
    # Phase 1.x → Intake
    {"stage_name": "Phase 1: Intake & Case Initiation", "phase_code": "intake"},
    {"stage_name": "Phase 1.1: CaseNet Checklist", "phase_code": "intake"},
    {"stage_name": "Phase 1.2: In Warrant - Initial Case Filing", "phase_code": "intake"},
    {"stage_name": "Phase 1.3: In Jail - Awaiting Bond Reduction", "phase_code": "intake"},

    # Phase 2.x → Discovery
    {"stage_name": "Phase 2: Discovery & Investigation", "phase_code": "discovery"},
    {"stage_name": "Phase 2.1: Supplemental Discovery Needed", "phase_code": "discovery"},

    # Phase 3.x → Motions
    {"stage_name": "Phase 3: Legal Analysis & Motion Practice", "phase_code": "motions"},

    # Phase 4.x → Strategy
    {"stage_name": "Phase 4: Case Strategy & Negotiation", "phase_code": "strategy"},
    {"stage_name": "Phase 4.2: Awaiting Client Program Complitions", "phase_code": "strategy"},

    # Phase 5.x → Trial Prep
    {"stage_name": "Phase 5: Trial Preparation", "phase_code": "trial_prep"},

    # Phase 6.x → Disposition
    {"stage_name": "Phase 6: Disposition & Sentencing", "phase_code": "disposition"},

    # Phase 7.x → Post-Disposition/Closing
    {"stage_name": "Phase 7: Post Disposition & Case Closure", "phase_code": "post_disposition"},
    {"stage_name": "Phase 7.1: Awaiting DOR Case Being Finalized", "phase_code": "post_disposition"},
]


# =============================================================================
# Case-Type Workflows
# =============================================================================

DEFAULT_WORKFLOWS = [
    CaseTypeWorkflow(
        code="muni",
        name="Municipal Court",
        description="Municipal/traffic court case workflow",
        case_type_patterns=["Municipal", "Traffic", "Muni"],
        stages=[
            {"code": "awaiting_rec", "name": "Awaiting Recommendation", "order": 1},
            {"code": "rec_requirements", "name": "Client Requirements Needed", "order": 2},
            {"code": "disposition_letter", "name": "Disposition Letter Mailed", "order": 3},
            {"code": "in_warrant", "name": "In Warrant (Client Needs to Pay Fines)", "order": 4},
        ],
        applies_alongside_phases=True
    ),
    CaseTypeWorkflow(
        code="dwi_pfr",
        name="DWI Petition for Review",
        description="Administrative license hearing (PFR) workflow for DWI cases",
        case_type_patterns=["DWI", "DUI"],
        stages=[
            {"code": "pfr_filed", "name": "PFR Filed", "order": 1},
            {"code": "awaiting_confession", "name": "Awaiting Confession Eligibility", "order": 2},
            {"code": "awaiting_judgment", "name": "Awaiting Final Judgment", "order": 3},
            {"code": "satop_appeal", "name": "SATOP Appeal - Waiver of Service Return", "order": 4},
        ],
        applies_alongside_phases=True
    ),
    CaseTypeWorkflow(
        code="expungement",
        name="Expungement",
        description="Record expungement/sealing workflow",
        case_type_patterns=["Expungement", "Expunge", "Seal"],
        stages=[
            {"code": "awaiting_fingerprints", "name": "Awaiting Client's Fingerprints", "order": 1},
            {"code": "petition_filed", "name": "Petition Filed", "order": 2},
            {"code": "awaiting_hearing", "name": "Awaiting Hearing", "order": 3},
            {"code": "order_entered", "name": "Order Entered", "order": 4},
        ],
        applies_alongside_phases=True
    ),
    CaseTypeWorkflow(
        code="reinstatement",
        name="License Reinstatement",
        description="Driver's license reinstatement (LDP/DL) workflow",
        case_type_patterns=["LDP", "Reinstatement", "License"],
        stages=[
            {"code": "awaiting_fingerprints", "name": "Awaiting Client's Fingerprints", "order": 1},
            {"code": "petition_filed", "name": "Petition Filed", "order": 2},
            {"code": "awaiting_hearing", "name": "Awaiting Hearing", "order": 3},
            {"code": "approved", "name": "Approved - Awaiting DOR", "order": 4},
        ],
        applies_alongside_phases=True
    ),
]


# =============================================================================
# Database Manager
# =============================================================================

class CasePhaseDB:
    """Database manager for case phases."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DATA_DIR / "case_phases.db"
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

            # Phase definitions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS phases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    firm_id INTEGER,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    short_name TEXT,
                    display_order INTEGER NOT NULL,
                    description TEXT,
                    primary_responsibility TEXT,
                    typical_duration_min_days INTEGER DEFAULT 1,
                    typical_duration_max_days INTEGER DEFAULT 30,
                    is_terminal BOOLEAN DEFAULT FALSE,
                    color TEXT DEFAULT '#6B7280',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(firm_id, code)
                )
            """)

            # MyCase stages (synced from API)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mycase_stages (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Stage to phase mappings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stage_phase_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    firm_id INTEGER,
                    mycase_stage_id INTEGER,
                    mycase_stage_name TEXT NOT NULL,
                    phase_code TEXT NOT NULL,
                    case_type_filter TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(firm_id, mycase_stage_name)
                )
            """)

            # Case-type workflows
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_type_workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    firm_id INTEGER,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    case_type_patterns TEXT,
                    stages_json TEXT,
                    applies_alongside_phases BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(firm_id, code)
                )
            """)

            # Case phase history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_phase_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    case_name TEXT,
                    case_type TEXT,
                    phase_code TEXT NOT NULL,
                    phase_name TEXT,
                    mycase_stage_id INTEGER,
                    mycase_stage_name TEXT,
                    entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    exited_at TIMESTAMP,
                    duration_days REAL,
                    notes TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_phase_history_case ON case_phase_history(case_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_phase_history_phase ON case_phase_history(phase_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_phase_history_entered ON case_phase_history(entered_at)")

            # Case workflow history (for case-type specific workflows)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_workflow_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    workflow_code TEXT NOT NULL,
                    stage_code TEXT NOT NULL,
                    stage_name TEXT,
                    entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    exited_at TIMESTAMP,
                    duration_days REAL,
                    notes TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_history_case ON case_workflow_history(case_id)")

            conn.commit()

    # ========== Phase Methods ==========

    def seed_default_phases(self, firm_id: int = None) -> int:
        """Seed default phases for a firm."""
        count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for phase in DEFAULT_PHASES:
                cursor.execute("""
                    INSERT OR IGNORE INTO phases
                    (firm_id, code, name, short_name, display_order, description,
                     primary_responsibility, typical_duration_min_days, typical_duration_max_days,
                     is_terminal, color)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    firm_id, phase.code, phase.name, phase.short_name, phase.display_order,
                    phase.description, phase.primary_responsibility,
                    phase.typical_duration_min_days, phase.typical_duration_max_days,
                    phase.is_terminal, phase.color
                ))
                if cursor.rowcount > 0:
                    count += 1
        return count

    def get_phases(self, firm_id: int = None) -> List[Phase]:
        """Get all phases for a firm."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM phases
                WHERE firm_id IS ? OR firm_id IS NULL
                ORDER BY display_order
            """, (firm_id,))
            return [Phase(
                code=row['code'],
                name=row['name'],
                short_name=row['short_name'] or row['name'],
                display_order=row['display_order'],
                description=row['description'] or '',
                primary_responsibility=row['primary_responsibility'] or '',
                typical_duration_min_days=row['typical_duration_min_days'] or 1,
                typical_duration_max_days=row['typical_duration_max_days'] or 30,
                is_terminal=bool(row['is_terminal']),
                color=row['color'] or '#6B7280'
            ) for row in cursor.fetchall()]

    def get_phase(self, code: str, firm_id: int = None) -> Optional[Phase]:
        """Get a specific phase by code."""
        phases = self.get_phases(firm_id)
        return next((p for p in phases if p.code == code), None)

    def add_phase(self, phase: Phase, firm_id: int = None) -> int:
        """Add a new phase."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO phases
                (firm_id, code, name, short_name, display_order, description,
                 primary_responsibility, typical_duration_min_days, typical_duration_max_days,
                 is_terminal, color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                firm_id, phase.code, phase.name, phase.short_name, phase.display_order,
                phase.description, phase.primary_responsibility,
                phase.typical_duration_min_days, phase.typical_duration_max_days,
                phase.is_terminal, phase.color
            ))
            return cursor.lastrowid

    def update_phase(self, code: str, updates: Dict, firm_id: int = None) -> bool:
        """Update an existing phase."""
        allowed_fields = ['name', 'short_name', 'display_order', 'description',
                         'primary_responsibility', 'typical_duration_min_days',
                         'typical_duration_max_days', 'is_terminal', 'color']

        set_clauses = []
        params = []
        for field, value in updates.items():
            if field in allowed_fields:
                set_clauses.append(f"{field} = ?")
                params.append(value)

        if not set_clauses:
            return False

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        params.extend([code, firm_id])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE phases SET {', '.join(set_clauses)}
                WHERE code = ? AND (firm_id IS ? OR firm_id IS NULL)
            """, params)
            return cursor.rowcount > 0

    def delete_phase(self, code: str, firm_id: int = None) -> bool:
        """Delete a phase."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM phases
                WHERE code = ? AND (firm_id IS ? OR firm_id IS NULL)
            """, (code, firm_id))
            return cursor.rowcount > 0

    # ========== MyCase Stage Methods ==========

    def sync_mycase_stages(self, stages: List[Dict]) -> int:
        """Sync MyCase stages to local database."""
        count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for stage in stages:
                cursor.execute("""
                    INSERT INTO mycase_stages (id, name, created_at, updated_at, synced_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        updated_at = excluded.updated_at,
                        synced_at = CURRENT_TIMESTAMP
                """, (
                    stage['id'],
                    stage['name'],
                    stage.get('created_at'),
                    stage.get('updated_at')
                ))
                count += 1
        return count

    def get_mycase_stages(self) -> List[Dict]:
        """Get all synced MyCase stages."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM mycase_stages ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    # ========== Stage Mapping Methods ==========

    def seed_default_mappings(self, firm_id: int = None) -> int:
        """Seed default stage-to-phase mappings."""
        count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for mapping in DEFAULT_STAGE_MAPPINGS:
                cursor.execute("""
                    INSERT OR IGNORE INTO stage_phase_mappings
                    (firm_id, mycase_stage_name, phase_code)
                    VALUES (?, ?, ?)
                """, (firm_id, mapping['stage_name'], mapping['phase_code']))
                if cursor.rowcount > 0:
                    count += 1
        return count

    def get_stage_mappings(self, firm_id: int = None) -> List[Dict]:
        """Get all stage-to-phase mappings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT spm.*, p.name as phase_name, p.short_name as phase_short_name
                FROM stage_phase_mappings spm
                LEFT JOIN phases p ON spm.phase_code = p.code
                    AND (p.firm_id IS spm.firm_id OR p.firm_id IS NULL)
                WHERE spm.firm_id IS ? OR spm.firm_id IS NULL
                ORDER BY spm.mycase_stage_name
            """, (firm_id,))
            return [dict(row) for row in cursor.fetchall()]

    def set_stage_mapping(self, stage_name: str, phase_code: str,
                         stage_id: int = None, firm_id: int = None) -> int:
        """Set or update a stage-to-phase mapping."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO stage_phase_mappings (firm_id, mycase_stage_id, mycase_stage_name, phase_code)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(firm_id, mycase_stage_name) DO UPDATE SET
                    mycase_stage_id = excluded.mycase_stage_id,
                    phase_code = excluded.phase_code
            """, (firm_id, stage_id, stage_name, phase_code))
            return cursor.lastrowid

    def get_phase_for_stage(self, stage_name: str, firm_id: int = None) -> Optional[str]:
        """Get the phase code for a MyCase stage name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT phase_code FROM stage_phase_mappings
                WHERE mycase_stage_name = ? AND (firm_id IS ? OR firm_id IS NULL)
            """, (stage_name, firm_id))
            row = cursor.fetchone()
            return row['phase_code'] if row else None

    # ========== Workflow Methods ==========

    def seed_default_workflows(self, firm_id: int = None) -> int:
        """Seed default case-type workflows."""
        count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for workflow in DEFAULT_WORKFLOWS:
                cursor.execute("""
                    INSERT OR IGNORE INTO case_type_workflows
                    (firm_id, code, name, description, case_type_patterns, stages_json, applies_alongside_phases)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    firm_id, workflow.code, workflow.name, workflow.description,
                    json.dumps(workflow.case_type_patterns),
                    json.dumps(workflow.stages),
                    workflow.applies_alongside_phases
                ))
                if cursor.rowcount > 0:
                    count += 1
        return count

    def get_workflows(self, firm_id: int = None) -> List[CaseTypeWorkflow]:
        """Get all case-type workflows."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM case_type_workflows
                WHERE firm_id IS ? OR firm_id IS NULL
                ORDER BY name
            """, (firm_id,))
            return [CaseTypeWorkflow(
                code=row['code'],
                name=row['name'],
                description=row['description'] or '',
                case_type_patterns=json.loads(row['case_type_patterns'] or '[]'),
                stages=json.loads(row['stages_json'] or '[]'),
                applies_alongside_phases=bool(row['applies_alongside_phases'])
            ) for row in cursor.fetchall()]

    def get_workflow_for_case_type(self, case_type: str, firm_id: int = None) -> Optional[CaseTypeWorkflow]:
        """Find the workflow that applies to a case type."""
        workflows = self.get_workflows(firm_id)
        case_type_lower = (case_type or '').lower()

        for workflow in workflows:
            for pattern in workflow.case_type_patterns:
                if pattern.lower() in case_type_lower:
                    return workflow
        return None

    # ========== Phase History Methods ==========

    def record_phase_entry(self, case_id: int, phase_code: str,
                          case_name: str = None, case_type: str = None,
                          mycase_stage_id: int = None, mycase_stage_name: str = None,
                          notes: str = None) -> int:
        """Record a case entering a phase."""
        phase = self.get_phase(phase_code)
        phase_name = phase.name if phase else phase_code

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Close any open phase entries for this case
            cursor.execute("""
                UPDATE case_phase_history
                SET exited_at = CURRENT_TIMESTAMP,
                    duration_days = julianday(CURRENT_TIMESTAMP) - julianday(entered_at)
                WHERE case_id = ? AND exited_at IS NULL
            """, (case_id,))

            # Insert new phase entry
            cursor.execute("""
                INSERT INTO case_phase_history
                (case_id, case_name, case_type, phase_code, phase_name,
                 mycase_stage_id, mycase_stage_name, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (case_id, case_name, case_type, phase_code, phase_name,
                  mycase_stage_id, mycase_stage_name, notes))

            return cursor.lastrowid

    def get_case_phase_history(self, case_id: int) -> List[Dict]:
        """Get phase history for a case."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM case_phase_history
                WHERE case_id = ?
                ORDER BY entered_at DESC
            """, (case_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_current_phase(self, case_id: int) -> Optional[Dict]:
        """Get the current phase for a case."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM case_phase_history
                WHERE case_id = ? AND exited_at IS NULL
                ORDER BY entered_at DESC
                LIMIT 1
            """, (case_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # ========== Analytics Methods ==========

    def get_phase_distribution(self, firm_id: int = None) -> List[Dict]:
        """Get distribution of cases by phase (current open phases)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    cph.phase_code,
                    cph.phase_name,
                    COUNT(*) as case_count,
                    AVG(julianday('now') - julianday(cph.entered_at)) as avg_days_in_phase
                FROM case_phase_history cph
                WHERE cph.exited_at IS NULL
                GROUP BY cph.phase_code, cph.phase_name
                ORDER BY MIN(cph.entered_at)
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_phase_duration_stats(self, firm_id: int = None) -> List[Dict]:
        """Get duration statistics by phase (completed phases only)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    phase_code,
                    phase_name,
                    COUNT(*) as completed_count,
                    AVG(duration_days) as avg_duration_days,
                    MIN(duration_days) as min_duration_days,
                    MAX(duration_days) as max_duration_days
                FROM case_phase_history
                WHERE exited_at IS NOT NULL AND duration_days IS NOT NULL
                GROUP BY phase_code, phase_name
                ORDER BY phase_code
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_cases_in_phase(self, phase_code: str, firm_id: int = None) -> List[Dict]:
        """Get all cases currently in a specific phase."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    cph.*,
                    julianday('now') - julianday(cph.entered_at) as days_in_phase
                FROM case_phase_history cph
                WHERE cph.phase_code = ? AND cph.exited_at IS NULL
                ORDER BY cph.entered_at ASC
            """, (phase_code,))
            return [dict(row) for row in cursor.fetchall()]

    def get_stalled_cases(self, threshold_days: int = 30, firm_id: int = None) -> List[Dict]:
        """Get cases that have been in their current phase longer than threshold."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    cph.*,
                    p.typical_duration_max_days,
                    julianday('now') - julianday(cph.entered_at) as days_in_phase
                FROM case_phase_history cph
                LEFT JOIN phases p ON cph.phase_code = p.code
                WHERE cph.exited_at IS NULL
                AND julianday('now') - julianday(cph.entered_at) > ?
                ORDER BY days_in_phase DESC
            """, (threshold_days,))
            return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Phase Manager (High-Level Operations)
# =============================================================================

class CasePhaseManager:
    """High-level manager for case phase operations."""

    def __init__(self, db: CasePhaseDB = None, cache=None, api_client=None):
        self.db = db or CasePhaseDB()
        self.cache = cache  # MyCaseCache instance
        self.api_client = api_client  # MyCaseClient instance

    def initialize(self, firm_id: int = None) -> Dict:
        """Initialize phases, mappings, and workflows with defaults."""
        phases_added = self.db.seed_default_phases(firm_id)
        mappings_added = self.db.seed_default_mappings(firm_id)
        workflows_added = self.db.seed_default_workflows(firm_id)

        return {
            'phases_added': phases_added,
            'mappings_added': mappings_added,
            'workflows_added': workflows_added
        }

    def sync_stages_from_mycase(self) -> int:
        """Sync stage definitions from MyCase API."""
        if not self.api_client:
            raise ValueError("API client required for sync")

        stages = self.api_client.get_case_stages()
        return self.db.sync_mycase_stages(stages)

    def compute_case_phase(self, case: Dict, firm_id: int = None) -> CasePhaseInfo:
        """Compute the current phase for a case based on its MyCase stage."""
        case_id = case.get('id')
        case_name = case.get('name', '')
        case_type = case.get('case_type', {})
        if isinstance(case_type, dict):
            case_type = case_type.get('name', '')

        # Get stage from case - can be dict {id, name} or just a string
        stage = case.get('case_stage')
        if isinstance(stage, dict):
            stage_id = stage.get('id')
            stage_name = stage.get('name')
        elif isinstance(stage, str):
            stage_id = None
            stage_name = stage
        else:
            stage_id = None
            stage_name = None

        # Look up phase mapping
        phase_code = None
        phase_name = None
        if stage_name:
            phase_code = self.db.get_phase_for_stage(stage_name, firm_id)
            if phase_code:
                phase = self.db.get_phase(phase_code, firm_id)
                phase_name = phase.name if phase else None

        # Check for applicable workflow
        workflow = self.db.get_workflow_for_case_type(case_type, firm_id)
        workflow_code = workflow.code if workflow else None

        # Find workflow stage if applicable
        workflow_stage = None
        if workflow and stage_name:
            for ws in workflow.stages:
                if ws['name'].lower() in stage_name.lower() or stage_name.lower() in ws['name'].lower():
                    workflow_stage = ws['name']
                    break

        return CasePhaseInfo(
            case_id=case_id,
            case_name=case_name,
            case_type=case_type,
            mycase_stage_id=stage_id,
            mycase_stage_name=stage_name,
            phase_code=phase_code,
            phase_name=phase_name,
            workflow_code=workflow_code,
            workflow_stage=workflow_stage
        )

    def sync_case_phases(self, firm_id: int = None) -> Dict:
        """Sync phase data for all cases from cache."""
        if not self.cache:
            raise ValueError("Cache required for sync")

        cases = self.cache.get_cases(status='open')

        updated = 0
        new_entries = 0
        unmapped = []

        for case in cases:
            phase_info = self.compute_case_phase(case, firm_id)

            if not phase_info.phase_code and phase_info.mycase_stage_name:
                unmapped.append({
                    'stage_name': phase_info.mycase_stage_name,
                    'case_name': phase_info.case_name
                })
                continue

            if not phase_info.phase_code:
                continue

            # Check current phase in history
            current = self.db.get_current_phase(phase_info.case_id)

            if current and current['phase_code'] == phase_info.phase_code:
                # Same phase, no change needed
                continue

            # Record phase entry (will close previous if exists)
            self.db.record_phase_entry(
                case_id=phase_info.case_id,
                phase_code=phase_info.phase_code,
                case_name=phase_info.case_name,
                case_type=phase_info.case_type,
                mycase_stage_id=phase_info.mycase_stage_id,
                mycase_stage_name=phase_info.mycase_stage_name
            )

            if current:
                updated += 1
            else:
                new_entries += 1

        return {
            'cases_processed': len(cases),
            'new_entries': new_entries,
            'updated': updated,
            'unmapped_stages': unmapped
        }

    def get_phase_report(self, firm_id: int = None) -> Dict:
        """Generate a comprehensive phase report."""
        phases = self.db.get_phases(firm_id)
        distribution = self.db.get_phase_distribution(firm_id)
        duration_stats = self.db.get_phase_duration_stats(firm_id)
        stalled = self.db.get_stalled_cases(30, firm_id)

        # Build phase lookup
        phase_lookup = {p.code: p for p in phases}

        # Merge distribution with phase info
        phase_summary = []
        for phase in phases:
            dist = next((d for d in distribution if d['phase_code'] == phase.code), None)
            stats = next((s for s in duration_stats if s['phase_code'] == phase.code), None)

            phase_summary.append({
                'code': phase.code,
                'name': phase.name,
                'short_name': phase.short_name,
                'color': phase.color,
                'current_cases': dist['case_count'] if dist else 0,
                'avg_days_in_phase': round(dist['avg_days_in_phase'], 1) if dist and dist['avg_days_in_phase'] else 0,
                'typical_min_days': phase.typical_duration_min_days,
                'typical_max_days': phase.typical_duration_max_days,
                'completed_cases': stats['completed_count'] if stats else 0,
                'historical_avg_days': round(stats['avg_duration_days'], 1) if stats and stats['avg_duration_days'] else None
            })

        return {
            'phases': phase_summary,
            'total_cases': sum(p['current_cases'] for p in phase_summary),
            'stalled_cases': len(stalled),
            'stalled_details': stalled[:10]  # Top 10
        }


# =============================================================================
# Singleton Instances
# =============================================================================

_db_instance = None
_manager_instance = None


def get_phase_db() -> CasePhaseDB:
    """Get singleton database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = CasePhaseDB()
    return _db_instance


def get_phase_manager(cache=None, api_client=None) -> CasePhaseManager:
    """Get singleton manager instance."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = CasePhaseManager(get_phase_db(), cache, api_client)
    return _manager_instance


# =============================================================================
# CLI Interface
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Case Phases Management")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # init command
    init_parser = subparsers.add_parser('init', help='Initialize default phases and mappings')

    # list command
    list_parser = subparsers.add_parser('list', help='List phases')

    # mappings command
    mappings_parser = subparsers.add_parser('mappings', help='List stage-to-phase mappings')

    # workflows command
    workflows_parser = subparsers.add_parser('workflows', help='List case-type workflows')

    # sync command
    sync_parser = subparsers.add_parser('sync', help='Sync stages from MyCase')

    # report command
    report_parser = subparsers.add_parser('report', help='Generate phase report')

    args = parser.parse_args()

    db = get_phase_db()

    if args.command == 'init':
        result = CasePhaseManager(db).initialize()
        print(f"Initialized:")
        print(f"  Phases added: {result['phases_added']}")
        print(f"  Mappings added: {result['mappings_added']}")
        print(f"  Workflows added: {result['workflows_added']}")

    elif args.command == 'list':
        phases = db.get_phases()
        print("\n7 Universal Case Phases:")
        print("-" * 60)
        for p in phases:
            terminal = " (terminal)" if p.is_terminal else ""
            print(f"  {p.display_order}. [{p.code}] {p.name}{terminal}")
            print(f"     Owner: {p.primary_responsibility}")
            print(f"     Typical: {p.typical_duration_min_days}-{p.typical_duration_max_days} days")
            print()

    elif args.command == 'mappings':
        mappings = db.get_stage_mappings()
        print("\nStage → Phase Mappings:")
        print("-" * 60)
        for m in mappings:
            print(f"  {m['mycase_stage_name']} → {m['phase_code']} ({m.get('phase_short_name', '')})")

    elif args.command == 'workflows':
        workflows = db.get_workflows()
        print("\nCase-Type Workflows:")
        print("-" * 60)
        for w in workflows:
            print(f"\n  [{w.code}] {w.name}")
            print(f"  Applies to: {', '.join(w.case_type_patterns)}")
            print(f"  Stages:")
            for s in w.stages:
                print(f"    {s['order']}. {s['name']}")

    elif args.command == 'sync':
        from api_client import MyCaseClient
        client = MyCaseClient()
        manager = CasePhaseManager(db, api_client=client)
        count = manager.sync_stages_from_mycase()
        print(f"Synced {count} stages from MyCase")

    elif args.command == 'report':
        from cache import get_cache
        from api_client import MyCaseClient

        cache = get_cache()
        client = MyCaseClient()
        manager = CasePhaseManager(db, cache, client)

        # First sync phases
        result = manager.sync_case_phases()
        print(f"Synced {result['cases_processed']} cases")
        print(f"  New entries: {result['new_entries']}")
        print(f"  Updated: {result['updated']}")

        if result['unmapped_stages']:
            print(f"\n  Unmapped stages ({len(result['unmapped_stages'])}):")
            unique_stages = set(s['stage_name'] for s in result['unmapped_stages'])
            for stage in sorted(unique_stages):
                print(f"    - {stage}")

        # Generate report
        report = manager.get_phase_report()
        print(f"\n{'='*60}")
        print("PHASE DISTRIBUTION REPORT")
        print(f"{'='*60}")
        print(f"Total Active Cases: {report['total_cases']}")
        print(f"Stalled Cases (>30 days): {report['stalled_cases']}")
        print()

        for p in report['phases']:
            if p['current_cases'] > 0:
                avg = f"(avg {p['avg_days_in_phase']} days)" if p['avg_days_in_phase'] else ""
                print(f"  {p['short_name']}: {p['current_cases']} cases {avg}")

    else:
        parser.print_help()
