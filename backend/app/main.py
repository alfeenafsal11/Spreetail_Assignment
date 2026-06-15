from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.pipeline import run_import_pipeline

app = FastAPI(title="Spreetail Shared Expenses App")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
