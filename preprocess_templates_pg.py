#!/usr/bin/env python3
"""
Preprocess Templates in PostgreSQL

Updates all Word templates in the database to use standardized {{placeholder}} syntax.
This is a one-time migration that:
1. Reads each template's .docx content
2. Detects sample data (names, addresses, case numbers, etc.)
3. Replaces sample data with {{placeholders}}
4. Updates the template in PostgreSQL

Run with:
    python preprocess_templates_pg.py --dry-run    # Preview changes without updating
    python preprocess_templates_pg.py --update     # Actually update the database
    python preprocess_templates_pg.py --firm jcs_law --update  # Update specific firm only
"""

import os
import io
import re
import sys
import signal
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# Handle broken pipe errors gracefully (when piping to head, etc.)
try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except AttributeError:
    pass  # SIGPIPE not available on Windows

# Load environment
from dotenv import load_dotenv
load_dotenv()

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    from docx import Document
except ImportError:
    print("ERROR: python-docx not installed. Run: pip install python-docx")
    sys.exit(1)


# =============================================================================
# Configuration
# =============================================================================

PG_CONFIG = {
    'host': os.getenv('PG_HOST'),
    'port': os.getenv('PG_PORT', '25060'),
    'database': os.getenv('PG_DATABASE', 'defaultdb'),
    'user': os.getenv('PG_USER', 'doadmin'),
    'password': os.getenv('PG_PASSWORD', ''),
    'sslmode': os.getenv('PG_SSLMODE', 'require')
}

# Standard placeholders we want to use
PLACEHOLDERS = {
    'defendant_name': '{{defendant_name}}',
    'plaintiff_name': '{{plaintiff_name}}',
    'petitioner_name': '{{petitioner_name}}',
    'case_number': '{{case_number}}',
    'county': '{{county}}',
    'division': '{{division}}',
    'bond_amount': '{{bond_amount}}',
    'fine_amount': '{{fine_amount}}',
    'amount': '{{amount}}',
    'firm_name': '{{firm_name}}',
    'firm_address': '{{firm_address}}',
    'firm_city_state_zip': '{{firm_city_state_zip}}',
    'attorney_name': '{{attorney_name}}',
    'bar_number': '{{bar_number}}',
    'phone': '{{phone}}',
    'email': '{{email}}',
    'fax': '{{fax}}',
    'date': '{{date}}',
    'service_date': '{{service_date}}',
}

# Known sample values to replace (firm-specific data)
KNOWN_FIRM_VALUES = {
    # Addresses
    "75 West Lockwood Ave., Suite 250": "{{firm_address}}",
    "75 West Lockwood Ave, Suite 250": "{{firm_address}}",
    "120 S. Central Ave. Suite 1550": "{{firm_address}}",
    "120 S. Central Ave Suite 1550": "{{firm_address}}",
    "120 S Central Ave Suite 1550": "{{firm_address}}",
    "120 S. Central Avenue, Suite 1550": "{{firm_address}}",
    
    # City/State/Zip
    "Webster Groves, MO 63119": "{{firm_city_state_zip}}",
    "Webster Groves, Missouri 63119": "{{firm_city_state_zip}}",
    "Clayton, MO 63105": "{{firm_city_state_zip}}",
    "Clayton, Missouri 63105": "{{firm_city_state_zip}}",
    
    # Firm names
    "John C. Schleiffarth, P.C.": "{{firm_name}}",
    "John C. Schleiffarth, PC": "{{firm_name}}",
    "John C. Schleiffarth P.C.": "{{firm_name}}",
    "JOHN C. SCHLEIFFARTH, P.C.": "{{firm_name}}",
}

# Known sample defendant/petitioner names (from actual templates)
KNOWN_SAMPLE_DEFENDANTS = [
    "JAMES GADDY", "James Gaddy",
    "JOE FULSOM", "Joe Fulsom",
    "JOHN DOE", "John Doe",
    "JANE DOE", "Jane Doe",
    "TYRONE JONES", "Tyrone Jones",
    "SAMPLE DEFENDANT", "Sample Defendant",
    "RICHARD HORAK", "Richard Horak",
    "DEMESHA HARRIS", "Demesha Harris",
    "DAVID SMITH", "David Smith",
    "MICHAEL JOHNSON", "Michael Johnson",
]

# Known sample plaintiff names (for civil cases)
KNOWN_SAMPLE_PLAINTIFFS = [
    "JOHN SMITH", "John Smith",
    "JANE SMITH", "Jane Smith",
    "SAMPLE PLAINTIFF", "Sample Plaintiff",
    "ABC COMPANY", "ABC Company",
    "XYZ CORPORATION", "XYZ Corporation",
    "ACME INC", "Acme Inc",
]

# Patterns for detecting values to replace
PATTERNS = {
    # Missouri case numbers: 24SL-CR00123, 22JE-CC00191-01
    'case_number': re.compile(r'\b\d{2}[A-Z]{2}-[A-Z]{2}\d{4,}(-\d+)?\b'),

    # Dollar amounts: $1,500.00 or $500
    'dollar_amount': re.compile(r'\$[\d,]+\.?\d{0,2}'),

    # Division numbers after "Division" or "Div"
    'division': re.compile(r'(Division\s*(?:No\.?)?:?\s*)(\d+)', re.IGNORECASE),

    # Dates: "December 3, 2024", "January 15, 2025", etc.
    'service_date': re.compile(
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        re.IGNORECASE
    ),

    # Dates: "12/3/2024", "1/15/2025"
    'service_date_numeric': re.compile(r'\b\d{1,2}/\d{1,2}/\d{4}\b'),
}


@dataclass
class ProcessingResult:
    """Result of processing a single template."""
    template_id: int
    template_name: str
    variables_found: List[str]
    replacements_made: int
    processed_content: Optional[bytes]
    error: Optional[str] = None


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


def process_template(template_id: int, name: str, content: bytes) -> ProcessingResult:
    """Process a single template, replacing sample data with placeholders."""
    variables_found = set()
    replacements_made = 0
    
    try:
        doc = Document(io.BytesIO(content))
    except Exception as e:
        return ProcessingResult(
            template_id=template_id,
            template_name=name,
            variables_found=[],
            replacements_made=0,
            processed_content=None,
            error=str(e)
        )
    
    def replace_in_text(text: str) -> Tuple[str, int]:
        """Replace sample values with placeholders in text."""
        if not text:
            return text, 0
        
        new_text = text
        count = 0
        
        # 1. Replace known firm values (addresses, names)
        for sample_value, placeholder in KNOWN_FIRM_VALUES.items():
            if sample_value in new_text:
                new_text = new_text.replace(sample_value, placeholder)
                variables_found.add(placeholder.strip('{}'))
                count += 1
        
        # 2. Replace known sample defendant names
        for sample_name in KNOWN_SAMPLE_DEFENDANTS:
            if sample_name in new_text:
                # Check context - only replace if it's a defendant reference
                # Avoid replacing in "STATE OF MISSOURI" or "Plaintiff" lines
                if 'STATE OF MISSOURI' not in new_text and 'Plaintiff' not in new_text:
                    # Replace with appropriate case
                    if sample_name.isupper():
                        new_text = new_text.replace(sample_name, '{{defendant_name}}')
                    else:
                        new_text = new_text.replace(sample_name, '{{defendant_name}}')
                    variables_found.add('defendant_name')
                    count += 1

        # 2b. Replace known sample plaintiff names (from list)
        for sample_name in KNOWN_SAMPLE_PLAINTIFFS:
            if sample_name in new_text:
                # Only replace if it looks like a plaintiff context (not defendant/state)
                if 'Defendant' not in new_text and 'STATE OF MISSOURI' not in new_text:
                    new_text = new_text.replace(sample_name, '{{plaintiff_name}}')
                    variables_found.add('plaintiff_name')
                    count += 1

        # 2c. Detect plaintiff name by position (NAME, followed by Plaintiff)
        # Pattern: "JOHN SMITH," or "John Smith," followed later by "Plaintiff"
        if 'Plaintiff' in new_text and '{{plaintiff_name}}' not in new_text:
            # Match: NAME (caps or title case), comma, then Plaintiff on same or next part
            plaintiff_pattern = re.compile(
                r'^([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*),?\s*$'  # Name alone on line
            )
            # Also try: NAME, ) pattern (case caption style)
            plaintiff_pattern2 = re.compile(
                r'^([A-Z][A-Z\s\.]+),\s*\)?$'  # ALL CAPS NAME, )
            )
            match = plaintiff_pattern.match(new_text.strip()) or plaintiff_pattern2.match(new_text.strip())
            if match:
                name = match.group(1).strip()
                # Make sure it's not a known entity
                if name not in ['STATE OF MISSOURI', 'DIRECTOR OF REVENUE', 'STATE', 'CITY']:
                    new_text = new_text.replace(name, '{{plaintiff_name}}')
                    variables_found.add('plaintiff_name')
                    count += 1

        # 2d. Detect defendant name by position (NAME, followed by Defendant)
        if 'Defendant' in new_text and '{{defendant_name}}' not in new_text:
            defendant_pattern = re.compile(
                r'^([A-Z][A-Z\s\.]+),\s*\)?$'  # ALL CAPS NAME, )
            )
            match = defendant_pattern.match(new_text.strip())
            if match:
                name = match.group(1).strip()
                if name not in ['STATE OF MISSOURI', 'DIRECTOR OF REVENUE', 'STATE', 'CITY']:
                    new_text = new_text.replace(name, '{{defendant_name}}')
                    variables_found.add('defendant_name')
                    count += 1

        # 3. Replace case numbers
        if PATTERNS['case_number'].search(new_text):
            # Don't replace if it looks like a template already
            if '{{case_number}}' not in new_text:
                new_text = PATTERNS['case_number'].sub('{{case_number}}', new_text)
                variables_found.add('case_number')
                count += 1
        
        # 4. Replace division numbers
        div_match = PATTERNS['division'].search(new_text)
        if div_match and '{{division}}' not in new_text:
            new_text = PATTERNS['division'].sub(r'\g<1>{{division}}', new_text)
            variables_found.add('division')
            count += 1
        
        # 5. Replace dollar amounts (be careful - only in bond/fine contexts)
        if PATTERNS['dollar_amount'].search(new_text):
            if '{{bond_amount}}' not in new_text and '{{fine_amount}}' not in new_text:
                # Determine which placeholder based on context
                lower_text = new_text.lower()
                if 'bond' in lower_text:
                    new_text = PATTERNS['dollar_amount'].sub('{{bond_amount}}', new_text)
                    variables_found.add('bond_amount')
                    count += 1
                elif 'fine' in lower_text or 'cost' in lower_text:
                    new_text = PATTERNS['dollar_amount'].sub('{{fine_amount}}', new_text)
                    variables_found.add('fine_amount')
                    count += 1
        
        # 6. Replace county names in "CIRCUIT COURT OF X COUNTY"
        county_match = re.search(r'CIRCUIT COURT OF ([A-Z][A-Z\s\.]+) COUNTY', new_text)
        if county_match and '{{county}}' not in new_text:
            county_name = county_match.group(1)
            if county_name not in ['THE', 'SAID']:  # Avoid false positives
                new_text = re.sub(
                    r'CIRCUIT COURT OF [A-Z][A-Z\s\.]+ COUNTY',
                    'CIRCUIT COURT OF {{county}} COUNTY',
                    new_text
                )
                variables_found.add('county')
                count += 1

        # 7. Replace dates (December 3, 2024 -> {{service_date}})
        if PATTERNS['service_date'].search(new_text) and '{{service_date}}' not in new_text:
            new_text = PATTERNS['service_date'].sub('{{service_date}}', new_text)
            variables_found.add('service_date')
            count += 1

        # 8. Replace numeric dates (12/3/2024 -> {{service_date}})
        if PATTERNS['service_date_numeric'].search(new_text) and '{{service_date}}' not in new_text:
            new_text = PATTERNS['service_date_numeric'].sub('{{service_date}}', new_text)
            variables_found.add('service_date')
            count += 1

        return new_text, count
    
    def process_paragraph(paragraph):
        """Process a paragraph, preserving formatting."""
        nonlocal replacements_made
        
        full_text = paragraph.text
        if not full_text:
            return
        
        new_text, count = replace_in_text(full_text)
        
        if new_text != full_text:
            replacements_made += count
            # Update the paragraph while preserving formatting
            if len(paragraph.runs) == 1:
                paragraph.runs[0].text = new_text
            elif len(paragraph.runs) > 1:
                # Put all text in first run, clear others
                paragraph.runs[0].text = new_text
                for run in paragraph.runs[1:]:
                    run.text = ''
            else:
                paragraph.text = new_text
    
    # Process all paragraphs
    for paragraph in doc.paragraphs:
        process_paragraph(paragraph)
    
    # Process tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    process_paragraph(paragraph)
    
    # Save processed document
    output = io.BytesIO()
    doc.save(output)
    
    return ProcessingResult(
        template_id=template_id,
        template_name=name,
        variables_found=sorted(list(variables_found)),
        replacements_made=replacements_made,
        processed_content=output.getvalue()
    )


def main():
    parser = argparse.ArgumentParser(description="Preprocess templates in PostgreSQL")
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating')
    parser.add_argument('--update', action='store_true', help='Actually update the database')
    parser.add_argument('--firm', type=str, help='Process only templates for this firm_id')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of templates to process')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    args = parser.parse_args()
    
    if not args.dry_run and not args.update:
        print("Please specify --dry-run or --update")
        parser.print_help()
        return
    
    print("=" * 60)
    print("Template Preprocessor for PostgreSQL")
    print("=" * 60)
    print(f"\nMode: {'DRY RUN (no changes)' if args.dry_run else 'UPDATE DATABASE'}")
    print(f"PostgreSQL: {PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['database']}")
    
    try:
        conn = get_pg_connection()
        print("✓ Connected to PostgreSQL")
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        return
    
    # Fetch templates
    with conn.cursor() as cur:
        query = "SELECT id, name, file_content FROM templates WHERE is_active = TRUE"
        params = []
        
        if args.firm:
            query += " AND firm_id = %s"
            params.append(args.firm)
        
        query += " ORDER BY id"
        
        if args.limit:
            query += " LIMIT %s"
            params.append(args.limit)
        
        cur.execute(query, params)
        templates = cur.fetchall()
    
    print(f"\nFound {len(templates)} templates to process")
    
    # Process templates
    results = []
    updated = 0
    errors = 0
    skipped = 0
    
    for i, (template_id, name, content) in enumerate(templates):
        if content is None:
            skipped += 1
            continue
        
        # Handle memoryview from PostgreSQL
        if hasattr(content, 'tobytes'):
            content = content.tobytes()
        
        result = process_template(template_id, name, content)
        results.append(result)
        
        if result.error:
            errors += 1
            if args.verbose:
                print(f"  ✗ {name}: {result.error}")
            continue
        
        if result.replacements_made > 0:
            if args.verbose:
                print(f"  ✓ {name}: {result.replacements_made} replacements, vars: {result.variables_found}")
            
            if args.update and result.processed_content:
                # Update the database
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE templates SET file_content = %s WHERE id = %s",
                        (psycopg2.Binary(result.processed_content), template_id)
                    )
                updated += 1
        else:
            skipped += 1
            if args.verbose:
                print(f"  - {name}: no changes needed")
        
        # Progress indicator
        if (i + 1) % 100 == 0:
            print(f"  Progress: {i + 1}/{len(templates)}")
    
    if args.update:
        conn.commit()
    
    conn.close()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total templates:     {len(templates)}")
    print(f"Updated:             {updated}")
    print(f"Skipped (no change): {skipped}")
    print(f"Errors:              {errors}")
    
    # Variable usage stats
    var_counts = {}
    for r in results:
        for v in r.variables_found:
            var_counts[v] = var_counts.get(v, 0) + 1
    
    if var_counts:
        print("\nVariables found:")
        for var, count in sorted(var_counts.items(), key=lambda x: -x[1]):
            print(f"  {var}: {count} templates")
    
    if args.dry_run:
        print("\n⚠ DRY RUN - no changes were made")
        print("Run with --update to apply changes")


if __name__ == "__main__":
    main()
