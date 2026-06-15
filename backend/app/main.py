from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date as date_type
from typing import List, Optional
from app.database import get_db
from app import models
from app.pipeline import run_import_pipeline
from app.balances import calculate_user_balances, optimize_settlements_greedy, get_user_breakdown
from app.auth import get_password_hash, verify_password, create_access_token

app = FastAPI(title="Spreetail Shared Expenses App")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Schemas ---

class RegisterRequest(BaseModel):
    name: str
    email: Optional[str] = None
    password: str

class LoginRequest(BaseModel):
    name: str
    password: str

class MembershipUpdate(BaseModel):
    left_at: date_type

class GroupCreate(BaseModel):
    name: str

class MemberAdd(BaseModel):
    user_id: int
    joined_at: date_type

class ExpenseCreate(BaseModel):
    group_id: int
    title: str
    description: Optional[str] = None
    amount: float
    currency: str
    paid_by: int
    expense_date: date_type
    split_type: str
    split_with_ids: List[int]
    split_details: Optional[str] = None

class SettlementCreate(BaseModel):
    payer_id: int
    receiver_id: int
    amount: float
    settlement_date: date_type
    group_id: int

class AnomalyReviewRequest(BaseModel):
    decision: str  # approve, reject
    reviewed_by: int

# --- Helper split builder ---

def create_expense_splits(db: Session, expense_id: int, total_amount: float, split_type: str, split_with_ids: list[int], split_details_str: str = None):
    n = len(split_with_ids)
    if n == 0:
        return
        
    if split_type == "equal":
        base_share = round(total_amount / n, 2)
        shares = [base_share] * n
        diff = round(total_amount - sum(shares), 2)
        if diff != 0:
            shares[0] = round(shares[0] + diff, 2)
        for uid, amt in zip(split_with_ids, shares):
            split = models.ExpenseSplit(
                expense_id=expense_id,
                user_id=uid,
                split_type=split_type,
                split_amount=amt,
                split_percentage=round(100.0 / n, 2)
            )
            db.add(split)
            
    elif split_type == "percentage":
        # Parse percentage details: "Name value; Name value; ..."
        parsed = {}
        if split_details_str:
            parts = split_details_str.split(";")
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                rparts = part.rsplit(None, 1)
                if len(rparts) == 2:
                    k, v_str = rparts
                    if v_str.endswith("%"):
                        v_str = v_str[:-1]
                    try:
                        parsed[k.strip().lower()] = float(v_str)
                    except ValueError:
                        pass
        for uid in split_with_ids:
            user = db.get(models.User, uid)
            pct = parsed.get(user.name.lower(), 0.0) if user else 0.0
            if pct == 0.0:
                pct = parsed.get(str(uid), 0.0)
            amt = round(total_amount * (pct / 100.0), 2)
            split = models.ExpenseSplit(
                expense_id=expense_id,
                user_id=uid,
                split_type=split_type,
                split_amount=amt,
                split_percentage=pct
            )
            db.add(split)
            
    elif split_type == "unequal":
        # Parse unequal details
        parsed = {}
        if split_details_str:
            parts = split_details_str.split(";")
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                rparts = part.rsplit(None, 1)
                if len(rparts) == 2:
                    k, v_str = rparts
                    try:
                        parsed[k.strip().lower()] = float(v_str)
                    except ValueError:
                        pass
        for uid in split_with_ids:
            user = db.get(models.User, uid)
            val = parsed.get(user.name.lower(), 0.0) if user else 0.0
            if val == 0.0:
                val = parsed.get(str(uid), 0.0)
            split = models.ExpenseSplit(
                expense_id=expense_id,
                user_id=uid,
                split_type=split_type,
                split_amount=val,
                split_percentage=round((val / total_amount * 100.0) if total_amount > 0 else 0.0, 2)
            )
            db.add(split)
            
    elif split_type == "share":
        # Parse weights
        parsed = {}
        if split_details_str:
            parts = split_details_str.split(";")
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                rparts = part.rsplit(None, 1)
                if len(rparts) == 2:
                    k, v_str = rparts
                    try:
                        parsed[k.strip().lower()] = float(v_str)
                    except ValueError:
                        pass
        total_shares = sum(parsed.values()) if parsed else 1.0
        if total_shares <= 0:
            total_shares = 1.0
        temp_splits = []
        for uid in split_with_ids:
            user = db.get(models.User, uid)
            w = parsed.get(user.name.lower(), 1.0) if user else 1.0
            if w == 1.0 and str(uid) in parsed:
                w = parsed.get(str(uid), 1.0)
            amt = round(total_amount * (w / total_shares), 2)
            temp_splits.append((uid, amt, w))
            
        diff = round(total_amount - sum(s[1] for s in temp_splits), 2)
        if diff != 0 and len(temp_splits) > 0:
            temp_splits[0] = (temp_splits[0][0], round(temp_splits[0][1] + diff, 2), temp_splits[0][2])
            
        for uid, amt, w in temp_splits:
            split = models.ExpenseSplit(
                expense_id=expense_id,
                user_id=uid,
                split_type=split_type,
                split_amount=amt,
                split_percentage=round((w / total_shares * 100.0), 2)
            )
            db.add(split)

# --- Routes ---

@app.get("/")
def read_root():
    return {"message": "Welcome to Spreetail Shared Expenses App API"}

# --- Auth ---

@app.post("/register")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter_by(name=data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
        
    user = models.User(
        name=data.name,
        email=data.email,
        password_hash=get_password_hash(data.password),
        is_guest=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Registration successful", "user_id": user.id, "name": user.name}

@app.post("/login")
def login_user(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(name=data.name, is_guest=False).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
        
    access_token = create_access_token(data={"sub": user.name, "user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id, "name": user.name}

# --- Groups ---

@app.post("/groups")
def create_group(data: GroupCreate, db: Session = Depends(get_db)):
    group = models.Group(name=data.name)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group

@app.get("/groups")
def list_groups(db: Session = Depends(get_db)):
    return db.query(models.Group).all()

@app.post("/groups/{group_id}/members")
def add_group_member(group_id: int, data: MemberAdd, db: Session = Depends(get_db)):
    group = db.get(models.Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    user = db.get(models.User, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Check if membership already exists
    existing = db.query(models.GroupMembership).filter_by(group_id=group_id, user_id=data.user_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member of this group")
        
    membership = models.GroupMembership(
        group_id=group_id,
        user_id=data.user_id,
        joined_at=data.joined_at
    )
    db.add(membership)
    db.commit()
    return {"message": "Member added successfully", "group_id": group_id, "user_id": data.user_id}

@app.patch("/groups/{group_id}/members/{user_id}")
def update_group_membership(group_id: int, user_id: int, data: MembershipUpdate, db: Session = Depends(get_db)):
    membership = db.query(models.GroupMembership).filter_by(group_id=group_id, user_id=user_id).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership record not found")
        
    membership.left_at = data.left_at
    db.commit()
    return {"message": "Membership successfully updated", "user_id": user_id, "left_at": str(data.left_at)}

# --- Expenses ---

@app.post("/expenses")
def create_expense(data: ExpenseCreate, db: Session = Depends(get_db)):
    # Calculate exchange rate and normalized amount
    rates = {"USD": 83.0, "INR": 1.0}
    rate = rates.get(data.currency.upper(), 1.0)
    normalized_amount = round(data.amount * rate, 2)
    
    expense = models.Expense(
        group_id=data.group_id,
        title=data.title,
        description=data.description,
        amount=data.amount,
        currency=data.currency.upper(),
        exchange_rate=rate,
        normalized_amount=normalized_amount,
        paid_by=data.paid_by,
        expense_date=data.expense_date,
        is_refund=False
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    
    # Create Splits
    create_expense_splits(db, expense.id, normalized_amount, data.split_type, data.split_with_ids, data.split_details)
    db.commit()
    return expense

@app.get("/expenses")
def list_expenses(group_id: int, db: Session = Depends(get_db)):
    return db.query(models.Expense).filter_by(group_id=group_id).order_by(models.Expense.expense_date.desc()).all()

# --- Settlements ---

@app.post("/settlements")
def create_settlement(data: SettlementCreate, db: Session = Depends(get_db)):
    settlement = models.Settlement(
        payer_id=data.payer_id,
        receiver_id=data.receiver_id,
        amount=data.amount,
        settlement_date=data.settlement_date,
        group_id=data.group_id
    )
    db.add(settlement)
    db.commit()
    db.refresh(settlement)
    return settlement

# --- Balances ---

@app.get("/groups/{group_id}/balances")
def get_group_balances(group_id: int, db: Session = Depends(get_db)):
    group = db.get(models.Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
        
    balances_dict = calculate_user_balances(db, group_id)
    balances_report = []
    
    for uid, net_bal in balances_dict.items():
        user = db.get(models.User, uid)
        balances_report.append({
            "user_id": uid,
            "name": user.name,
            "is_guest": user.is_guest,
            "net_balance": net_bal
        })
        
    # Sort by name for neat list
    balances_report.sort(key=lambda x: x["name"])
    return {
        "group_id": group_id,
        "group_name": group.name,
        "balances": balances_report
    }

@app.get("/groups/{group_id}/balances/settlements")
def get_group_optimized_settlements(group_id: int, db: Session = Depends(get_db)):
    group = db.get(models.Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
        
    balances_dict = calculate_user_balances(db, group_id)
    
    username_balances = {}
    for uid, net_bal in balances_dict.items():
        user = db.get(models.User, uid)
        username_balances[user.name] = net_bal
        
    suggestions = optimize_settlements_greedy(username_balances)
    return {
        "group_id": group_id,
        "group_name": group.name,
        "settlements": suggestions
    }

@app.get("/users/{user_id}/explanation")
def get_user_balance_explanation(user_id: int, group_id: int, db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    group = db.get(models.Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
        
    breakdown = get_user_breakdown(db, group_id, user_id)
    return breakdown

# --- Import ---

@app.post("/import")
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        content = await file.read()
        csv_text = content.decode("utf-8")
        session_id = run_import_pipeline(db, csv_text, file.filename)
        return {
            "message": "CSV imported successfully",
            "import_session_id": session_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")

@app.get("/import/{session_id}/report")
def get_import_report(session_id: int, db: Session = Depends(get_db)):
    session = db.get(models.ImportSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Import session not found")
        
    anomalies = db.query(models.Anomaly).filter_by(import_session_id=session_id).order_by(models.Anomaly.row_number).all()
    
    report = []
    for anomaly in anomalies:
        report.append({
            "id": anomaly.id,
            "row_number": anomaly.row_number,
            "anomaly_type": anomaly.anomaly_type,
            "severity": anomaly.severity,
            "detected_value": anomaly.detected_value,
            "action_taken": anomaly.action_taken,
            "requires_approval": anomaly.requires_approval
        })
        
    return {
        "filename": session.filename,
        "status": session.status,
        "created_at": session.created_at,
        "anomalies_count": len(report),
        "anomalies": report
    }

# --- Anomalies Review ---

@app.post("/anomalies/{anomaly_id}/review")
def review_anomaly(anomaly_id: int, data: AnomalyReviewRequest, db: Session = Depends(get_db)):
    anomaly = db.get(models.Anomaly, anomaly_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
        
    # Check if already reviewed
    existing_review = db.query(models.AnomalyReview).filter_by(anomaly_id=anomaly_id).first()
    if existing_review:
        raise HTTPException(status_code=400, detail="Anomaly has already been reviewed")
        
    review = models.AnomalyReview(
        anomaly_id=anomaly_id,
        decision=data.decision,
        reviewed_by=data.reviewed_by
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    
    # Audit logic if decision is to reject
    if data.decision == "reject":
        if anomaly.anomaly_type == "DuplicateRule":
            # Revert duplicate by deleting the duplicate expense
            expense = db.query(models.Expense).filter_by(
                import_session_id=anomaly.import_session_id,
                row_number=anomaly.row_number
            ).first()
            if expense:
                db.delete(expense)
                db.commit()
                
    return {"message": "Anomaly review successfully logged", "review_id": review.id, "decision": data.decision}
