# Spreetail Shared Expenses App — Final Implementation Plan (v2, gap-fixed)

This is a revision of the original plan. Every change below exists to close a
gap between the plan and (a) the assignment's stated requirements, or (b) a
question you would otherwise be unable to answer in the live session.
Changes from v1 are marked **[FIX]**.

## Objective

Build and deploy a shared expenses application that handles real-world
financial data, supports changing group memberships over time, provides
transparent balance calculations, and imports messy CSV data with full
anomaly detection, auditability, and user-controlled resolution.

The primary focus is not expense CRUD, but building a reliable import and
reconciliation system capable of handling imperfect data.

## Technology Stack

**Backend:** FastAPI, SQLAlchemy, Alembic, PostgreSQL
**Frontend:** React (Vite), TailwindCSS
**Deployment:** Frontend → Vercel, Backend → Render, Database → Neon PostgreSQL

## Database Schema

### users
- id, name, email, password_hash, created_at
- **[FIX]** `email` and `password_hash` are nullable
- **[FIX]** `is_guest BOOLEAN DEFAULT FALSE` — set true for non-member
  participants (e.g. Kabir) created by ParticipantRule. Guests can't log in
  but can appear in expense_splits.

### groups
- id, name, created_at

### group_memberships
- id, group_id, user_id, joined_at, left_at
- Tracks historical membership. `left_at` nullable = still active.

### expenses
- id, group_id, title, description, amount, currency, exchange_rate,
  normalized_amount, paid_by, expense_date, created_at
- **[FIX]** `is_refund BOOLEAN DEFAULT FALSE`
- **[FIX]** `refund_of_expense_id INTEGER NULL REFERENCES expenses(id)` —
  links a refund row to the original expense it offsets (nullable, best-effort
  match; if no confident match, leave null and still flag for review).

### expense_splits
- id, expense_id, user_id, split_type, split_amount, split_percentage

### settlements
- id, payer_id, receiver_id, amount, settlement_date, group_id

### deposits
- id, user_id, amount, deposit_date, group_id
- **[FIX]** added `group_id` — deposits are scoped to a group's shared pool.

### import_sessions
- id, filename, status, created_at

### anomalies
- id, import_session_id, row_number, anomaly_type, severity, detected_value,
  action_taken, requires_approval

### anomaly_reviews
- id, anomaly_id, decision, reviewed_by, reviewed_at
- **[FIX]** now reachable via `POST /anomalies/{id}/review` (see API section).

### person_aliases
- id, canonical_user_id, alias_name

## Import Pipeline

### Step 1: Upload CSV
User uploads `expenses_export.csv` exactly as provided. No manual edits.

### Step 2: Normalization Layer
- Names: lowercase + trim, look up in `person_aliases`, else fuzzy-match
  against known users (see Name Normalization below).
- Amounts: strip commas, round to 2 decimals (`1,200` → `1200.00`,
  `899.995` → `900.00`, using standard rounding).
- Dates: parse multiple formats into ISO `YYYY-MM-DD`. If unparseable or
  genuinely ambiguous (e.g. `04-05-2026` could be Apr 5 or May 4), flag via
  DateRule rather than guessing.

### Step 3: Validation Layer
Required fields, date validity, currency validity, split correctness,
membership validity (against `group_memberships`).

### Step 4: Anomaly Detection Engine

**[FIX] Rules run in this fixed order per row.** Earlier rules can short-circuit
later ones (e.g. a row converted to a Settlement skips SplitRule and
DuplicateRule entirely, since it's no longer an expense). This order exists
so the classification of any row is deterministic and explainable — if asked
"why was row 14 treated as X and not Y," the answer is always "rule N fired
first."

```python
class ValidationRule:
    def validate(row, context) -> AnomalyResult | None:
        pass

RULE_ORDER = [
    ParticipantRule,        # 1. resolve/create users for all named people
    NameNormalizationRule,  # 2. apply person_aliases, record new aliases
    DateRule,               # 3. parse/normalize date, flag ambiguous
    MembershipRule,         # 4. check participants vs group_memberships
    CurrencyRule,           # 5. normalize currency + compute normalized_amount
    SettlementRule,         # 6. "X paid Y back" pattern -> convert to settlement, STOP
    DepositRule,            # 7. "deposit" pattern -> convert to deposit, STOP
    RefundRule,             # 8. negative amount + "refund" in description -> refund
    NegativeAmountRule,     # 9. negative amount, no refund keyword -> flag, STOP
    ZeroAmountRule,         # 10. amount == 0 -> flag, require review
    SplitRule,              # 11. validate split_type / percentages sum to 100
    DuplicateRule,          # 12. exact duplicate check (runs last, post-normalization)
    NearDuplicateRule,      # 13. fuzzy duplicate w/ different amount
]
```

**[FIX] Duplicate matching definition.**
- *Exact duplicate*: same `group_id`, same `expense_date`, same `paid_by`,
  same `normalized_amount`, and normalized titles (lowercase, strip
  punctuation, collapse whitespace, sort words) are identical or have token
  overlap ≥ 0.8 (e.g. "Dinner at Marina Bites" vs "dinner - marina bites" →
  tokens {dinner, marina, bites} vs {dinner, marina, bites} = 1.0 overlap).
  Action: flag as `DuplicateRule`, severity `high`, `requires_approval=true`,
  default `action_taken = "kept_first_flagged_second"` — both rows are
  imported, the second is marked pending; nothing is auto-deleted (Meera's
  requirement).
- *Near-duplicate, different amount*: same match criteria above but
  `normalized_amount` differs. Action: `NearDuplicateRule`, severity `high`,
  both rows imported, `requires_approval=true`, `action_taken = "kept_both_pending_review"`.

**[FIX] Settlement detection.** Description matches a regex like
`r"(\w+)\s+paid\s+(\w+)\s+back"` (case-insensitive). `payer_id` = matched
group 1 (resolved via aliases), `receiver_id` = matched group 2. Row is
removed from `expenses` and inserted into `settlements`.
`requires_approval=true` always, since this is regex-based and could
misfire.

**[FIX] Deposit detection.** Description contains "deposit" (case-insensitive).
Row is removed from `expenses` and inserted into `deposits` with
`user_id = paid_by`, `group_id`, `amount = normalized_amount`.
`requires_approval=false` (low risk).

**[FIX] Refund vs. plain negative amount.** If `amount < 0`:
- If description contains "refund" → `RefundRule`. Set `is_refund=true`,
  `normalized_amount` stays negative (it subtracts from totals naturally).
  Attempt to match `refund_of_expense_id` to a prior expense in the same
  group with the same payer and a title token overlap ≥ 0.5; if no match,
  leave null. Always `requires_approval=true`.
- Else → `NegativeAmountRule`, severity `medium`, `requires_approval=true`,
  row is imported as-is but flagged — do not silently coerce to positive.

**[FIX] Exchange rate source (DECISIONS.md entry).** The CSV does not carry a
live rate column. Given the 1-hour constraint, use a **fixed, documented
rate table** in code: `{"USD": 83.0, "INR": 1.0}` (1 USD = 83 INR, INR is
base currency). This is a deliberate simplification — document it explicitly
as a known limitation with "use live FX API" as the stated future
improvement.

### Confirmed Anomalies (unchanged from v1, now mapped to RULE_ORDER above)

| Anomaly | Rule | Action |
|---|---|---|
| Duplicate expenses | DuplicateRule | flag, require approval, keep both |
| Duplicate w/ different amounts | NearDuplicateRule | flag, require approval, keep both |
| Missing payer | (validation layer) | reject row |
| Settlement recorded as expense | SettlementRule | convert to settlement |
| Deposit recorded as expense | DepositRule | convert to deposit |
| Currency conversion required | CurrencyRule | convert via fixed rate, store original + normalized |
| Negative amount | RefundRule / NegativeAmountRule | refund or flag |
| Missing currency | CurrencyRule | require review, default to group's base currency, flag |
| Ambiguous dates | DateRule | flag, require confirmation |
| Name variations | NameNormalizationRule | normalize, record alias |
| Non-member participants | ParticipantRule | create guest user, flag |
| Membership violations | MembershipRule | exclude member from split, flag |
| Zero amount | ZeroAmountRule | flag, require review |
| Percentage split validation | SplitRule | ensure sums to 100%, flag if not |
| Split type inconsistency | SplitRule | require manual review |

## Membership Timeline Logic

Validity: `joined_at <= expense_date <= left_at (or NULL = still active)`.
Never hardcode names/dates — always query `group_memberships`.

## Currency Handling

```
normalized_amount = original_amount × exchange_rate
```
`exchange_rate` comes from the fixed table above, keyed on `currency`.
Every balance calculation uses `normalized_amount` only.

## Balance Engine

```
Net Balance =
    Amount Paid (sum of normalized_amount where paid_by = user, excluding
                  rows where user was excluded by MembershipRule)
  − Amount Owed (sum of expense_splits.split_amount for user, in normalized terms)
  − Settlements Made
  + Settlements Received
  + Deposits Made          [FIX]
  − Refunds Received       [FIX] (refund reduces the original payer's "amount paid")
```

**[FIX] Deposit treatment (DECISIONS.md entry):** a deposit is treated as
additional "amount paid" by that user into the group's shared pool — i.e. it
increases their net balance (others owe them more / they owe less), exactly
as if they'd pre-paid for future shared expenses. This is a simplification;
a more correct model would track pool consumption separately, but that's out
of scope for the time available.

### Balance Explainability

`GET /users/{id}/explanation?group_id={id}` returns:
- Expenses Paid (list, with normalized_amount)
- Expense Shares (list, with normalized split amounts)
- Settlements Made/Received
- Deposits Made
- Refunds applied
- Final Balance Calculation (the arithmetic, shown explicitly — no hidden numbers)

### Settlement Optimization

Creditor-debtor minimization (greedy): sort debtors and creditors by amount,
repeatedly match the largest debtor to the largest creditor until all
balances are zero (within rounding tolerance of 0.01).

## Import Report

Generated after every import. For each anomaly: Row Number, Severity,
Anomaly Type, Original Value, Action Taken, Requires Approval.
Export as JSON and UI table.

## API Endpoints

### Authentication
- `POST /register`
- `POST /login`

### Groups
- `POST /groups`
- `GET /groups`
- `POST /groups/{id}/members` — add member (sets `joined_at`)
- **[FIX]** `PATCH /groups/{id}/members/{user_id}` — body `{left_at: date}`,
  closes a membership period. Required for Meera's move-out.

### Expenses
- `POST /expenses`
- `GET /expenses?group_id=`

### Settlements
- `POST /settlements`

### Balances
- **[FIX]** `GET /groups/{id}/balances` (was `/balances` — must be group-scoped)
- `GET /users/{id}/explanation?group_id=`
- **[FIX]** `GET /groups/{id}/balances/settlements` — optimized settlement suggestions

### Import
- `POST /import` — upload CSV, runs full pipeline, returns `import_session_id`
- `GET /import/{id}/report`

### Anomalies
- **[FIX]** `POST /anomalies/{id}/review` — body `{decision: "approve"|"reject",
  reviewed_by: user_id}`. Writes to `anomaly_reviews`. "Approve" finalizes the
  `action_taken`; "reject" reverts the row to its pre-anomaly state (e.g.
  un-flags a near-duplicate as "this is fine, both are real expenses" or
  removes the second of an exact duplicate). This is the endpoint that
  satisfies Meera's requirement.

## Documentation Deliverables (unchanged)

- `README.md` — Setup, Architecture, Deployment, Import Workflow, Assumptions
- `SCOPE.md` — All anomalies detected, detection logic, resolution policy,
  database schema, ER diagram
- `DECISIONS.md` — Decision / Alternatives / Chosen Solution / Reason for each
  significant call, **including the new ones flagged [FIX] above** (exchange
  rate source, deposit treatment, duplicate threshold, rule ordering)
- `AI_USAGE.md` — AI tools used, key prompts, incorrect outputs + corrections
  (minimum 3, logged as they happen, not reconstructed afterward)

## Development Priority (revised for ~1 hour remaining)

**Phase 1 (build + explain-ready, ~60% of time):**
1. Database schema + migrations (with the [FIX] columns)
2. Import pipeline + RULE_ORDER anomaly engine (this is what gets quizzed)
3. Membership logic + balance engine + explanation endpoint
4. Import report endpoint

**Phase 2 (~25% of time):**
5. Minimal expense/group/settlement CRUD + auth
6. `POST /anomalies/{id}/review`

**Phase 3 (~15% of time):**
7. Bare-minimum React frontend (login, import screen, balances table,
   anomaly review list) — function over polish
8. Deploy: Render (backend), Vercel (frontend), Neon (DB) — even a partially
   working deploy satisfies the "Public deployed app URL" requirement better
   than none
9. Write all four docs — DECISIONS.md can largely be filled from the [FIX]
   notes above, which are already pre-written rationale
