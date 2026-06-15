# CSV-Verified Patch to Spreetail_Final_Implementation_Plan.md

This file records the deltas found by checking the implementation plan
against the real `expenses_export.csv`. Keep this alongside DECISIONS.md —
several entries below should be copied into it verbatim.

## 1. split_type enum correction
**Plan said:** Equal, Percentage, Exact Amount, Custom
**Actual CSV values:** `equal`, `percentage`, `unequal`, `share` (lowercase)

Mapping:
- `equal` → divide `amount` evenly across everyone in `split_with`
- `percentage` → `split_details` gives per-person `%`, must sum to 100
  (rows "Pizza Friday" and "Weekend Brunch" both sum to 110% — both must be
  flagged by SplitRule)
- `unequal` → `split_details` gives exact per-person rupee amounts, must sum
  to `amount` (row "Aisha birthday cake": 700+400+400=1500=amount, valid)
- `share` → `split_details` gives integer weights, divide `amount`
  proportionally (rows "Scooter rentals", "April rent")

`split_details` format: `"Name value; Name value; ..."`, `;`-separated,
`%` suffix only for percentage type. Build one shared parser, used by
SplitRule for all four types.

**Split Type Inconsistency confirmed:** "Furniture for common room" has
`split_type=equal` but a populated `split_details` field. SplitRule flags
this, `requires_approval=true`, default action = honor `split_type` (treat
as equal, ignore the stray `split_details`) pending human review.

## 2. Dev — temporary member, not repeated non-member flags
Dev appears in 8 rows (Feb 8 – Mar 12). Pre-seed a `group_memberships`
record: `joined_at = 2026-02-08`, `left_at = 2026-03-12`, inferred from his
first/last appearance in the CSV. This avoids 8 redundant "Non-Member
Participant" anomalies. **DECISIONS.md entry:** document this inference
explicitly as a deliberate simplification.

Kabir (row 23 only) gets **no** membership record — created live by
ParticipantRule as `is_guest=true`, flagged once as Non-Member Participant.

## 3. "Dev's friend Kabir" alias
Row 23's `split_with` contains the literal string `Dev's friend Kabir`, not
`Kabir`. Add a one-off `person_aliases` seed entry:
`"Dev's friend Kabir" -> Kabir`. **DECISIONS.md entry:** note this is a
literal-string alias, not general possessive-phrase parsing — out of scope
given time constraints.

## 4. Whitespace trimming
Row 27: `paid_by = "rohan "` (trailing space). Confirm NameNormalizationRule
trims before alias lookup. (Was implied in v2; now confirmed required.)

## 5. Single group, no group column in CSV
The CSV has no group identifier. Import seeds/uses one default group (e.g.
"The Flat"). All rows import into it. Multi-group endpoints (`POST /groups`
etc.) are still built per spec but this import doesn't exercise them — note
as an assumption in README.md.

## 6. Date ambiguity — confirmed rows
File convention is DD-MM-YYYY throughout. Two rows are flagged by DateRule
with `requires_approval=true`:
- `Mar-14` (no year, month-name format) → parse as `2026-03-14`
- `04-05-2026` (own notes call this out as ambiguous) → parse as
  `2026-05-04` per the file's DD-MM-YYYY convention

Both are flagged regardless of the parse result — the point is surfacing the
ambiguity, not silently resolving it.

## 7. Missing currency
Row "Groceries DMart" (15-03-2026, Priya) has an empty currency field →
default to INR, flag as Missing Currency. Confirmed matches plan.

## Unchanged — verified correct against real data
- RULE_ORDER and all 13 rules (no reordering needed)
- Exact duplicate definition (rows "Dinner at Marina Bites" / "dinner -
  marina bites" — token overlap 1.0, same date/payer/amount)
- Near-duplicate-different-amount (rows "Dinner at Thalassa" 2400 / "Thalassa
  dinner" 2450)
- Settlement detection regex ("Rohan paid Aisha back")
- Deposit detection ("Sam deposit share")
- Refund linking ("Parasailing refund" -30 USD → "Parasailing" 150 USD,
  same payer Dev, token overlap 0.5)
- Fixed exchange rate table (only INR/USD appear)
- Missing payer row ("House cleaning supplies")
- Zero amount row ("Dinner order Swiggy")
- Membership violation: Meera included in "Groceries BigBasket" (02-04-2026)
  after her `left_at = 2026-03-31` — exclude her from the split, flag
