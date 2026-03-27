# Template Consolidation Analysis - Documentation Index

**Generated:** 2026-02-21  
**Status:** Batches 1-5 ✅ READY FOR PRODUCTION | Batch 6 ⏳ IDENTIFIED & PLANNED

---

## Quick Start

1. **Read First:** [`TEMPLATE_CONSOLIDATION_SUMMARY.txt`](./TEMPLATE_CONSOLIDATION_SUMMARY.txt) (5 min read)
   - High-level overview of consolidation status
   - Current metrics (404 active → 369 after import)
   - 12 remaining duplicate groups identified
   - Roadmap for Batch 6

2. **For Details:** [`TEMPLATE_CONSOLIDATION_STATUS.md`](./TEMPLATE_CONSOLIDATION_STATUS.md) (15 min read)
   - Complete analysis of all 12 duplicate groups
   - Priority matrix for deactivations vs. consolidations
   - Batch 6 recommendations
   - Database deactivation queries

3. **For CSV Tracking:** [`BATCH6_CONSOLIDATION_CANDIDATES.csv`](./BATCH6_CONSOLIDATION_CANDIDATES.csv)
   - 12-row spreadsheet of consolidation candidates
   - Status (Ready, Pending), Action (Deactivate/Consolidate)
   - Variables needed for each template

---

## Key Findings

### Current State (Before Any Imports)
```
Total active templates:     404
├─ Consolidated (50):       50 (Batches 1-5 in DB)
├─ Remaining unique:        325 (no variants)
└─ Duplicate groups (12):   29 variants total
```

### After Running import_consolidated_templates.py
```
Action: Deactivate ~1,535 old variants from Batches 1-5
Result:
  • Active templates: 404 → ~369
  • Consolidated: 0 → 50
  • Reduction: 1,535 duplicates hidden
```

### After Batch 6 Consolidation
```
Expected result:
  • New consolidated templates: 12
  • Additional variants consolidated: 16
  • Final active templates: ~387
  • Total consolidated: 62 master templates
```

---

## The 12 Remaining Duplicate Groups

### Immediate Deactivations (Master templates already exist)
1. **Motion for Continuance** (6 variants)
2. **Bond Assignment** (2 variants)
3. **Entry** (2 variants)
4. **NOH Bond Reduction** (3 variants)

### Batch 6 New Consolidations (12 new masters needed)
5. **90 Day Letter with No Priors** (2 variants) — DCC variant
6. **Client Status Update** (2 variants) — DCC variant
7. **Ltr with Loss of PFR Case** (2 variants) — DCC variant
8. **Motion to Set Aside Dismissal - PFR** (2 variants) — DCC variant
9. **MTW - Warning Letter** (2 variants) — Finance vs. Communication
10. **OOP Entry** (2 variants) — City vs. County jurisdiction
11. **Petition for LDP During 10 Year Denial** (2 variants) — DCC variant
12. **Substitution of Counsel** (2 variants) — Internal vs. External

**Pattern:** 5 groups have DCC (Drug Court Case) variants — indicates need for firm-wide DCC document strategy.

---

## Implementation Roadmap

### Phase 1: IMMEDIATE (This Week)
```bash
cd /opt/jcs-mycase
git pull
export $(grep -v '^#' .env | xargs)
.venv/bin/python import_consolidated_templates.py
```

**Effect:**
- Activates 50 consolidated templates (Batches 1-5)
- Deactivates ~1,535 old variants
- No breaking changes (old templates remain in DB, just inactive)
- Cleaner search results, faster template lookup

**Time:** 1 day (test on staging, deploy to production)

### Phase 2: BATCH 6 PLANNING (Next Week)
1. Extract 8 template groups from database
2. Create 12 master templates with {{placeholders}} in `data/templates/`
3. Add entries to `DOCUMENT_TYPES` registry in `document_chat.py`
4. Create `import_batch6_templates.py` script
5. Update dashboard Quick Generate panel
6. Test on staging, deploy to production

**Effect:**
- Consolidates 8 more template groups (16 variants)
- Adds 12 new master templates
- Reduces duplicate groups from 12 → 4 (only NOH Bond Reduction remains)

**Time:** 3-5 days

### Phase 3: DEACTIVATION CLEANUP (Optional, Low Priority)
Deactivate the 13 variants from Phase 1 groups (Motion for Continuance, Bond Assignment, Entry, NOH Bond Reduction).

**Time:** 1 day

---

## Related Documentation

Other consolidation-related docs in `/docs/`:

- **[`DETAILED_TEMPLATE_INVENTORY.md`](./DETAILED_TEMPLATE_INVENTORY.md)** — Complete inventory of all ~4,800 original template files
- **[`TEMPLATE_CONVERSION_REPORT.md`](./TEMPLATE_CONVERSION_REPORT.md)** — Report on LibreOffice .doc → .docx conversion (Batch 5)
- **[`OLE_TEMPLATE_CONSOLIDATION_ANALYSIS.md`](./OLE_TEMPLATE_CONSOLIDATION_ANALYSIS.md)** — Analysis of legacy OLE format templates
- **[`TEMPLATE_FOLDER_STRUCTURE.md`](./TEMPLATE_FOLDER_STRUCTURE.md)** — Recommended template folder organization

---

## Database Queries

### Check Consolidated Templates
```sql
SELECT name, COUNT(*) as count, is_active
FROM templates
WHERE firm_id = 'jcs_law'
AND name IN (
  'Motion for Continuance',
  'Request for Discovery',
  'Waiver of Arraignment',
  'Notice of Hearing',
  'Bond Assignment',
  -- ... etc
)
GROUP BY name, is_active
ORDER BY count DESC;
```

### Find Duplicate Groups
```sql
SELECT 
  CASE 
    WHEN name LIKE '%Motion for Continuance%' THEN 'Motion for Continuance'
    WHEN name LIKE '%Bond Assignment%' THEN 'Bond Assignment'
    -- ... etc
  END as group_name,
  name,
  COUNT(*) OVER (PARTITION BY ...) as group_size
FROM templates
WHERE firm_id = 'jcs_law' AND is_active = TRUE
ORDER BY group_name, name;
```

### Deactivate Variants
```sql
UPDATE templates 
SET is_active = FALSE
WHERE firm_id = 'jcs_law'
AND name IN (
  'Motion for Continuance 03-09-23',
  'Motion for Continuance 07.22.20',
  'Motion for Continuance 10-07-22',
  'Motion for Continuance - Kirkwood',
  'Motion for Continuance Lewis County',
  'Motion for Continuance - Pevely Muni'
);
```

---

## Metrics Summary

| Metric | Before | After Batch 1-5 | After Batch 6 |
|--------|--------|-----------------|---------------|
| Total active templates | 404 | ~369 | ~387 |
| Consolidated templates | 0 | 50 | 62 |
| Duplicate groups | 12 | 8 | 4 |
| Duplicate variants | 29 | 16 | 0 |
| Unique templates | 325 | 325 | 325 |
| Reduction from variants | — | 1,535 | 1,551 |

---

## Recommendations

### ✅ DO THIS NOW (Batch 1-5)
1. Run `import_consolidated_templates.py` on staging
2. Test Quick Generate panel, document search, and bulk operations
3. Verify no breaking changes (old templates should still exist but be inactive)
4. Deploy to production

### ⏳ PLAN FOR NEXT WEEK (Batch 6)
1. Extract 8 template groups
2. Create master templates with variables
3. Add DOCUMENT_TYPES entries
4. Create import script
5. Update dashboard UI

### ⏸️ DON'T DO (Unique Templates)
Don't consolidate the 325 single, unique templates:
- They're legitimate, specific documents (not duplicates)
- Consolidating would lose important specificity
- Keep them organized by category in the database

---

## Questions?

See the detailed analysis:
- **Quick Summary:** `TEMPLATE_CONSOLIDATION_SUMMARY.txt` (5 min)
- **Detailed Report:** `TEMPLATE_CONSOLIDATION_STATUS.md` (20 min)
- **CSV Tracker:** `BATCH6_CONSOLIDATION_CANDIDATES.csv` (reference)

Last updated: 2026-02-21
