# OLE Template Deactivation Map

For batch consolidation of .doc (OLE) format templates into .docx equivalents.

## Admin Continuance Request (10 templates → 1)

Consolidated into: `Admin_Continuance_Request.docx`

Templates to DEACTIVATE (keep ID 1425 as canonical):
```
1425 Admin Continuance Request                    (KEEP - canonical)
1473 Admin Continuance Request - ATM              (deactivate)
1472 Admin Continuance Request - DCC              (deactivate)
1471 Admin Continuance Request - DCL              (deactivate)
1469 Admin Continuance Request - DRT              (deactivate)
1474 Admin Continuance Request - HL               (deactivate)
1426 Admin Continuance Request - HLL              (deactivate)
1428 Admin Continuance Request - HPH              (deactivate)
1429 Admin Continuance Request - In Person        (deactivate)
1427 Admin Continuance Request - JCS              (deactivate)
```

Deactivate patterns:
```python
'Admin Continuance Request - ATM'
'Admin Continuance Request - DCC'
'Admin Continuance Request - DCL'
'Admin Continuance Request - DRT'
'Admin Continuance Request - HL'
'Admin Continuance Request - HLL'
'Admin Continuance Request - HPH'
'Admin Continuance Request - In Person'
'Admin Continuance Request - JCS'
```

## Admin Hearing Requests (20 templates → 5 document types)

### Type 1: Admin Hearing Request (5 templates → 1)
Consolidated into: `Admin_Hearing_Request.docx`

Keep ID 1673 as canonical:
```
1673 Admin Hearing Request                       (KEEP - canonical)
1667 Admin Hearing Request - DCC                 (deactivate)
1670 Admin Hearing Request - DCL                 (deactivate)
1539 Admin Hearing Request - HL                  (deactivate)
1540 Admin Hearing Request - PH                  (deactivate)
```

Also deactivate (mixed into group, different variants):
```
1541 Admin Hearing Request - Established Hearing (deactivate)
1542 Admin Hearing Request - HLL                 (deactivate)
1538 Admin Hearing Request - JCS                 (deactivate)
1665 Admin Hearing Request - Out of State DL     (deactivate)
```

### Type 2: Admin Hearing Submit on the Record Request (5 templates → 1)
Consolidated into: `Admin_Hearing_Submit_on_Record_Request.docx`

Keep ID 1666 as canonical:
```
1666 Admin Hearing Submit on the Record Request                    (KEEP - canonical)
1672 Admin Hearing Submit on the Record Request - ATM              (deactivate)
1669 Admin Hearing Submit on the Record Request - DCC              (deactivate)
1456 Admin Hearing Submit on the Record Request - HL               (deactivate)
1671 Admin Hearing Submit on the Record Request Specific Issue-ATM (deactivate)
```

### Type 3: Admin Hearing Withdraw Request (2 templates → 1)
Consolidated into: `Admin_Hearing_Withdraw_Request.docx`

Keep ID 1668 as canonical:
```
1668 Admin Hearing Withdraw Request              (KEEP - canonical)
1458 Admin Hearing Withdraw Request - DCL        (deactivate)
```

### Type 4: Admin Hearing Entry on Already Requested Hearing (1 template - keep as-is)
```
1455 Admin Hearing Entry on Already Requested Hearing (KEEP)
```

### Type 5: Admin Hearing EOA (1 template - keep as-is)
```
1457 Admin Hearing EOA (KEEP)
```

### NOT included in consolidation (different doc types):
```
 234 90 Day Letter with No Priors - No Admin Hearing (different document, keep)
 349 DWI - Admin Hearing New Client Checklist        (checklist, different, keep)
```

## Petition for Trial De Novo (7 templates → 1)

Consolidated into: `Petition_for_TDN.docx`

Keep ID 1563 as canonical:
```
1563 Petition for TDN                           (KEEP - canonical)
1485 Petition for TDN - DCL                     (deactivate)
1489 Petition for TDN Double Suspension         (deactivate)
1564 Petition for TDN - Franklin County         (deactivate)
1565 Petition for TDN - St. Louis County        (deactivate)
```

NOT included in consolidation (different doc types):
```
 323 Ltr to DOR with TDN                        (letter format, different structure - keep separate)
1440 Request for Alias Summons - Muni TDN      (summons format, different structure - keep separate)
```

## Summary

Total templates to deactivate: 26
Total canonical templates to keep: 7
Total to create new: 3

New consolidated templates to create:
1. Admin_Continuance_Request.docx
2. Admin_Hearing_Request.docx
3. Admin_Hearing_Submit_on_Record_Request.docx
4. Admin_Hearing_Withdraw_Request.docx
5. Petition_for_TDN.docx

Templates to keep as-is (no consolidation):
6. Admin_Hearing_Entry_on_Already_Requested_Hearing.docx (ID 1455)
7. Admin_Hearing_EOA.docx (ID 1457)
8. 90 Day Letter with No Priors - No Admin Hearing.docx (ID 234)
9. DWI - Admin Hearing New Client Checklist.docx (ID 349)
10. Ltr to DOR with TDN.docx (ID 323)
11. Request for Alias Summons - Muni TDN.docx (ID 1440)

SQL to deactivate (SAFE - only marks is_active=FALSE, doesn't delete):
```sql
UPDATE templates SET is_active = FALSE WHERE id IN (
  1473, 1472, 1471, 1469, 1474, 1426, 1428, 1429, 1427,
  1667, 1670, 1541, 1542, 1538, 1665, 1539, 1540,
  1672, 1669, 1456, 1671,
  1458,
  1485, 1489, 1564, 1565
) AND firm_id = 'jcs_law';
```

