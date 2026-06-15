# Spreetail Shared Expenses App

A shared expenses application built to parse financial CSV transaction sheets, perform robust multi-layered anomaly detection with human-in-the-loop review overrides, handle historic group memberships, and optimize debt clearance.

## Technology Stack

- **Backend:** FastAPI, SQLAlchemy, Alembic, SQLite (for local development), PostgreSQL (for production/Neon)
- **Frontend:** React (Vite), Vanilla CSS (custom glassmorphic theme)
- **Deployment target:** Backend → Render, Frontend → Vercel, Database → Neon Postgres

---

## Local Development Setup

### 1. Prerequisites
- Python 3.10+
- Node.js 18+

### 2. Backend Setup
1. Open a terminal and navigate to the `backend` folder:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run Alembic migrations to create database schema:
   ```bash
   alembic upgrade head
   ```
5. Seed initial group membership and name aliases:
   ```bash
   python -m app.seeding
   ```
6. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   The API will be available at [http://localhost:8000](http://localhost:8000).

### 3. Frontend Setup
1. Open a terminal and navigate to the `frontend` folder:
   ```bash
   cd frontend
   ```
2. Install npm dependencies:
   ```bash
   npm install
   ```
3. Start the Vite React development server:
   ```bash
   npm run dev
   ```
   Open your browser to the URL printed in the console (usually [http://localhost:5173](http://localhost:5173)).

---

## Import Workflow & Anomaly Detection

1. **Upload CSV:** Users upload `Expenses Export.csv` directly into the "Import Center".
2. **Normalization:** Column fields are formatted: whitespace trimmed from names, amounts cleaned (commas stripped and rounded to 2 decimals), and dates parsed.
3. **13 Ordered Validation Rules:** The engine evaluates every row against `RULE_ORDER`:
   1. `ParticipantRule` — Creates guest users on-the-fly and flags non-members.
   2. `NameNormalizationRule` — Normalizes case and maps name aliases.
   3. `DateRule` — Parses date and flags format ambiguity.
   4. `MembershipRule` — Excludes inactive members from split calculations.
   5. `CurrencyRule` — Sets base currency (INR), defaults empty currency to INR, and performs conversion (1 USD = 83 INR).
   6. `SettlementRule` — Detects regex `"X paid Y back"`, inserts a `Settlement` record, and **STOPS** downstream validation.
   7. `DepositRule` — Detects `"deposit"`, inserts a `Deposit` record, and **STOPS** downstream validation.
   8. `RefundRule` — Matches negative amounts with "refund" keyword, links to original expense, and flags for approval.
   9. `NegativeAmountRule` — Flags negative amounts without refund keyword and **STOPS** validation.
   10. `ZeroAmountRule` — Flags amounts equal to 0.00.
   11. `SplitRule` — Validates unequal/percentage/share split sums and type inconsistencies.
   12. `DuplicateRule` — Flags exact duplicates (overlap >= 80%, same date/amount/payer/group).
   13. `NearDuplicateRule` — Flags near duplicates (same as above but different amounts).
4. **Audit and Review Override:** High-severity anomalies (like exact duplicates) require approval.
   - **Approve:** Finalizes the automated action.
   - **Reject:** Reverts the row. For example, rejecting a `DuplicateRule` anomaly deletes the duplicate expense from the database, and rejecting a `NearDuplicateRule` anomaly accepts both as normal, un-flagged expenses.

---

## Key Design Assumptions

1. **Single Group Scope:** Since the CSV contains no group column, all imported records default to a single pre-seeded group "The Flat". Endpoints are fully group-scoped in the schema for multi-group scalability, but the CSV pipeline maps to this default.
2. **Fixed Exchange Rate:** A fixed exchange rate table `{"USD": 83.0, "INR": 1.0}` is implemented. A live FX API is planned for future improvement.
3. **Deposit Simplification:** Deposits are treated as pre-payments into the group's shared pool, which directly increases the depositor's net balance.
4. **Guest Membership Timeline:** Guest users (like Kabir) participate in splits without requiring explicit group membership records. Only regular members are validated against membership timeline slots.
5. **Ambiguous Dates:** Unusual date formats (e.g. `Mar-14`) and format-ambiguous dates (e.g. `04-05-2026`) are parsed per convention but flagged to require audit approval.

---

## Production Deployment Instructions

### 1. Database (Neon PostgreSQL)
1. Register on [Neon](https://neon.tech) and create a PostgreSQL database.
2. Copy the Connection String URI.

### 2. Backend (Render)
1. Connect your GitHub repository to [Render](https://render.com).
2. Create a Web Service pointing to the `backend` folder.
3. Set Build Command: `pip install -r requirements.txt`
4. Set Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Configure Environment Variables:
   - `DATABASE_URL`: Your Neon Connection String URI.
   - `JWT_SECRET`: A secure random secret string.

### 3. Frontend (Vercel)
1. Connect your repository to [Vercel](https://vercel.com).
2. Create a Project pointing to the `frontend` folder.
3. Configure Environment Variables:
   - `VITE_API_URL`: The deployed URL of your Render backend.
