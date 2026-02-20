"""
Courts and Agencies Database

Manages court and law enforcement agency information for Missouri.
Used for template selection and variable population in document generation.

Key tables (PostgreSQL):
- courts: Circuit courts, municipal courts, administrative agencies
- agencies: Police departments, sheriff's offices, state patrol

These are reference data tables shared across all firms (no firm_id needed).
"""

import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from db.connection import get_connection


class CourtType(Enum):
    """Types of courts in Missouri."""
    CIRCUIT = "circuit"
    MUNICIPAL = "municipal"
    ASSOCIATE_CIRCUIT = "associate_circuit"
    DOR = "dor"  # Department of Revenue administrative
    CANRB = "canrb"  # Criminal Activity Nuisance Review Board
    OTHER = "other"


class AgencyType(Enum):
    """Types of law enforcement agencies."""
    STATE_POLICE = "state_police"  # MSHP
    COUNTY_SHERIFF = "county_sheriff"
    MUNICIPAL_PD = "municipal_pd"
    CAMPUS_POLICE = "campus_police"
    OTHER = "other"


@dataclass
class Court:
    """Represents a court or administrative body."""
    id: Optional[int] = None
    name: str = ""
    short_name: str = ""
    court_type: CourtType = CourtType.OTHER
    county: Optional[str] = None
    city: Optional[str] = None
    address: str = ""
    phone: str = ""
    fax: str = ""
    hours: str = ""
    payment_methods: List[str] = field(default_factory=list)
    clerk_name: str = ""
    clerk_email: str = ""
    case_number_format: str = ""  # Regex pattern
    prosecutor_name: str = ""
    prosecutor_address: str = ""
    prosecutor_email: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "short_name": self.short_name,
            "court_type": self.court_type.value,
            "county": self.county,
            "city": self.city,
            "address": self.address,
            "phone": self.phone,
            "hours": self.hours,
            "payment_methods": self.payment_methods,
            "prosecutor_name": self.prosecutor_name,
        }


@dataclass
class Agency:
    """Represents a law enforcement agency."""
    id: Optional[int] = None
    name: str = ""
    short_name: str = ""
    agency_type: AgencyType = AgencyType.OTHER
    county: Optional[str] = None
    city: Optional[str] = None
    address: str = ""
    phone: str = ""
    fax: str = ""
    records_custodian: str = ""
    records_email: str = ""
    records_phone: str = ""
    preservation_email: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "short_name": self.short_name,
            "agency_type": self.agency_type.value,
            "county": self.county,
            "city": self.city,
            "address": self.address,
            "records_custodian": self.records_custodian,
        }


class CourtsDatabase:
    """PostgreSQL database for court and agency management."""

    def __init__(self):
        """Initialize database tables if they don't exist."""
        self._init_tables()

    def _init_tables(self):
        """Initialize database tables (PostgreSQL)."""
        with get_connection(autocommit=True) as conn:
            cursor = conn.cursor()

            # Courts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS courts (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    short_name TEXT,
                    court_type TEXT NOT NULL,
                    county TEXT,
                    city TEXT,
                    address TEXT,
                    phone TEXT,
                    fax TEXT,
                    hours TEXT,
                    payment_methods TEXT,  -- JSON array
                    clerk_name TEXT,
                    clerk_email TEXT,
                    case_number_format TEXT,
                    prosecutor_name TEXT,
                    prosecutor_address TEXT,
                    prosecutor_email TEXT,
                    metadata TEXT,  -- JSON object
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name, county)
                )
            """)

            # Agencies table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agencies (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    short_name TEXT,
                    agency_type TEXT NOT NULL,
                    county TEXT,
                    city TEXT,
                    address TEXT,
                    phone TEXT,
                    fax TEXT,
                    records_custodian TEXT,
                    records_email TEXT,
                    records_phone TEXT,
                    preservation_email TEXT,
                    metadata TEXT,  -- JSON object
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name, county)
                )
            """)

            # Full-text search index for courts
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS courts_fts_idx
                ON courts USING GIN (
                    to_tsvector('english', COALESCE(name, '') || ' ' ||
                                COALESCE(short_name, '') || ' ' ||
                                COALESCE(county, '') || ' ' ||
                                COALESCE(city, ''))
                )
            """)

            # Full-text search index for agencies
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS agencies_fts_idx
                ON agencies USING GIN (
                    to_tsvector('english', COALESCE(name, '') || ' ' ||
                                COALESCE(short_name, '') || ' ' ||
                                COALESCE(county, '') || ' ' ||
                                COALESCE(city, ''))
                )
            """)

    # =========================================================================
    # Court CRUD Operations
    # =========================================================================

    def add_court(self, court: Court) -> int:
        """Add a new court to the database."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO courts (
                    name, short_name, court_type, county, city, address,
                    phone, fax, hours, payment_methods, clerk_name, clerk_email,
                    case_number_format, prosecutor_name, prosecutor_address,
                    prosecutor_email, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name, county) DO UPDATE SET
                    short_name = EXCLUDED.short_name,
                    court_type = EXCLUDED.court_type,
                    city = EXCLUDED.city,
                    address = EXCLUDED.address,
                    phone = EXCLUDED.phone,
                    fax = EXCLUDED.fax,
                    hours = EXCLUDED.hours,
                    payment_methods = EXCLUDED.payment_methods,
                    clerk_name = EXCLUDED.clerk_name,
                    clerk_email = EXCLUDED.clerk_email,
                    case_number_format = EXCLUDED.case_number_format,
                    prosecutor_name = EXCLUDED.prosecutor_name,
                    prosecutor_address = EXCLUDED.prosecutor_address,
                    prosecutor_email = EXCLUDED.prosecutor_email,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (
                court.name,
                court.short_name,
                court.court_type.value,
                court.county,
                court.city,
                court.address,
                court.phone,
                court.fax,
                court.hours,
                json.dumps(court.payment_methods),
                court.clerk_name,
                court.clerk_email,
                court.case_number_format,
                court.prosecutor_name,
                court.prosecutor_address,
                court.prosecutor_email,
                json.dumps(court.metadata),
            ))
            row = cursor.fetchone()
            return row['id'] if row else None

    def get_court(self, court_id: int) -> Optional[Court]:
        """Get a court by ID."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM courts WHERE id = %s", (court_id,))
            row = cursor.fetchone()
            return self._row_to_court(row) if row else None

    def get_court_by_name(self, name: str, county: Optional[str] = None) -> Optional[Court]:
        """Get a court by name, optionally filtering by county."""
        with get_connection() as conn:
            cursor = conn.cursor()
            if county:
                cursor.execute(
                    "SELECT * FROM courts WHERE name ILIKE %s AND county = %s",
                    (f"%{name}%", county)
                )
            else:
                cursor.execute("SELECT * FROM courts WHERE name ILIKE %s", (f"%{name}%",))
            row = cursor.fetchone()
            return self._row_to_court(row) if row else None

    def search_courts(self, query: str, limit: int = 20) -> List[Court]:
        """Full-text search for courts using PostgreSQL tsvector."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM courts
                WHERE to_tsvector('english', COALESCE(name, '') || ' ' ||
                                  COALESCE(short_name, '') || ' ' ||
                                  COALESCE(county, '') || ' ' ||
                                  COALESCE(city, ''))
                    @@ plainto_tsquery('english', %s)
                ORDER BY name ASC
                LIMIT %s
            """, (query, limit))
            return [self._row_to_court(row) for row in cursor.fetchall()]

    def list_courts(
        self,
        court_type: Optional[str] = None,
        county: Optional[str] = None,
        limit: int = 100
    ) -> List[Court]:
        """List courts with optional filters."""
        with get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM courts WHERE 1=1"
            params = []

            if court_type:
                query += " AND court_type = %s"
                params.append(court_type)

            if county:
                query += " AND county = %s"
                params.append(county)

            query += " ORDER BY name ASC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            return [self._row_to_court(row) for row in cursor.fetchall()]

    def update_court(self, court_id: int, updates: dict) -> bool:
        """Update a court's information."""
        with get_connection() as conn:
            cursor = conn.cursor()

            set_clauses = []
            params = []
            for key, value in updates.items():
                if key in ("payment_methods", "metadata"):
                    value = json.dumps(value)
                set_clauses.append(f"{key} = %s")
                params.append(value)

            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            params.append(court_id)

            cursor.execute(
                f"UPDATE courts SET {', '.join(set_clauses)} WHERE id = %s",
                params
            )
            return cursor.rowcount > 0

    # =========================================================================
    # Agency CRUD Operations
    # =========================================================================

    def add_agency(self, agency: Agency) -> int:
        """Add a new agency to the database."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agencies (
                    name, short_name, agency_type, county, city, address,
                    phone, fax, records_custodian, records_email, records_phone,
                    preservation_email, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name, county) DO UPDATE SET
                    short_name = EXCLUDED.short_name,
                    agency_type = EXCLUDED.agency_type,
                    city = EXCLUDED.city,
                    address = EXCLUDED.address,
                    phone = EXCLUDED.phone,
                    fax = EXCLUDED.fax,
                    records_custodian = EXCLUDED.records_custodian,
                    records_email = EXCLUDED.records_email,
                    records_phone = EXCLUDED.records_phone,
                    preservation_email = EXCLUDED.preservation_email,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (
                agency.name,
                agency.short_name,
                agency.agency_type.value,
                agency.county,
                agency.city,
                agency.address,
                agency.phone,
                agency.fax,
                agency.records_custodian,
                agency.records_email,
                agency.records_phone,
                agency.preservation_email,
                json.dumps(agency.metadata),
            ))
            row = cursor.fetchone()
            return row['id'] if row else None

    def get_agency(self, agency_id: int) -> Optional[Agency]:
        """Get an agency by ID."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM agencies WHERE id = %s", (agency_id,))
            row = cursor.fetchone()
            return self._row_to_agency(row) if row else None

    def get_agency_by_name(self, name: str) -> Optional[Agency]:
        """Get an agency by name."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM agencies WHERE name ILIKE %s", (f"%{name}%",))
            row = cursor.fetchone()
            return self._row_to_agency(row) if row else None

    def search_agencies(self, query: str, limit: int = 20) -> List[Agency]:
        """Full-text search for agencies using PostgreSQL tsvector."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM agencies
                WHERE to_tsvector('english', COALESCE(name, '') || ' ' ||
                                  COALESCE(short_name, '') || ' ' ||
                                  COALESCE(county, '') || ' ' ||
                                  COALESCE(city, ''))
                    @@ plainto_tsquery('english', %s)
                ORDER BY name ASC
                LIMIT %s
            """, (query, limit))
            return [self._row_to_agency(row) for row in cursor.fetchall()]

    def list_agencies(
        self,
        agency_type: Optional[str] = None,
        county: Optional[str] = None,
        limit: int = 100
    ) -> List[Agency]:
        """List agencies with optional filters."""
        with get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM agencies WHERE 1=1"
            params = []

            if agency_type:
                query += " AND agency_type = %s"
                params.append(agency_type)

            if county:
                query += " AND county = %s"
                params.append(county)

            query += " ORDER BY name ASC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            return [self._row_to_agency(row) for row in cursor.fetchall()]

    # =========================================================================
    # Helpers
    # =========================================================================

    def _row_to_court(self, row: dict) -> Court:
        """Convert a database row (dict) to a Court object."""
        return Court(
            id=row["id"],
            name=row["name"],
            short_name=row.get("short_name") or "",
            court_type=CourtType(row["court_type"]),
            county=row.get("county"),
            city=row.get("city"),
            address=row.get("address") or "",
            phone=row.get("phone") or "",
            fax=row.get("fax") or "",
            hours=row.get("hours") or "",
            payment_methods=json.loads(row.get("payment_methods") or "[]"),
            clerk_name=row.get("clerk_name") or "",
            clerk_email=row.get("clerk_email") or "",
            case_number_format=row.get("case_number_format") or "",
            prosecutor_name=row.get("prosecutor_name") or "",
            prosecutor_address=row.get("prosecutor_address") or "",
            prosecutor_email=row.get("prosecutor_email") or "",
            metadata=json.loads(row.get("metadata") or "{}"),
        )

    def _row_to_agency(self, row: dict) -> Agency:
        """Convert a database row (dict) to an Agency object."""
        return Agency(
            id=row["id"],
            name=row["name"],
            short_name=row.get("short_name") or "",
            agency_type=AgencyType(row["agency_type"]),
            county=row.get("county"),
            city=row.get("city"),
            address=row.get("address") or "",
            phone=row.get("phone") or "",
            fax=row.get("fax") or "",
            records_custodian=row.get("records_custodian") or "",
            records_email=row.get("records_email") or "",
            records_phone=row.get("records_phone") or "",
            preservation_email=row.get("preservation_email") or "",
            metadata=json.loads(row.get("metadata") or "{}"),
        )


def get_courts_db() -> CourtsDatabase:
    """Get a CourtsDatabase instance."""
    return CourtsDatabase()


# =========================================================================
# Missouri Courts Seed Data
# =========================================================================

MISSOURI_COUNTIES = [
    "Adair", "Andrew", "Atchison", "Audrain", "Barry", "Barton", "Bates", "Benton",
    "Bollinger", "Boone", "Buchanan", "Butler", "Caldwell", "Callaway", "Camden",
    "Cape Girardeau", "Carroll", "Carter", "Cass", "Cedar", "Chariton", "Christian",
    "Clark", "Clay", "Clinton", "Cole", "Cooper", "Crawford", "Dade", "Dallas",
    "Daviess", "DeKalb", "Dent", "Douglas", "Dunklin", "Franklin", "Gasconade",
    "Gentry", "Greene", "Grundy", "Harrison", "Henry", "Hickory", "Holt", "Howard",
    "Howell", "Iron", "Jackson", "Jasper", "Jefferson", "Johnson", "Knox", "Laclede",
    "Lafayette", "Lawrence", "Lewis", "Lincoln", "Linn", "Livingston", "McDonald",
    "Macon", "Madison", "Maries", "Marion", "Mercer", "Miller", "Mississippi",
    "Moniteau", "Monroe", "Montgomery", "Morgan", "New Madrid", "Newton", "Nodaway",
    "Oregon", "Osage", "Ozark", "Pemiscot", "Perry", "Pettis", "Phelps", "Pike",
    "Platte", "Polk", "Pulaski", "Putnam", "Ralls", "Randolph", "Ray", "Reynolds",
    "Ripley", "St. Charles", "St. Clair", "St. Francois", "St. Louis",
    "Ste. Genevieve", "Saline", "Schuyler", "Scotland", "Scott", "Shannon",
    "Shelby", "Stoddard", "Stone", "Sullivan", "Taney", "Texas", "Vernon",
    "Warren", "Washington", "Wayne", "Webster", "Worth", "Wright",
    "St. Louis City"  # Independent city
]

# Sample municipalities from Master Document Folder analysis
STL_AREA_MUNICIPALITIES = [
    "Arnold", "Ballwin", "Berkeley", "Bridgeton", "Byrnes Mill", "Chesterfield",
    "Clayton", "Cool Valley", "Cottleville", "Crestwood", "Creve Coeur",
    "Dellwood", "DeSoto", "Ellisville", "Eureka", "Fenton", "Festus",
    "Florissant", "Frontenac", "Hazelwood", "Kirkwood", "Ladue", "Lake St. Louis",
    "Manchester", "Maplewood", "Maryland Heights", "Normandy", "O'Fallon",
    "Olivette", "Overland", "Richmond Heights", "Rock Hill", "St. Charles",
    "St. John", "St. Peters", "Town & Country", "University City",
    "Valley Park", "Webster Groves", "Wentzville", "Wildwood"
]


def seed_missouri_courts(db: CourtsDatabase) -> int:
    """Seed database with Missouri circuit courts."""
    count = 0
    for county in MISSOURI_COUNTIES:
        court = Court(
            name=f"{county} County Circuit Court",
            short_name=f"{county} Circuit",
            court_type=CourtType.CIRCUIT,
            county=county,
        )
        try:
            db.add_court(court)
            count += 1
        except Exception:
            pass  # Skip duplicates
    return count


def seed_stl_municipal_courts(db: CourtsDatabase) -> int:
    """Seed database with St. Louis area municipal courts."""
    count = 0
    for city in STL_AREA_MUNICIPALITIES:
        court = Court(
            name=f"{city} Municipal Court",
            short_name=f"{city} Muni",
            court_type=CourtType.MUNICIPAL,
            city=city,
            county="St. Louis" if city not in ["St. Charles", "O'Fallon", "Lake St. Louis", "Wentzville", "Cottleville"] else "St. Charles",
        )
        try:
            db.add_court(court)
            count += 1
        except Exception:
            pass
    return count


def seed_state_agencies(db: CourtsDatabase) -> int:
    """Seed database with state law enforcement agencies."""
    agencies_data = [
        Agency(
            name="Missouri State Highway Patrol",
            short_name="MSHP",
            agency_type=AgencyType.STATE_POLICE,
            address="1510 East Elm Street, Jefferson City, Missouri 65102",
            records_custodian="Lieutenant Gerald Callahan",
        ),
        Agency(
            name="Missouri Department of Revenue",
            short_name="DOR",
            agency_type=AgencyType.OTHER,
            address="Harry S Truman State Office Building, 301 W High St, Jefferson City, MO 65101",
        ),
    ]

    count = 0
    for agency in agencies_data:
        try:
            db.add_agency(agency)
            count += 1
        except Exception:
            pass
    return count
