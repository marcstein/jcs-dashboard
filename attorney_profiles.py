"""
Attorney Profile Management

Stores attorney and firm information for automatic signature block population.
Each attorney belongs to a firm, and the signature block is generated based on
the logged-in attorney.

Uses PostgreSQL multi-tenant database via db.attorneys module.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

from db import attorneys as db_attorneys


@dataclass
class AttorneyProfile:
    """Attorney profile with all signature block information."""
    id: Optional[int] = None
    firm_id: str = ""

    # Attorney info
    attorney_name: str = ""
    bar_number: str = ""
    email: str = ""
    phone: str = ""
    fax: Optional[str] = None

    # Firm info
    firm_name: str = ""
    firm_address: str = ""
    firm_city: str = ""
    firm_state: str = "Missouri"
    firm_zip: str = ""

    # Additional
    is_primary: bool = False  # Primary attorney for the firm
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def get_signature_block(self) -> str:
        """Generate the signature block text for this attorney."""
        lines = [
            self.firm_name,
            "",
            "",
            f"/s/{self.attorney_name}",
            f"{self.attorney_name}    #{self.bar_number}",
            self.firm_address,
            f"{self.firm_city}, {self.firm_state} {self.firm_zip}",
            f"Telephone: {self.phone}",
        ]
        if self.fax:
            lines.append(f"Facsimile: {self.fax}")
        lines.append(f"Email: {self.email}")

        return "\n".join(lines)

    def get_signature_dict(self) -> Dict[str, str]:
        """Get signature block as a dictionary for template substitution."""
        return {
            "attorney_name": self.attorney_name,
            "attorney_bar_number": self.bar_number,
            "attorney_email": self.email,
            "attorney_phone": self.phone,
            "attorney_fax": self.fax or "",
            "firm_name": self.firm_name,
            "firm_address": self.firm_address,
            "firm_city": self.firm_city,
            "firm_state": self.firm_state,
            "firm_zip": self.firm_zip,
            "firm_city_state_zip": f"{self.firm_city}, {self.firm_state} {self.firm_zip}",
            "firm_phone": self.phone,
            "firm_fax": self.fax or "",
            "firm_email": self.email,
        }


class AttorneyProfileManager:
    """Manager for attorney profiles, delegating to db.attorneys module."""

    def __init__(self, firm_id: str):
        """Initialize with a firm ID for multi-tenant support."""
        self.firm_id = firm_id

    def save_attorney(self, profile: AttorneyProfile) -> int:
        """Save or update an attorney profile. Returns the attorney ID."""
        attorney_id = db_attorneys.add_attorney(
            firm_id=profile.firm_id,
            attorney_name=profile.attorney_name,
            bar_number=profile.bar_number,
            email=profile.email,
            phone=profile.phone,
            fax=profile.fax,
            firm_name=profile.firm_name,
            firm_address=profile.firm_address,
            firm_city=profile.firm_city,
            firm_state=profile.firm_state,
            firm_zip=profile.firm_zip,
            is_primary=profile.is_primary,
        )

        # Update is_active if needed
        if not profile.is_active:
            db_attorneys.update_attorney(attorney_id, is_active=False)

        return attorney_id

    def get_attorney(self, attorney_id: int) -> Optional[AttorneyProfile]:
        """Get an attorney by ID."""
        row = db_attorneys.get_attorney(attorney_id)
        if row:
            return self._dict_to_profile(row)
        return None

    def get_attorney_by_bar(self, bar_number: str) -> Optional[AttorneyProfile]:
        """Get an attorney by bar number for this firm."""
        attorneys = db_attorneys.get_attorneys(self.firm_id, active_only=False)
        for atty in attorneys:
            if atty.get("bar_number") == bar_number:
                return self._dict_to_profile(atty)
        return None

    def get_primary_attorney(self) -> Optional[AttorneyProfile]:
        """Get the primary attorney for this firm."""
        row = db_attorneys.get_primary_attorney(self.firm_id)
        if row:
            return self._dict_to_profile(row)

        # If no primary, return first active attorney
        attorneys = db_attorneys.get_attorneys(self.firm_id, active_only=True)
        if attorneys:
            return self._dict_to_profile(attorneys[0])

        return None

    def list_attorneys(self, active_only: bool = True) -> List[AttorneyProfile]:
        """List all attorneys for this firm."""
        rows = db_attorneys.get_attorneys(self.firm_id, active_only=active_only)
        return [self._dict_to_profile(row) for row in rows]

    def set_primary_attorney(self, attorney_id: int) -> bool:
        """Set an attorney as the primary for this firm."""
        db_attorneys.set_primary_attorney(self.firm_id, attorney_id)
        return True

    def deactivate_attorney(self, attorney_id: int) -> bool:
        """Deactivate an attorney (soft delete)."""
        db_attorneys.deactivate_attorney(self.firm_id, attorney_id)
        return True

    @staticmethod
    def _dict_to_profile(row: Dict[str, Any]) -> AttorneyProfile:
        """Convert a database row dict to an AttorneyProfile."""
        return AttorneyProfile(
            id=row.get("id"),
            firm_id=row.get("firm_id", ""),
            attorney_name=row.get("attorney_name", ""),
            bar_number=row.get("bar_number", ""),
            email=row.get("email", ""),
            phone=row.get("phone", ""),
            fax=row.get("fax"),
            firm_name=row.get("firm_name", ""),
            firm_address=row.get("firm_address", ""),
            firm_city=row.get("firm_city", ""),
            firm_state=row.get("firm_state", "Missouri"),
            firm_zip=row.get("firm_zip", ""),
            is_primary=bool(row.get("is_primary", False)),
            is_active=bool(row.get("is_active", True)),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


# Convenience module-level functions
def save_attorney(profile: AttorneyProfile, firm_id: str = None) -> int:
    """Save an attorney profile."""
    firm_id = firm_id or profile.firm_id
    manager = AttorneyProfileManager(firm_id)
    return manager.save_attorney(profile)


def get_attorney(attorney_id: int, firm_id: str = None) -> Optional[AttorneyProfile]:
    """Get an attorney by ID."""
    row = db_attorneys.get_attorney(attorney_id)
    if row:
        return AttorneyProfileManager._dict_to_profile(row)
    return None


def get_primary_attorney(firm_id: str) -> Optional[AttorneyProfile]:
    """Get the primary attorney for a firm."""
    manager = AttorneyProfileManager(firm_id)
    return manager.get_primary_attorney()


def list_attorneys(firm_id: str) -> List[AttorneyProfile]:
    """List all active attorneys for a firm."""
    manager = AttorneyProfileManager(firm_id)
    return manager.list_attorneys(active_only=True)
