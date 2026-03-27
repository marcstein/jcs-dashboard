# Active Templates After Import - Analysis Summary

## Overview
This analysis examines which templates from the JCS Law Firm's database will remain active after running the `import_consolidated_templates.py` script.

**Generated:** 2026-02-21  
**Database:** lawmetrics_platform (jcs_law firm)  
**Firm ID:** jcs_law

## Key Findings

### Current State (Active Templates)
- **Total Active Templates:** 400
- **Consolidated Masters:** 51 of 53 possible consolidated templates
- **Unique/Non-Consolidated:** 349 templates

### After Running Import Script
- **Would Remain Active:** 399 templates
- **Would Be Deactivated:** 1 template
  - **Notice of Hearing - Motion to Withdraw** (ID: 1748)
    - Matches pattern: `Notice of Hearing - %`
    - This matches the consolidated template "Notice of Hearing - Motion to Withdraw" itself
    - The import script excludes consolidated masters from deactivation, but this appears to be a variant

### Consolidated Templates Included
51 of the 53 consolidated templates are currently active:

#### Batch 1-2 (13 templates, replaces ~989 variants)
1. Entry of Appearance (State)
2. Entry of Appearance (Muni)
3. Motion for Continuance
4. Request for Discovery
5. Potential Prosecution Letter
6. Preservation/Supplemental Discovery Letter
7. Preservation Letter
8. Motion to Recall Warrant
9. Proposed Stay Order
10. Disposition Letter to Client
11. Filing Fee Memo
12. Bond Assignment
13. Motion to Dismiss (General)

#### Batch 3 (24 templates, replaces ~291 variants)
14. Motion for Change of Judge
15. Notice of Hearing (General)
16. Petition for Review (PFR)
17. After Supplemental Disclosure Letter
18. Waiver of Arraignment
19. Notice to Take Deposition
20. Motion for Bond Reduction
21. Motion to Certify for Jury Trial
22. Letter to DOR with PFR
23. Letter to DOR with Stay Order
24. DOR Motion to Dismiss
25. Notice of Hearing - Motion to Withdraw
26. Motion to Shorten Time
27. Letter to DOR with Judgment
28. Motion to Appear via WebEx
29. Motion to Place on Docket
30. Notice of Change of Address
31. Request for Supplemental Discovery
32. Motion to Amend Bond Conditions
33. Letter to Client with Discovery
34. Motion to Compel Discovery
35. Motion to Terminate Probation
36. Request for Jury Trial
37. DL Reinstatement Letter

#### Batch 4 (12 templates)
38. Request for Recommendation Letter to PA
39. Entry (Generic)
40. Plea of Guilty
41. Motion to Dismiss (County)
42. Request for Stay Order
43. Waiver of Preliminary Hearing
44. Request for Transcripts
45. Motion to Withdraw Guilty Plea
46. PH Waiver
47. Answer for Request to Produce
48. Available Court Dates for Trial
49. Requirements for Rec Letter to Client
50. Motion to Withdraw
51. Closing Letter

#### Batch 5 (3 templates, converted from OLE format)
52. Admin Continuance Request
53. Admin Hearing Request
54. Petition for Trial De Novo

#### Batch 6 (2 templates)
55. NOH Bond Reduction
56. OOP Entry

**Missing:** 2 consolidated templates (likely one is a Motion to Dismiss variant not yet consolidated, or an earlier batch template that wasn't imported)

## Excel File Structure

### Sheet 1: Remaining Templates
- **Rows:** 399 (all templates that would remain active)
- **Columns:** 
  - `#` - Row number
  - `ID` - Database template ID
  - `Name` - Template name
  - `Category` - Template category (pleading, motion, letter, etc.)
  - `Subcategory` - More specific categorization
  - `File Size (KB)` - Template file size in kilobytes
  - `Is Consolidated` - Yes/No indicator (marks the 51 consolidated masters)

### Sheet 2: Would Be Deactivated
- **Rows:** 1 (only "Notice of Hearing - Motion to Withdraw")
- **Columns:**
  - `#` - Row number
  - `ID` - Database template ID
  - `Name` - Template name
  - `Matched Pattern` - The deactivation pattern it matched

### Sheet 3: Summary
- **Metric** | **Count**
- Total Active Now | 400
- Would Be Deactivated | 1
- Would Remain | 399
- Of Which Consolidated | 51
- Of Which Unique (Non-Consolidated) | 348

## Deactivation Logic

The `import_consolidated_templates.py` script uses these rules:

1. For each consolidated template, it defines `deactivate_patterns` (SQL LIKE patterns)
2. When the script runs, it executes:
   ```sql
   UPDATE templates SET is_active = FALSE
   WHERE firm_id = 'jcs_law' 
     AND name ILIKE <pattern>
     AND is_active = TRUE
     AND name != <consolidated_master_name>
   ```
3. This ensures variant templates (like "Entry - Jefferson County") are deactivated, but the consolidated master ("Entry of Appearance (State)") is preserved

## Variant Patterns Defined

Examples of patterns that would deactivate variants:
- `Entry - % County%` → matches variants like "Entry - Jefferson County"
- `Entry - % Muni%` → matches variants like "Entry - Springfield Muni"
- `Motion to Recall Warrant - %` → matches county-specific versions
- `DL Reinstatement Letter%` → matches all variations of DL reinstatement letter

## Notes

1. **Import Idempotence:** The import script is idempotent - it can be run multiple times safely
2. **Current State:** The script has likely already been run, as many old variants are already inactive
3. **One Outlier:** "Notice of Hearing - Motion to Withdraw" (ID: 1748) appears to match its own deactivation pattern but is kept because it IS the consolidated master itself
4. **Total Coverage:** 51 consolidated templates replace hundreds of county/jurisdiction-specific variants, reducing template maintenance burden significantly

## Recommendations

1. Run the import script in production to standardize templates
2. Monitor the "Would Be Deactivated" sheet for any unexpected template removals
3. Train staff on the 56 consolidated templates (all have auto-fill from attorney profiles)
4. Archive old county-specific variants after deactivation

---

**Output File:** `/sessions/blissful-upbeat-feynman/mnt/Legal/data/Active_Templates_After_Import.xlsx`  
**Analysis Tool:** Python with psycopg2, openpyxl  
**Matching Engine:** SQL LIKE pattern simulation with fnmatch
