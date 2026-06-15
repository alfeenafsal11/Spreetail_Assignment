from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date as date_type
from app.database import get_db
from app import models
from app.pipeline import run_import_pipeline
from app.balances import calculate_user_balances, optimize_settlements_greedy, get_user_breakdown

app = FastAPI(title="Spreetail Shared Expenses App")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class MembershipUpdate(BaseModel):
    left_at: date_type

@app.get("/")
def read_root():
    return {"message": "Welcome to Spreetail Shared Expenses App API"}

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

@app.patch("/groups/{group_id}/members/{user_id}")
def update_group_membership(group_id: int, user_id: int, data: MembershipUpdate, db: Session = Depends(get_db)):
    membership = db.query(models.GroupMembership).filter_by(group_id=group_id, user_id=user_id).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership record not found")
        
    membership.left_at = data.left_at
    db.commit()
    return {"message": "Membership successfully updated", "user_id": user_id, "left_at": str(data.left_at)}

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
    
    # Map user_id to username for optimized settlements input
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
