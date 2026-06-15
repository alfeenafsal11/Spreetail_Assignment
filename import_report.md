# CSV Import Anomaly Report

This report lists every anomaly detected during the ingestion of Expenses Export.csv (Import Session ID: 1), along with the automated action taken and review requirements.

| Row Number | Anomaly Rule | Severity | Detected Value | Action Taken | Requires Review |
|---|---|---|---|---|---|
| 6 | DuplicateRule | HIGH | Matches row 5 ('Dinner at Marina Bites') | kept_first_flagged_second | Yes |
| 9 | NameNormalizationRule | LOW | Raw: 'priya' normalized to 'Priya' | normalized_name | No |
| 11 | NameNormalizationRule | LOW | Raw: 'Priya S' normalized to 'Priya' | normalized_name | No |
| 13 | ValidationError | HIGH | {'date': '22-02-2026', 'description': 'House cleaning supplies', 'paid_by': '', 'amount': '780', 'currency': 'INR', 'split_type': 'equal', 'split_with': 'Aisha;Rohan;Priya;Meera', 'split_details': '', 'notes': "can't remember who paid"} | row_rejected | Yes |
| 14 | SettlementRule | MEDIUM | Rohan paid Aisha back | converted_to_settlement | Yes |
| 15 | SplitRule | HIGH | Sum of percentages: 110.0% | flagged_percentage_mismatch_kept_raw | Yes |
| 23 | ParticipantRule | MEDIUM | Kabir | flagged_non_member_participant | Yes |
| 26 | RefundRule | MEDIUM | Parasailing refund | linked_to_original_expense | Yes |
| 27 | NameNormalizationRule | LOW | Raw: 'rohan ' normalized to 'Rohan' | normalized_name | No |
| 27 | DateRule | MEDIUM | Mar-14 | parsed_date_requires_approval | Yes |
| 28 | CurrencyRule | MEDIUM | Empty currency field | defaulted_to_inr_pending_review | Yes |
| 31 | ZeroAmountRule | MEDIUM | 0.00 | imported_as_is_requires_review | Yes |
| 32 | SplitRule | HIGH | Sum of percentages: 110.0% | flagged_percentage_mismatch_kept_raw | Yes |
| 34 | DateRule | MEDIUM | 04-05-2026 | parsed_date_requires_approval | Yes |
| 36 | MembershipRule | HIGH | Split user Meera inactive on 2026-04-02 | excluded_inactive_user_from_split | Yes |
| 38 | DepositRule | LOW | Sam deposit share | converted_to_deposit | No |
| 42 | SplitRule | MEDIUM | Type equal, Details present: 'Aisha 1; Rohan 1; Priya 1; Sam 1' | honored_equal_split_ignored_details | Yes |
