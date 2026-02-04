# Pleading Template Analysis

## Document 1: Request for Jury Trial

### Full Structure
```
IN THE CIRCUIT COURT OF {{county}} COUNTY
STATE OF MISSOURI

STATE OF MISSOURI,                )
                                  )
         Plaintiff,               )    Case No. {{case_number}}
                                  )
vs.                               )
                                  )
{{defendant_name}},               )
                                  )
         Defendant.               )

                    REQUEST FOR JURY TRIAL

Comes now Defendant, by and through counsel, and pursuant to RSMo
Section 543.200, requests a trial by jury in the above-captioned case.

                                        Respectfully Submitted,

                                        John C. Schleiffarth, P.C.

                                        /s/{{signing_attorney_name}}_______
                                        {{signing_attorney_name}} #{{bar_number}}
                                        {{additional_attorneys}}
                                        75 West Lockwood Avenue, Suite 250
                                        Webster Groves, Missouri 63119
                                        Telephone: 314-561-9690
                                        Facsimile: 314-596-0658
                                        Email: {{attorney_email}}
                                        Attorney for Defendant

                    CERTIFICATE OF SERVICE

The below signature certifies a true and accurate copy of the foregoing
was filed via the Court's electronic filing system, this {{service_date}},
to all counsel of record.

                                        /s/{{service_signer}}_______
```

### Variable Analysis

| Variable | Type | Source | Example |
|----------|------|--------|---------|
| `county` | text | Case data | "Scott", "St. Louis" |
| `case_number` | text | Case data | "18AB-CR02689" |
| `defendant_name` | text | Case data | "BOBBY STEEVER" |
| `signing_attorney_name` | text | Firm/Case | "John Schleiffarth" |
| `bar_number` | text | Attorney data | "63222" |
| `additional_attorneys` | text/list | Case data | "Andrew Morris #67504" |
| `attorney_email` | text | Attorney data | "john@jcsattorney.com" |
| `service_date` | date | Generated | "July 26, 2021" |
| `service_signer` | text | Staff | "Tiffany Willis" |

### Boilerplate (Constant)
- "STATE OF MISSOURI" as plaintiff
- RSMo Section 543.200 reference
- Firm address
- Phone/fax numbers
- Document title and basic legal language

---

## Document 2: Waiver of Arraignment

### Full Structure
```
IN THE CIRCUIT COURT OF {{county}} COUNTY
STATE OF MISSOURI

STATE OF MISSOURI,                )
                                  )
         Plaintiff,               )    Case No.: {{case_number}}
                                  )
vs.                               )
                                  )
{{defendant_name}},               )
                                  )
         Defendant.               )

                    WAIVER OF ARRAIGNMENT

I, {{defendant_name}}, understand that I am charged with the following
offenses:

{{charges_list}}

I am represented by my attorney, {{attorney_name}} of the Law Office
of John C. Schleiffarth, P.C. I understand I have a right to have the
Judge of this Court read the charges to me word for word, and I
understand that I can give up that right if I wish to do so. By signing
my name below, I am notifying the Court that I am revoking my right to
have the charges read aloud and that I understand the offenses with
which I have been charged.

I hereby enter a plea of {{plea_type}} and request this case be placed on
the docket for setting or disposition on a future date.

__________________________________    ________________________
Defendant's Signature                 Date

__________________________________    ________________________
Attorney for Defendant                Date
```

### Variable Analysis

| Variable | Type | Source | Example |
|----------|------|--------|---------|
| `county` | text | Case data | "Scott" |
| `case_number` | text | Case data | "22SO-CR00195" |
| `defendant_name` | text | Case data | "GLENN MANSFIELD" |
| `attorney_name` | text | Case data | "John C. Schleiffarth" |
| `charges_list` | **complex** | Case data | See below |
| `plea_type` | choice | User input | "not-guilty", "guilty" |

### The Charges Challenge

The charges list is the most complex variable. Example:
```
Count I: Delivery of Controlled Substance Except 35 Grams or Less of
         Marijuana or Synthetic Cannabinoid, a Class C Felony

Count II: Unlawful Possession of a Firearm, a Class D Felony

Count III: Promoting Gambling – 1st Degree, a Class E Felony

Count IV: Tampering with Physical Evidence, a Class A Misdemeanor
```

**Structure per charge:**
- Count number (Roman numeral: I, II, III, IV, V...)
- Charge description (from statute)
- Classification (Class A-E Felony, Class A-D Misdemeanor, Infraction)

---

## Common Elements Across Pleadings

### 1. Case Caption (Header)
Every pleading shares this structure:
```
IN THE CIRCUIT COURT OF {{county}} COUNTY
STATE OF MISSOURI

STATE OF MISSOURI,                )
                                  )
         Plaintiff,               )    Case No.: {{case_number}}
                                  )
vs.                               )
                                  )
{{defendant_name}},               )
                                  )
         Defendant.               )
```

### 2. Attorney Signature Block
```
                                        John C. Schleiffarth, P.C.

                                        /s/{{signing_attorney}}_______
                                        {{attorney_name}} #{{bar_number}}
                                        75 West Lockwood Avenue, Suite 250
                                        Webster Groves, Missouri 63119
                                        Telephone: 314-561-9690
                                        Facsimile: 314-596-0658
                                        Email: {{attorney_email}}
                                        Attorney for Defendant
```

### 3. Certificate of Service
```
                    CERTIFICATE OF SERVICE

The below signature certifies a true and accurate copy of the foregoing
was filed via the Court's electronic filing system, this {{service_date}},
to all counsel of record.

                                        /s/{{service_signer}}_______
```

---

## Recommended Variable Types

### 1. Simple Variables (Direct Substitution)
```python
{{defendant_name}}      # "JOHN SMITH"
{{case_number}}         # "22SO-CR00195"
{{county}}              # "Scott"
```

### 2. Case-Mapped Variables (Auto-filled from MyCase)
```python
{{case.defendant_name}}       # Maps to contact.name
{{case.case_number}}          # Maps to case.number
{{case.court_county}}         # Extracted from case.court
{{case.lead_attorney}}        # Maps to case.lead_attorney
{{case.charges}}              # Maps to case.practice_area + custom field
```

### 3. Computed Variables
```python
{{today}}                     # Current date formatted
{{today_formal}}              # "January 15, 2026"
{{defendant_name_caps}}       # Uppercase version
```

### 4. Complex/List Variables (Require AI)
```python
{{charges_list}}              # Formatted list of all charges
{{attorneys_block}}           # All attorneys on case
```

### 5. Choice Variables
```python
{{plea_type: not-guilty|guilty|nolo contendere}}
{{court_type: Circuit|Municipal|Federal}}
```

---

## Implementation Strategy

### Option A: Template Sections (Composable)
Build documents from reusable sections:
```
[caption]       → Case caption header
[title]         → Document title (e.g., "REQUEST FOR JURY TRIAL")
[body]          → Document-specific content
[signature]     → Attorney signature block
[service_cert]  → Certificate of service
[defendant_sig] → Defendant signature line (when needed)
```

### Option B: Smart AI Generation
Let Claude handle complex formatting:
- Provide case data + template outline
- AI generates properly formatted document
- Handles edge cases (multiple counts, unusual charges)

### Option C: Hybrid (Recommended)
- Use templates for boilerplate (caption, signature blocks)
- Use AI for complex sections (charges list, customized language)
- Variable substitution for simple fields

---

## MyCase Field Mapping

| Template Variable | MyCase Field | Notes |
|-------------------|--------------|-------|
| `defendant_name` | `contact.name` | From primary contact |
| `case_number` | `case.number` | Case number field |
| `county` | `case.court` | Parse county from court name |
| `lead_attorney` | `case.lead_attorney` | Attorney assigned |
| `charges` | `case.custom_fields.charges` or parse from `case.description` | May need custom field |
| `case_type` | `case.case_type` | DWI, Traffic, etc. |

---

## Next Steps

1. **Create charge data structure** - How to store/retrieve charge info
2. **Build template sections** - Reusable caption, signature blocks
3. **Implement AI charge formatting** - Handle variable count lists
4. **Add template metadata** - Which courts, case types each applies to
