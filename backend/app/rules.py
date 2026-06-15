import re
from datetime import date
from sqlalchemy.orm import Session
from app import models
from app.utils import parse_amount, parse_date, parse_split_details

class AnomalyResult:
    def __init__(self, anomaly_type: str, severity: str, detected_value: str = None, action_taken: str = None, requires_approval: bool = False):
        self.anomaly_type = anomaly_type
        self.severity = severity
        self.detected_value = detected_value
        self.action_taken = action_taken
        self.requires_approval = requires_approval

    def to_dict(self):
        return {
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "detected_value": self.detected_value,
            "action_taken": self.action_taken,
            "requires_approval": self.requires_approval
        }

class ValidationRule:
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        """
        Validates the row and mutates the state.
        Returns AnomalyResult if an anomaly is detected, else None.
        May return a special code or flag in state to short-circuit further rules.
        """
        pass

# Utility for title token overlap
def clean_title_tokens(title: str) -> set:
    if not title:
        return set()
    # Lowercase, strip punctuation, split
    cleaned = re.sub(r'[^\w\s]', '', str(title).lower())
    return set(cleaned.split())

def calculate_overlap(title1: str, title2: str) -> float:
    tokens1 = clean_title_tokens(title1)
    tokens2 = clean_title_tokens(title2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    # Using Jaccard similarity or overlap ratio based on max tokens
    # Spec says: tokens {dinner, marina, bites} vs {dinner, marina, bites} = 1.0 overlap.
    # E.g. "Dinner at Marina Bites" vs "dinner - marina bites" -> set1 = {dinner, at, marina, bites}, set2 = {dinner, marina, bites}
    # Let's count matching tokens divided by max token count (spec: tokens {dinner, marina, bites} vs {dinner, marina, bites} = 1.0 overlap)
    # Actually, if we filter out common stopwords (like "at", "for", "in", "the", "a"), it is even better, but let's stick to simple overlap.
    # Let's do: len(set1 & set2) / max(len(set1), len(set2))
    # Wait, let's look at "at" in "Dinner at Marina Bites": {dinner, at, marina, bites} (len=4), "dinner - marina bites" {dinner, marina, bites} (len=3). Overlap = 3/4 = 0.75.
    # To get >= 0.8 or 1.0 for "Marina Bites" matches, we should ignore stopwords or compute overlap relative to min/max.
    # Let's ignore standard small words: "at", "for", "in", "of", "on", "to", "the", "a", "an", "and", "or", "with", "by", "from", "is".
    stopwords = {"at", "for", "in", "of", "on", "to", "the", "a", "an", "and", "or", "with", "by", "from", "is", "-"}
    tokens1 = tokens1 - stopwords
    tokens2 = tokens2 - stopwords
    if not tokens1 or not tokens2:
        return 0.0
    return len(tokens1.intersection(tokens2)) / max(len(tokens1), len(tokens2))


class ParticipantRule(ValidationRule):
    """
    1. Resolve or create users for all named people in paid_by and split_with.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        raw_payer = row.get("paid_by", "").strip()
        raw_split_with = row.get("split_with", "").strip()

        # Validation: Missing payer (reject row)
        if not raw_payer:
            raise ValueError(f"Validation Error: Row {row_num} is missing a payer name. Row rejected.")

        # Resolve payer
        payer_canonical = context["aliases_cache"].get(raw_payer.lower())
        if not payer_canonical:
            # Check direct user name
            user = db.query(models.User).filter(models.User.name.ilike(raw_payer)).first()
            if user:
                payer_canonical = user.name
                context["aliases_cache"][raw_payer.lower()] = user.name
            else:
                # Create guest user
                user = models.User(name=raw_payer, is_guest=True)
                db.add(user)
                db.commit()
                db.refresh(user)
                payer_canonical = user.name
                context["aliases_cache"][raw_payer.lower()] = user.name
                
                # Add to aliases cache
                alias = models.PersonAlias(alias_name=raw_payer, canonical_user_id=user.id)
                db.add(alias)
                db.commit()
                
                # Flag Non-Member Participant anomaly (guest user created)
                state["anomalies"].append(AnomalyResult(
                    anomaly_type="ParticipantRule",
                    severity="low",
                    detected_value=raw_payer,
                    action_taken="created_guest_user",
                    requires_approval=False
                ))

        # Resolve split_with names
        split_names = [n.strip() for n in raw_split_with.split(";") if n.strip()]
        resolved_split_names = []
        for name in split_names:
            canon_name = context["aliases_cache"].get(name.lower())
            if not canon_name:
                user = db.query(models.User).filter(models.User.name.ilike(name)).first()
                if user:
                    canon_name = user.name
                    context["aliases_cache"][name.lower()] = user.name
                else:
                    # Create guest user on the fly
                    user = models.User(name=name, is_guest=True)
                    db.add(user)
                    db.commit()
                    db.refresh(user)
                    canon_name = user.name
                    context["aliases_cache"][name.lower()] = user.name
                    
                    alias = models.PersonAlias(alias_name=name, canonical_user_id=user.id)
                    db.add(alias)
                    db.commit()
                    
                    # Flag Non-Member Participant anomaly
                    state["anomalies"].append(AnomalyResult(
                        anomaly_type="ParticipantRule",
                        severity="low",
                        detected_value=name,
                        action_taken="created_guest_user",
                        requires_approval=False
                    ))
            resolved_split_names.append(canon_name)

        # Store resolved names in state for next rules
        state["payer_canonical"] = payer_canonical
        state["split_names_canonical"] = resolved_split_names
        
        # Check if payer is a member of the group
        payer_user = db.query(models.User).filter_by(name=payer_canonical).first()
        state["payer_user_id"] = payer_user.id
        
        # We also check for non-member participant anomalies here (like Kabir who gets no membership record)
        # Check if payer has membership
        has_payer_memb = db.query(models.GroupMembership).filter_by(group_id=group_id, user_id=payer_user.id).first() is not None
        if not has_payer_memb and payer_canonical not in state.get("flagged_non_members", set()):
            state["flagged_non_members"].add(payer_canonical)
            state["anomalies"].append(AnomalyResult(
                anomaly_type="ParticipantRule",
                severity="medium",
                detected_value=payer_canonical,
                action_taken="flagged_non_member_participant",
                requires_approval=True
            ))
            
        # Check if split users have memberships
        for s_name in resolved_split_names:
            s_user = db.query(models.User).filter_by(name=s_name).first()
            has_memb = db.query(models.GroupMembership).filter_by(group_id=group_id, user_id=s_user.id).first() is not None
            if not has_memb and s_name not in state.get("flagged_non_members", set()):
                state["flagged_non_members"].add(s_name)
                state["anomalies"].append(AnomalyResult(
                    anomaly_type="ParticipantRule",
                    severity="medium",
                    detected_value=s_name,
                    action_taken="flagged_non_member_participant",
                    requires_approval=True
                ))

        return None


class NameNormalizationRule(ValidationRule):
    """
    2. Apply person_aliases, record new aliases.
    (Note: NameNormalizationRule runs after ParticipantRule resolves canonical names).
    We check if the raw name matches canonical. If it has whitespace differences or casing differences, flag.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        raw_payer = row.get("paid_by", "")
        # Row 27 has "rohan " (trailing space). Normalization rule checks and normalizes.
        normalized_payer = state["payer_canonical"]
        
        if raw_payer != normalized_payer:
            # Trace alias match
            return AnomalyResult(
                anomaly_type="NameNormalizationRule",
                severity="low",
                detected_value=f"Raw: '{raw_payer}' normalized to '{normalized_payer}'",
                action_taken="normalized_name",
                requires_approval=False
            )
        return None


class DateRule(ValidationRule):
    """
    3. Parse/normalize date, check formatting, flag ambiguous.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        raw_date = row.get("date", "").strip()
        try:
            parsed_dt, is_ambiguous = parse_date(raw_date)
            state["expense_date"] = parsed_dt
            
            if is_ambiguous:
                return AnomalyResult(
                    anomaly_type="DateRule",
                    severity="medium",
                    detected_value=raw_date,
                    action_taken="parsed_date_requires_approval",
                    requires_approval=True
                )
        except ValueError as e:
            # Fatal date parsing error
            raise ValueError(f"Validation Error: Row {row_num} has unparseable date '{raw_date}'. Details: {str(e)}")
            
        return None


class MembershipRule(ValidationRule):
    """
    4. Check participants vs group_memberships timeline.
    joined_at <= expense_date <= left_at (or NULL)
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        exp_date = state["expense_date"]
        payer_canonical = state["payer_canonical"]
        split_names = state["split_names_canonical"]
        
        # Payer membership check
        payer_user = db.query(models.User).filter_by(name=payer_canonical).first()
        p_memb = db.query(models.GroupMembership).filter_by(group_id=group_id, user_id=payer_user.id).first()
        
        # If they have membership, verify date window
        if p_memb:
            if p_memb.joined_at > exp_date or (p_memb.left_at and p_memb.left_at < exp_date):
                state["anomalies"].append(AnomalyResult(
                    anomaly_type="MembershipRule",
                    severity="medium",
                    detected_value=f"Payer {payer_canonical} active {p_memb.joined_at} to {p_memb.left_at}, expense date {exp_date}",
                    action_taken="flagged_payer_membership_violation",
                    requires_approval=True
                ))

        # Split members membership check
        active_splits = []
        for name in split_names:
            s_user = db.query(models.User).filter_by(name=name).first()
            s_memb = db.query(models.GroupMembership).filter_by(group_id=group_id, user_id=s_user.id).first()
            
            is_active = True
            if s_memb:
                if s_memb.joined_at > exp_date or (s_memb.left_at and s_memb.left_at < exp_date):
                    is_active = False
            else:
                # If they don't even have membership record (like Kabir guest), they are not active members
                is_active = False

            if not is_active:
                # Membership violation: "exclude member from split, flag"
                # Row 36: Meera (left 2026-03-31) included on 2026-04-02 -> exclude Meera, split among Aisha, Rohan, Priya
                state["anomalies"].append(AnomalyResult(
                    anomaly_type="MembershipRule",
                    severity="high",
                    detected_value=f"Split user {name} inactive on {exp_date}",
                    action_taken="excluded_inactive_user_from_split",
                    requires_approval=True
                ))
            else:
                active_splits.append(name)
                
        # Update split list in state to contain only active members
        state["split_names_canonical"] = active_splits
        return None


class CurrencyRule(ValidationRule):
    """
    5. Normalize currency + compute normalized_amount.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        raw_currency = str(row.get("currency", "")).strip()
        raw_amount_str = str(row.get("amount", "")).strip()
        
        amount = parse_amount(raw_amount_str)
        state["original_amount"] = amount
        
        # Missing currency: row 28 has empty field -> default to INR, flag
        is_missing = False
        if not raw_currency:
            raw_currency = "INR"
            is_missing = True
            
        currency = raw_currency.upper()
        state["currency"] = currency
        
        # Fixed rate conversion table
        rates = {"USD": 83.0, "INR": 1.0}
        rate = rates.get(currency, 1.0)
        state["exchange_rate"] = rate
        
        # Compute normalized amount
        normalized_amount = round(amount * rate, 2)
        state["normalized_amount"] = normalized_amount
        
        if is_missing:
            return AnomalyResult(
                anomaly_type="CurrencyRule",
                severity="medium",
                detected_value="Empty currency field",
                action_taken="defaulted_to_inr_pending_review",
                requires_approval=True
            )
            
        return None


class SettlementRule(ValidationRule):
    """
    6. "X paid Y back" pattern -> convert to settlement, STOP.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        desc = str(row.get("description", "")).strip()
        # Regex: X paid Y back
        match = re.match(r"(\w+)\s+paid\s+(\w+)\s+back", desc, re.IGNORECASE)
        if match:
            raw_payer = match.group(1).strip()
            raw_receiver = match.group(2).strip()
            
            # Resolve aliases
            payer_canonical = context["aliases_cache"].get(raw_payer.lower(), raw_payer)
            receiver_canonical = context["aliases_cache"].get(raw_receiver.lower(), raw_receiver)
            
            # Fetch user records
            p_user = db.query(models.User).filter_by(name=payer_canonical).first()
            r_user = db.query(models.User).filter_by(name=receiver_canonical).first()
            
            if not p_user or not r_user:
                raise ValueError(f"Error in SettlementRule: Could not resolve users for {payer_canonical} or {receiver_canonical}")
                
            # Create Settlement object scheduled for DB write
            settlement = models.Settlement(
                payer_id=p_user.id,
                receiver_id=r_user.id,
                amount=state["normalized_amount"],
                settlement_date=state["expense_date"],
                group_id=group_id
            )
            state["settlement_to_create"] = settlement
            state["stop_validation"] = True  # Short-circuit downstream rules
            
            return AnomalyResult(
                anomaly_type="SettlementRule",
                severity="medium",
                detected_value=desc,
                action_taken="converted_to_settlement",
                requires_approval=True
            )
        return None


class DepositRule(ValidationRule):
    """
    7. "deposit" pattern -> convert to deposit, STOP.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        desc = str(row.get("description", "")).strip()
        if "deposit" in desc.lower():
            payer_id = state["payer_user_id"]
            
            deposit = models.Deposit(
                user_id=payer_id,
                amount=state["normalized_amount"],
                deposit_date=state["expense_date"],
                group_id=group_id
            )
            state["deposit_to_create"] = deposit
            state["stop_validation"] = True  # Short-circuit
            
            return AnomalyResult(
                anomaly_type="DepositRule",
                severity="low",
                detected_value=desc,
                action_taken="converted_to_deposit",
                requires_approval=False
            )
        return None


class RefundRule(ValidationRule):
    """
    8. Negative amount + "refund" in description -> refund.
    Try to link refund_of_expense_id.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        amount = state["original_amount"]
        desc = str(row.get("description", "")).strip()
        
        if amount < 0 and "refund" in desc.lower():
            state["is_refund"] = True
            
            # Find matching original expense in DB
            payer_id = state["payer_user_id"]
            refund_date = state["expense_date"]
            
            # Query candidate prior expenses
            candidates = db.query(models.Expense).filter(
                models.Expense.group_id == group_id,
                models.Expense.paid_by == payer_id,
                models.Expense.expense_date <= refund_date,
                models.Expense.amount > 0
            ).all()
            
            matched_expense_id = None
            best_overlap = 0.0
            
            for cand in candidates:
                overlap = calculate_overlap(desc, cand.title)
                if overlap >= 0.5 and overlap > best_overlap:
                    best_overlap = overlap
                    matched_expense_id = cand.id
            
            state["refund_of_expense_id"] = matched_expense_id
            action = "linked_to_original_expense" if matched_expense_id else "refund_not_linked"
            
            return AnomalyResult(
                anomaly_type="RefundRule",
                severity="medium",
                detected_value=desc,
                action_taken=action,
                requires_approval=True
            )
        return None


class NegativeAmountRule(ValidationRule):
    """
    9. Negative amount, no refund keyword -> flag, STOP.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        amount = state["original_amount"]
        is_refund = state.get("is_refund", False)
        
        if amount < 0 and not is_refund:
            state["stop_validation"] = True
            return AnomalyResult(
                anomaly_type="NegativeAmountRule",
                severity="medium",
                detected_value=str(amount),
                action_taken="imported_as_is_requires_review",
                requires_approval=True
            )
        return None


class ZeroAmountRule(ValidationRule):
    """
    10. amount == 0 -> flag, require review.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        amount = state["original_amount"]
        if amount == 0:
            return AnomalyResult(
                anomaly_type="ZeroAmountRule",
                severity="medium",
                detected_value="0.00",
                action_taken="imported_as_is_requires_review",
                requires_approval=True
            )
        return None


class SplitRule(ValidationRule):
    """
    11. Validate split_type / percentages sum to 100.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        split_type = str(row.get("split_type", "")).strip().lower()
        raw_split_details = row.get("split_details", "")
        
        # Valid types check
        valid_types = {"equal", "percentage", "unequal", "share"}
        if not split_type or split_type not in valid_types:
            # Default to equal split
            split_type = "equal"
            state["anomalies"].append(AnomalyResult(
                anomaly_type="SplitRule",
                severity="medium",
                detected_value=str(row.get("split_type")),
                action_taken="defaulted_to_equal_split",
                requires_approval=True
            ))

        state["split_type"] = split_type
        
        # Fetch active split members
        active_names = state["split_names_canonical"]
        if not active_names:
            # No active members in split -> default to all members of group at that date
            # Get group members on this date
            memberships = db.query(models.GroupMembership).filter(
                models.GroupMembership.group_id == group_id,
                models.GroupMembership.joined_at <= state["expense_date"],
                (models.GroupMembership.left_at == None) | (models.GroupMembership.left_at >= state["expense_date"])
            ).all()
            active_names = [db.get(models.User, m.user_id).name for m in memberships]
            state["split_names_canonical"] = active_names
            
        if not active_names:
            raise ValueError(f"Validation Error: Row {row_num} has no active group members to split with.")

        # Parse split details
        parsed_details = parse_split_details(raw_split_details, split_type)
        
        # Verify split-with alias normalization for details mapping
        norm_details = {}
        for k, v in parsed_details.items():
            canon_k = context["aliases_cache"].get(k.lower(), k)
            norm_details[canon_k] = v

        splits_data = [] # List of dicts with user_id, amount, percentage
        total_amount = state["normalized_amount"]
        
        anomaly = None
        
        if split_type == "equal":
            # Equal: divide total_amount evenly across active split_names
            if raw_split_details and raw_split_details.strip():
                # Split Type Inconsistency: equal split type with details
                # Default action: honor split_type (ignore details), flag for review
                anomaly = AnomalyResult(
                    anomaly_type="SplitRule",
                    severity="medium",
                    detected_value=f"Type equal, Details present: '{raw_split_details}'",
                    action_taken="honored_equal_split_ignored_details",
                    requires_approval=True
                )
                
            # Divide evenly
            n_people = len(active_names)
            base_share = round(total_amount / n_people, 2)
            # Adjust rounding differences by adding it to the first person
            shares = [base_share] * n_people
            rounding_diff = round(total_amount - sum(shares), 2)
            if rounding_diff != 0:
                shares[0] = round(shares[0] + rounding_diff, 2)
                
            for name, share_amt in zip(active_names, shares):
                user = db.query(models.User).filter_by(name=name).first()
                splits_data.append({
                    "user_id": user.id,
                    "split_type": "equal",
                    "split_amount": share_amt,
                    "split_percentage": round(100.0 / n_people, 2)
                })

        elif split_type == "percentage":
            # Percentage split: sum must equal 100
            total_pct = sum(norm_details.values())
            is_mismatch = abs(total_pct - 100.0) > 0.01
            
            if is_mismatch:
                anomaly = AnomalyResult(
                    anomaly_type="SplitRule",
                    severity="high",
                    detected_value=f"Sum of percentages: {total_pct}%",
                    action_taken="flagged_percentage_mismatch_kept_raw",
                    requires_approval=True
                )
            
            # Calculate shares
            for name in active_names:
                user = db.query(models.User).filter_by(name=name).first()
                pct = norm_details.get(name, 0.0)
                # Calculate share amount
                share_amt = round(total_amount * (pct / 100.0), 2)
                splits_data.append({
                    "user_id": user.id,
                    "split_type": "percentage",
                    "split_amount": share_amt,
                    "split_percentage": pct
                })
                
        elif split_type == "unequal":
            # Unequal split: sum must equal total expense amount
            # Details are in original currency? Convert to INR if needed, but detail amounts are given.
            # Row 12: Aisha birthday cake (1500 INR): Rohan 700; Priya 400; Meera 400. Sum = 1500 = total.
            total_details = sum(norm_details.values())
            original_amt = state["original_amount"]
            
            is_mismatch = abs(total_details - original_amt) > 0.01
            if is_mismatch:
                anomaly = AnomalyResult(
                    anomaly_type="SplitRule",
                    severity="high",
                    detected_value=f"Sum of unequal amounts: {total_details} (Expected: {original_amt})",
                    action_taken="flagged_unequal_mismatch_kept_raw",
                    requires_approval=True
                )
                
            # Build splits (converting detail amounts if currency is not INR)
            rate = state["exchange_rate"]
            for name in active_names:
                user = db.query(models.User).filter_by(name=name).first()
                original_detail_val = norm_details.get(name, 0.0)
                share_amt = round(original_detail_val * rate, 2)
                splits_data.append({
                    "user_id": user.id,
                    "split_type": "unequal",
                    "split_amount": share_amt,
                    "split_percentage": round((original_detail_val / original_amt * 100.0) if original_amt != 0 else 0.0, 2)
                })

        elif split_type == "share":
            # Share split: weights divide proportionally
            total_shares = sum(norm_details.values())
            if total_shares <= 0:
                raise ValueError(f"Validation Error: Total shares weight is zero or negative in row {row_num}")
                
            # Calculate shares
            temp_splits = []
            for name in active_names:
                user = db.query(models.User).filter_by(name=name).first()
                weight = norm_details.get(name, 0.0)
                share_amt = round(total_amount * (weight / total_shares), 2)
                temp_splits.append((user.id, share_amt, weight))
                
            # Adjust rounding differences
            rounding_diff = round(total_amount - sum(s[1] for s in temp_splits), 2)
            if rounding_diff != 0 and len(temp_splits) > 0:
                # Add/subtract rounding difference to/from first share
                first_uid, first_share, first_w = temp_splits[0]
                temp_splits[0] = (first_uid, round(first_share + rounding_diff, 2), first_w)
                
            for uid, share_amt, weight in temp_splits:
                splits_data.append({
                    "user_id": uid,
                    "split_type": "share",
                    "split_amount": share_amt,
                    "split_percentage": round((weight / total_shares * 100.0), 2)
                })

        state["splits_data"] = splits_data
        return anomaly


class DuplicateRule(ValidationRule):
    """
    12. Exact duplicate check.
    Same group, same date, same payer, same normalized amount, title tokens overlap >= 0.8.
    Action: flag, requires approval, keep both. First is valid, second is flagged pending.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        exp_date = state["expense_date"]
        payer_id = state["payer_user_id"]
        normalized_amount = state["normalized_amount"]
        title = row.get("description", "")
        
        # Check against previously imported expenses in this import session
        # As well as in the database
        # Find matches in current session
        for prev_idx, prev in enumerate(state["session_expenses"]):
            if (prev["group_id"] == group_id and
                prev["expense_date"] == exp_date and
                prev["paid_by"] == payer_id and
                abs(prev["normalized_amount"] - normalized_amount) < 0.01):
                
                # Check title overlap
                overlap = calculate_overlap(title, prev["title"])
                if overlap >= 0.8:
                    return AnomalyResult(
                        anomaly_type="DuplicateRule",
                        severity="high",
                        detected_value=f"Matches row {prev['row_number']} ('{prev['title']}')",
                        action_taken="kept_first_flagged_second",
                        requires_approval=True
                    )
                    
        # Check against DB
        db_candidates = db.query(models.Expense).filter(
            models.Expense.group_id == group_id,
            models.Expense.expense_date == exp_date,
            models.Expense.paid_by == payer_id,
            models.Expense.normalized_amount == normalized_amount
        ).all()
        
        for cand in db_candidates:
            overlap = calculate_overlap(title, cand.title)
            if overlap >= 0.8:
                return AnomalyResult(
                    anomaly_type="DuplicateRule",
                    severity="high",
                    detected_value=f"Matches DB expense ID {cand.id} ('{cand.title}')",
                    action_taken="kept_first_flagged_second",
                    requires_approval=True
                )
                
        return None


class NearDuplicateRule(ValidationRule):
    """
    13. Near duplicate check (different amounts).
    Same as DuplicateRule but amount differs.
    """
    def validate(self, row: dict, row_num: int, db: Session, group_id: int, state: dict, context: dict) -> AnomalyResult | None:
        exp_date = state["expense_date"]
        payer_id = state["payer_user_id"]
        title = row.get("description", "")
        normalized_amount = state["normalized_amount"]
        
        # Check session
        for prev in state["session_expenses"]:
            if (prev["group_id"] == group_id and
                prev["expense_date"] == exp_date and
                prev["paid_by"] == payer_id and
                abs(prev["normalized_amount"] - normalized_amount) >= 0.01):
                
                overlap = calculate_overlap(title, prev["title"])
                if overlap >= 0.8:
                    return AnomalyResult(
                        anomaly_type="NearDuplicateRule",
                        severity="high",
                        detected_value=f"Matches row {prev['row_number']} ('{prev['title']}') but amount differs: {normalized_amount} vs {prev['normalized_amount']}",
                        action_taken="kept_both_pending_review",
                        requires_approval=True
                    )
                    
        # Check DB
        db_candidates = db.query(models.Expense).filter(
            models.Expense.group_id == group_id,
            models.Expense.expense_date == exp_date,
            models.Expense.paid_by == payer_id
        ).all()
        
        for cand in db_candidates:
            if abs(cand.normalized_amount - normalized_amount) >= 0.01:
                overlap = calculate_overlap(title, cand.title)
                if overlap >= 0.8:
                    return AnomalyResult(
                        anomaly_type="NearDuplicateRule",
                        severity="high",
                        detected_value=f"Matches DB expense ID {cand.id} ('{cand.title}') but amount differs: {normalized_amount} vs {cand.normalized_amount}",
                        action_taken="kept_both_pending_review",
                        requires_approval=True
                    )
                    
        return None


# Global ordered list of rules
RULE_ORDER = [
    ParticipantRule(),
    NameNormalizationRule(),
    DateRule(),
    MembershipRule(),
    CurrencyRule(),
    SettlementRule(),
    DepositRule(),
    RefundRule(),
    NegativeAmountRule(),
    ZeroAmountRule(),
    SplitRule(),
    DuplicateRule(),
    NearDuplicateRule()
]
