# AGENT GUIDE — Spreetail Shared Expenses App
### For use in Antigravity with Sonnet 4.6 and/or Gemini 3.5 Flash

## How to use this file
Paste this whole file as the system/task prompt for your coding agent, then
attach `Spreetail_Final_Implementation_Plan.md` and `expenses_export.csv` as
context. Work through the phases **in order, top to bottom**. Do not skip
ahead — each phase produces things the next phase depends on.

This guide is written to be deterministic on purpose: it spells out schemas,
rule order, and formulas explicitly rather than leaving them to the model's
judgment. Both Sonnet 4.6 and Gemini 3.5 Flash should produce near-identical
output from this file. If using Gemini 3.5 Flash, follow each numbered step
literally and in isolation — do not let it batch multiple phases into one
generation, as smaller models tend to drop earlier requirements when given
too much scope at once.

## Non-negotiable constraints (apply to every phase)
1. Every file the agent writes must be something you (the human) can explain
   line-by-line in a live session. If the agent generates something you
   don't understand, ask it to explain that block before moving on — do not
   accept code you can't defend.
2. `expenses_export.csv` is read-only. No row may be edited before import.
3. Every anomaly rule must be its own function/class implementing
   `ValidationRule`, in the exact order given in
   `Spreetail_Final_Implementation_Plan.md` under "Anomaly Detection Engine."
4. After EVERY phase, commit to git with a message describing what was built
   (the "meaningful commit history" requirement is graded).
5. As you go, whenever the AI gets something wrong and you correct it, append
   a short entry to `AI_USAGE.md` immediately — don't try to reconstruct this
   at the end. You need a minimum of 3 real entries.

---

## Phase 0 — Setup (5 min)
- [ ] Initialize repo, FastAPI + SQLAlchemy + Alembic project skeleton
- [ ] Initialize React (Vite) + Tailwind frontend skeleton
- [ ] Open `expenses_export.csv` and dump the first 20 rows + column headers
      to confirm: actual column names, which split types appear (Equal /
      Percentage / Exact / Custom — confirm all 4 are real, or adjust schema
      if a different set appears), and confirm currency values present.
- [ ] Commit: "project skeleton"

**Checkpoint:** agent must report the actual CSV columns and split types
found before proceeding. If the split types differ from the plan, update
`expense_splits.split_type` enum accordingly and note it in DECISIONS.md.

## Phase 1 — Database schema + migrations (10 min)
- [ ] Implement all tables exactly as listed in
      `Spreetail_Final_Implementation_Plan.md` "Database Schema" section,
      including every line marked **[FIX]** (nullable email/password_hash,
      `is_guest`, `is_refund`, `refund_of_expense_id`, `group_id` on
      deposits/settlements).
- [ ] Generate Alembic migration, apply to local/Neon Postgres.
- [ ] Write `SCOPE.md` section "Database schema" + ER diagram (mermaid or
      image) now, while the schema is fresh — don't defer to the end.
- [ ] Commit: "database schema + migrations"

**Checkpoint:** run the migration and confirm it applies cleanly with no
errors. If it fails, fix before continuing — do not proceed with a broken DB.

## Phase 2 — Import pipeline + anomaly engine (the core — 20 min)
Build in this exact sub-order:

- [ ] 2a. Normalization layer: name lookup/alias matching, amount cleanup
      (strip commas, round to 2dp), date parsing into ISO format.
- [ ] 2b. Implement `ValidationRule` base class and **all 13 rules in
      `RULE_ORDER`** from the plan, in that exact order, each as a separate
      function/class. Each rule returns either `None` (no anomaly) or an
      `AnomalyResult` with `anomaly_type`, `severity`, `detected_value`,
      `action_taken`, `requires_approval`.
- [ ] 2c. Pipeline runner: for each CSV row, run rules in `RULE_ORDER`,
      respecting the "STOP" rules (SettlementRule, DepositRule,
      NegativeAmountRule short-circuit remaining rules for that row — see
      plan for exactly which ones stop).
- [ ] 2d. Write resulting expenses/settlements/deposits/anomalies to DB
      inside one `import_session`.
- [ ] 2e. `GET /import/{id}/report` — returns the anomalies table (JSON).
- [ ] 2f. Append to `SCOPE.md`: full anomaly log table (one row per anomaly
      type found, matching the table in the plan) and resolution policy for
      each.
- [ ] Commit: "import pipeline + anomaly detection engine"

**Checkpoint — run the actual import now** against `expenses_export.csv` and
print the anomaly report. Read through every flagged row yourself. If
something looks wrong (e.g. a real duplicate wasn't caught, or a normal
expense was wrongly flagged), fix the relevant rule now — this is the part
you'll be quizzed on most heavily.

## Phase 3 — Membership + balance engine (10 min)
- [ ] `PATCH /groups/{id}/members/{user_id}` to set `left_at`.
- [ ] Membership validity check used by MembershipRule (already wired in
      Phase 2) — confirm it's actually querying `group_memberships`, not
      hardcoded names.
- [ ] Balance engine implementing the exact formula in the plan (including
      Deposits Made and Refunds Received).
- [ ] `GET /groups/{id}/balances`
- [ ] `GET /groups/{id}/balances/settlements` (greedy min-cashflow as
      described in plan)
- [ ] `GET /users/{id}/explanation?group_id=` — returns the itemized
      breakdown with the arithmetic shown explicitly.
- [ ] Commit: "membership logic + balance engine + explainability endpoint"

**Checkpoint:** manually hand-calculate one user's balance from the imported
CSV data and compare to the API output. If they don't match, debug now — you
will be asked to do this exact walkthrough live.

## Phase 4 — Remaining CRUD + review endpoint (10 min)
- [ ] Auth: `POST /register`, `POST /login` (JWT)
- [ ] `POST /groups`, `GET /groups`, `POST /groups/{id}/members`
- [ ] `POST /expenses`, `GET /expenses?group_id=`
- [ ] `POST /settlements`
- [ ] `POST /anomalies/{id}/review` — approve/reject, writes
      `anomaly_reviews`, and on reject reverts the row per the plan
- [ ] Commit: "auth, group/expense/settlement CRUD, anomaly review endpoint"

## Phase 5 — Minimal frontend (10 min)
Function over polish. Required screens only:
- [ ] Login/register
- [ ] CSV import screen → shows import report table
- [ ] Anomaly review list with approve/reject buttons → calls
      `/anomalies/{id}/review`
- [ ] Group balances table → calls `/groups/{id}/balances`
- [ ] User explanation view → calls `/users/{id}/explanation`
- [ ] Commit: "minimal frontend"

If time is critically short, cut this phase down to import + balances views
only — auth can be stubbed with a hardcoded test user. Note this as a known
limitation in README.md rather than leaving it unexplained.

## Phase 6 — Deploy + finish docs (10 min)
- [ ] Neon: create Postgres DB, run migrations against it
- [ ] Render: deploy backend, set env vars (DB URL, JWT secret, exchange
      rate config)
- [ ] Vercel: deploy frontend, point at Render backend URL
- [ ] Smoke-test the deployed URL: register → login → import CSV → view
      balances. If any step 500s, fix before final commit.
- [ ] `README.md`: setup, architecture, deployment, import workflow,
      assumptions (including the fixed exchange rate and deposit-handling
      simplifications)
- [ ] `DECISIONS.md`: pull directly from every **[FIX]**/"DECISIONS.md entry"
      note in the implementation plan — these are pre-written rationale, just
      format them as Decision / Alternatives / Chosen / Reason
- [ ] `AI_USAGE.md`: finalize, confirm ≥ 3 real entries
- [ ] Final commit: "deployment + documentation"
- [ ] Submit: deployed URL + GitHub repo link

---

## If you run out of time
Priority order for what to cut, worst-case:
1. Frontend polish (already minimal)
2. Phase 4 CRUD endpoints beyond what Phase 5's screens call
3. Deployment of frontend (backend deploy + README explaining how to run
   frontend locally is a fallback, but try hard not to cut this — "deployed
   app URL" is a hard requirement)

**Never cut:** Phase 2 (import/anomaly engine) or Phase 3 (balance engine +
explainability). These are the entire point of the assignment and the
primary subject of the live session.
