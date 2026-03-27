================================================================================
DETAILED TEMPLATE INVENTORY
================================================================================

GROUP 1: ADMIN CONTINUANCE REQUEST (10 Templates → 1 Consolidation)
────────────────────────────────────────────────────────────────────────────
ID    Name                                    Status      Size    Action
────────────────────────────────────────────────────────────────────────────
1425  Admin Continuance Request               ACTIVE      37 KB   KEEP
1473  Admin Continuance Request - ATM         ACTIVE      38 KB   DEACTIVATE
1472  Admin Continuance Request - DCC         ACTIVE      38 KB   DEACTIVATE
1471  Admin Continuance Request - DCL         ACTIVE      38 KB   DEACTIVATE
1469  Admin Continuance Request - DRT         ACTIVE      38 KB   DEACTIVATE
1474  Admin Continuance Request - HL          ACTIVE     102 KB   DEACTIVATE
1426  Admin Continuance Request - HLL         ACTIVE     266 KB   DEACTIVATE
1428  Admin Continuance Request - HPH         ACTIVE      38 KB   DEACTIVATE
1429  Admin Continuance Request - In Person   ACTIVE     267 KB   DEACTIVATE
1427  Admin Continuance Request - JCS         ACTIVE     270 KB   DEACTIVATE
────────────────────────────────────────────────────────────────────────────
Group Size: ~1.2 MB across 10 files
Consolidated Size: ~14 KB in 1 file
Projected Savings: ~1.18 MB, ~90% reduction
DB Rows Saved: 9


GROUP 2: ADMIN HEARING (20 Templates → 5 Consolidations)
────────────────────────────────────────────────────────────────────────────

SUB-GROUP 2A: Admin Hearing Request (9 Templates → 1 Consolidation)
────────────────────────────────────────────────────────────────────────────
ID    Name                                    Status      Size    Action
────────────────────────────────────────────────────────────────────────────
1673  Admin Hearing Request                   ACTIVE     341 KB   KEEP
1667  Admin Hearing Request - DCC             ACTIVE      38 KB   DEACTIVATE
1670  Admin Hearing Request - DCL             ACTIVE      38 KB   DEACTIVATE
1541  Admin Hearing Request - Established     ACTIVE      39 KB   DEACTIVATE
1539  Admin Hearing Request - HL              ACTIVE     103 KB   DEACTIVATE
1542  Admin Hearing Request - HLL             ACTIVE     493 KB   DEACTIVATE
1538  Admin Hearing Request - JCS             ACTIVE      38 KB   DEACTIVATE
1665  Admin Hearing Request - Out of State    ACTIVE      37 KB   DEACTIVATE
1540  Admin Hearing Request - PH              ACTIVE     103 KB   DEACTIVATE

SUB-GROUP 2B: Admin Hearing Submit on Record (5 Templates → 1 Consolidation)
────────────────────────────────────────────────────────────────────────────
ID    Name                                    Status      Size    Action
────────────────────────────────────────────────────────────────────────────
1666  Admin Hearing Submit on the Record      ACTIVE     116 KB   KEEP
1672  Admin Hearing Submit on Record - ATM    ACTIVE     105 KB   DEACTIVATE
1669  Admin Hearing Submit on Record - DCC    ACTIVE     105 KB   DEACTIVATE
1456  Admin Hearing Submit on Record - HL     ACTIVE     104 KB   DEACTIVATE
1671  Admin Hearing Submit on Record Spec     ACTIVE     104 KB   DEACTIVATE

SUB-GROUP 2C: Admin Hearing Withdraw Request (2 Templates → 1 Consolidation)
────────────────────────────────────────────────────────────────────────────
ID    Name                                    Status      Size    Action
────────────────────────────────────────────────────────────────────────────
1668  Admin Hearing Withdraw Request          ACTIVE      99 KB   KEEP
1458  Admin Hearing Withdraw Request - DCL    ACTIVE      38 KB   DEACTIVATE

SUB-GROUP 2D: Admin Hearing Entry (1 Template - Keep as-is)
────────────────────────────────────────────────────────────────────────────
ID    Name                                    Status      Size    Action
────────────────────────────────────────────────────────────────────────────
1455  Admin Hearing Entry on Already Req      ACTIVE     341 KB   KEEP

SUB-GROUP 2E: Admin Hearing EOA (1 Template - Keep as-is)
────────────────────────────────────────────────────────────────────────────
ID    Name                                    Status      Size    Action
────────────────────────────────────────────────────────────────────────────
1457  Admin Hearing EOA                       ACTIVE     270 KB   KEEP

OTHER (Not consolidated - different document types):
────────────────────────────────────────────────────────────────────────────
ID    Name                                    Status      Size    Action
────────────────────────────────────────────────────────────────────────────
 234  90 Day Letter with No Priors            ACTIVE     179 KB   KEEP
 349  DWI - Admin Hearing New Client Check    ACTIVE      15 KB   KEEP
────────────────────────────────────────────────────────────────────────────
Group Size: ~3.2 MB across 20 files
Consolidated Size: ~307 KB in 5 files
Projected Savings: ~2.9 MB, ~90% reduction
DB Rows Saved: 13


GROUP 3: PETITION FOR TRIAL DE NOVO (7 Templates)
────────────────────────────────────────────────────────────────────────────

SUB-GROUP 3A: Petition for TDN (4 Templates → 1 Consolidation)
────────────────────────────────────────────────────────────────────────────
ID    Name                                    Status      Size    Action
────────────────────────────────────────────────────────────────────────────
1563  Petition for TDN                        ACTIVE      34 KB   KEEP
1485  Petition for TDN - DCL                  ACTIVE      34 KB   DEACTIVATE
1489  Petition for TDN Double Suspension      ACTIVE      49 KB   DEACTIVATE
1564  Petition for TDN - Franklin County      ACTIVE      33 KB   DEACTIVATE
1565  Petition for TDN - St. Louis County     ACTIVE      32 KB   DEACTIVATE

OTHER (Different document types - Keep separate):
────────────────────────────────────────────────────────────────────────────
ID    Name                                    Status      Size    Action
────────────────────────────────────────────────────────────────────────────
 323  Ltr to DOR with TDN                     ACTIVE      15 KB   KEEP
1440  Request for Alias Summons - Muni TDN   ACTIVE      37 KB   KEEP
────────────────────────────────────────────────────────────────────────────
Group Size: ~450 KB across 7 files
Consolidated Size: ~8 KB in 1 file
Projected Savings: ~180 KB (but keeping separate letter/summons)
DB Rows Saved: 4


================================================================================
MASTER DEACTIVATION LIST
================================================================================

Total Templates to Deactivate: 26

Admin Continuance Request Variants: 9
  1473, 1472, 1471, 1469, 1474, 1426, 1428, 1429, 1427

Admin Hearing Request Variants: 8
  1667, 1670, 1541, 1539, 1542, 1538, 1665, 1540

Admin Hearing Submit on Record Variants: 4
  1672, 1669, 1456, 1671

Admin Hearing Withdraw Variants: 1
  1458

Petition for TDN Variants: 4
  1485, 1489, 1564, 1565


================================================================================
CANONICAL TEMPLATES TO KEEP
================================================================================

Keep (7 total):
  1425 - Admin Continuance Request
  1673 - Admin Hearing Request
  1666 - Admin Hearing Submit on the Record Request
  1668 - Admin Hearing Withdraw Request
  1455 - Admin Hearing Entry on Already Requested Hearing
  1457 - Admin Hearing EOA
  1563 - Petition for TDN

Keep separate (6 total - different doc types):
   234 - 90 Day Letter with No Priors - No Admin Hearing
   349 - DWI - Admin Hearing New Client Checklist
   323 - Ltr to DOR with TDN
  1440 - Request for Alias Summons - Muni TDN


================================================================================
CONVERSION RESULTS
================================================================================

Successfully Converted (3 Representative Templates):

1. Admin_Continuance_Request
   Source: ID 1425
   Original: .doc (OLE) 37 KB
   Converted: .docx 14 KB
   Status: ✓ Ready for consolidation
   Content: Letter requesting administrative hearing continuance

2. Admin_Hearing_Request
   Source: ID 1673
   Original: .doc (OLE) 334 KB
   Converted: .docx 307 KB (contains embedded images)
   Status: ✓ Converted (may need image optimization)
   Content: Letter requesting administrative hearing

3. Petition_for_TDN
   Source: ID 1563
   Original: .doc (OLE) 34 KB
   Converted: .docx 8 KB
   Status: ✓ Ready for consolidation
   Content: Petition for Trial De Novo - DOR license suspension

Total Conversion Time: ~10 seconds (headless LibreOffice)
Conversion Success Rate: 3/3 (100%)


================================================================================
STATISTICS SUMMARY
================================================================================

Templates Analyzed:              37 active .doc files
Templates to Consolidate:        33 (89%)
Templates to Keep Separate:      4 (11%)

Database Impact:
  Current Active Templates:      37
  After Consolidation:           13 (7 consolidated + 6 separate)
  Rows to Deactivate:           26
  Space Saved:                  ~90% in file content

Placeholders Identified:
  Required (user input):         15 unique variables
  Auto-filled (profile):         10 unique variables
  Total:                        25 unique placeholder positions


================================================================================

