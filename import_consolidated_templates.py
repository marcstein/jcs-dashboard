"""
Import consolidated templates into the database.

Usage:
    python import_consolidated_templates.py

Templates imported (Batch 1 - ~197 variants replaced):
  1. Entry of Appearance (State) - replaces ~30 county variants
  2. Entry of Appearance (Muni) - replaces ~76 municipal variants
  3. Motion for Continuance - replaces ~34 county/muni variants
  4. Request for Discovery - replaces ~36 county/muni variants
  5. Potential Prosecution Letter - replaces ~21 county/muni variants

Templates imported (Batch 2 - ~792 variants replaced):
  6. Preservation/Supplemental Discovery Letter - replaces ~164 variants
  7. Preservation Letter - replaces ~105 variants
  8. Motion to Recall Warrant - replaces ~70 variants
  9. Proposed Stay Order - replaces ~54 variants
  10. Disposition Letter to Client - replaces ~399 variants
"""
import sys
import json
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from db.connection import get_connection
from db.documents import ensure_documents_tables


TEMPLATE_DIR = Path(__file__).parent / "data" / "templates"

# ── Template definitions ──────────────────────────────────────────────

TEMPLATES = [
    {
        "name": "Entry of Appearance (State)",
        "filename": "Entry_of_Appearance_State.docx",
        "category": "pleading",
        "subcategory": "entry_of_appearance",
        "tags": ["entry", "appearance", "state", "circuit court"],
        "deactivate_patterns": ["Entry - % County%", "Entry - % OOP%", "EOA - %County%", "EOA %County%"],
        "case_variables": [
            "county", "plaintiff_name", "defendant_name", "case_number",
            "attorney_names", "signing_attorney",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "service_date", "service_signatory",
        ],
        "profile_variables": [
            "firm_name", "attorney_name", "attorney_bar", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    {
        "name": "Entry of Appearance (Muni)",
        "filename": "Entry_of_Appearance_Muni.docx",
        "category": "pleading",
        "subcategory": "entry_of_appearance",
        "tags": ["entry", "appearance", "municipal", "muni"],
        "deactivate_patterns": ["Entry - % Muni%", "EOA - %Muni%", "EOA %Muni%"],
        "case_variables": [
            "city", "defendant_name", "case_number",
            "attorney_names", "signing_attorney",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "prosecutor_name", "prosecutor_address", "prosecutor_city_state_zip",
            "service_date", "service_signatory",
        ],
        "profile_variables": [
            "firm_name", "attorney_name", "attorney_bar", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    {
        "name": "Motion for Continuance",
        "filename": "Motion_for_Continuance.docx",
        "category": "motion",
        "subcategory": "continuance",
        "tags": ["motion", "continuance", "continue", "mtc"],
        "deactivate_patterns": ["MTC - %", "Motion to Continue%", "Motion for Continuance - %"],
        "case_variables": [
            "county", "defendant_name", "case_number",
            "hearing_date", "continuance_reason",
            "attorney_names", "signing_attorney",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "service_date", "service_signatory",
        ],
        "profile_variables": [
            "firm_name", "attorney_name", "attorney_bar", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    {
        "name": "Request for Discovery",
        "filename": "Request_for_Discovery.docx",
        "category": "discovery",
        "subcategory": "request",
        "tags": ["discovery", "request", "rog", "interrogatories"],
        "deactivate_patterns": ["Request for Discovery - %", "RFD - %", "Discovery Request - %"],
        "case_variables": [
            "county", "defendant_name", "case_number",
            "signing_attorney",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "service_date", "service_signatory",
        ],
        "profile_variables": [
            "firm_name", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    {
        "name": "Potential Prosecution Letter",
        "filename": "Potential_Prosecution_Letter.docx",
        "category": "letter",
        "subcategory": "prosecution",
        "tags": ["letter", "prosecution", "potential", "representation"],
        "deactivate_patterns": ["Potential Prosecution Ltr%", "Prosecution Letter - %", "Potential Pros%"],
        "case_variables": [
            "letter_date", "client_name",
            "prosecutor_name", "prosecutor_title", "court_name",
            "prosecutor_address_line1", "prosecutor_address_line2",
            "prosecutor_city_state_zip", "prosecutor_salutation",
            "initials",
        ],
        "profile_variables": [
            "attorney_name", "attorney_bar", "attorney_email",
            "firm_address_line1", "firm_address_line2",
            "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    # ── Batch 2 templates ────────────────────────────────────────────
    {
        "name": "Preservation/Supplemental Discovery Letter",
        "filename": "Preservation_Supplemental_Discovery_Letter.docx",
        "category": "letter",
        "subcategory": "preservation",
        "tags": ["preservation", "supplemental", "discovery", "evidence", "video"],
        "deactivate_patterns": ["Preservation%Supplemental%", "Pres%Supp%Disc%"],
        "case_variables": [
            "letter_date", "agency_name", "agency_attention",
            "agency_address", "agency_city_state_zip",
            "defendant_name", "defendant_dob", "charges",
            "arrest_date", "ticket_number", "arresting_officer",
            "defendant_honorific", "defendant_last_name", "defendant_pronoun",
            "initials",
        ],
        "profile_variables": [
            "attorney_name", "attorney_bar", "attorney_email",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone",
        ],
    },
    {
        "name": "Preservation Letter",
        "filename": "Preservation_Letter.docx",
        "category": "letter",
        "subcategory": "preservation",
        "tags": ["preservation", "evidence", "video", "booking"],
        "deactivate_patterns": ["Preservation Ltr%", "Preservation Letter - %"],
        "case_variables": [
            "letter_date", "agency_name", "agency_attention",
            "agency_address", "agency_city_state_zip",
            "defendant_name", "defendant_dob", "charges",
            "arrest_date", "ticket_number", "arresting_officer",
            "initials",
        ],
        "profile_variables": [
            "attorney_name", "attorney_bar", "attorney_email",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone",
        ],
    },
    {
        "name": "Motion to Recall Warrant",
        "filename": "Motion_to_Recall_Warrant.docx",
        "category": "motion",
        "subcategory": "recall_warrant",
        "tags": ["motion", "recall", "warrant", "muni"],
        "deactivate_patterns": ["Motion to Recall Warrant - %", "Recall Warrant - %", "Recall Warrant %"],
        "case_variables": [
            "county", "defendant_name", "case_number",
            "signing_attorney",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "service_date", "service_signatory",
        ],
        "profile_variables": [
            "firm_name", "attorney_name", "attorney_bar", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    {
        "name": "Proposed Stay Order",
        "filename": "Proposed_Stay_Order.docx",
        "category": "motion",
        "subcategory": "stay_order",
        "tags": ["stay", "order", "dor", "pfr", "refusal", "driving"],
        "deactivate_patterns": ["Proposed Stay Order - %", "Stay Order - %", "Stay Order %"],
        "case_variables": [
            "county", "petitioner_name", "dln", "dob", "case_number",
            "arrest_date",
            "respondent_attorney_name", "respondent_attorney_bar",
            "judge_name", "judge_title", "division",
            "order_month", "order_year",
        ],
        "profile_variables": [
            "attorney_name", "attorney_full_name", "attorney_bar",
        ],
    },
    {
        "name": "Disposition Letter to Client",
        "filename": "Disposition_Letter_to_Client.docx",
        "category": "letter",
        "subcategory": "disposition",
        "tags": ["disposition", "dispo", "letter", "client", "result", "plea"],
        "deactivate_patterns": ["Dispo Ltr%", "Disposition Ltr%", "Disposition Letter - %"],
        "case_variables": [
            "letter_date", "client_name", "client_first_name",
            "client_address", "client_city_state_zip",
            "disposition_paragraph", "court_name",
            "court_address", "court_city_state_zip",
            "payment_instructions", "payment_deadline",
            "initials",
        ],
        "profile_variables": [
            "attorney_name", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone",
        ],
    },
    # ── Batch 3 templates (automated consolidation) ──────────────────
    {
        "name": "Motion for Change of Judge",
        "filename": "Motion_for_COJ.docx",
        "category": "motion",
        "subcategory": "change_of_judge",
        "tags": ["motion", "change", "judge", "coj"],
        "deactivate_patterns": ["Motion for COJ%"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Notice of Hearing (General)",
        "filename": "Notice_of_Hearing.docx",
        "category": "notice",
        "subcategory": "hearing",
        "tags": ["notice", "hearing", "noh"],
        "deactivate_patterns": ["Notice of Hearing - %"],
        "case_variables": ["county", "defendant_name", "case_number", "hearing_date", "hearing_time", "division", "motion_type"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip"],
    },
    {
        "name": "Petition for Review (PFR)",
        "filename": "Petition_for_Review.docx",
        "category": "pleading",
        "subcategory": "pfr",
        "tags": ["pfr", "petition", "review", "dor", "refusal"],
        "deactivate_patterns": ["PFR - %"],
        "case_variables": ["county", "petitioner_name", "case_number", "dob"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip"],
    },
    {
        "name": "After Supplemental Disclosure Letter",
        "filename": "After_Supplemental_Disclosure_Ltr.docx",
        "category": "letter",
        "subcategory": "disclosure",
        "tags": ["supplemental", "disclosure", "discovery", "dvd"],
        "deactivate_patterns": ["After Supplemental Disclosure Ltr%"],
        "case_variables": ["prosecutor_name", "prosecutor_title", "court_name", "prosecutor_address", "prosecutor_city_state_zip", "prosecutor_salutation", "defendant_name", "case_number", "disclosure_date"],
        "profile_variables": ["attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone"],
    },
    {
        "name": "Waiver of Arraignment",
        "filename": "Waiver_of_Arraignment.docx",
        "category": "pleading",
        "subcategory": "arraignment",
        "tags": ["waiver", "arraignment", "not guilty", "plea"],
        "deactivate_patterns": ["Waiver of Arraignment - %"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone"],
    },
    {
        "name": "Notice to Take Deposition",
        "filename": "Notice_to_Take_Deposition.docx",
        "category": "notice",
        "subcategory": "deposition",
        "tags": ["notice", "deposition", "deponent"],
        "deactivate_patterns": ["Notice to Take Deposition - %"],
        "case_variables": ["county", "defendant_name", "case_number", "prosecutor_name", "prosecutor_title", "prosecutor_address", "prosecutor_city_state_zip", "deponent_name", "deposition_date", "deposition_time", "deposition_location"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Motion for Bond Reduction",
        "filename": "Motion_for_Bond_Reduction.docx",
        "category": "motion",
        "subcategory": "bond_reduction",
        "tags": ["motion", "bond", "reduction", "bail"],
        "deactivate_patterns": ["Motion for Bond Reduction - %"],
        "case_variables": ["county", "defendant_name", "case_number", "division", "bond_amount"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Motion to Certify for Jury Trial",
        "filename": "Motion_to_Certify.docx",
        "category": "motion",
        "subcategory": "certify",
        "tags": ["motion", "certify", "jury", "municipal"],
        "deactivate_patterns": ["Motion to Certify - %"],
        "case_variables": ["city", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip"],
    },
    {
        "name": "Letter to DOR with PFR",
        "filename": "Ltr_to_DOR_with_PFR.docx",
        "category": "letter",
        "subcategory": "dor",
        "tags": ["letter", "dor", "pfr", "petition", "review"],
        "deactivate_patterns": ["Ltr to DOR with PFR - %", "Ltr to DOR with PFR and Stay Order"],
        "case_variables": ["petitioner_name"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Letter to DOR with Stay Order",
        "filename": "Ltr_to_DOR_with_Stay_Order.docx",
        "category": "letter",
        "subcategory": "dor",
        "tags": ["letter", "dor", "stay", "order"],
        "deactivate_patterns": ["Ltr to DOR with Stay Order - %"],
        "case_variables": ["petitioner_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "DOR Motion to Dismiss",
        "filename": "DOR_Motion_to_Dismiss.docx",
        "category": "motion",
        "subcategory": "dismiss_dor",
        "tags": ["motion", "dismiss", "dor", "petitioner"],
        "deactivate_patterns": ["DOR - Motion to Dismiss - %"],
        "case_variables": ["county", "petitioner_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip"],
    },
    {
        "name": "Notice of Hearing - Motion to Withdraw",
        "filename": "Notice_of_Hearing_MTW.docx",
        "category": "notice",
        "subcategory": "hearing_mtw",
        "tags": ["notice", "hearing", "withdraw", "mtw"],
        "deactivate_patterns": ["Notice of Hearing - MTW%", "Notice of MTW Hearing%", "NOH for MTW%", "NOH%MTW%"],
        "case_variables": ["county", "defendant_name", "case_number", "division", "hearing_date", "hearing_time"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip"],
    },
    {
        "name": "Motion to Shorten Time",
        "filename": "Motion_to_Shorten_Time.docx",
        "category": "motion",
        "subcategory": "shorten_time",
        "tags": ["motion", "shorten", "time"],
        "deactivate_patterns": ["Motion to Shorten Time - %"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip"],
    },
    {
        "name": "Letter to DOR with Judgment",
        "filename": "Ltr_to_DOR_with_Judgment.docx",
        "category": "letter",
        "subcategory": "dor",
        "tags": ["letter", "dor", "judgment", "final", "order"],
        "deactivate_patterns": ["Ltr to DOR with Judgment - %"],
        "case_variables": ["petitioner_name", "dln"],
        "profile_variables": ["attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Motion to Appear via WebEx",
        "filename": "Motion_to_Appear_via_WebEx.docx",
        "category": "motion",
        "subcategory": "webex",
        "tags": ["motion", "appear", "webex", "remote", "virtual"],
        "deactivate_patterns": ["Motion to Appear via WebEx - %", "Motion to appear via WebEx%", "Motion to appear via webex%"],
        "case_variables": ["county", "petitioner_name", "respondent_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Motion to Place on Docket",
        "filename": "Motion_to_Place_on_Docket.docx",
        "category": "motion",
        "subcategory": "docket",
        "tags": ["motion", "place", "docket", "traffic"],
        "deactivate_patterns": ["Motion to Place on Docket - %", "Motion to Place on Docket %"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip"],
    },
    {
        "name": "Notice of Change of Address",
        "filename": "Notice_of_Change_of_Address.docx",
        "category": "notice",
        "subcategory": "change_address",
        "tags": ["notice", "change", "address"],
        "deactivate_patterns": ["Notice of Change of Address - %"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Request for Supplemental Discovery",
        "filename": "Request_for_Supplemental_Discovery.docx",
        "category": "discovery",
        "subcategory": "supplemental",
        "tags": ["discovery", "supplemental", "body cam", "dash cam"],
        "deactivate_patterns": ["Request for Supplemental Discovery - %", "Motion for Supplemental Discovery%"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Motion to Amend Bond Conditions",
        "filename": "Motion_to_Amend_Bond_Conditions.docx",
        "category": "motion",
        "subcategory": "amend_bond",
        "tags": ["motion", "amend", "bond", "conditions"],
        "deactivate_patterns": ["Motion to Amend Bond Conditions - %", "Motion to Amend Bond - %"],
        "case_variables": ["county", "defendant_name", "case_number", "division", "bond_amount"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Letter to Client with Discovery",
        "filename": "Ltr_to_Client_with_Discovery.docx",
        "category": "letter",
        "subcategory": "discovery_cover",
        "tags": ["letter", "client", "discovery", "enclosed"],
        "deactivate_patterns": ["Ltr to Client with Discovery - %"],
        "case_variables": ["client_name", "client_salutation", "client_address", "client_city_state_zip", "case_number"],
        "profile_variables": ["attorney_name", "firm_city_state_zip", "firm_phone"],
    },
    {
        "name": "Motion to Compel Discovery",
        "filename": "Motion_to_Compel.docx",
        "category": "motion",
        "subcategory": "compel",
        "tags": ["motion", "compel", "discovery"],
        "deactivate_patterns": ["Motion to Compel - %", "Motion to Compel Discovery%"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Motion to Terminate Probation",
        "filename": "Motion_to_Terminate_Probation.docx",
        "category": "motion",
        "subcategory": "terminate_probation",
        "tags": ["motion", "terminate", "probation"],
        "deactivate_patterns": ["Motion to Terminate Probation - %"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip"],
    },
    {
        "name": "Request for Jury Trial",
        "filename": "Request_for_Jury_Trial.docx",
        "category": "motion",
        "subcategory": "jury_trial",
        "tags": ["request", "jury", "trial"],
        "deactivate_patterns": ["Request for Jury Trial - %"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "DL Reinstatement Letter",
        "filename": "DL_Reinstatement_Ltr.docx",
        "category": "letter",
        "subcategory": "reinstatement",
        "tags": ["letter", "dl", "reinstatement", "license", "driving"],
        "deactivate_patterns": ["DL Reinstatement Ltr%", "DL Reinstatment Ltr%", "DL Reinstatement Letter%", "Drivers License Reinstatement%"],
        "case_variables": ["client_name", "client_first_name", "client_email", "client_address", "client_city_state_zip"],
        "profile_variables": ["attorney_name"],
    },
    # ── Batch 4: Request for Rec- Letter to PA (replaces ~141 variants, 119 corrupted) ──
    {
        "name": "Request for Recommendation Letter to PA",
        "filename": "Request_for_Recommendation_Letter_to_PA.docx",
        "category": "letter",
        "subcategory": "recommendation",
        "tags": ["letter", "recommendation", "prosecutor", "pa", "request", "rec"],
        "deactivate_patterns": [
            "Request for Rec%",
            "Request for Recommendation%",
            "Burleyson Request for Recommendation%",
            "Request for Records from MO DSS%",
        ],
        "case_variables": [
            "service_date", "defendant_name", "case_number",
            "prosecutor_name", "court_name", "court_name_short",
            "prosecutor_address", "prosecutor_city_state_zip", "prosecutor_email",
        ],
        "profile_variables": [
            "attorney_name", "attorney_bar", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    # ── Batch 4 (remaining multi-variant groups) ──────────────────────
    {
        "name": "Entry (Generic)",
        "filename": "Entry_Generic.docx",
        "category": "pleading",
        "subcategory": "entry",
        "tags": ["entry", "generic", "municipal"],
        "deactivate_patterns": ["Entry - %"],
        "case_variables": ["city", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Plea of Guilty",
        "filename": "Plea_of_Guilty.docx",
        "category": "pleading",
        "subcategory": "plea",
        "tags": ["plea", "guilty", "municipal"],
        "deactivate_patterns": ["Plea of Guilty%"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "firm_city_state_zip"],
    },
    {
        "name": "Motion to Dismiss (County)",
        "filename": "Motion_to_Dismiss_County.docx",
        "category": "motion",
        "subcategory": "dismiss",
        "tags": ["motion", "dismiss", "county", "criminal"],
        "deactivate_patterns": ["Motion to Dismiss - %"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Request for Stay Order",
        "filename": "Request_for_Stay_Order.docx",
        "category": "motion",
        "subcategory": "stay",
        "tags": ["request", "stay", "order", "dor"],
        "deactivate_patterns": ["Request for Stay Order%"],
        "case_variables": ["county", "petitioner_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Waiver of Preliminary Hearing",
        "filename": "Waiver_of_Preliminary_Hearing.docx",
        "category": "pleading",
        "subcategory": "preliminary_hearing",
        "tags": ["waiver", "preliminary", "hearing"],
        "deactivate_patterns": ["Waiver of Preliminary Hearing%"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Request for Transcripts",
        "filename": "Request_for_Transcripts.docx",
        "category": "letter",
        "subcategory": "transcripts",
        "tags": ["request", "transcripts", "court", "reporter"],
        "deactivate_patterns": ["Request for Transcript%"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["attorney_name", "attorney_bar", "firm_city_state_zip", "firm_phone"],
    },
    {
        "name": "Motion to Withdraw Guilty Plea",
        "filename": "Motion_to_Withdraw_Guilty_Plea.docx",
        "category": "motion",
        "subcategory": "withdraw_plea",
        "tags": ["motion", "withdraw", "guilty", "plea"],
        "deactivate_patterns": ["Motion to Withdraw Guilty Plea%"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "PH Waiver",
        "filename": "PH_Waiver.docx",
        "category": "pleading",
        "subcategory": "preliminary_hearing",
        "tags": ["ph", "waiver", "preliminary", "hearing"],
        "deactivate_patterns": ["PH Waiver%"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Answer for Request to Produce",
        "filename": "Answer_for_Request_to_Produce.docx",
        "category": "discovery",
        "subcategory": "answer_produce",
        "tags": ["answer", "request", "produce", "discovery"],
        "deactivate_patterns": ["Answer for Request to Produce%"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Available Court Dates for Trial",
        "filename": "Available_Court_Dates_for_Trial.docx",
        "category": "letter",
        "subcategory": "trial_dates",
        "tags": ["available", "court", "dates", "trial"],
        "deactivate_patterns": ["Available Court Dates for Trial%"],
        "case_variables": ["county", "defendant_name", "case_number"],
        "profile_variables": ["firm_name", "attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Requirements for Rec Letter to Client",
        "filename": "Requirements_for_Rec_Letter_to_Client.docx",
        "category": "letter",
        "subcategory": "recommendation_requirements",
        "tags": ["requirements", "recommendation", "client", "letter"],
        "deactivate_patterns": ["Requirements for a Rec Letter%"],
        "case_variables": ["client_name", "client_address", "client_city_state_zip"],
        "profile_variables": ["attorney_name", "firm_city_state_zip", "firm_phone"],
    },
    # Motion to Withdraw (from DOCX subset of old variants)
    {
        "name": "Motion to Withdraw",
        "filename": "Motion_to_Withdraw.docx",
        "category": "motion",
        "subcategory": "withdraw",
        "tags": ["motion", "withdraw", "withdrawal", "counsel"],
        "deactivate_patterns": ["Motion to Withdraw%"],
        "case_variables": ["county", "defendant_name", "case_number", "service_date"],
        "profile_variables": ["attorney_name", "attorney_bar", "attorney_email", "firm_name", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    # Closing Letter (replaces 28 variants)
    {
        "name": "Closing Letter",
        "filename": "Closing_Letter.docx",
        "category": "letter",
        "subcategory": "closing",
        "tags": ["closing", "letter", "disposition", "case", "summary"],
        "deactivate_patterns": ["Closing Letter%", "Closing Ltr%", "Closing letter%"],
        "case_variables": ["client_name", "client_first_name", "client_address", "client_city_state_zip", "case_reference", "county", "disposition_paragraph", "closing_paragraph"],
        "profile_variables": ["attorney_name"],
    },
    # Batch 5 — former .doc (OLE) templates, converted via LibreOffice
    {
        "name": "Admin Continuance Request",
        "filename": "Admin_Continuance_Request.docx",
        "category": "motion",
        "subcategory": "continuance",
        "tags": ["admin", "continuance", "dor", "hearing", "administrative"],
        "deactivate_patterns": ["Admin Continuance%", "Administrative Continuance%"],
        "case_variables": ["petitioner_name", "docket_number", "case_number", "dln", "hearing_date"],
        "profile_variables": ["attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Admin Hearing Request",
        "filename": "Admin_Hearing_Request.docx",
        "category": "motion",
        "subcategory": "hearing",
        "tags": ["admin", "hearing", "dor", "administrative", "telephonic", "entry of appearance"],
        "deactivate_patterns": ["Admin Hearing%", "Administrative Hearing%"],
        "case_variables": ["petitioner_name", "dob", "drivers_license_number", "arrest_county", "arrest_date", "case_number"],
        "profile_variables": ["attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
    {
        "name": "Petition for Trial De Novo",
        "filename": "Petition_for_TDN.docx",
        "category": "pleading",
        "subcategory": "petition",
        "tags": ["petition", "trial de novo", "tdn", "license", "suspension", "revocation", "dor"],
        "deactivate_patterns": ["Petition for TDN%", "Petition for Trial De Novo%"],
        "case_variables": ["county", "case_number", "petitioner_name", "arrest_date", "officer_name", "police_department", "hearing_date"],
        "profile_variables": ["attorney_name", "attorney_bar", "attorney_email", "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax"],
    },
]


def import_template(tmpl_def):
    """Import a single consolidated template."""
    filepath = TEMPLATE_DIR / tmpl_def["filename"]
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found, skipping")
        return None

    content = filepath.read_bytes()
    file_hash = hashlib.sha256(content).hexdigest()
    all_vars = tmpl_def["case_variables"] + tmpl_def["profile_variables"]

    # Build variable_mappings
    variable_mappings = {}
    for v in tmpl_def["case_variables"]:
        variable_mappings[v] = {"source": "manual", "type": "text"}
    for v in tmpl_def["profile_variables"]:
        if v.startswith("firm_"):
            variable_mappings[v] = {"source": "firm", "field": v}
        elif v.startswith("attorney_"):
            variable_mappings[v] = {"source": "attorney", "field": v}

    with get_connection() as conn:
        cur = conn.cursor()

        # Deactivate old variant templates that this consolidated template replaces
        patterns = tmpl_def.get("deactivate_patterns", [])
        # Also support legacy single-pattern field
        if tmpl_def.get("deactivate_pattern"):
            patterns.append(tmpl_def["deactivate_pattern"])
        total_deactivated = 0
        for pattern in patterns:
            cur.execute(
                """UPDATE templates SET is_active = FALSE
                   WHERE firm_id = %s AND name ILIKE %s AND is_active = TRUE
                     AND name != %s
                   RETURNING id, name""",
                ("jcs_law", pattern, tmpl_def["name"])
            )
            deactivated = cur.fetchall()
            total_deactivated += len(deactivated)
            for row in deactivated:
                old_name = row['name'] if isinstance(row, dict) else row[1]
                print(f"    Deactivated: {old_name}")
        if total_deactivated:
            print(f"  Total deactivated: {total_deactivated} old variant(s)")

        cur.execute("""
            INSERT INTO templates (
                firm_id, name, original_filename, category, subcategory,
                variables, variable_mappings, tags,
                file_content, file_hash, file_size, is_active
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, TRUE
            )
            ON CONFLICT (firm_id, name) DO UPDATE SET
                original_filename = EXCLUDED.original_filename,
                category = EXCLUDED.category,
                subcategory = EXCLUDED.subcategory,
                variables = EXCLUDED.variables,
                variable_mappings = EXCLUDED.variable_mappings,
                tags = EXCLUDED.tags,
                file_content = EXCLUDED.file_content,
                file_hash = EXCLUDED.file_hash,
                file_size = EXCLUDED.file_size,
                is_active = TRUE
            RETURNING id
        """, (
            "jcs_law",
            tmpl_def["name"],
            tmpl_def["filename"],
            tmpl_def["category"],
            tmpl_def["subcategory"],
            json.dumps(all_vars),
            json.dumps(variable_mappings),
            json.dumps(tmpl_def["tags"]),
            content,
            file_hash,
            len(content),
        ))
        row = cur.fetchone()
        new_id = row['id'] if isinstance(row, dict) else row[0]
        conn.commit()

    return new_id


def main():
    ensure_documents_tables()
    print("Importing consolidated templates...\n")

    for tmpl_def in TEMPLATES:
        filepath = TEMPLATE_DIR / tmpl_def["filename"]
        size = filepath.stat().st_size if filepath.exists() else 0
        print(f"[{tmpl_def['name']}] ({size:,} bytes)")
        tid = import_template(tmpl_def)
        if tid:
            print(f"  -> Template ID: {tid}")
            print(f"     Case vars: {len(tmpl_def['case_variables'])}, "
                  f"Profile vars: {len(tmpl_def['profile_variables'])}")
        print()

    print("Done! All templates imported.")


if __name__ == "__main__":
    main()
