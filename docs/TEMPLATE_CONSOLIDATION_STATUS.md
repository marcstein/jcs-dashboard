# Template Consolidation Analysis Report
**Generated:** 2026-02-21  
**Database:** lawmetrics_platform (JCS Law, firm_id='jcs_law')

---

## Executive Summary

### Current Status
- **Total active templates:** 404
- **Consolidated templates (Batches 1-5):** 50 out of 54 (4 not yet in DB)
- **Remaining unconsoli: 354
- **After deactivation:** ~387 unique templates

### Key Finding
**12 duplicate groups (29 variants) remain unconsolidated.**

These are NOT old variants of already-consolidated templates. They are new groups that haven't been part of Batches 1-5 consolidation and still have county/qualifier duplicates that should be merged.

---

## Template Consolidation Tally

### Batches 1-5 (Already Processed)
- **Batch 1-2:** 13 templates, ~989 variants replaced ✅
- **Batch 3:** 24 templates, ~291 variants replaced ✅
- **Batch 4:** 12 templates, ~220+ variants replaced ✅
- **Batch 5:** 3 templates, ~35 variants replaced ✅
- **Subtotal:** 52 templates, ~1,535 variants consolidated ✅

### In Database (Active, is_active=TRUE)
- **Consolidated templates found:** 50 ✅
- **Not yet imported:** 4 (likely Requirements for Recommendation Letter to Client, DOR Motion to Dismiss, and 2 others)

---

## Remaining Unconsolidated Templates (12 Duplicate Groups)

These 12 groups (29 total variants) are still in the database with county/qualifier suffixes and have not been consolidated:

### High Priority (6+ Variants)

#### 1. **Motion for Continuance** — 6 variants
```
[CONSOLIDATED TEMPLATE EXISTS]
Master: Motion for Continuance (Batch 2, already active)

Remaining Duplicates:
• Motion for Continuance 03-09-23
• Motion for Continuance 07.22.20
• Motion for Continuance 10-07-22
• Motion for Continuance - Kirkwood
• Motion for Continuance Lewis County
• Motion for Continuance - Pevely Muni

Action: These should be DEACTIVATED, not consolidated (master already exists)
```

### Medium Priority (3 Variants)

#### 2. **NOH Bond Reduction** — 3 variants
```
[LIKELY REPRESENTS] Notice of Hearing (Bond Reduction variant)
Master exists as: Notice of Hearing (Batch 3, generic)

Remaining Duplicates:
• NOH Bond Reduction - Franklin County
• NOH Bond Reduction - Jefferson County
• NOH Bond Reduction - St. Louis City

Action: Either deactivate (if Notice of Hearing covers it) OR consolidate into Notice of Hearing with bond_reduction=true
```

### Low Priority (2 Variants Each)

#### 3. **90 Day Letter with No Priors** — 2 variants
```
Duplicates:
• 90 Day Letter with No Priors
• 90 Day Letter with No Priors - DCC

Consolidation Need: YES (variant for Drug Court Case track)
```

#### 4. **Bond Assignment** — 2 variants
```
[CONSOLIDATED TEMPLATE EXISTS]
Master: Bond Assignment (Batch 2, already active in DB)

Duplicates (SHOULD BE DEACTIVATED):
• Bond Assignment - Jefferson County
• Bond Assignment - St. Louis County

Action: Deactivate these (master template handles all counties via {{county}} placeholder)
```

#### 5. **Client Status Update** — 2 variants
```
Duplicates:
• Client Status Update
• Client Status Update - DCL

Consolidation Need: YES (variant for Drug Court Case track)
```

#### 6. **Entry** — 2 variants
```
[CONSOLIDATED TEMPLATES EXIST]
Masters: Entry (Generic), Entry of Appearance (State), Entry of Appearance (Muni) from Batches 1-2

Duplicates (SHOULD BE DEACTIVATED):
• Entry
• Entry - Wentzville Muni

Action: Deactivate these (masters already cover entry documents)
```

#### 7. **Ltr with Loss of PFR Case** — 2 variants
```
Duplicates:
• Ltr with Loss of PFR Case
• Ltr with Loss of PFR Case - DCL

Consolidation Need: YES (variant for Drug Court Case track)
```

#### 8. **Motion to Set Aside Dismissal - PFR** — 2 variants
```
Duplicates:
• Motion to Set Aside Dismissal - PFR
• Motion to Set Aside Dismissal - PFR DCL

Consolidation Need: YES (variant for Drug Court Case track)
```

#### 9. **MTW - Warning Letter** — 2 variants
```
Duplicates:
• MTW - Warning Letter (Finances and Communication)
• MTW - Warning Letter (Finances)

Consolidation Need: YES (two warning scenarios: finance-only vs. combined issue)
Variables: issue_type (communication, finance, both), warning_tone
```

#### 10. **OOP Entry - Saint Louis** — 2 variants
```
[OOP = Out of Province/Out of Practice?]

Duplicates:
• OOP Entry - Saint Louis City
• OOP Entry - Saint Louis County

Consolidation Need: YES (city vs. county variant)
Variables: jurisdiction (city or county), defendant_name, case_number
```

#### 11. **Petition for LDP During 10 Year Denial** — 2 variants
```
Duplicates:
• Petition for LDP During 10 Year Denial
• Petition for LDP During 10 Year Denial (Modified Drug Court Track)

Consolidation Need: YES (standard vs. DCC variant)
Variables: petitioner_name, dob, dln, drug_court_track=true/false
```

#### 12. **Substitution of Counsel** — 2 variants
```
Duplicates:
• Substitution of Counsel
• Substitution of Counsel (Within Firm)

Consolidation Need: YES (within-firm vs. external new counsel)
Variables: new_counsel_name, new_counsel_bar, internal_transfer=true/false
```

---

## Consolidation Priority Matrix

### Immediate Action (Deactivate existing masters don't need consolidation)
1. **Motion for Continuance** (6 variants) → Master exists, deactivate all 6
2. **Bond Assignment** (2 variants) → Master exists, deactivate both
3. **Entry** (2 variants) → Masters exist, deactivate both
4. **NOH Bond Reduction** (3 variants) → Likely covered by Notice of Hearing, deactivate or audit

### Next Phase (NEW Consolidation Projects — Batch 6)
5. **90 Day Letter with No Priors** (2 variants) — DCC variant
6. **Client Status Update** (2 variants) — DCC variant
7. **Ltr with Loss of PFR Case** (2 variants) — DCC variant
8. **Motion to Set Aside Dismissal - PFR** (2 variants) — DCC variant
9. **MTW - Warning Letter** (2 variants) — Two distinct warning scenarios
10. **OOP Entry** (2 variants) — City vs. County jurisdiction
11. **Petition for LDP During 10 Year Denial** (2 variants) — DCC variant
12. **Substitution of Counsel** (2 variants) — Within-firm vs. external

---

## Batch 6 Recommendation

**Create a "Batch 6" consolidation focusing on:**

1. **Pattern Recognition:** Many of the 12 groups have "DCC" (Drug Court Case) variants — consider creating a firm-wide policy for DCC document variants
2. **Scope:** 12 templates, 29 variants → could consolidate to 12 master templates
3. **Estimated Templates:** 12 new consolidated templates
4. **Estimated Old Variants Replaced:** 29 variants

### Suggested Batch 6 Templates
```
data/templates/
  ├── 90_Day_Letter_with_No_Priors.docx          # {{track}} = "standard" or "dcc"
  ├── Client_Status_Update.docx                  # {{is_drug_court}} = true/false
  ├── Ltr_with_Loss_of_PFR_Case.docx            # {{is_drug_court}} = true/false
  ├── Motion_to_Set_Aside_Dismissal_PFR.docx    # {{is_drug_court}} = true/false
  ├── MTW_Warning_Letter.docx                    # {{issue_type}} = "finance|communication|both"
  ├── OOP_Entry.docx                             # {{jurisdiction}} = "city"|"county"
  ├── Petition_for_LDP_10_Year_Denial.docx      # {{track}} = "standard"|"dcc"
  └── Substitution_of_Counsel.docx               # {{internal_transfer}} = true/false
```

---

## Quick Actions

### 1. Immediate (Run Now)
Run the existing `import_consolidated_templates.py` for Batches 1-5:
```bash
export DATABASE_URL='...'
python import_consolidated_templates.py
```

**Expected Result:**
- Deactivates ~1,535 old variants from Batches 1-5
- Activates 52 new consolidated templates
- Reduces active count from 404 → ~354 (removes old variants)

### 2. Next Week (Batch 6 Planning)
1. Extract templates for 12 groups above
2. Consolidate into masters with {{placeholders}}
3. Add entries to `DOCUMENT_TYPES` in `document_chat.py`
4. Create `import_batch6_templates.py` script
5. Test on staging, deploy to production

### 3. Dashboard Updates Needed
After Batch 6, update `dashboard/templates/documents.html` Quick Generate panel to include:
- 90 Day Letter (with DCC track selector)
- Client Status Update (with DCC option)
- Loss of PFR Case Letter (with DCC option)
- Motion to Set Aside Dismissal - PFR (with DCC option)
- MTW Warning Letter (with issue type selector)
- OOP Entry (with jurisdiction selector)
- Petition for LDP (with track selector)
- Substitution of Counsel (with transfer type selector)

---

## Database Deactivation Query

If you want to test deactivation of the 6 Motion for Continuance variants before full Batch 6:

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

Similar queries for Bond Assignment, Entry variants can be prepared.

---

## Final Template Count Projection

**Current:** 404 active templates

**After Batch 1-5 Import + Batch 6 Consolidation + Deactivation:**
- Consolidated templates: 50 (Batches 1-5) + 12 (Batch 6) = **62 master templates**
- Remaining unique (no duplicates): **325 templates**
- **Final active count: ~387 unique templates** (down from 404)

---

## Remaining Non-Duplicate Templates (325)

These 325 templates are single, unique documents with no obvious variants:
- Specific case motions (Motion to Suppress Evidence, Motion to Quash, etc.)
- Client letters (individualized, one-off documents)
- Court-specific documents (court briefs, responses, orders)
- Checklists and instructions
- Specialized forms (LDP petitions, IID waivers, etc.)
- Legacy documents and drafts

**These should NOT be consolidated further** — they serve specific purposes and don't have systematic variants. If they become problematic (e.g., too many similar-named documents), they can be organized into categories in the database, but not consolidated into templates.

---

## Conclusion

1. ✅ Batches 1-5 consolidation covers **1,535 variants** across **52 templates**
2. ⚠️ **12 remaining duplicate groups** (29 variants) should be Batch 6
3. ✅ **325 single templates** are legitimate unique documents — no consolidation needed
4. 📊 **Final database:** 62 consolidated master templates + 325 unique templates = ~387 active

**Recommendation:** Run Batch 1-5 import now, plan Batch 6 for next week.

