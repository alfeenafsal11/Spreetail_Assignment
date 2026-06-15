from sqlalchemy.orm import Session
from sqlalchemy import func
from app import models

def calculate_user_balances(db: Session, group_id: int) -> dict[int, float]:
    """
    Calculates the net balance for each user involved in the group.
    Returns a dict mapping user_id -> net_balance.
    """
    # 1. Fetch all users involved in the group
    user_ids = set()
    
    # Members
    members = db.query(models.GroupMembership.user_id).filter_by(group_id=group_id).all()
    for m in members:
        user_ids.add(m[0])
        
    # Payers of expenses
    payers = db.query(models.Expense.paid_by).filter_by(group_id=group_id).all()
    for p in payers:
        user_ids.add(p[0])
        
    # Users in splits
    split_users = db.query(models.ExpenseSplit.user_id).join(models.Expense).filter(models.Expense.group_id == group_id).all()
    for s in split_users:
        user_ids.add(s[0])
        
    # Users in deposits
    deposit_users = db.query(models.Deposit.user_id).filter_by(group_id=group_id).all()
    for d in deposit_users:
        user_ids.add(d[0])
        
    # Users in settlements
    settlements = db.query(models.Settlement.payer_id, models.Settlement.receiver_id).filter_by(group_id=group_id).all()
    for s in settlements:
        user_ids.add(s[0])
        user_ids.add(s[1])

    balances = {}
    for uid in user_ids:
        # Expenses Paid (excluding refund rows)
        exp_paid_sum = db.query(func.sum(models.Expense.normalized_amount)).filter(
            models.Expense.group_id == group_id,
            models.Expense.paid_by == uid,
            models.Expense.is_refund == False,
            models.Expense.amount > 0
        ).scalar() or 0.0
        
        # Refunds Received (absolute sum of refund rows paid by this user)
        refunds_sum = db.query(func.sum(models.Expense.normalized_amount)).filter(
            models.Expense.group_id == group_id,
            models.Expense.paid_by == uid,
            models.Expense.is_refund == True
        ).scalar() or 0.0
        # refunds_sum will be negative since refund normalized_amounts are negative, so make it positive
        refunds_sum = abs(refunds_sum)
        
        # Amount Owed (sum of splits for this user in group)
        owed_sum = db.query(func.sum(models.ExpenseSplit.split_amount)).join(models.Expense).filter(
            models.Expense.group_id == group_id,
            models.ExpenseSplit.user_id == uid
        ).scalar() or 0.0
        
        # Settlements Made (payments user made to others)
        settlements_made = db.query(func.sum(models.Settlement.amount)).filter_by(
            group_id=group_id, payer_id=uid
        ).scalar() or 0.0
        
        # Settlements Received (payments user received from others)
        settlements_received = db.query(func.sum(models.Settlement.amount)).filter_by(
            group_id=group_id, receiver_id=uid
        ).scalar() or 0.0
        
        # Deposits Made (payments user made to group pool)
        deposits_made = db.query(func.sum(models.Deposit.amount)).filter_by(
            group_id=group_id, user_id=uid
        ).scalar() or 0.0
        
        # Net Balance Formula (corrected signs for settlements)
        # Net Balance = Expenses Paid - Amount Owed + Settlements Made - Settlements Received + Deposits Made - Refunds Received
        net_balance = exp_paid_sum - owed_sum + settlements_made - settlements_received + deposits_made - refunds_sum
        balances[uid] = round(net_balance, 2)
        
    return balances

def optimize_settlements_greedy(balances: dict[str, float]) -> list[dict]:
    """
    Greedy min-cashflow algorithm.
    Balances mapping from username -> net_balance.
    """
    debtors = []
    creditors = []
    
    for name, bal in balances.items():
        if bal < -0.01:
            debtors.append([name, bal])
        elif bal > 0.01:
            creditors.append([name, bal])
            
    debtors.sort(key=lambda x: x[1])
    creditors.sort(key=lambda x: x[1], reverse=True)
    
    suggestions = []
    i, j = 0, 0
    
    while i < len(debtors) and j < len(creditors):
        d_name, d_bal = debtors[i]
        c_name, c_bal = creditors[j]
        
        amount = min(-d_bal, c_bal)
        amount = round(amount, 2)
        
        if amount > 0:
            suggestions.append({
                "from_user": d_name,
                "to_user": c_name,
                "amount": amount
            })
            
        debtors[i][1] += amount
        creditors[j][1] -= amount
        
        if abs(debtors[i][1]) < 0.01:
            i += 1
        if abs(creditors[j][1]) < 0.01:
            j += 1
            
    return suggestions

def get_user_breakdown(db: Session, group_id: int, user_id: int) -> dict:
    """
    Generates itemized explanation breakdown for a specific user.
    """
    user = db.get(models.User, user_id)
    if not user:
        return {}
        
    # Expenses Paid
    expenses_paid_q = db.query(models.Expense).filter(
        models.Expense.group_id == group_id,
        models.Expense.paid_by == user_id,
        models.Expense.is_refund == False,
        models.Expense.amount > 0
    ).all()
    expenses_paid = [{"title": e.title, "amount": e.normalized_amount, "date": str(e.expense_date)} for e in expenses_paid_q]
    expenses_paid_total = sum(e["amount"] for e in expenses_paid)
    
    # Refunds Received
    refunds_q = db.query(models.Expense).filter(
        models.Expense.group_id == group_id,
        models.Expense.paid_by == user_id,
        models.Expense.is_refund == True
    ).all()
    refunds = [{"title": r.title, "amount": abs(r.normalized_amount), "date": str(r.expense_date)} for r in refunds_q]
    refunds_total = sum(r["amount"] for r in refunds)
    
    # Expense Shares
    shares_q = db.query(models.ExpenseSplit, models.Expense).join(models.Expense).filter(
        models.Expense.group_id == group_id,
        models.ExpenseSplit.user_id == user_id
    ).all()
    expense_shares = [{"title": e.title, "amount": s.split_amount, "date": str(e.expense_date)} for s, e in shares_q]
    expense_shares_total = sum(s["amount"] for s in expense_shares)
    
    # Settlements Made
    settlements_made_q = db.query(models.Settlement, models.User).join(models.User, models.Settlement.receiver_id == models.User.id).filter(
        models.Settlement.group_id == group_id,
        models.Settlement.payer_id == user_id
    ).all()
    settlements_made = [{"to_user": u.name, "amount": s.amount, "date": str(s.settlement_date)} for s, u in settlements_made_q]
    settlements_made_total = sum(s["amount"] for s in settlements_made)
    
    # Settlements Received
    settlements_recv_q = db.query(models.Settlement, models.User).join(models.User, models.Settlement.payer_id == models.User.id).filter(
        models.Settlement.group_id == group_id,
        models.Settlement.receiver_id == user_id
    ).all()
    settlements_received = [{"from_user": u.name, "amount": s.amount, "date": str(s.settlement_date)} for s, u in settlements_recv_q]
    settlements_received_total = sum(s["amount"] for s in settlements_received)
    
    # Deposits Made
    deposits_q = db.query(models.Deposit).filter_by(group_id=group_id, user_id=user_id).all()
    deposits = [{"amount": d.amount, "date": str(d.deposit_date)} for d in deposits_q]
    deposits_total = sum(d["amount"] for d in deposits)
    
    # Re-calculate net balance
    net_balance = expenses_paid_total - expense_shares_total + settlements_made_total - settlements_received_total + deposits_total - refunds_total
    net_balance = round(net_balance, 2)
    
    # Arithmetic explanation string
    formula = (
        f"Expenses Paid ({expenses_paid_total:.2f}) - "
        f"Amount Owed ({expense_shares_total:.2f}) + "
        f"Settlements Made ({settlements_made_total:.2f}) - "
        f"Settlements Received ({settlements_received_total:.2f}) + "
        f"Deposits Made ({deposits_total:.2f}) - "
        f"Refunds Received ({refunds_total:.2f}) = {net_balance:.2f}"
    )
    
    return {
        "user_name": user.name,
        "expenses_paid": expenses_paid,
        "expenses_paid_total": round(expenses_paid_total, 2),
        "expense_shares": expense_shares,
        "expense_shares_total": round(expense_shares_total, 2),
        "settlements_made": settlements_made,
        "settlements_made_total": round(settlements_made_total, 2),
        "settlements_received": settlements_received,
        "settlements_received_total": round(settlements_received_total, 2),
        "deposits_made": deposits,
        "deposits_made_total": round(deposits_total, 2),
        "refunds_received": refunds,
        "refunds_received_total": round(refunds_total, 2),
        "net_balance": net_balance,
        "explanation": formula
    }
