from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=True, index=True)
    password_hash = Column(String, nullable=True)
    is_guest = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    memberships = relationship("GroupMembership", back_populates="user", cascade="all, delete-orphan")
    aliases = relationship("PersonAlias", back_populates="canonical_user", cascade="all, delete-orphan")
    splits = relationship("ExpenseSplit", back_populates="user", cascade="all, delete-orphan")

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    memberships = relationship("GroupMembership", back_populates="group", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="group", cascade="all, delete-orphan")
    settlements = relationship("Settlement", back_populates="group", cascade="all, delete-orphan")
    deposits = relationship("Deposit", back_populates="group", cascade="all, delete-orphan")

class GroupMembership(Base):
    __tablename__ = "group_memberships"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(Date, nullable=False)
    left_at = Column(Date, nullable=True)

    group = relationship("Group", back_populates="memberships")
    user = relationship("User", back_populates="memberships")

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    exchange_rate = Column(Float, nullable=False)
    normalized_amount = Column(Float, nullable=False)
    paid_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expense_date = Column(Date, nullable=False)
    is_refund = Column(Boolean, default=False, nullable=False)
    refund_of_expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    group = relationship("Group", back_populates="expenses")
    payer = relationship("User", foreign_keys=[paid_by])
    refund_of = relationship("Expense", remote_side=[id], foreign_keys=[refund_of_expense_id])
    splits = relationship("ExpenseSplit", back_populates="expense", cascade="all, delete-orphan")

class ExpenseSplit(Base):
    __tablename__ = "expense_splits"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    split_type = Column(String, nullable=False)  # equal, percentage, unequal, share
    split_amount = Column(Float, nullable=False)
    split_percentage = Column(Float, nullable=True)

    expense = relationship("Expense", back_populates="splits")
    user = relationship("User", back_populates="splits")

class Settlement(Base):
    __tablename__ = "settlements"

    id = Column(Integer, primary_key=True, index=True)
    payer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)
    settlement_date = Column(Date, nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    group = relationship("Group", back_populates="settlements")
    payer = relationship("User", foreign_keys=[payer_id])
    receiver = relationship("User", foreign_keys=[receiver_id])

class Deposit(Base):
    __tablename__ = "deposits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)
    deposit_date = Column(Date, nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    group = relationship("Group", back_populates="deposits")
    user = relationship("User", foreign_keys=[user_id])

class ImportSession(Base):
    __tablename__ = "import_sessions"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    status = Column(String, nullable=False)  # processing, completed, failed
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    anomalies = relationship("Anomaly", back_populates="import_session", cascade="all, delete-orphan")

class Anomaly(Base):
    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True, index=True)
    import_session_id = Column(Integer, ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False)
    row_number = Column(Integer, nullable=False)
    anomaly_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    detected_value = Column(String, nullable=True)
    action_taken = Column(String, nullable=True)
    requires_approval = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    import_session = relationship("ImportSession", back_populates="anomalies")
    reviews = relationship("AnomalyReview", back_populates="anomaly", cascade="all, delete-orphan")

class AnomalyReview(Base):
    __tablename__ = "anomaly_reviews"

    id = Column(Integer, primary_key=True, index=True)
    anomaly_id = Column(Integer, ForeignKey("anomalies.id", ondelete="CASCADE"), nullable=False)
    decision = Column(String, nullable=False)  # approve, reject
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reviewed_at = Column(DateTime, server_default=func.now(), nullable=False)

    anomaly = relationship("Anomaly", back_populates="reviews")
    reviewer = relationship("User", foreign_keys=[reviewed_by])

class PersonAlias(Base):
    __tablename__ = "person_aliases"

    id = Column(Integer, primary_key=True, index=True)
    canonical_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    alias_name = Column(String, unique=True, nullable=False, index=True)

    canonical_user = relationship("User", back_populates="aliases")
