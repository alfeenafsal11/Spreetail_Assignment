import csv
import io
from datetime import datetime
from sqlalchemy.orm import Session
from app import models
from app.rules import RULE_ORDER, AnomalyResult

def run_import_pipeline(db: Session, csv_file_content: str, filename: str) -> int:
    """
    Runs the CSV import pipeline.
    Creates an ImportSession, parses rows, runs rules, inserts records and anomalies,
    and returns the import_session_id.
    """
    # Create ImportSession
    import_session = models.ImportSession(
        filename=filename,
        status="processing"
    )
    db.add(import_session)
    db.commit()
    db.refresh(import_session)
    
    # Cache aliases and users for performance
    # Map lowercase raw name -> canonical user name
    aliases_cache = {}
    db_aliases = db.query(models.PersonAlias).all()
    for alias in db_aliases:
        user = db.get(models.User, alias.canonical_user_id)
        if user:
            aliases_cache[alias.alias_name.lower()] = user.name
            
    # Also add standard user names to alias cache
    db_users = db.query(models.User).all()
    for user in db_users:
        aliases_cache[user.name.lower()] = user.name

    context = {
        "aliases_cache": aliases_cache
    }
    
    # We will use the single seeded group "The Flat" (ID = 1)
    group = db.query(models.Group).filter_by(name="The Flat").first()
    if not group:
        # Fallback in case seeding was not run yet
        group = models.Group(name="The Flat")
        db.add(group)
        db.commit()
        db.refresh(group)
    group_id = group.id

    session_expenses = []
    flagged_non_members = set()
    
    try:
        # Parse CSV content
        f = io.StringIO(csv_file_content.strip())
        reader = csv.DictReader(f)
        
        # Row 1 is header, data rows start at row_number = 2
        for idx, row in enumerate(reader):
            row_num = idx + 2
            
            # Initial state for this row
            state = {
                "anomalies": [],
                "session_expenses": session_expenses,
                "flagged_non_members": flagged_non_members,
                "stop_validation": False
            }
            
            try:
                # Run each validation rule in order
                for rule in RULE_ORDER:
                    if state.get("stop_validation"):
                        break
                        
                    anomaly = rule.validate(row, row_num, db, group_id, state, context)
                    if anomaly:
                        state["anomalies"].append(anomaly)
                        
            except ValueError as e:
                # Validation error: reject row (e.g. missing payer or unparseable date)
                # Log a high severity anomaly and skip creating any expense/settlement/deposit for this row
                error_msg = str(e)
                print(f"Row {row_num} rejected: {error_msg}")
                
                db_anomaly = models.Anomaly(
                    import_session_id=import_session.id,
                    row_number=row_num,
                    anomaly_type="ValidationError",
                    severity="high",
                    detected_value=str(row),
                    action_taken="row_rejected",
                    requires_approval=True
                )
                db.add(db_anomaly)
                db.commit()
                continue  # Skip processing the rest of this row
                
            # If validation succeeded, create DB models based on what rules decided
            if state.get("settlement_to_create"):
                settlement = state["settlement_to_create"]
                db.add(settlement)
                db.commit()
                
            elif state.get("deposit_to_create"):
                deposit = state["deposit_to_create"]
                db.add(deposit)
                db.commit()
                
            else:
                # Create Expense
                expense = models.Expense(
                    group_id=group_id,
                    title=row.get("description", "").strip(),
                    description=row.get("notes", "").strip() or None,
                    amount=state["original_amount"],
                    currency=state["currency"],
                    exchange_rate=state["exchange_rate"],
                    normalized_amount=state["normalized_amount"],
                    paid_by=state["payer_user_id"],
                    expense_date=state["expense_date"],
                    is_refund=state.get("is_refund", False),
                    refund_of_expense_id=state.get("refund_of_expense_id")
                )
                db.add(expense)
                db.commit()
                db.refresh(expense)
                
                # Create Splits
                for split_item in state.get("splits_data", []):
                    split = models.ExpenseSplit(
                        expense_id=expense.id,
                        user_id=split_item["user_id"],
                        split_type=split_item["split_type"],
                        split_amount=split_item["split_amount"],
                        split_percentage=split_item["split_percentage"]
                    )
                    db.add(split)
                db.commit()
                
                # Cache expense details for duplicate checks in subsequent rows
                session_expenses.append({
                    "row_number": row_num,
                    "group_id": group_id,
                    "expense_date": state["expense_date"],
                    "paid_by": state["payer_user_id"],
                    "normalized_amount": state["normalized_amount"],
                    "title": row.get("description", "").strip()
                })
                
            # Insert logged anomalies
            for anomaly in state["anomalies"]:
                db_anomaly = models.Anomaly(
                    import_session_id=import_session.id,
                    row_number=row_num,
                    anomaly_type=anomaly.anomaly_type,
                    severity=anomaly.severity,
                    detected_value=anomaly.detected_value,
                    action_taken=anomaly.action_taken,
                    requires_approval=anomaly.requires_approval
                )
                db.add(db_anomaly)
            db.commit()
            
        import_session.status = "completed"
        db.commit()
        
    except Exception as e:
        db.rollback()
        import_session.status = "failed"
        db.commit()
        raise e
        
    return import_session.id
