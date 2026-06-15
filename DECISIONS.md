# Architectural Decisions Log

## 1. Split Type Enumeration
- **Decision:** Use lowercase values `equal`, `percentage`, `unequal`, and `share` for `expense_splits.split_type` to exactly match the CSV fields.
- **Alternatives:** Use title case `Equal`, `Percentage`, `Exact`, `Custom` as in the original plan.
- **Chosen Solution:** Lowercase `equal`, `percentage`, `unequal`, `share`.
- **Reason:** The real CSV values are lowercase and maps to these exact split behaviors. Aligning DB schema and parser with real CSV values avoids translation logic and complexity.

## 2. Dev Temporary Membership Period Inference
- **Decision:** Seed `group_memberships` for `Dev` with `joined_at = 2026-02-08` and `left_at = 2026-03-12`.
- **Alternatives:** Do not seed membership and flag all Dev's appearances as anomalies.
- **Chosen Solution:** Pre-seed a membership record matching Dev's exact window of activity.
- **Reason:** Dev is a temporary participant. We can infer his membership dates from his first (Feb 8) and last (Mar 12) appearance in the CSV. Pre-seeding this prevents generating 8 redundant "Non-Member Participant" anomaly flags and reflects a cleaner state.

## 3. Kabir Guest Status and Membership
- **Decision:** Do not create a membership record for Kabir. Create him on the fly with `is_guest = True` via `ParticipantRule` when row 23 is processed. Flag a single "Non-Member Participant" anomaly.
- **Alternatives:** Pre-seed a membership record for Kabir or reject the row.
- **Chosen Solution:** Live guest creation and anomaly flag.
- **Reason:** Kabir only appears once as a guest of Dev ("Dev's friend Kabir") and is not a permanent group member, so he has no membership record.

## 4. Kabir One-Off Alias Mapping
- **Decision:** Seed `person_aliases` with `"Dev's friend Kabir" -> Kabir`.
- **Alternatives:** Write generic NLP parsing to extract "Kabir" from "Dev's friend Kabir".
- **Chosen Solution:** A one-off literal string match in database aliases.
- **Reason:** The phrase "Dev's friend Kabir" is a one-off literal string mapping to Kabir in this CSV. Generalizing possessive phrase parsing is out of scope and error-prone for the time available.

## 5. Whitespace Trimming in Name Normalization
- **Decision:** Trim leading and trailing whitespace from the `paid_by` and `split_with` fields before checking `person_aliases`.
- **Alternatives:** Require exact string match including trailing spaces.
- **Chosen Solution:** Trim name whitespace before lookup.
- **Reason:** Row 27 has a trailing space in `paid_by = "rohan "`. Whitespace trimming ensures robust matching.

## 6. Currency Source and Defaulting
- **Decision:** Use a fixed exchange rate table `{"USD": 83.0, "INR": 1.0}`. Default empty currency field to `INR` and flag as `Missing Currency`.
- **Alternatives:** Integrate a live forex API or require manual entry.
- **Chosen Solution:** Fixed conversion table and defaulting.
- **Reason:** Only INR and USD appear in the CSV. A fixed table simplifies development and satisfies project scope. Defaulting empty values (as in row 28 "Groceries DMart") to the base currency (INR) and flagging ensures auditability.

## 7. Ambiguous Date Flagging
- **Decision:** Parse `Mar-14` as `2026-03-14` and `04-05-2026` as `2026-05-04` (DD-MM-YYYY convention). Flag both with `requires_approval = True` in `DateRule`.
- **Alternatives:** Silently parse and correct, or reject the rows.
- **Chosen Solution:** Parse and flag for approval.
- **Reason:** Both dates are ambiguous (one has no year, the other is format-ambiguous between MM-DD and DD-MM). Flagging them allows auditability and control.

## 8. Group Column Absence in CSV
- **Decision:** Pre-seed and use a single group "The Flat" (`group_id = 1`) for all imported rows.
- **Alternatives:** Fail the import, or parse group names from descriptions.
- **Chosen Solution:** Import all rows into one default group.
- **Reason:** The CSV has no group column. Associating everything with a single seeded group is the most logical simplification.

## 9. Deposit Treatment
- **Decision:** Treat deposits as pre-payments that increase a user's net balance directly.
- **Alternatives:** Track deposits in a separate pool account.
- **Chosen Solution:** Direct addition to net balance.
- **Reason:** Simple and effective. It represents the member paying cash into the group's shared pool, which naturally offsets their future owed shares.
