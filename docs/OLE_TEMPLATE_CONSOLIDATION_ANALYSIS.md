================================================================================
TEMPLATE CONVERSION & CONSOLIDATION ANALYSIS
================================================================================

Completed: February 21, 2026
Conversion Tool: LibreOffice (headless)
Source Format: .doc (OLE/Office 97-2003)
Target Format: .docx (Office Open XML)
Database: lawmetrics_platform (firm_id: jcs_law, is_active: TRUE)

================================================================================
1. ADMIN CONTINUANCE REQUEST
================================================================================

TEMPLATES IN GROUP (10 total):
  1. ID 1425 | Admin Continuance Request (REPRESENTATIVE)
  2. ID 1473 | Admin Continuance Request - ATM
  3. ID 1472 | Admin Continuance Request - DCC
  4. ID 1471 | Admin Continuance Request - DCL
  5. ID 1469 | Admin Continuance Request - DRT
  6. ID 1474 | Admin Continuance Request - HL
  7. ID 1426 | Admin Continuance Request - HLL
  8. ID 1428 | Admin Continuance Request - HPH
  9. ID 1429 | Admin Continuance Request - In Person
 10. ID 1427 | Admin Continuance Request - JCS

REPRESENTATIVE TEMPLATE CONTENT:
--------
February 21, 2026

Via Fax: (573)751-8115

Mr. Joshua M. Cox
Missouri Department of Revenue
General Counsel's Office
Post Office Box 475
Jefferson City, Missouri 65105-0475

RE:
Petitioner:  Suzanne Hock
Docket No.: LINC0055
Case No.: AD24010681
DLN: A054174001
Hearing Date: December 3rd, 2024

Dear Mr. Cox:

I am requesting a continuance from December 3rd, 2024, regarding the above-referenced 
matter. Petitioner's Counsel's requests additional time to review arrest packet and 
body camera and dash camera footage recently received. Please call me right away if 
there is an issue with this request or if you should have any questions.

Thank you for your assistance and your courtesy.

Sincerely,

/s/ John Schleiffarth
_________________
John C. Schleiffarth #63222
120 S Central Avenue, Suite 1550
Clayton, Missouri 63105
Telephone: 314-561-9690
Facsimile: 314-596-0658
Email: john@jcsattorney.com

Attorney for Petitioner
--------

IDENTIFIED PLACEHOLDERS FOR CONSOLIDATION:
  Required Variables (asked from user):
    - {{petitioner_name}}      : Petitioner name (currently: "Suzanne Hock")
    - {{docket_number}}        : Docket number (currently: "LINC0055")
    - {{case_number}}          : Case number (currently: "AD24010681")
    - {{dln}}                  : Driver's License Number (currently: "A054174001")
    - {{hearing_date}}         : Hearing date (currently: "December 3rd, 2024")
    - {{continuance_reason}}   : Reason for continuance (default: "additional time to review 
                                  arrest packet and body camera and dash camera footage")
    - {{fax_number}}           : Recipient fax number (default: (573)751-8115 for DOR)

  Auto-Filled from Attorney Profile:
    - {{attorney_name}}        : Attorney name (currently: "John C. Schleiffarth")
    - {{attorney_bar}}         : Bar number (currently: "#63222")
    - {{firm_address}}         : Firm address (currently: "120 S Central Avenue, Suite 1550")
    - {{firm_city_state_zip}}  : City, state, zip (currently: "Clayton, Missouri 63105")
    - {{attorney_phone}}       : Phone (currently: "314-561-9690")
    - {{attorney_fax}}         : Fax (currently: "314-596-0658")
    - {{attorney_email}}       : Email (currently: "john@jcsattorney.com")

  Note: Letter format is standardized for Department of Revenue (DOR) administrative hearings.
        Different attorney variants (ATM, DCC, HL, HLL, JCS, etc.) differ primarily in 
        signature blocks and contact info.

================================================================================
2. ADMIN HEARING REQUEST
================================================================================

TEMPLATES IN GROUP (20 total):
  1. ID  234 | 90 Day Letter with No Priors - No Admin Hearing (different doc type)
  2. ID 1455 | Admin Hearing Entry on Already Requested Hearing
  3. ID 1457 | Admin Hearing EOA
  4. ID 1673 | Admin Hearing Request (REPRESENTATIVE)
  5. ID 1667 | Admin Hearing Request - DCC
  6. ID 1670 | Admin Hearing Request - DCL
  7. ID 1541 | Admin Hearing Request - Established Hearing
  8. ID 1539 | Admin Hearing Request - HL
  9. ID 1542 | Admin Hearing Request - HLL
 10. ID 1538 | Admin Hearing Request - JCS
 11. ID 1665 | Admin Hearing Request - Out of State DL
 12. ID 1540 | Admin Hearing Request - PH
 13. ID 1666 | Admin Hearing Submit on the Record Request
 14. ID 1672 | Admin Hearing Submit on the Record Request - ATM
 15. ID 1669 | Admin Hearing Submit on the Record Request - DCC
 16. ID 1456 | Admin Hearing Submit on the Record Request - HL
 17. ID 1671 | Admin Hearing Submit on the Record Request Specific Issue- ATM
 18. ID 1668 | Admin Hearing Withdraw Request
 19. ID 1458 | Admin Hearing Withdraw Request - DCL
 20. ID  349 | DWI - Admin Hearing New Client Checklist

NOTE: This group contains multiple document types mixed together:
  - "Admin Hearing Request" (5 templates)
  - "Admin Hearing Submit on the Record Request" (5 templates)
  - "Admin Hearing Withdraw Request" (2 templates)
  - "Admin Hearing Entry on Already Requested Hearing" (1 template)
  - "Admin Hearing EOA" (1 template)
  - Other unrelated docs (ID 234, 349)

Recommend consolidating into 5 DOCUMENT TYPES instead of 1:
  1. Admin Hearing Request (generic)
  2. Admin Hearing Submit on the Record Request
  3. Admin Hearing Withdraw Request
  4. Admin Hearing Entry on Already Requested Hearing
  5. Admin Hearing EOA

REPRESENTATIVE TEMPLATE CONTENT (Admin Hearing Request - ID 1673):
--------
February 21, 2026

Via Facsimile: 573-751-7151

Attn: ADMINISTRATIVE HEARING SECTION
General Counsel's Office
Post Office Box 475
Jefferson City, Missouri 65105-0465

RE:
Petitioner's Name:     Matthew Sellers
D.O.B.:                10/23/1978
Drivers License No.:   U153266004
State of Issue:        Missouri
County Where Allegedly Arrested: Saint Genevieve County
Date Allegedly Arrested: 02/13/2023
Case Number:           Unknown

Dear Sir or Madam:

Please let this letter serve as my entry of appearance on behalf of the Petitioner. My 
client is requesting a telephone hearing. Please forward all correspondence to me at the 
below address.

If you have any questions, please do not hesitate to contact me.

Respectfully submitted,

John C. Schleiffarth, P.C.

/s/John Schleiffarth
______________________
John C. Schleiffarth
#63222
Andrew Morris
#675047
5 West Lockwood Avenue, Suite 250
Webster Groves, Missouri 63119
Telephone: (314) 561-9690
Facsimile: (314) 596-0658
Email: john@jcsattorney.com and y@jcsattorney.com
--------

IDENTIFIED PLACEHOLDERS FOR CONSOLIDATION:
  Required Variables (asked from user):
    - {{petitioner_name}}         : Petitioner name (currently: "Matthew Sellers")
    - {{dob}}                     : Date of birth (currently: "10/23/1978")
    - {{dln}}                     : Driver's License Number (currently: "U153266004")
    - {{state_of_issue}}          : State of issue (currently: "Missouri")
    - {{arrest_county}}           : County where arrested (currently: "Saint Genevieve County")
    - {{arrest_date}}             : Date of arrest (currently: "02/13/2023")
    - {{case_number}}             : Case number (currently: "Unknown")
    - {{hearing_type}}            : Type of hearing requested (e.g., "telephone hearing")

  Auto-Filled from Attorney Profile:
    - {{attorney_name}}           : Attorney name (currently: "John C. Schleiffarth")
    - {{attorney_bar}}            : Bar number (currently: "#63222")
    - {{co_attorney_name}}        : Co-counsel name (currently: "Andrew Morris")
    - {{co_attorney_bar}}         : Co-counsel bar number (currently: "#675047")
    - {{firm_address}}            : Firm address (currently: "5 West Lockwood Avenue, Suite 250")
    - {{firm_city_state_zip}}     : City, state, zip (currently: "Webster Groves, Missouri 63119")
    - {{attorney_phone}}          : Phone (currently: "(314) 561-9690")
    - {{attorney_fax}}            : Fax (currently: "(314) 596-0658")
    - {{attorney_email}}          : Email (currently: "john@jcsattorney.com")
    - {{co_attorney_email}}       : Co-counsel email (currently: "y@jcsattorney.com")

  Note: Different variants include attorney-specific contact info. Some have single attorney,
        some have multiple (e.g., "HLL" might have different co-counsel setup).

================================================================================
3. PETITION FOR TRIAL DE NOVO (TDN)
================================================================================

TEMPLATES IN GROUP (7 total):
  1. ID  323 | Ltr to DOR with TDN (different doc type - letter, not petition)
  2. ID 1563 | Petition for TDN (REPRESENTATIVE)
  3. ID 1485 | Petition for TDN - DCL
  4. ID 1489 | Petition for TDN Double Suspension
  5. ID 1564 | Petition for TDN - Franklin County
  6. ID 1565 | Petition for TDN - St. Louis County
  7. ID 1440 | Request for Alias Summons - Muni TDN (different doc type - alias summons)

NOTE: This group contains 3 different document types:
  1. "Petition for TDN" (3 templates: standard, DCL, Double Suspension)
  2. "Ltr to DOR with TDN" (1 template)
  3. "Request for Alias Summons - Muni TDN" (1 template)

Recommend consolidating into 2-3 DOCUMENT TYPES:
  1. Petition for Trial De Novo
  2. Letter to DOR with TDN (separate, already mostly covered)
  3. Request for Alias Summons (separate)

REPRESENTATIVE TEMPLATE CONTENT (Petition for TDN - ID 1563):
--------
IN THE CIRCUIT COURT OF *WHATEVER COUNTY* COUNTY
STATE OF MISSOURI

Name                    )
DL:                     )
SSN:                    )
                        )
Cause No.: case number

Petitioner,             )
                        )
      v.                )
                        )
DIRECTOR OF REVENUE,    )
                        )
Respondent.             )

PETITION FOR TRIAL DE NOVO OF LICENSE SUSPENSION/REVOCATION

COMES NOW Petitioner, NAME, by and through counsel, and states as follows:

1. Petitioner is a resident of the State of Missouri;

2. Petitioner was arrested in ENTER County on or about date of arrest;

3. On date of arrest, name of officer on the notice, a law enforcement officer with the 
   name of Police Department, served Petitioner with a Notice of Suspension or Revocation 
   of Driving Privilege notifying Petitioner, inter alia, that his driving privilege would 
   be suspended or revoked 15 days from the notice;

4. Pursuant to such Notice, Petitioner requested an administrative hearing before the 
   Department of Revenue;

5. An administrative review of such order was held pursuant to Section 302.530 RSMo., on 
   date of hearing, and the suspension/revocation was sustained on that date;

6. Petitioner's privilege to drive a motor vehicle will be suspended or revoked by Respondent, 
   pursuant to Sections 302.505 and 302.525, RSMo.;

7. Petitioner was not arrested upon probable cause to believe Petitioner was operating a 
   motor vehicle while intoxicated or while the alcohol concentration was .08% or more by 
   weight of alcohol in Petitioner's blood;

8. Based on the alcohol influence report on file with the Department of Revenue, Petitioner 
   does not believe that the blood that was drawn to prove Petitioner was operating a motor 
   vehicle while intoxicated or while the alcohol concentration was .08% or more by weight 
   of alcohol in Petitioner's blood was drawn in compliances with 19CSR25-30.070 and 
   RSMo. 577.029;

9. Petitioner is aggrieved by the decision and filed this petition for judicial review and 
   trial de novo pursuant to Section 302.535 RSMo.

WHEREFORE, Petitioner prays that this Court order that the ruling of Respondent be ordered 
set aside and held for naught and that Respondent be ordered to reinstate all privileges 
of Petitioner to operate a motor vehicle in the State of Missouri, and for such and further 
relief as this Court deems proper.

Respectfully submitted,

John C. Schleiffarth, P.C.

/s/John Schleiffarth
________________
John C. Schleiffarth #63222
120 S Central Avenue, Suite 1550
Clayton, Missouri 63105
Telephone: (314) 561-9690
Facsimile: (314) 596-0658
Email: john@jcsattorney.com

Attorney for Petitioner
--------

IDENTIFIED PLACEHOLDERS FOR CONSOLIDATION:
  Required Variables (asked from user):
    - {{county}}                  : County (currently: "*WHATEVER COUNTY*")
    - {{petitioner_name}}         : Petitioner name (currently: "NAME")
    - {{petitioner_dln}}          : Driver's License Number (currently: "DL: [blank]")
    - {{petitioner_ssn}}          : Social Security Number (currently: "SSN: [blank]")
    - {{case_number}}             : Cause number (currently: "case number")
    - {{arrest_county}}           : County where arrested (currently: "ENTER County")
    - {{arrest_date}}             : Date of arrest (currently: "date of arrest")
    - {{officer_name}}            : Name of officer (currently: "name of officer on the notice")
    - {{police_department}}       : Police department (currently: "name of Police Department")
    - {{hearing_date}}            : Date of hearing (currently: "date of hearing")
    - {{suspension_type}}         : Suspension or Revocation (default: "suspended or revoked")

  Auto-Filled from Attorney Profile:
    - {{attorney_name}}           : Attorney name (currently: "John C. Schleiffarth")
    - {{attorney_bar}}            : Bar number (currently: "#63222")
    - {{firm_address}}            : Firm address (currently: "120 S Central Avenue, Suite 1550")
    - {{firm_city_state_zip}}     : City, state, zip (currently: "Clayton, Missouri 63105")
    - {{attorney_phone}}          : Phone (currently: "(314) 561-9690")
    - {{attorney_fax}}            : Fax (currently: "(314) 596-0658")
    - {{attorney_email}}          : Email (currently: "john@jcsattorney.com")

  Note: Court caption format is "IN THE CIRCUIT COURT OF {{COUNTY}} COUNTY, STATE OF MISSOURI"
        {{COUNTY}} should be uppercase for court caption.

================================================================================
CONSOLIDATION RECOMMENDATIONS
================================================================================

1. ADMIN CONTINUANCE REQUEST
   Consolidate 10 variants into 1 template: Admin_Continuance_Request.docx
   - Replace {{placeholder}} for: petitioner_name, docket_number, case_number, dln, 
     hearing_date, continuance_reason
   - Auto-fill attorney block (name, bar, address, phone, fax, email)

2. ADMIN HEARING REQUESTS
   Create 5 separate document types (not 1 consolidation):
   
   a) Admin_Hearing_Request.docx (5 variants: base, DCC, DCL, HL, PH)
      - Replace {{placeholder}} for: petitioner_name, dob, dln, state_of_issue, 
        arrest_county, arrest_date, case_number, hearing_type
      - Auto-fill attorney block + co-counsel if applicable
   
   b) Admin_Hearing_Submit_on_Record_Request.docx (5 variants)
      - Similar variables, used for "on the record" submissions
   
   c) Admin_Hearing_Withdraw_Request.docx (2 variants)
      - Variables for withdrawing a previous request
   
   d) Admin_Hearing_Entry_on_Already_Requested.docx (1 variant)
      - Entry of appearance on existing hearing request
   
   e) Admin_Hearing_EOA.docx (1 variant)
      - Entry of Appearance format for admin hearings

3. PETITION FOR TRIAL DE NOVO
   Consolidate 3 variants into 1 template: Petition_for_TDN.docx
   - Replace {{placeholder}} for: county (UPPERCASE), petitioner_name, petitioner_dln, 
     petitioner_ssn, case_number, arrest_county, arrest_date, officer_name, 
     police_department, hearing_date, suspension_type
   - Auto-fill attorney block (name, bar, address, phone, fax, email)

   Note: Keep separate for now:
   - ID 323 "Ltr to DOR with TDN" (already a letter format, different structure)
   - ID 1440 "Request for Alias Summons - Muni TDN" (different document type)

================================================================================
ESTIMATED IMPACT
================================================================================

Admin Continuance Request:  10 variants → 1 consolidated template (saves 9 db rows)
Admin Hearing (group):     20 variants → 5 consolidated templates (saves 15 db rows)
Petition for TDN:           3 variants → 1 consolidated template (saves 2 db rows)

Total: 33 templates consolidated into ~7 document types
       Saves ~26 database rows (66 IDs deactivated in deactivate_patterns)
       Reduces clutter from per-county/per-attorney duplicates

================================================================================
