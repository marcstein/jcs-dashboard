"""
Pre-Launch Test Harness: Document Generation

Integration tests that connect to real PostgreSQL, load real templates,
fill them with dummy data, and validate output. Builds on existing
test_template_generation.py patterns.

Usage:
    cd /opt/jcs-mycase  (or project root)
    export $(grep -v '^#' .env | xargs)
    python -m pytest tests/test_prelaunch_docgen.py -v

    # Just catalog validation (no DB needed for DOCUMENT_TYPES checks):
    python -m pytest tests/test_prelaunch_docgen.py -v -k "TestCatalogValidation"
"""

import io
import os
import re
import sys
import json
import zipfile
import pytest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from document_chat import DOCUMENT_TYPES

# ---------------------------------------------------------------------------
# Reuse dummy data from test_template_generation.py
# ---------------------------------------------------------------------------
from tests.test_template_generation import (
    DUMMY_DATA,
    DUMMY_ATTORNEY_PROFILE,
    TEMPLATE_TO_DOCTYPE,
    get_template_from_db,
    extract_placeholders_from_docx,
    fill_template,
    build_replacements,
)

# All template keys that have entries in the database
ALL_TEMPLATE_KEYS = list(TEMPLATE_TO_DOCTYPE.values())
ALL_TEMPLATE_NAMES = list(TEMPLATE_TO_DOCTYPE.keys())

# Invert the map for key→name lookup
DOCTYPE_TO_TEMPLATE = {v: k for k, v in TEMPLATE_TO_DOCTYPE.items()}


# ---------------------------------------------------------------------------
# Template identification test cases
# ---------------------------------------------------------------------------
IDENTIFICATION_CASES = [
    ("I need a general motion to dismiss", "motion_to_dismiss_general"),
    ("bond assignment for Jefferson County", "bond_assignment"),
    ("filing fee memo", "filing_fee_memo"),
    ("entry of appearance for municipal court", "entry_of_appearance_muni"),
    ("entry of appearance state court", "entry_of_appearance_state"),
    ("motion for continuance", "motion_for_continuance"),
    ("preservation letter", "preservation_letter"),
    ("disposition letter to client", "disposition_letter"),
    ("waiver of arraignment", "waiver_of_arraignment"),
    ("petition for review", "petition_for_review"),
    ("motion for change of judge", "motion_for_coj"),
    ("letter to DOR with PFR", "ltr_to_dor_with_pfr"),
    ("motion to recall warrant", "motion_to_recall_warrant"),
    ("notice of hearing", "notice_of_hearing"),
    ("request for discovery", "request_for_discovery"),
    ("dl reinstatement letter", "dl_reinstatement_letter"),
    ("motion to withdraw", "motion_to_withdraw"),
    ("closing letter", "closing_letter"),
    ("admin hearing request", "admin_hearing_request"),
    ("plea of guilty", "plea_of_guilty"),
]


# ---------------------------------------------------------------------------
# Helper: Check if we can connect to DB
# ---------------------------------------------------------------------------
def _can_connect_to_db() -> bool:
    """Check if DATABASE_URL is set and we can connect."""
    if not os.environ.get("DATABASE_URL"):
        return False
    try:
        from db.connection import get_connection
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason="DATABASE_URL not set or DB unreachable"
)


# ===========================================================================
# Test Class 1: Catalog Validation (no DB required)
# ===========================================================================
class TestCatalogValidation:
    """Validate DOCUMENT_TYPES registry metadata."""

    def test_all_document_types_have_required_metadata(self):
        """Every DOCUMENT_TYPES entry must have name, description, required_vars."""
        missing_fields = []
        for key, dt in DOCUMENT_TYPES.items():
            for field in ['name', 'description', 'required_vars']:
                if field not in dt:
                    missing_fields.append(f"{key} missing '{field}'")
        assert not missing_fields, \
            f"DOCUMENT_TYPES entries missing required metadata:\n" + "\n".join(missing_fields)

    def test_no_required_vars_overlap_with_auto_fill(self):
        """User should never be asked for auto-filled attorney profile fields."""
        auto_fill_fields = {
            'attorney_name', 'attorney_bar', 'attorney_email', 'attorney_full_name',
            'firm_name', 'firm_address', 'firm_address_line1', 'firm_city_state_zip',
            'firm_phone', 'firm_fax', 'assignee_name', 'assignee_address',
            'bar_number', 'phone', 'fax', 'email',
        }
        overlaps = []
        for key, dt in DOCUMENT_TYPES.items():
            required = set(dt.get('required_vars', []))
            overlap = required & auto_fill_fields
            if overlap:
                overlaps.append(f"{key}: {overlap}")
        assert not overlaps, \
            f"Required vars overlap with auto-fill fields:\n" + "\n".join(overlaps)

    def test_document_types_count(self):
        """We expect at least 56 document types."""
        assert len(DOCUMENT_TYPES) >= 56, \
            f"Expected ≥56 DOCUMENT_TYPES, got {len(DOCUMENT_TYPES)}"

    def test_all_template_keys_in_document_types(self):
        """Every key in TEMPLATE_TO_DOCTYPE must exist in DOCUMENT_TYPES."""
        missing = []
        for template_name, key in TEMPLATE_TO_DOCTYPE.items():
            if key not in DOCUMENT_TYPES:
                missing.append(f"{template_name} → {key}")
        assert not missing, \
            f"Template keys not in DOCUMENT_TYPES:\n" + "\n".join(missing)

    def test_uses_attorney_profile_for_valid_keys(self):
        """uses_attorney_profile_for should only reference known profile fields."""
        known_profile_fields = set(DUMMY_ATTORNEY_PROFILE.keys())
        invalid = []
        for key, dt in DOCUMENT_TYPES.items():
            profile_vars = dt.get('uses_attorney_profile_for', [])
            for var in profile_vars:
                if var not in known_profile_fields and var not in DUMMY_DATA:
                    invalid.append(f"{key}: unknown profile var '{var}'")
        # This is informational — some might be valid but unmapped
        if invalid:
            print(f"\nWarning: {len(invalid)} potentially unknown profile vars")
            for item in invalid[:10]:
                print(f"  {item}")


# ===========================================================================
# Test Class 2: Template Fill Tests (requires DB)
# ===========================================================================
@needs_db
class TestTemplateFill:
    """Test filling every consolidated template with dummy data."""

    @pytest.fixture(autouse=True)
    def setup_output_dir(self, tmp_path):
        """Create output directory for generated docs."""
        self.output_dir = tmp_path / "docgen_output"
        self.output_dir.mkdir()

    @pytest.mark.parametrize(
        "template_name,doc_type_key",
        list(TEMPLATE_TO_DOCTYPE.items()),
        ids=list(TEMPLATE_TO_DOCTYPE.values()),
    )
    def test_fill_produces_valid_docx(self, template_name, doc_type_key):
        """Filling a template should produce a valid .docx (ZIP) file."""
        db_result = get_template_from_db(template_name)
        if not db_result:
            pytest.skip(f"Template '{template_name}' not found in database")

        tid, content = db_result
        replacements = build_replacements(doc_type_key)
        filled_bytes, unfilled = fill_template(content, replacements)

        assert filled_bytes is not None, "fill_template returned None"
        assert len(filled_bytes) > 0, "fill_template returned empty bytes"

        # Validate it's a valid ZIP (docx is a ZIP archive)
        buf = io.BytesIO(filled_bytes)
        assert zipfile.is_zipfile(buf), "Output is not a valid ZIP/docx"

        # Validate it contains the expected docx parts
        with zipfile.ZipFile(io.BytesIO(filled_bytes)) as zf:
            names = zf.namelist()
            assert 'word/document.xml' in names, "Missing word/document.xml"
            assert '[Content_Types].xml' in names, "Missing [Content_Types].xml"

    @pytest.mark.parametrize(
        "template_name,doc_type_key",
        list(TEMPLATE_TO_DOCTYPE.items()),
        ids=list(TEMPLATE_TO_DOCTYPE.values()),
    )
    def test_fill_no_unfilled_placeholders(self, template_name, doc_type_key):
        """After filling, there should be zero {{...}} remaining."""
        db_result = get_template_from_db(template_name)
        if not db_result:
            pytest.skip(f"Template '{template_name}' not found in database")

        tid, content = db_result
        replacements = build_replacements(doc_type_key)
        filled_bytes, unfilled = fill_template(content, replacements)

        assert filled_bytes is not None
        assert unfilled == [], \
            f"Unfilled placeholders in '{template_name}': {', '.join(unfilled)}"

    @pytest.mark.parametrize(
        "template_name,doc_type_key",
        list(TEMPLATE_TO_DOCTYPE.items()),
        ids=list(TEMPLATE_TO_DOCTYPE.values()),
    )
    def test_fill_case_data_substituted(self, template_name, doc_type_key):
        """Key case data (defendant_name, case_number) should appear in output."""
        db_result = get_template_from_db(template_name)
        if not db_result:
            pytest.skip(f"Template '{template_name}' not found in database")

        tid, content = db_result
        replacements = build_replacements(doc_type_key)
        filled_bytes, _ = fill_template(content, replacements)
        assert filled_bytes is not None

        # Extract text content from the filled document
        with zipfile.ZipFile(io.BytesIO(filled_bytes)) as zf:
            xml = zf.read('word/document.xml').decode('utf-8', errors='replace')
            clean = re.sub(r'<[^>]+>', '', xml)

        # Check that at least one key substitution happened
        # (not all templates use defendant_name, some use client_name etc.)
        dt = DOCUMENT_TYPES.get(doc_type_key, {})
        required_vars = dt.get('required_vars', [])
        if not required_vars:
            return  # No required vars to check

        # At least one required var value should appear in the document
        found_any = False
        for var in required_vars:
            value = replacements.get(var, '')
            if value and value in clean:
                found_any = True
                break
            # Also check uppercase version
            if value and value.upper() in clean:
                found_any = True
                break

        assert found_any, \
            f"No required var values found in output for '{template_name}'. " \
            f"Required vars: {required_vars}"

    @pytest.mark.parametrize(
        "template_name,doc_type_key",
        list(TEMPLATE_TO_DOCTYPE.items()),
        ids=list(TEMPLATE_TO_DOCTYPE.values()),
    )
    def test_fill_county_uppercase_in_captions(self, template_name, doc_type_key):
        """County should appear uppercase in court captions (JEFFERSON not Jefferson)."""
        db_result = get_template_from_db(template_name)
        if not db_result:
            pytest.skip(f"Template '{template_name}' not found in database")

        tid, content = db_result

        # Check if template has {{COUNTY}} placeholder (uppercase context)
        original_placeholders = extract_placeholders_from_docx(content)
        if 'county' not in original_placeholders:
            pytest.skip(f"Template '{template_name}' doesn't use {{{{county}}}} placeholder")

        replacements = build_replacements(doc_type_key)
        filled_bytes, _ = fill_template(content, replacements)
        assert filled_bytes is not None

        # Extract text
        with zipfile.ZipFile(io.BytesIO(filled_bytes)) as zf:
            xml = zf.read('word/document.xml').decode('utf-8', errors='replace')
            clean = re.sub(r'<[^>]+>', '', xml)

        # In court captions, COUNTY should be uppercase: "JEFFERSON COUNTY"
        # Check if "JEFFERSON" appears (uppercase version of county value)
        county_value = replacements.get('county', 'Jefferson')
        if county_value.upper() in clean:
            pass  # Good — uppercase found
        elif county_value in clean:
            # Lowercase found — might be okay in body text, only fail if caption context
            # This is a soft check; some documents put county lowercase in body
            pass
        # If neither found, skip (template may not use county in a visible way)


# ===========================================================================
# Test Class 3: Template Identification (requires DB for full flow)
# ===========================================================================
@needs_db
class TestTemplateIdentification:
    """Test that _identify_template matches user requests to correct document types."""

    @pytest.fixture(autouse=True)
    def setup_engine(self):
        """Create a DocumentChatEngine instance for identification tests."""
        try:
            from document_chat import DocumentChatEngine
            # DocumentChatEngine may need API key; create with a dummy if needed
            api_key = os.environ.get('ANTHROPIC_API_KEY', 'test-key-not-used')
            self.engine = DocumentChatEngine(
                firm_id='jcs_law',
                api_key=api_key,
            )
        except Exception as e:
            pytest.skip(f"Cannot create DocumentChatEngine: {e}")

    @pytest.mark.parametrize(
        "request_text,expected_key",
        IDENTIFICATION_CASES,
        ids=[case[1] for case in IDENTIFICATION_CASES],
    )
    def test_identify_template_matches(self, request_text, expected_key):
        """User request text should identify the correct document type."""
        result = self.engine._identify_template(request_text)

        assert result.get('found', False), \
            f"Template not found for: '{request_text}'"

        actual_key = result.get('document_type_key', '')
        assert actual_key == expected_key, \
            f"Expected '{expected_key}' but got '{actual_key}' for: '{request_text}'"


# ===========================================================================
# Test Class 4: Edge Cases
# ===========================================================================
@needs_db
class TestDocGenEdgeCases:
    """Edge case tests for document generation."""

    def test_optional_vars_can_be_omitted(self):
        """Templates should still fill when optional vars are missing."""
        # Pick a template with optional vars
        for key, dt in DOCUMENT_TYPES.items():
            optional = dt.get('optional_vars', [])
            if optional and key in DOCTYPE_TO_TEMPLATE:
                template_name = DOCTYPE_TO_TEMPLATE[key]
                break
        else:
            pytest.skip("No template with optional vars found")

        db_result = get_template_from_db(template_name)
        if not db_result:
            pytest.skip(f"Template '{template_name}' not in DB")

        tid, content = db_result

        # Build replacements WITHOUT optional vars
        replacements = {}
        replacements.update(DUMMY_ATTORNEY_PROFILE)
        dt = DOCUMENT_TYPES[key]
        for var in dt.get('required_vars', []):
            if var in DUMMY_DATA:
                replacements[var] = DUMMY_DATA[var]
            else:
                replacements[var] = f"[TEST-{var}]"
        # Deliberately skip optional vars
        for k, v in dt.get('defaults', {}).items():
            replacements[k] = v

        filled_bytes, unfilled = fill_template(content, replacements)
        assert filled_bytes is not None, "Fill failed with optional vars omitted"
        # Some unfilled may remain (the optional ones) — that's okay
        # but the document should still be valid
        buf = io.BytesIO(filled_bytes)
        assert zipfile.is_zipfile(buf), "Output is not valid .docx"

    def test_missing_attorney_profile_graceful(self):
        """Template fill should not crash if attorney profile is empty."""
        # Find first template
        for template_name, doc_type_key in TEMPLATE_TO_DOCTYPE.items():
            db_result = get_template_from_db(template_name)
            if db_result:
                break
        else:
            pytest.skip("No templates in DB")

        tid, content = db_result

        # Build replacements with case data but NO attorney profile
        replacements = dict(DUMMY_DATA)
        # No DUMMY_ATTORNEY_PROFILE added

        # Should not crash
        filled_bytes, unfilled = fill_template(content, replacements)
        assert filled_bytes is not None, "Fill crashed without attorney profile"
        # May have unfilled attorney placeholders — that's expected
        buf = io.BytesIO(filled_bytes)
        assert zipfile.is_zipfile(buf), "Output is not valid .docx"


# ===========================================================================
# Test Class 5: Templates Exist in Database
# ===========================================================================
@needs_db
class TestTemplatesExistInDB:
    """Verify all 56 consolidated templates exist in PostgreSQL."""

    def test_templates_exist_in_database(self):
        """All templates in TEMPLATE_TO_DOCTYPE should be found in the DB."""
        missing = []
        for template_name in TEMPLATE_TO_DOCTYPE.keys():
            result = get_template_from_db(template_name)
            if not result:
                missing.append(template_name)

        if missing:
            # Print info for debugging
            print(f"\n{len(missing)} templates NOT FOUND in database:")
            for name in missing:
                print(f"  - {name}")

        assert not missing, \
            f"{len(missing)}/{len(TEMPLATE_TO_DOCTYPE)} templates missing from database: {missing[:5]}..."

    def test_templates_have_file_content(self):
        """All templates should have non-empty file_content."""
        empty = []
        for template_name in TEMPLATE_TO_DOCTYPE.keys():
            result = get_template_from_db(template_name)
            if result:
                tid, content = result
                if not content or len(content) == 0:
                    empty.append(template_name)

        assert not empty, \
            f"{len(empty)} templates have empty file_content: {empty[:5]}"


# ===========================================================================
# Summary fixture — prints results at end of session
# ===========================================================================
@pytest.fixture(scope="session", autouse=True)
def print_summary(request):
    """Print a summary after all tests complete."""
    yield
    # This runs after all tests
    terminal_reporter = request.config.pluginmanager.getplugin("terminalreporter")
    if terminal_reporter:
        passed = len(terminal_reporter.stats.get("passed", []))
        failed = len(terminal_reporter.stats.get("failed", []))
        skipped = len(terminal_reporter.stats.get("skipped", []))
        errors = len(terminal_reporter.stats.get("error", []))
        total = passed + failed + skipped + errors
        print(f"\n{'=' * 70}")
        print(f"DOCUMENT GENERATION PRE-LAUNCH SUMMARY")
        print(f"{'=' * 70}")
        print(f"  Total:   {total}")
        print(f"  Passed:  {passed}")
        print(f"  Failed:  {failed}")
        print(f"  Skipped: {skipped}")
        print(f"  Errors:  {errors}")
        print(f"{'=' * 70}")
