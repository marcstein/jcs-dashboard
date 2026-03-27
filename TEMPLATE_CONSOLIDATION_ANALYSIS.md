# Template Consolidation Analysis: 12 Remaining Groups

**Analysis Date:** 2026-02-21
**Database:** lawmetrics_platform (PostgreSQL)
**Firm:** jcs_law

## Executive Summary

Analysis of the 12 remaining template groups identified:
- **Groups 1-3:** Already have consolidated masters (Motion for Continuance, Bond Assignment, Entry of Appearance)
  - Action: Deactivate variants (~205 total)
  - **Status:** Simple deactivation, no new consolidation needed

- **Groups 4-9:** Remaining groups requiring consolidation or deactivation
  - Groups 4, 8: True duplicates with only county/court variants → **Consolidate to 1 master each**
  - Groups 5, 6: Client-specific variants → **Keep master, deactivate filled variants**
  - Group 7: Mixed document types (OOP vs PFR) → **Keep 2 masters, deactivate duplicate**
  - Group 9: Different use cases (within-firm vs full substitution) → **Keep both masters**

- **Groups 10-12:** Do not exist in database
  - Loss of PFR Case Letter: NOT FOUND
  - MTW Warning Letter: NOT FOUND
  - Petition for LDP 10Y Denial: NOT FOUND

---

## GROUP 1: Motion for Continuance (193 templates)

**Status:** Already has consolidated master ✓

### Current State
- **Master Template:** ID 445 "Motion for Continuance"
- **Total Templates:** 193 active
- **Variants:** 192 county, attorney, and specialized variants

### Placeholders Required
```
Required: case_number, COUNTY (uppercase), defendant_name, hearing_date, continuance_reason, service_date
Optional: second_attorney_name, second_attorney_bar, second_attorney_email, service_signatory
Auto-fill: attorney_name, attorney_bar, attorney_email, firm_name, firm_address, firm_city_state_zip, firm_phone, firm_fax, signing_attorney
```

### Recommendation
**DEACTIVATE all 192 variants.** The master template at ID 445 handles all use cases with placeholder variables.

---

## GROUP 2: Bond Assignment (4 templates)

**Status:** Already has consolidated master ✓

### Current State
- **Master Template:** ID 1145 "Bond Assignment"
- **Total Templates:** 4 active
- **Variants:**
  - ID 93: Bond Assignment - Jefferson County
  - ID 89: Bond Assignment - St. Louis County
  - ID 797: Bond Assignment to Court Costs and Fines (different purpose)

### Key Differences
1. **ID 93** (Jefferson): Has hardcoded defendant name "TYLOR KITCHELL" in one location
2. **ID 89** (St. Louis): Different signature block layout (missing underscores in assignor/assignee section)
3. **ID 797** (Court Costs): Entirely different document purpose (assigns to court costs, not bond amount)

### Placeholders Required
```
Master (1145): county, case_number, defendant_name, division, bond_amount, firm_address, firm_city_state_zip, firm_name
```

### Recommendation
**DEACTIVATE all 3 variants (IDs 93, 89, 797).** The master at ID 1145 handles standard bond assignments. ID 797 is a different document type (Court Costs Bond) and may need separate treatment.

---

## GROUP 3: Entry of Appearance (5 templates)

**Status:** Already has consolidated masters ✓

### Current State
- **Master Templates:** 
  - ID 1687 "Entry of Appearance (State)"
  - ID 1688 "Entry of Appearance (Muni)"
- **Total Templates:** 5 active
- **Variants:**
  - ID 1675: Entry of Appearance - Single Attorney
  - ID 1676: Entry of Appearance - Multiple Attorneys
  - ID 1677: Entry of Appearance, Waiver of Arraignment, Plea of Not Guilty (combined document)

### Key Differences
- **1675 & 1676:** Have different header structure: `{{court}} STATE OF MISSOURI COUNTY OF {{county}}` (more flexible)
- **1677:** Combines three documents into one (Entry, Waiver, Plea) - distinct use case

### Placeholders
```
State (1687): COUNTY, plaintiff_name, case_number, defendant_name, attorney_names, attorney_name, attorney_bar, attorney_email, firm_name, firm_address, firm_city_state_zip, firm_phone, firm_fax, service_date, service_signatory, signing_attorney

Muni (1688): CITY, city, case_number, defendant_name, attorney_names, attorney_name, attorney_bar, attorney_email, prosecutor_name, prosecutor_address, prosecutor_city_state_zip, firm_name, firm_address, firm_city_state_zip, firm_phone, firm_fax, service_date, service_signatory, signing_attorney
```

### Recommendation
**DEACTIVATE variants 1675, 1676.** Keep both 1687 and 1688 as they serve different purposes (State vs Municipal courts). ID 1677 is a combined document - keep separate if used.

---

## GROUP 4: NOH Bond Reduction (3 templates)

**Status:** NEW CONSOLIDATION CANDIDATE ✓

### Current State
- **IDs:** 1100, 1099, 1104
- **Names:** 
  - 1100: NOH Bond Reduction - Franklin County
  - 1099: NOH Bond Reduction - Jefferson County
  - 1104: NOH Bond Reduction - St. Louis City

### Variant Analysis

| Aspect | Franklin | Jefferson | St. Louis City |
|--------|----------|-----------|----------------|
| Court Type | Circuit | Circuit | City |
| Hearing Day | Thursday | Tuesday | "By consent" |
| Hearing Time | 1:00 p.m. | 9:00 a.m. | (varies) |
| County Reference | Franklin | Jefferson | - |

### Key Finding
**TRULY IDENTICAL EXCEPT FOR:**
- County/court name
- Hearing day of week
- Hearing time

This is perfect for consolidation with placeholders.

### Placeholders Required
```
Required from user: case_number, county, defendant_name, division, service_date, hearing_day, hearing_time
Auto-fill from profile: firm_name, firm_city_state_zip
```

### Template Text
```
IN THE CIRCUIT COURT OF {{county}} COUNTY
STATE OF MISSOURI

STATE OF MISSOURI,)
)
Plaintiff,)
)
v.) Case No.: {{case_number}}
)
{{defendant_name}},)
)
Defendant.)

{{defendant_name}}

All parties are hereby notified that the above captioned cause has been set 
for hearing on Defendant's Motion for Amend Bond on {{hearing_day}}, {{service_date}}, 
at {{hearing_time}}, in Division {{division}} of the {{county}} County Circuit Courthouse, 
or as soon thereafter as counsel may be heard.

Respectfully submitted,

{{firm_name}}
/s/ John Schleiffarth________________
John C. Schleiffarth #63222
75 West Lockwood Avenue, Suite 250
{{firm_city_state_zip}}
Telephone: (314) 561-9690
Facsimile: (314) 596-0658
Email: john@jcsattorney.com
Attorney for Defendant

CERTIFICATE OF SERVICE

The below signature certifies a true and accurate copy of the foregoing 
was given via operation of the Court electronic filing system, this {{service_date}}, 
to all counsel of record.

/s/Tiffany Willis___________________
```

### Recommendation
**CONSOLIDATE to 1 master template.** Deactivate IDs 1099 and 1104. Create universal master with `{{county}}`, `{{hearing_day}}`, and `{{hearing_time}}` placeholders.

---

## GROUP 5: 90 Day Letter with No Priors (5 templates)

**Status:** CLIENT-SPECIFIC VARIANTS - Keep master, deactivate filled instances

### Current State
- **IDs:** 1160, 1413, 230, 234, 1412
- **Master:** ID 1160 (generic/template version)
- **Filled Variants:**
  - 1413: Client filled (Nicholas Schlueter) - actual client data
  - 230: DCC version - actual client data
  - 234: No Admin Hearing variant
  - 1412: SATOP Comparable variant

### Key Finding
Templates 1413, 230, and 1412 contain **actual client names, addresses, and email addresses**. These are previous client cases that have been stored as template variants. They should be deactivated as they are client-filled, not templates.

### Master Template (ID 1160) Analysis
The generic master has proper placeholders:
```
Required: service_date
Optional: fine_amount, client_name, client_address, client_email
Auto-fill: firm_name
```

This is a **client letter** explaining administrative hearing results and 90-day suspension/restricted driving privileges.

### Recommendation
**KEEP master ID 1160.** DEACTIVATE filled client variants (1413, 230, 1412). These are prior client cases stored as templates and should not be active in the system.

---

## GROUP 6: Client Status Update (3 templates)

**Status:** CLIENT-SPECIFIC VARIANTS - Keep master, deactivate filled instances

### Current State
- **IDs:** 419, 418, 429
- **Master:** ID 419 (generic version)
- **Filled Variants:**
  - 418: Client Status Update - DCL (actual client: Staci L Kaiser, case details filled)
  - 429: Final Client Status Update - DCL (actual client data)

### Master Template (ID 419) Analysis
Generic monthly case status letter to client:
```
Required: service_date
Optional: case_update_text, client_name, status_summary
Auto-fill: firm_name
```

### Key Finding
IDs 418 and 429 contain actual client email addresses, names, and case-specific paragraphs. These are previous client letters saved as variants, not generic templates.

### Recommendation
**KEEP master ID 419.** DEACTIVATE filled client variants (418, 429). These are prior client communications stored as templates.

---

## GROUP 7: Motion to Set Aside Dismissal (3 templates)

**Status:** MIXED DOCUMENT TYPES - Keep 2 masters, deactivate 1 duplicate

### Current State
- **IDs:** 758, 726, 68
- **Names:**
  - 758: Motion to Set Aside Dismissal (general - civil/OOP)
  - 726: Motion to Set Aside Dismissal - PFR
  - 68: Motion to Set Aside Dismissal - PFR DCL

### Variant Analysis

| Aspect | ID 758 (General) | ID 726 (PFR) | ID 68 (PFR DCL) |
|--------|------------------|--------------|-----------------|
| Party Role | Respondent | Petitioner | Petitioner |
| Opposing Party | {{respondent_name}} | DIRECTOR OF REVENUE | DIRECTOR OF REVENUE |
| Case Type | OOP/Civil | PFR (DOR) | PFR (DCL) |
| Court Caption | Standard civil | Standard civil | Standard civil |

### Key Finding
- **ID 758 vs 726:** Different party terminology and opposing party. These are genuinely different use cases.
- **ID 726 vs 68:** Nearly identical - both PFR motions with same party roles and structure.

### Placeholders
```
General (758): case_number, county, petitioner_name, respondent_name, service_date, firm_name, firm_city_state_zip

PFR (726): case_number, county, petitioner_name, service_date, firm_name, firm_city_state_zip
```

### Recommendation
**KEEP both masters (758 general, 726 PFR).** DEACTIVATE ID 68 as it's a duplicate of 726 (both are PFR motions with identical structure).

---

## GROUP 8: OOP Entry (2 templates)

**Status:** COUNTY VARIANTS - Consolidate to 1 master

### Current State
- **IDs:** 394, 397
- **Names:**
  - 394: OOP Entry - Saint Louis City
  - 397: OOP Entry - Saint Louis County

### Variant Analysis

| Aspect | City (394) | County (397) |
|--------|-----------|-------------|
| Court Header | "CIRCUIT COURT OF THE CITY OF SAINT LOUIS" (hardcoded) | `IN THE CIRCUIT COURT OF {{county}} COUNTY` |
| Case Party | State of Missouri vs Respondent | `{{defendant_name}}` |
| Case Structure | OOP/Protective order | Appears to be criminal or mixed |

### Key Differences
- **ID 394:** Hardcoded "THE CITY OF SAINT LOUIS" with static case number "2422-PN01822"
- **ID 397:** Parametrized with `{{county}}` and `{{case_number}}`

### Placeholders Required
```
Required: service_date
Optional: petitioner_name, respondent_name, case_number (for county variant)
Auto-fill: firm_name, firm_city_state_zip
```

### Recommendation
**CONSOLIDATE to 1 master using ID 397 as base** (it's more flexible with `{{county}}` placeholder). Create conditional placeholders or separate document types for City vs County courts. DEACTIVATE ID 394 (hardcoded city).

---

## GROUP 9: Substitution of Counsel (2 templates)

**Status:** DIFFERENT USE CASES - Keep both masters

### Current State
- **IDs:** 762, 709
- **Names:**
  - 762: Substitution of Counsel (attorney change)
  - 709: Substitution of Counsel (Within Firm)

### Variant Analysis

| Aspect | ID 762 (Full Substitution) | ID 709 (Within Firm) |
|--------|---------------------------|----------------------|
| Replacing Attorney | "{{firm_name}}" (external) | "David Casey with {{firm_name}}" (internal) |
| Withdrawn Attorney | "Matthew Kallial" (hardcoded) | Not explicitly named |
| Purpose | Full substitution of counsel | Internal attorney change |
| Defendant Name | {{defendant_name}} (parametrized) | "EDWIN GONZALEZ" (hardcoded) |

### Key Finding
- **ID 762:** General attorney substitution (one attorney replaces another, possibly from different firm)
- **ID 709:** Within-firm substitution (internal team reassignment)

Both are legitimately different scenarios and require different language/structure.

### Placeholders
```
General (762): county, defendant_name, service_date, firm_name, firm_city_state_zip

Within Firm (709): county, case_number, service_date, firm_name, firm_city_state_zip
```

### Recommendation
**KEEP BOTH MASTERS (762 and 709).** They serve different legal purposes and require different information. No deactivation needed.

---

## GROUPS 10-12: Not Found

### Group 10: Loss of PFR Case Letter
**Status:** NOT FOUND in database
- Searched for: "Loss of PFR Case Letter"
- Result: 0 templates

### Group 11: MTW Warning Letter  
**Status:** NOT FOUND in database
- Searched for: "MTW Warning Letter"
- Result: 0 templates

### Group 12: Petition for LDP 10Y Denial
**Status:** NOT FOUND in database
- Searched for: "Petition for LDP 10Y Denial"
- Result: 0 templates

### Recommendation
These three groups either:
1. Do not exist in the jcs_law firm templates
2. Are named differently in the database
3. Are stored in a different firm's template library

**Action:** No consolidation needed. These templates may be on a future roadmap.

---

## Summary: Consolidation Actions

### To Consolidate (2 groups)
1. **Group 4: NOH Bond Reduction** - Consolidate 3 county variants → 1 master
2. **Group 8: OOP Entry** - Consolidate 2 court variants → 1 master

### To Deactivate (Keep Masters)
3. **Group 1:** Deactivate 192 Motion for Continuance variants
4. **Group 2:** Deactivate 3 Bond Assignment variants
5. **Group 3:** Deactivate 2 Entry of Appearance variants (keep 1688 Muni, deactivate 1675-1676)
6. **Group 5:** Deactivate 3 filled 90-Day Letter variants (1413, 230, 1412)
7. **Group 6:** Deactivate 2 filled Client Status Update variants (418, 429)
8. **Group 7:** Deactivate 1 PFR Dismissal duplicate (68)

### To Keep (No Action)
9. **Group 9: Substitution of Counsel** - Keep both masters (different use cases)

### Not Found (No Action)
10-12: Loss of PFR Letter, MTW Warning Letter, Petition for LDP 10Y Denial

---

## Next Steps

1. Create consolidated master templates for Groups 4 and 8
2. Run deactivation SQL for all variant IDs across Groups 1-3, 5-8
3. Update `DOCUMENT_TYPES` registry in `document_chat.py` for new consolidations
4. Test document generation with new placeholders
5. Update dashboard Quick Generate panel

