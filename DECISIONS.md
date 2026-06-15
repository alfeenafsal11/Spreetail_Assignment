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

## 10. Settlements Sign Adjustment in Net Balance Formula
- **Decision:** Correct the net balance formula's settlement signs in code: `Net Balance = Expenses Paid - Amount Owed + Settlements Made - Settlements Received + Deposits Made - Refunds Received`.
- **Alternatives:** Follow the plan's written signs literally: `- Settlements Made + Settlements Received`.
- **Chosen Solution:** Swap the signs in code to `+ Settlements Made - Settlements Received`.
- **Reason:** The written formula in the plan had swapped signs. If B owes A 25 INR, A is a creditor (+25) and B is a debtor (-25). If B pays A 25 INR (settlement), B makes a settlement (+25) and A receives a settlement (+25). B's balance should go to 0 (`-25 + 25 = 0`), and A's balance should go to 0 (`+25 - 25 = 0`). Swapping the signs is mathematically required for proper balance resolution.

## 11. Non-Zero Total Balance Sum Reconciliation
- **Decision:** Document and accept that the sum of all net user balances is exactly `+14,636.00 INR` instead of `0.00 INR`.
- **Reason:** The sum is non-zero due to two factors:
  1. **Sam's Deposit (+15,000.00 INR):** A deposit represents funds paid into the group's shared pool. Since the pool is an asset and not a user, this cash input increases Sam's credit by +15,000 INR without a matching user-balance decrease.
  2. **110% Percentage Splits (-364.00 INR):** Two rows in the CSV have percentage splits summing to 110% instead of 100%: Row 15 Pizza Friday (1,440.00 INR total, 10% mismatch = `-144.00 INR`) and Row 32 Weekend brunch (2,200.00 INR total, 10% mismatch = `-220.00 INR`). These mismatches increase total Owed by +364 INR, resulting in a `-364.00 INR` balance reduction.
  Reconciliation: `15,000.00 INR (deposit) - 364.00 INR (mismatches) = 14,636.00 INR`. Because of this non-zero sum, the settlement optimizer cannot fully zero out all user balances (a net surplus of +14,636.00 INR remains).

