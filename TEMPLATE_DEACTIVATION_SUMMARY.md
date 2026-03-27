# Template Deactivation Summary - Import Script Impact

## Overview

This document shows the complete impact of running `import_consolidated_templates.py` on the active template list.

---

## Executive Summary

| Metric | Count |
|--------|-------|
| **Total active templates NOW** | 400 |
| **Templates to be DEACTIVATED** | 21 |
| **Templates that will REMAIN** | 379 |

---

## Templates to be DEACTIVATED (21)

These templates match the deactivation patterns in the import script and will be deactivated:

| # | ID | Name | Deactivation Reason |
|---|----|----|-----|
| 1 | 1425 | Admin Continuance Request | Matches `Admin Continuance%` |
| 2 | 1673 | Admin Hearing Request | Matches `Admin Hearing%` |
| 3 | 739 | Answer for Request to Produce | Matches `Answer for Request to Produce%` |
| 4 | 1109 | Available Court Dates for Trial | Matches `Available Court Dates for Trial%` |
| 5 | 1514 | Closing Letter | Matches `Closing Letter%` |
| 6 | 1770 | DL Reinstatement Letter | Matches `DL Reinstatement Ltr%` |
| 7 | 131 | Motion to Appear via WebEx | Matches `Motion to Appear via WebEx - %` |
| 8 | 803 | Motion to Compel Discovery | Matches `Motion to Compel Discovery%` |
| 9 | 1547 | Motion to Withdraw | Matches `Motion to Withdraw%` |
| 10 | 2002 | NOH Bond Reduction | Matches `NOH Bond Reduction%` |
| 11 | 1758 | Notice of Hearing - Motion to Withdraw | Matches `NOH%MTW%` |
| 12 | 2003 | OOP Entry | Matches `OOP Entry%` |
| 13 | 763 | PH Waiver | Matches `PH Waiver%` |
| 14 | 1950 | Petition for Trial De Novo | Matches `Petition for Trial De Novo%` |
| 15 | 774 | Plea of Guilty | Matches `Plea of Guilty%` |
| 16 | 1674 | Potential Prosecution Letter | Matches `Potential Prosecution Ltr%` |
| 17 | 1692 | Preservation/Supplemental Discovery Letter | Matches `Preservation%Supplemental%` |
| 18 | 1839 | Request for Recommendation Letter to PA | Matches `Request for Rec%` |
| 19 | 1843 | Request for Stay Order | Matches `Request for Stay Order%` |
| 20 | 6 | Request for Transcripts | Matches `Request for Transcript%` |
| 21 | 1844 | Waiver of Preliminary Hearing | Matches `Waiver of Preliminary Hearing%` |

---

## Complete List of REMAINING Templates (379)

The following 379 templates will remain active AFTER running the import script:

```
1    153      --ENGAGEMENT AGREEMENT TEMPLATE
2    1410     1 Year Letter
3    1413     90 Day Letter with No Priors
4    234      90 Day Letter with No Priors - No Admin Hearing
5    1412     90 Day Letter with No Priors - SATOP Comparable
6    1411     90 Day Letter with Priors
7    1160     90 day Letter with No Priors
8    1159     90 day Letter with Priors
9    313      A Few Things
10   810      Affidavit of Non Prosecution
11   308      Affidavit of Non-Prosecution
12   314      Affidavit of PFR
13   316      Affidavit of Service
14   1750     After Supplemental Disclosure Letter
15   310      Amended Notice to take Deposition
16   577      Appearance Plea of Guilty and Waiver Franklin
17   708      Application for Recusal of Judge
18   1487     Application for Trial de Novo - Muni Court
19   330      Attorney County Breakdown
20   319      Attorney-Client Waiver
21   1107     Available Court Dates - DCL
22   1110     Available Court Dates - DCL Movant
23   1112     Available Court Dates - Juvenile Court
24   76       Available Court Dates for PH
25   1459     Avery15264ShippingLabels (1)
26   317      Blank Letterhead
27   1145     Bond Assignment
28   93       Bond Assignment - Jefferson County
29   89       Bond Assignment - St. Louis County
30   797      Bond Assignment to Court Costs and Fines
31   1470     CANRB Continuance Request
32   281      CURTIS CONTINUANCE 10-28-2024
33   306      Certificate of Service
34   12       Chesterfield's Amicus Brief
35   11       City's Motion for Rehearing
36   414      Client Appt Reminder
37   16       Client Letter to Employer
38   419      Client Status Update
39   418      Client Status Update - DCL
40   428      Client Survey
41   305      Clio Instructions
42   775      Confinement Order
43   1146     Consent Bond Order
44   711      Consent Memo
45   110      Consent Order Granting Addtional Time for Probation Requirements
46   94       Consent To Release Records
47   98       Consent Warrant Recall Order - Jefferson County
48   713      Costley NOH Mot to Recall Warrant
49   304      Cover Letter
50   267      Cover letter Hipaa
51   347      Criminal New Client Checklist
52   1166     DL Reinstatement - SATOP Comparable Letter
53   112      DOC Writ
54   773      DOR - Motion to Dismiss
55   1757     DOR Motion to Dismiss
56   81       DPA
57   349      DWI - Admin Hearing New Client Checklist
58   350      DWI - PFR New Client Checklist
59   1154     DWI - prior NOT in the past 5 years
60   1155     DWI - second offense in over 5 years
61   1        DWI Checklist
62   575      DWI Engagement Agreement
63   1158     DWI first time
64   406      Disengagement Ltr
65   1696     Disposition Letter to Client
66   57       EA - Precharge Case
67   59       EA - USE THIS ONE
68   1449     EA, NEW LETTERHEAD
69   329      EMPLOYMENT EXEMPTION VARIANCE
70   154      ENGAGEMENT AGREEMENT TEMPLATE
71   309      Elysse Broussard Req for Contact Letter
72   269      Employer Letter
73   730      Endorsement of Witness
74   576      Engagement Agreement- EA
75   346      Entering New Clients into MyCase
76   1268     Entry
77   1840     Entry (Generic)
78   1688     Entry of Appearance (Muni)
79   1687     Entry of Appearance (State)
80   1676     Entry of Appearance - Multiple Attorneys
81   1675     Entry of Appearance - Single Attorney
82   1677     Entry of Appearance, Waiver of Arraignment, Plea of Not Guilty
83   718      Entry, Arraignment Waiver, NG Plea
84   1032     Entry- City of Clayton Muni
85   1038     Entry- Wentzville Muni
86   134      Fee Memo - ATM
87   102      Fee Memo - Saint Louis City Civil
88   1478     Filing Fee Memo
89   429      Final Client Status Update - DCL
90   410      Final Pay Your Rec Letter
91   56       Financial POA
92   327      Generic Motion for Bond Reduction
93   302      Generic Motion for Bond Reduction specific
94   67       IID Employment Waiver
95   1414     Instructions for Blow Cases
96   688      Instructions for Refusal Cases
97   326      JCCC Request to Schedule Attorney Call
98   505      Johnson Motion for Continuance 09-21-23
99   9        Judgment Dismising Case - Not Filed Within One Year
100  1163     LDP - 10 year denial
101  1161     LDP - Application Instructions Letter
102  1164     LDP - Graduate of Treatment Court - Sample Questions
103  1162     LDP - Participant of Treatment Court - Sample Questions
104  605      LH- Preservation Letter
105  422      LTA
106  155      Legal Services Agreement - Criminal Case
107  226      Legal Services Agreement- Criminal
108  227      Legal Services Agreement- DWI
109  229      Legal Services Agreement- Federal
110  228      Legal Services Agreement- Pre-Charge
111  157      Legal Services Agreement- Traffic
112  159      Legal Services agreement - Accident injury
113  161      Legal Services agreement - Bankruptcy
114  162      Legal Services agreement - Collections
115  163      Legal Services agreement - Divorce
116  165      Legal Services agreement - Domestic violence
117  166      Legal Services agreement - Federal
118  168      Legal Services agreement - Probate
119  167      Legal Services agreement - Tax
120  164      Legal Services agreement - Workers Comp
121  269      Letter To Employer - ATM
122  275      Letter Indicating Notice of Intent to Withdraw
123  289      Letter Indicating Notice of Intent to Withdraw - St. Louis County Muni
124  274      Letter of Notice of Intent to Withdraw - ATM
125  276      Letter of Notice of Intent to Withdraw - St. Louis County
126  277      Letter of Notice of Intent to Withdraw - DOR
127  1449     LTR FOR NEW CLIENTS, DO NOT USE OLDER LETTERHEAD (CURTIS CONTINUING)
128  433      Letterhead-  Billable Time
129  704      Letterhead, updated for service
130  1446     Ltr to Client with Discovery
131  1751     Ltr to DOR with Judgment
132  1744     Ltr to DOR with PFR
133  1743     Ltr to DOR with Stay Order
134  764      Membership Letter
135  1471     Membership Letter for AOMC (New)
136  1452     Membership Letter- AOMC Wittenberg
137  1453     Membership Letter - Peacemakers
138  260      Motion For Bond Reduction - Cass County
139  1688     Motion For Bond Reduction - Cass County
140  1366     Motion for Bond Reduction
141  1697     Motion for Bond Reduction
142  1684     Motion for Change of Judge
143  1547     Motion for Continuance
144  1268     Motion for COJ
144  1268     Motion for COJ
145  1689     Motion for Discovery - Attachment style - use if need to send to prosecutor
146  1690     Motion to Amend Bond Conditions
147  1686     Motion to Amend Bond Conditions
148  1632     Motion to Appear via WebEx
149  1691     Motion to Certify
150  1683     Motion to Certify for Jury Trial
151  1692     Motion to Compel
152  1547     Motion to Withdraw
153  1685     Motion to Place on Docket
154  1682     Motion to Shorten Time
155  1681     Motion to Terminate Probation
156  1680     Motion to Withdraw Guilty Plea
157  767      Motion to Withdraw Guilty Plea - ATM
158  1678     Motions to Dismiss (General)
159  1679     Notice of Change of Address
160  1693     Notice of Hearing
161  1758     Notice of Hearing - Motion to Withdraw
162  1748     Notice of Hearing for Motion to Withdraw
163  1494     Notice of Hearing Motion to Recall Warrant
164  1497     Notice of Inquiry and Change
165  1475     Notice of Inquiry and Change of Address
166  1473     Notice of Inquiry and Change of Address - Expedited
167  1491     Notice of Motion to Compel
168  1493     Notice of Motion to Recall Warrant
169  1502     Notice to Appear in Court
170  1500     Notice to Appear in Court - Muni TDN
171  1501     Notice to Appear in Court - Muni TDN with Fees
172  1693     Notice to Take Deposition
173  1694     Notification of Change of Address
174  1699     Notyice of Hearing
175  753      OATH
176  1638     One Paragraph Motion to Dismiss - Criminal
177  1639     One Paragraph Motion to Dismiss - DOR
178  1640     One Paragraph Motion to Dismiss - Failure to Prosecute
179  1641     One Paragraph Motion to Dismiss - Lack of Jurisdiction
180  1641     One Paragraph Motion to Dismiss - Lack of Jurisdiction
181  1642     One Paragraph Motion to Dismiss - Lack of Jurisdiction (Criminal)
182  1643     One Paragraph Motion to Dismiss - Lack of Jurisdiction (DOR)
183  1644     One Paragraph Motion to Dismiss - Statute of Limitations
184  1645     One Paragraph Motion to Dismiss - Statute of Limitations (DOR)
185  1646     One Paragraph Motion to Dismiss - Statute of Limitations (Failure to Prosecute)
186  1647     One Paragraph Motion to Dismiss - Statute of Limitations (Failure to Prosecute) (DOR)
187  1648     One Paragraph Motion to Dismiss - Statute of Limitations (Lack of Jurisdiction)
188  1649     One Paragraph Motion to Dismiss - Statute of Limitations (Lack of Jurisdiction) (DOR)
189  1721     OOP Entry
190  1720     OOP Order
191  1714     Order to Amend Bond
192  1729     Order to Appear for PFR Hearing
193  1716     Order to Appear for Probation Review Hearing
194  1728     Order to Compel
195  1717     Order to Compel Testimony
196  1727     Order to Produce Documents
197  1722     Order to Show Cause
198  1731     Orders of Expungement - Case Dismissed
199  1732     Orders of Expungement - Guilty Plea
200  1733     Orders of Expungement - Not Guilty Plea
201  1734     Orders of Expungement - Nolle Prosequi
202  1735     Orders of Expungement - Violation of Probation
203  1736     Orders of Expungement - Waitlistfor Plea
204  1737     Orders of Expungement - Waitlist for Guilty Plea
205  1738     Orders of Expungement - Waitlist for Not Guilty Plea
206  1739     Orders of Expungement - Waitlist for Nolle Prosequi
207  1740     Orders of Expungement - Waitlist for Violation of Probation
208  1741     Orders of Expungement - Waitlist for Waitlist
209  1665     Over the phone Service Template
210  1663     Potential Prosecution Letter
211  1664     Potential Prosecution Letter - Generic
212  1625     Practice Court Date - Muni Court
213  1626     Practice Court Date - Sample
214  1741     Preserve Letter
215  1695     Preservation Letter
216  1749     Preservation Letter
217  1360     Preservation Letter - ATM
218  1361     Preservation Letter - MTW  
219  282      Preserve Supp Disc Ltr - County
220  283      Preserve Supp Disc Ltr - Muni
221  707      Preservation/Supplemental Discovery Ltr
222  282      Preservation/Supplemental Discovery Ltr - County
223  283      Preservation/Supplemental Discovery Ltr - Muni
224  284      Preservation/Supplemental Discovery Ltr - St. Louis City Muni
225  604      Presrvation/Supplemental Discovery Ltr - County DWI
226  686      Presrvation/Supplemental Discovery Ltr - Muni DWI
227  285      Preservation/Supplemental Discovery Ltr - Traffic County
228  287      Preservation/Supplemental Discovery Ltr - Traffic Muni
229  286      Preservation/Supplemental Discovery Ltr - Traffic, Muni
230  290      Preserve[sic] Supplemental Discovery Letter
231  288      Preservation-Supplemental Discovery Ltr - St. Louis City Muni
232  352      Phone Calls
233  413      Plea Agreement Ltr
234  905      Plea Offer Ltr to Client - Bridgeton Muni Probation
235  886      Plea Offer Ltr to Client - Crawford County
236  420      Plea by Mail Ltr
237  1157     Plead Guilty with points letter
238  345      Potentials
239  703      Preservation Letter
240  662      Preservation Letter
241  219      Proposed Confession - Warren County
242  743      Proposed Guilty Columbia Muni
243  728      Proposed Order
244  106      Proposed Order to Amend Bond - Crawford County
245  716      Proposed Order to Amend Bond Conditions
246  85       Proposed Order to Amend Bond Conditions by Consent
247  114      Proposed Order to Compel Records
248  126      Proposed Order to Complete CHOICES
249  217      Proposed Order to Raise Security Level - St. Louis County
250  771      Proposed Order to Recall Warrant - STL City Muni
251  87       Proposed Order to Reduce Bond by Consent
252  302      Proposed Order to Transfer Division
253  88       Proposed Order to Withdraw Guilty Plea
254  96       Proposed Qualified Protective Order
255  1407     Proposed Stay Order
256  1081     Proposed Stay Order with Motion - Phelps County
257  814      Public Records Request
258  408      Rec Requirement Example Letter
259  225      Reign Kehoe Legal Services Agreement
260  1008     Req for Discovery - Owensville Muni
261  382      Reqest for Discovery - St. Louis County Muni South
262  426      Request Contact with Firm
263  1476     Request for Alias Summons
264  1440     Request for Alias Summons - Muni TDN
265  1482     Request for Alias Summons by Mail
266  1359     Request for Discovery
267  1362     Request for Discovery Word
268  1212     Request for Discovery aw
269  1015     Request for Discovery- Hazelwood Muni
270  1001     Request for Discovery- Saint Peters Muni
271  303      Request for Documents
272  741      Request for Jury Trial
273  4        Request for Jury Trial Transcript
274  1443     Request for Pluries Summons
275  799      Request for Preliminary Hearing
276  3        Request for Sound Recording - Crawford County
277  1499     Request for Summons by Certified Mail - Needs to be filed with Petition except S
278  735      Request for Supplemental Discovery
279  721      Request for Video Link
280  1850     Requirements for Rec Letter to Client
281  405      Requirements for a Petition for DL After Denial
282  742      Response to State's Motion for Continuance
283  1442     Response to State's Motion for Protective Order Regarding Discovery
284  1090     Robles Motion to Recall Warrant
285  14       SATOP Comparable Instructions
286  1153     SIS DWI No Companion Tickets - Eureka Muni
287  1169     Sample Hearing Questions - 10 year denial
288  1338     Sample Invoice
289  441      Schilf Mot for Extension of Time
290  776      Service Fee Memorandum - JCS
291  328      Shepard Disposition ltr
292  1156     Speeding to No Points closing letter
293  324      Statement Chart
294  262      Stealing SIS 5 Years
295  762      Substitution of Counsel
296  709      Substitution of Counsel (Within Firm)
297  311      Suggestion of Death
298  224      Sulejmani Motion for Supllemental Discovery
299  1662     Updated Rec Request (Requirements Met)
300  318      Virtual Court Apperance Template - WebEx
301  737      Waiver of Appearance and Guily Plea - Perry County
302  720      Waiver of Appearance and Guily Plea form
303  1119     Waiver of Arraignment
304  813      Waiver of Arraignment -
305  782      Waiver of Jury Trial - ATM
306  578      Waiver of Service
307  579      Waiver of Service - EMASS
308  580      Waiver of Service - Safety Council of Greater St Louis
309  60       Welcome Letter Draft
310  1445     Withdraw of Motion
311  751      Witness Endorsment
312  86       Witness List- ATM
313  1512     draft plack ltr to client Re Mot. to Withdraw Communication, Finance, Warrant
314  1513     draft plack ltr to client Re Mot. to Withdraw Communication, Warrant
315  431      invoice
316  1510     ltr to client Re Mot. to Withdraw
317  1152     ltr to client Re Mot. to Withdraw - Client Request
318  1559     ltr to client Re Mot. to Withdraw - No Upcoming Court Date
319  1509     ltr to client Re Mot. to Withdraw - PFR
320  1508     ltr to client Re Mot. to Withdraw Circuit Finance Communication
321  1504     ltr to client Re Mot. to Withdraw Circuit Finance No EA
322  1446     ltr to client Re Mot. to Withdraw Communication Issues - Creve Coeur
323  1560     ltr to client Re Mot. to Withdraw Communication Issues - No Upcoming Court Date
324  1556     ltr to client Re Mot. to Withdraw Communication Issues - Ste Genevieve County
325  1505     ltr to client Re Mot. to Withdraw Communication, Finance
326  1506     ltr to client Re Mot. to Withdraw Communication, Finance, Warrant
327  1511     ltr to client Re Mot. to Withdraw Finance Muni
328  1507     ltr to client Re Mot. to Withdraw Post-Conviction
329  1468     withdraw
```

---

## Notes

- The consolidated templates added by the import script (56 new templates) will become active after running the import
- These consolidated templates are new additions, not replacements of the 379 remaining templates
- After import runs, total active templates will be: 379 (remaining) + 56 (new consolidated) = **435 total active templates**
- The deactivation patterns are designed to retire old per-county or per-attorney variants, keeping only the consolidated universal templates

