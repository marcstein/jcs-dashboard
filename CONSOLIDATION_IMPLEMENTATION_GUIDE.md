# Template Consolidation Implementation Guide

**Date:** 2026-02-21
**Author:** Analysis - Code Implementation Required

---

## PART A: NEW CONSOLIDATIONS (2 templates)

### Consolidation 1: NOH Bond Reduction

**Status:** Ready for implementation
**Master to Create:** From template ID 1100 (Franklin County)
**Variants to Deactivate:** IDs 1099, 1104

#### Analysis of Variants

All three templates are structurally identical except for:

1. **Hearing day/time:**
   - Franklin (1100): "Thursday, {{service_date}}, at 1:00 p.m."
   - Jefferson (1099): "Tuesday, {{service_date}}, at 9:00 a.m."
   - St. Louis City (1104): "Thursday, {{service_date}}, at 9:00 a.m." + "By consent of the parties"

2. **County reference in courthouse line:**
   - Franklin: "Franklin County Circuit Courthouse"
   - Jefferson: "Jefferson County Circuit Courthouse"
   - St. Louis City: "Saint Louis County Circuit Courthouse" (note: says City in name but County in text)

3. **Signatory (Certificate of Service):**
   - Franklin: "Tiffany Willis"
   - Jefferson: "Tiffany Willis"
   - St. Louis City: "Cole Chadderdon"

4. **Address variations:**
   - Franklin: "75 West Lockwood Avenue, Suite 250" (with specific formatting)
   - Jefferson: "75 West Lockwood Avenue, Suite 250" (same)
   - St. Louis City: "120 S Central Ave, Suite 1550"

#### Universal Master Template (NOH Bond Reduction)

Create new master with these placeholders:

```
REQUIRED (from user):
  - case_number
  - county
  - defendant_name
  - division
  - hearing_day (e.g., "Monday", "Tuesday", "Wednesday", etc.)
  - hearing_time (e.g., "9:00 a.m.", "1:00 p.m.")
  - consent_flag (optional - if true, prepend "By consent of the parties,")

AUTO-FILL (from attorney profile):
  - firm_name
  - firm_city_state_zip
  - signing_attorney (default: "Tiffany Willis" or current staff member)
```

#### Master Template Text

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

{% if consent_flag %}By consent of the parties, the above captioned cause has been set for hearing on Defendant's Motion for Bond Reduction on {{hearing_day}}, {{service_date}}, at {{hearing_time}}, in Division {{division}} of the {{county}} County Circuit Courthouse, or as soon thereafter as counsel may be heard.{% else %}All parties are hereby notified that the above captioned cause has been set for hearing on Defendant's Motion for Amend Bond on {{hearing_day}}, {{service_date}}, at {{hearing_time}}, in Division {{division}} of the {{county}} County Circuit Courthouse, or as soon thereafter as counsel may be heard.{% endif %}

Respectfully submitted,

{{firm_name}}
/s/ John Schleiffarth________________
John C. Schleiffarth         #63222
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

/s/{{signing_attorney}}___________________
```

#### DOCUMENT_TYPES Registry Entry

```python
"noh_bond_reduction": {
    "display_name": "Notice of Hearing - Bond Reduction",
    "description": "Notice of hearing on motion for bond reduction/amendment",
    "document_type_key": "noh_bond_reduction",
    "required_vars": ["case_number", "county", "defendant_name", "division", "hearing_day", "hearing_time", "service_date"],
    "optional_vars": ["consent_flag"],
    "uses_attorney_profile_for": ["firm_name", "firm_city_state_zip", "signing_attorney"],
    "_identify_template": lambda template_name: "noh" in template_name.lower() and "bond" in template_name.lower(),
    "case_type": ["criminal", "dwi", "traffic"],
},
```

#### Implementation Checklist

- [ ] Create new master template in `data/templates/NOH_Bond_Reduction.docx`
  - Use template ID 1100 as base
  - Replace hardcoded county with `{{county}}`
  - Replace "Franklin County Circuit Courthouse" with `{{county}} County Circuit Courthouse`
  - Replace "Thursday, {{service_date}}, at 1:00 p.m." with `{{hearing_day}}, {{service_date}}, at {{hearing_time}}`
  - Replace "Tiffany Willis" with `{{signing_attorney}}`
  - Add conditional logic for "By consent of the parties"

- [ ] Import template to database using import script
  - Set deactivate_patterns: ["NOH Bond Reduction - Franklin County", "NOH Bond Reduction - Jefferson County", "NOH Bond Reduction - St. Louis City"]
  - IDs to deactivate: 1099, 1104

- [ ] Add entry to DOCUMENT_TYPES in `document_chat.py`

- [ ] Add template detection logic to `_identify_template()`

- [ ] Add dashboard button to Quick Generate panel

- [ ] Test document generation with sample input:
  ```
  Case: Jefferson County, case #2024-CR01234
  Defendant: John Smith
  Division: 5
  Hearing: Tuesday, March 15, 2025, at 9:00 a.m.
  ```

---

### Consolidation 2: OOP Entry

**Status:** Ready for implementation
**Master to Create:** From template ID 397 (Saint Louis County - more flexible)
**Variant to Deactivate:** ID 394 (Saint Louis City - hardcoded values)

#### Analysis of Variants

The two templates differ significantly:

**ID 394 (Saint Louis City - HARDCODED):**
- Court header: "CIRCUIT COURT OF THE CITY OF SAINT LOUIS" (hardcoded)
- Parties: "Petitioner" vs hardcoded "Respondent"
- Case number: hardcoded "2422-PN01822"
- Party names: Parameterized but for OOP case structure
- Appears to be an Order of Protection (OOP) case

**ID 397 (Saint Louis County - FLEXIBLE):**
- Court header: `IN THE CIRCUIT COURT OF {{county}} COUNTY` (parameterized)
- Parties: "Plaintiff" vs hardcoded "{{defendant_name}}"
- Case number: `{{case_number}}` (parameterized)
- More flexible structure

#### Key Differences

| Aspect | ID 394 | ID 397 |
|--------|--------|--------|
| Court Header | Hardcoded city | `{{county}}` |
| Party Setup | Petitioner/Respondent | Plaintiff/Defendant |
| Case Type | OOP (Order of Protection) | Criminal/General |
| Case Number | 2422-PN01822 | `{{case_number}}` |
| Address | 120 S Central Avenue, Suite 1550 | Same |

#### Decision: KEEP BOTH OR CONSOLIDATE?

**Issue:** These represent different legal case types:
- **ID 394:** OOP (Order of Protection/Domestic Relations)
- **ID 397:** Criminal/General civil

**Recommendation:** Create TWO separate document types:
1. **OOP Entry (Protective Order)** - Based on ID 394, make flexible
2. **Entry (Criminal/Civil)** - Based on ID 397 (already flexible)

#### Universal Master 1: OOP Entry

```
REQUIRED:
  - county (or use "Saint Louis" for OOP cases)
  - case_number
  - petitioner_name
  - respondent_name
  - service_date

AUTO-FILL:
  - firm_name
  - firm_city_state_zip
```

#### Master 1 Text

```
IN THE CIRCUIT COURT OF {{county}} COUNTY
STATE OF MISSOURI

{{petitioner_name}}, )
)
Petitioner,)
)    
vs.)Case No: {{case_number}}
)       
{{respondent_name}}, )
)
Respondent.)

{{respondent_name}}

COMES NOW, John Schleiffarth and the law firm of JCS Law, and enters their 
appearance as the attorney of record on behalf of the above-named Respondent.

Respectfully submitted,

{{firm_name}}
{{firm_name}}
120 S Central Avenue, Suite 1550
{{firm_city_state_zip}}
Telephone: (314) 561-9690
Facsimile: (314) 596-0658

Attorney for Respondent

/s/John C. Schleiffarth
John Schleiffarth #63222
john@jcsattorney.com

Attorney for Respondent

CERTIFICATE OF SERVICE

The below signature certifies a true and accurate copy of the foregoing 
was filed via the Court's electronic filing system this {{service_date}}, 
to all counsel of record.

/s/Tiffany Willis__________
```

#### DOCUMENT_TYPES Registry Entries

```python
"entry_oopprotection_order": {
    "display_name": "Entry of Appearance (Order of Protection)",
    "description": "Entry of appearance in OOP/protective order case",
    "document_type_key": "entry_oopprotection_order",
    "required_vars": ["county", "case_number", "petitioner_name", "respondent_name", "service_date"],
    "optional_vars": [],
    "uses_attorney_profile_for": ["firm_name", "firm_city_state_zip"],
    "_identify_template": lambda template_name: ("oop" in template_name.lower() and "entry" in template_name.lower()),
    "case_type": ["protective_order", "divorce"],
},

"entry_criminal_general": {
    "display_name": "Entry of Appearance (Criminal/Civil)",
    "description": "Entry of appearance in criminal or civil case",
    "document_type_key": "entry_criminal_general",
    "required_vars": ["county", "case_number", "defendant_name", "service_date"],
    "optional_vars": [],
    "uses_attorney_profile_for": ["firm_name", "firm_city_state_zip"],
    "_identify_template": lambda template_name: "entry" in template_name.lower() and "criminal" not in template_name.lower(),
    "case_type": ["criminal", "dwi", "traffic", "civil"],
},
```

#### Implementation Checklist

- [ ] Create new master templates:
  - `data/templates/Entry_of_Appearance_OOP.docx` (from 394, make parameterized)
  - Keep existing Entry of Appearance (State), Entry of Appearance (Muni) - they are different

- [ ] Import both templates with deactivation of old variants
  - Deactivate ID 394 (hardcoded city version)

- [ ] Add entries to DOCUMENT_TYPES in `document_chat.py`

- [ ] Add template detection logic to `_identify_template()`

- [ ] Add dashboard buttons to Quick Generate panel

- [ ] Test document generation

---

## PART B: DEACTIVATIONS (211 templates)

### Batch 1: Motion for Continuance (192 variants - ID 445 is master)

```sql
UPDATE templates
SET is_active = FALSE
WHERE firm_id = 'jcs_law'
  AND id != 445
  AND name ILIKE '%Motion for Continuance%'
  AND is_active = TRUE;
```

**Count:** 192 templates

### Batch 2: Bond Assignment (3 variants - ID 1145 is master)

```sql
UPDATE templates
SET is_active = FALSE
WHERE firm_id = 'jcs_law'
  AND id IN (93, 89, 797)
  AND is_active = TRUE;
```

**Count:** 3 templates

### Batch 3: Entry of Appearance (2 variants - 1687 State, 1688 Muni are masters)

```sql
UPDATE templates
SET is_active = FALSE
WHERE firm_id = 'jcs_law'
  AND id IN (1675, 1676)
  AND is_active = TRUE;
```

**Count:** 2 templates
**Note:** Keep 1677 (combined doc) for now - may be needed

### Batch 4: 90 Day Letter (3 client-filled variants - 1160 is master)

```sql
UPDATE templates
SET is_active = FALSE
WHERE firm_id = 'jcs_law'
  AND id IN (1413, 230, 1412)
  AND is_active = TRUE;
```

**Count:** 3 templates
**Note:** Keep 234 if it has structural differences (No Admin Hearing variant)

### Batch 5: Client Status Update (2 client-filled variants - 419 is master)

```sql
UPDATE templates
SET is_active = FALSE
WHERE firm_id = 'jcs_law'
  AND id IN (418, 429)
  AND is_active = TRUE;
```

**Count:** 2 templates

### Batch 6: Motion to Set Aside Dismissal (1 duplicate - 758, 726 are masters)

```sql
UPDATE templates
SET is_active = FALSE
WHERE firm_id = 'jcs_law'
  AND id = 68
  AND is_active = TRUE;
```

**Count:** 1 template

### Batch 7: OOP Entry (1 hardcoded variant - 397 is new master)

```sql
UPDATE templates
SET is_active = FALSE
WHERE firm_id = 'jcs_law'
  AND id = 394
  AND is_active = TRUE;
```

**Count:** 1 template

---

## PART C: EXECUTION ORDER

1. **Create new masters** (Groups 4 & 8)
   - Extract templates from DB
   - Modify to add missing placeholders
   - Create .docx files in `data/templates/`

2. **Import new masters**
   - Run import script to add to DB
   - Set deactivate_patterns for replaced variants

3. **Update DOCUMENT_TYPES**
   - Add entries for new consolidations
   - Update existing entries if needed

4. **Run SQL deactivations**
   - Execute all 7 batch updates
   - Total: 211 templates deactivated

5. **Test**
   - Document generation for each new master
   - Dashboard Quick Generate panel
   - Search/lookup for each document type

6. **Deploy**
   - Commit changes
   - Push to production
   - Run import on production server

---

## Next Steps

1. Review this analysis with team
2. Determine if both OOP and Criminal Entry docs are needed
3. Create/modify .docx files for new masters
4. Write import script
5. Execute consolidation plan

