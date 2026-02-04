# Recommended Template Folder Structure

## Overview

This document defines the standard folder structure for law firm document templates. The structure accommodates all major practice areas and firm types.

---

## Firm Type Templates

Different firm types will use different subsets of this structure:

| Firm Type | Primary Folders |
|-----------|-----------------|
| Criminal Defense | Criminal, Traffic, DWI, DOR |
| Personal Injury | Personal_Injury, Civil, Medical |
| Workers Compensation | Workers_Comp, Administrative |
| Family Law | Family, Juvenile |
| Estate Planning | Estate, Probate, Trust |
| Business/Corporate | Business, Corporate, Contracts |
| Immigration | Immigration, Administrative |
| Bankruptcy | Bankruptcy, Collections |
| Real Estate | Real_Estate, Contracts |
| General Practice | Multiple areas |

---

## Complete Folder Hierarchy

```
Templates/
│
├── ══════════════════════════════════════════════════════════════
│   LITIGATION - PLAINTIFF SIDE
│   ══════════════════════════════════════════════════════════════
│
├── Personal_Injury/
│   ├── Intake/
│   │   ├── Client_Intake_Form.docx
│   │   ├── Medical_Authorization_HIPAA.docx
│   │   ├── Contingency_Fee_Agreement.docx
│   │   └── Client_Questionnaire.docx
│   ├── Demand/
│   │   ├── Demand_Letter_Auto_Accident.docx
│   │   ├── Demand_Letter_Slip_Fall.docx
│   │   ├── Demand_Letter_Medical_Malpractice.docx
│   │   ├── Demand_Letter_Product_Liability.docx
│   │   └── Settlement_Demand_Package.docx
│   ├── Pleadings/
│   │   ├── Petition_Negligence.docx
│   │   ├── Petition_Auto_Accident.docx
│   │   ├── Petition_Premises_Liability.docx
│   │   ├── Petition_Medical_Malpractice.docx
│   │   ├── Petition_Wrongful_Death.docx
│   │   └── Petition_Product_Liability.docx
│   ├── Motions/
│   │   ├── Motion_to_Compel_Discovery.docx
│   │   ├── Motion_to_Compel_IME.docx
│   │   ├── Motion_for_Sanctions.docx
│   │   ├── Motion_in_Limine.docx
│   │   └── Motion_for_Summary_Judgment.docx
│   ├── Discovery/
│   │   ├── Interrogatories_Auto_Accident.docx
│   │   ├── Interrogatories_Premises_Liability.docx
│   │   ├── Request_for_Production_Medical.docx
│   │   ├── Request_for_Production_Employment.docx
│   │   ├── Request_for_Admissions.docx
│   │   ├── Subpoena_Medical_Records.docx
│   │   └── Deposition_Notice.docx
│   ├── Settlement/
│   │   ├── Settlement_Agreement.docx
│   │   ├── Release_Full.docx
│   │   ├── Release_Partial.docx
│   │   ├── Settlement_Statement.docx
│   │   └── Medicare_Set_Aside.docx
│   └── Letters/
│       ├── Letter_of_Representation.docx
│       ├── Medical_Records_Request.docx
│       ├── Lien_Letter.docx
│       ├── Status_Update_Client.docx
│       └── Lien_Reduction_Request.docx
│
├── Workers_Comp/
│   ├── Intake/
│   │   ├── Client_Intake_Form.docx
│   │   ├── Medical_Authorization.docx
│   │   └── Fee_Agreement.docx
│   ├── Claims/
│   │   ├── Claim_for_Compensation.docx
│   │   ├── Application_for_Review.docx
│   │   ├── Hardship_Application.docx
│   │   └── Request_for_Hearing.docx
│   ├── Motions/
│   │   ├── Motion_to_Compel_Medical_Treatment.docx
│   │   ├── Motion_for_Temporary_Total_Disability.docx
│   │   ├── Motion_for_Permanent_Disability.docx
│   │   └── Motion_to_Reopen_Claim.docx
│   ├── Discovery/
│   │   ├── Interrogatories_Employer.docx
│   │   ├── Request_for_Production.docx
│   │   └── Deposition_Notice.docx
│   ├── Settlement/
│   │   ├── Compromise_Settlement.docx
│   │   ├── Stipulation_for_Settlement.docx
│   │   └── Lump_Sum_Agreement.docx
│   └── Letters/
│       ├── Letter_to_Employer.docx
│       ├── Letter_to_Insurance_Carrier.docx
│       ├── Medical_Provider_Letter.docx
│       └── Status_Update_Client.docx
│
├── Medical_Malpractice/
│   ├── Intake/
│   │   ├── Medical_Malpractice_Intake.docx
│   │   ├── Expert_Affidavit_Request.docx
│   │   └── HIPAA_Authorization.docx
│   ├── Pleadings/
│   │   ├── Petition_Medical_Malpractice.docx
│   │   ├── Affidavit_of_Merit.docx
│   │   └── Expert_Designation.docx
│   └── Discovery/
│       ├── Interrogatories_Medical_Provider.docx
│       ├── Request_for_Medical_Records.docx
│       └── Expert_Deposition_Notice.docx
│
├── ══════════════════════════════════════════════════════════════
│   LITIGATION - DEFENSE SIDE
│   ══════════════════════════════════════════════════════════════
│
├── Criminal/
│   ├── Motions/
│   │   ├── Motion_to_Dismiss_General.docx
│   │   ├── Motion_to_Dismiss_SOL.docx
│   │   ├── Motion_to_Dismiss_Failure_to_Prosecute.docx
│   │   ├── Motion_to_Dismiss_Speedy_Trial.docx
│   │   ├── Motion_to_Suppress_Search.docx
│   │   ├── Motion_to_Suppress_Statements.docx
│   │   ├── Motion_to_Suppress_Identification.docx
│   │   ├── Motion_to_Continue.docx
│   │   ├── Motion_for_Discovery.docx
│   │   ├── Motion_for_Bill_of_Particulars.docx
│   │   ├── Motion_to_Sever.docx
│   │   └── Motion_for_Change_of_Venue.docx
│   ├── Pleadings/
│   │   ├── Entry_of_Appearance.docx
│   │   ├── Waiver_of_Arraignment.docx
│   │   ├── Request_for_Jury_Trial.docx
│   │   ├── Waiver_of_Jury_Trial.docx
│   │   ├── Plea_Agreement.docx
│   │   └── Notice_of_Alibi.docx
│   ├── Letters/
│   │   ├── Preservation_Letter_Police.docx
│   │   ├── Preservation_Letter_MSHP.docx
│   │   ├── Client_Engagement.docx
│   │   ├── Disposition_Letter.docx
│   │   └── Probation_Letter.docx
│   ├── Discovery/
│   │   ├── Request_for_Discovery.docx
│   │   ├── Response_to_Discovery.docx
│   │   ├── Brady_Request.docx
│   │   └── Subpoena_Duces_Tecum.docx
│   └── Sentencing/
│       ├── Sentencing_Memorandum.docx
│       ├── Motion_for_Probation.docx
│       └── Character_Reference_Request.docx
│
├── Traffic/
│   ├── Motions/
│   │   ├── Motion_to_Dismiss_General.docx
│   │   ├── Motion_to_Dismiss_SOL.docx
│   │   └── Motion_to_Continue.docx
│   ├── Pleadings/
│   │   ├── Entry_of_Appearance.docx
│   │   ├── Waiver_of_Arraignment.docx
│   │   └── Request_for_Jury_Trial.docx
│   └── Letters/
│       ├── Client_Engagement.docx
│       └── Disposition_Letter.docx
│
├── DWI/
│   ├── Motions/
│   │   ├── Motion_to_Suppress_Stop.docx
│   │   ├── Motion_to_Suppress_FST.docx
│   │   ├── Motion_to_Suppress_Breathalyzer.docx
│   │   ├── Motion_to_Suppress_Blood_Draw.docx
│   │   ├── Motion_to_Dismiss_General.docx
│   │   └── Motion_to_Continue.docx
│   ├── Pleadings/
│   │   ├── Entry_of_Appearance.docx
│   │   ├── Waiver_of_Arraignment.docx
│   │   └── Request_for_Jury_Trial.docx
│   ├── Discovery/
│   │   ├── Request_for_Discovery_DWI.docx
│   │   ├── Breathalyzer_Maintenance_Request.docx
│   │   └── Officer_Training_Records_Request.docx
│   └── Letters/
│       ├── Preservation_Letter_BAC.docx
│       └── DMV_Hearing_Request.docx
│
├── DOR/
│   ├── Motions/
│   │   ├── Motion_to_Dismiss_General.docx
│   │   ├── Motion_to_Stay.docx
│   │   └── Motion_for_Limited_Driving_Privilege.docx
│   ├── Pleadings/
│   │   ├── Petition_for_Review.docx
│   │   ├── Entry_of_Appearance.docx
│   │   └── Request_for_Hearing.docx
│   └── Letters/
│       ├── Hearing_Request.docx
│       └── Client_Update.docx
│
├── Civil_Defense/
│   ├── Motions/
│   │   ├── Motion_to_Dismiss_Failure_to_State_Claim.docx
│   │   ├── Motion_to_Dismiss_Lack_Jurisdiction.docx
│   │   ├── Motion_to_Dismiss_Improper_Venue.docx
│   │   ├── Motion_to_Dismiss_Improper_Service.docx
│   │   ├── Motion_to_Dismiss_SOL.docx
│   │   ├── Motion_for_Summary_Judgment.docx
│   │   ├── Motion_for_More_Definite_Statement.docx
│   │   └── Motion_to_Strike.docx
│   ├── Pleadings/
│   │   ├── Answer_General_Denial.docx
│   │   ├── Answer_with_Affirmative_Defenses.docx
│   │   ├── Answer_with_Counterclaim.docx
│   │   ├── Third_Party_Petition.docx
│   │   └── Entry_of_Appearance.docx
│   ├── Discovery/
│   │   ├── Interrogatories_Plaintiff.docx
│   │   ├── Request_for_Production.docx
│   │   ├── Request_for_Admissions.docx
│   │   └── Deposition_Notice.docx
│   └── Letters/
│       ├── Litigation_Hold_Notice.docx
│       └── Meet_and_Confer_Letter.docx
│
├── ══════════════════════════════════════════════════════════════
│   FAMILY LAW
│   ══════════════════════════════════════════════════════════════
│
├── Family/
│   ├── Dissolution/
│   │   ├── Petition_for_Dissolution.docx
│   │   ├── Petition_for_Dissolution_with_Children.docx
│   │   ├── Response_to_Dissolution.docx
│   │   ├── Separation_Agreement.docx
│   │   ├── Parenting_Plan.docx
│   │   └── Child_Support_Worksheet.docx
│   ├── Custody/
│   │   ├── Petition_for_Custody.docx
│   │   ├── Motion_to_Modify_Custody.docx
│   │   ├── Motion_for_Temporary_Custody.docx
│   │   └── Guardian_ad_Litem_Motion.docx
│   ├── Support/
│   │   ├── Motion_to_Modify_Child_Support.docx
│   │   ├── Motion_for_Contempt_Support.docx
│   │   ├── Income_and_Expense_Statement.docx
│   │   └── Motion_to_Terminate_Maintenance.docx
│   ├── Protection/
│   │   ├── Petition_for_Order_of_Protection.docx
│   │   ├── Motion_to_Modify_Protection_Order.docx
│   │   └── Motion_to_Dissolve_Protection_Order.docx
│   ├── Motions/
│   │   ├── Motion_to_Compel_Discovery.docx
│   │   ├── Motion_for_Contempt.docx
│   │   ├── Motion_for_Attorney_Fees.docx
│   │   └── Motion_for_Temporary_Orders.docx
│   └── Letters/
│       ├── Client_Engagement_Family.docx
│       └── Opposing_Counsel_Letter.docx
│
├── Juvenile/
│   ├── Delinquency/
│   │   ├── Entry_of_Appearance_Juvenile.docx
│   │   ├── Motion_to_Dismiss.docx
│   │   └── Motion_to_Transfer_to_Adult_Court.docx
│   ├── Dependency/
│   │   ├── Motion_for_Visitation.docx
│   │   └── Motion_to_Reunify.docx
│   └── Adoption/
│       ├── Petition_for_Adoption.docx
│       ├── Consent_to_Adoption.docx
│       └── Termination_of_Parental_Rights.docx
│
├── ══════════════════════════════════════════════════════════════
│   ESTATE & PROBATE
│   ══════════════════════════════════════════════════════════════
│
├── Estate/
│   ├── Wills/
│   │   ├── Simple_Will.docx
│   │   ├── Will_with_Trust.docx
│   │   ├── Pour_Over_Will.docx
│   │   └── Codicil.docx
│   ├── Trusts/
│   │   ├── Revocable_Living_Trust.docx
│   │   ├── Irrevocable_Trust.docx
│   │   ├── Special_Needs_Trust.docx
│   │   └── Trust_Amendment.docx
│   ├── Powers/
│   │   ├── Durable_Power_of_Attorney.docx
│   │   ├── Healthcare_Power_of_Attorney.docx
│   │   ├── Limited_Power_of_Attorney.docx
│   │   └── HIPAA_Authorization.docx
│   ├── Directives/
│   │   ├── Living_Will.docx
│   │   ├── Advance_Healthcare_Directive.docx
│   │   └── DNR_Declaration.docx
│   └── Letters/
│       ├── Estate_Planning_Engagement.docx
│       └── Trust_Funding_Instructions.docx
│
├── Probate/
│   ├── Administration/
│   │   ├── Petition_for_Letters.docx
│   │   ├── Letters_Testamentary.docx
│   │   ├── Letters_of_Administration.docx
│   │   ├── Inventory.docx
│   │   ├── Annual_Settlement.docx
│   │   └── Final_Settlement.docx
│   ├── Motions/
│   │   ├── Motion_for_Family_Allowance.docx
│   │   ├── Motion_to_Sell_Property.docx
│   │   └── Motion_for_Discharge.docx
│   ├── Notices/
│   │   ├── Notice_to_Creditors.docx
│   │   ├── Notice_to_Heirs.docx
│   │   └── Notice_of_Hearing.docx
│   └── Small_Estate/
│       ├── Small_Estate_Affidavit.docx
│       └── Refusal_of_Letters.docx
│
├── ══════════════════════════════════════════════════════════════
│   BUSINESS & CORPORATE
│   ══════════════════════════════════════════════════════════════
│
├── Business/
│   ├── Formation/
│   │   ├── Articles_of_Organization_LLC.docx
│   │   ├── Operating_Agreement_Single_Member.docx
│   │   ├── Operating_Agreement_Multi_Member.docx
│   │   ├── Articles_of_Incorporation.docx
│   │   ├── Bylaws.docx
│   │   ├── Partnership_Agreement.docx
│   │   └── Shareholder_Agreement.docx
│   ├── Contracts/
│   │   ├── Service_Agreement.docx
│   │   ├── Employment_Agreement.docx
│   │   ├── Independent_Contractor_Agreement.docx
│   │   ├── Non_Disclosure_Agreement.docx
│   │   ├── Non_Compete_Agreement.docx
│   │   ├── Purchase_Agreement.docx
│   │   └── Lease_Agreement_Commercial.docx
│   ├── Corporate/
│   │   ├── Board_Resolution.docx
│   │   ├── Shareholder_Resolution.docx
│   │   ├── Meeting_Minutes.docx
│   │   ├── Stock_Certificate.docx
│   │   └── Stock_Transfer_Agreement.docx
│   └── Letters/
│       ├── Demand_Letter_Contract.docx
│       ├── Cease_and_Desist.docx
│       └── Opinion_Letter.docx
│
├── Real_Estate/
│   ├── Residential/
│   │   ├── Purchase_Agreement_Residential.docx
│   │   ├── Lease_Agreement_Residential.docx
│   │   ├── Deed_Warranty.docx
│   │   ├── Deed_Quitclaim.docx
│   │   └── Deed_of_Trust.docx
│   ├── Commercial/
│   │   ├── Purchase_Agreement_Commercial.docx
│   │   ├── Lease_Agreement_Commercial.docx
│   │   └── Letter_of_Intent.docx
│   ├── Closing/
│   │   ├── Closing_Statement.docx
│   │   ├── Title_Opinion.docx
│   │   └── Affidavit_of_Title.docx
│   └── Disputes/
│       ├── Notice_to_Quit.docx
│       ├── Eviction_Petition.docx
│       └── Quiet_Title_Petition.docx
│
├── ══════════════════════════════════════════════════════════════
│   BANKRUPTCY & COLLECTIONS
│   ══════════════════════════════════════════════════════════════
│
├── Bankruptcy/
│   ├── Chapter_7/
│   │   ├── Petition_Chapter_7.docx
│   │   ├── Statement_of_Financial_Affairs.docx
│   │   ├── Schedules.docx
│   │   └── Means_Test.docx
│   ├── Chapter_13/
│   │   ├── Petition_Chapter_13.docx
│   │   ├── Chapter_13_Plan.docx
│   │   └── Motion_to_Modify_Plan.docx
│   ├── Motions/
│   │   ├── Motion_for_Relief_from_Stay.docx
│   │   ├── Motion_to_Avoid_Lien.docx
│   │   └── Motion_to_Reopen_Case.docx
│   └── Letters/
│       ├── Client_Engagement_Bankruptcy.docx
│       └── Creditor_Notice.docx
│
├── Collections/
│   ├── Demand_Letters/
│   │   ├── First_Notice_15_Days.docx
│   │   ├── Second_Notice_30_Days.docx
│   │   ├── Final_Notice_60_Days.docx
│   │   └── Pre_Litigation_Notice.docx
│   ├── Pleadings/
│   │   ├── Petition_on_Account.docx
│   │   ├── Petition_on_Note.docx
│   │   ├── Motion_for_Default_Judgment.docx
│   │   └── Garnishment.docx
│   ├── Post_Judgment/
│   │   ├── Execution.docx
│   │   ├── Interrogatories_in_Aid.docx
│   │   └── Judgment_Lien.docx
│   └── Letters/
│       └── Payment_Plan_Agreement.docx
│
├── ══════════════════════════════════════════════════════════════
│   IMMIGRATION
│   ══════════════════════════════════════════════════════════════
│
├── Immigration/
│   ├── Family_Based/
│   │   ├── I_130_Petition.docx
│   │   ├── I_485_Adjustment.docx
│   │   ├── I_864_Affidavit_of_Support.docx
│   │   └── Cover_Letter_Family.docx
│   ├── Employment/
│   │   ├── H1B_Petition.docx
│   │   ├── PERM_Application.docx
│   │   ├── I_140_Petition.docx
│   │   └── Cover_Letter_Employment.docx
│   ├── Naturalization/
│   │   ├── N_400_Application.docx
│   │   └── Cover_Letter_Naturalization.docx
│   ├── Removal_Defense/
│   │   ├── Motion_to_Reopen.docx
│   │   ├── Cancellation_of_Removal.docx
│   │   └── Asylum_Application.docx
│   └── Letters/
│       ├── RFE_Response.docx
│       └── Client_Engagement_Immigration.docx
│
├── ══════════════════════════════════════════════════════════════
│   ADMINISTRATIVE
│   ══════════════════════════════════════════════════════════════
│
├── Administrative/
│   ├── Social_Security/
│   │   ├── Request_for_Hearing.docx
│   │   ├── Brief_on_the_Merits.docx
│   │   └── Appeals_Council_Review.docx
│   ├── Unemployment/
│   │   ├── Appeal_Letter.docx
│   │   └── Hearing_Brief.docx
│   └── Licensing/
│       ├── License_Defense_Letter.docx
│       └── Hearing_Request.docx
│
├── ══════════════════════════════════════════════════════════════
│   SHARED / COMMON
│   ══════════════════════════════════════════════════════════════
│
├── _Jurisdiction_Specific/
│   ├── Missouri/
│   │   ├── Jefferson_County/
│   │   ├── St_Louis_County/
│   │   ├── St_Louis_City/
│   │   ├── Jackson_County/
│   │   └── Municipal/
│   ├── Illinois/
│   │   ├── St_Clair_County/
│   │   └── Madison_County/
│   └── Federal/
│       ├── Eastern_District_MO/
│       └── Western_District_MO/
│
└── _Common/
    ├── Service/
    │   ├── Certificate_of_Service.docx
    │   ├── Affidavit_of_Service.docx
    │   └── Acceptance_of_Service.docx
    ├── Notices/
    │   ├── Notice_of_Hearing.docx
    │   ├── Notice_of_Deposition.docx
    │   └── Notice_of_Filing.docx
    ├── Orders/
    │   ├── Proposed_Order.docx
    │   ├── Agreed_Order.docx
    │   └── Judgment_Entry.docx
    ├── Correspondence/
    │   ├── Engagement_Letter_General.docx
    │   ├── Disengagement_Letter.docx
    │   ├── Conflict_Waiver.docx
    │   └── Fee_Agreement_Hourly.docx
    └── Affidavits/
        ├── Affidavit_General.docx
        ├── Affidavit_of_Indigence.docx
        └── Verification.docx
```

---

## Firm Type Quick Reference

### Criminal Defense Firm (like JCS)
```
Templates/
├── Criminal/
├── Traffic/
├── DWI/
├── DOR/
├── _Common/
└── _Jurisdiction_Specific/
```
**Estimated templates: 150-250**

### Personal Injury Firm
```
Templates/
├── Personal_Injury/
├── Medical_Malpractice/
├── Workers_Comp/
├── Civil_Defense/      (for counterclaims)
├── _Common/
└── _Jurisdiction_Specific/
```
**Estimated templates: 200-350**

### Family Law Firm
```
Templates/
├── Family/
├── Juvenile/
├── Estate/             (often combined)
├── _Common/
└── _Jurisdiction_Specific/
```
**Estimated templates: 150-250**

### Estate Planning Firm
```
Templates/
├── Estate/
├── Probate/
├── Business/           (business succession)
├── Real_Estate/        (property transfers)
├── _Common/
└── _Jurisdiction_Specific/
```
**Estimated templates: 100-200**

### General Practice Firm
```
Templates/
├── (Multiple practice areas)
├── _Common/
└── _Jurisdiction_Specific/
```
**Estimated templates: 300-500+**

---

## Naming Conventions

### File Names

| Pattern | Example |
|---------|---------|
| `Document_Type.docx` | `Motion_to_Dismiss.docx` |
| `Document_Type_Qualifier.docx` | `Motion_to_Dismiss_SOL.docx` |
| `Document_Type_Subtype.docx` | `Petition_Auto_Accident.docx` |

### Standard Qualifiers

| Qualifier | Meaning |
|-----------|---------|
| `_General` | Default/generic version |
| `_SOL` | Statute of Limitations |
| `_with_Children` | Includes child-related provisions |
| `_Single_Member` | For single-member LLC |
| `_Multi_Member` | For multi-member LLC |

---

## Variable Syntax

All templates should use `{{variable_name}}` for replaceable content:

### Universal Variables
| Variable | Description |
|----------|-------------|
| `{{client_name}}` | Client's full legal name |
| `{{opposing_party}}` | Opposing party name |
| `{{case_number}}` | Court case number |
| `{{county}}` | County name |
| `{{court}}` | Full court name |
| `{{date}}` | Current date |
| `{{attorney_name}}` | Attorney's name |
| `{{bar_number}}` | Attorney's bar number |

### Practice-Specific Variables

**Personal Injury:**
| Variable | Description |
|----------|-------------|
| `{{accident_date}}` | Date of incident |
| `{{injury_description}}` | Description of injuries |
| `{{medical_expenses}}` | Total medical expenses |
| `{{lost_wages}}` | Lost wage amount |
| `{{demand_amount}}` | Settlement demand |

**Family Law:**
| Variable | Description |
|----------|-------------|
| `{{petitioner_name}}` | Filing spouse |
| `{{respondent_name}}` | Other spouse |
| `{{marriage_date}}` | Date of marriage |
| `{{separation_date}}` | Date of separation |
| `{{child_name}}` | Child's name |
| `{{child_dob}}` | Child's date of birth |

**Estate Planning:**
| Variable | Description |
|----------|-------------|
| `{{testator_name}}` | Person making will |
| `{{beneficiary_name}}` | Beneficiary |
| `{{executor_name}}` | Executor/Personal Rep |
| `{{trustee_name}}` | Trustee |

---

## Onboarding Checklist by Firm Type

### All Firms
- [ ] Set up attorney profile(s)
- [ ] Create `_Common/` templates
- [ ] Configure jurisdiction-specific forms

### Criminal Defense
- [ ] Create `Criminal/`, `Traffic/`, `DWI/`, `DOR/` folders
- [ ] Add preservation letter templates
- [ ] Add motion templates for each ground

### Personal Injury
- [ ] Create `Personal_Injury/` folder structure
- [ ] Add demand letter templates by case type
- [ ] Add medical records request templates
- [ ] Add settlement document templates

### Family Law
- [ ] Create `Family/` folder structure
- [ ] Add parenting plan templates
- [ ] Add child support worksheets
- [ ] Add protection order templates

### Estate Planning
- [ ] Create `Estate/` and `Probate/` folders
- [ ] Add will templates (simple, complex)
- [ ] Add trust templates
- [ ] Add power of attorney forms
