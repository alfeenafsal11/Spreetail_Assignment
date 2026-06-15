from datetime import date
from app.database import SessionLocal, engine
from app import models

def seed_db():
    db = SessionLocal()
    try:
        # Create default group
        group = db.query(models.Group).filter_by(name="The Flat").first()
        if not group:
            group = models.Group(name="The Flat")
            db.add(group)
            db.commit()
            db.refresh(group)
        
        # Create users
        users_data = [
            {"name": "Aisha", "is_guest": False},
            {"name": "Rohan", "is_guest": False},
            {"name": "Priya", "is_guest": False},
            {"name": "Meera", "is_guest": False},
            {"name": "Sam", "is_guest": False},
            {"name": "Dev", "is_guest": False},
            {"name": "Kabir", "is_guest": True},  # Kabir is seeded as a guest user with no membership
        ]
        
        users = {}
        for u_data in users_data:
            user = db.query(models.User).filter_by(name=u_data["name"]).first()
            if not user:
                user = models.User(name=u_data["name"], is_guest=u_data["is_guest"])
                db.add(user)
                db.commit()
                db.refresh(user)
            users[u_data["name"]] = user

        # Create group memberships (Kabir gets NO membership record)
        memberships_data = [
            {"user_name": "Aisha", "joined_at": date(2026, 1, 1), "left_at": None},
            {"user_name": "Rohan", "joined_at": date(2026, 1, 1), "left_at": None},
            {"user_name": "Priya", "joined_at": date(2026, 1, 1), "left_at": None},
            {"user_name": "Meera", "joined_at": date(2026, 1, 1), "left_at": date(2026, 3, 31)},
            {"user_name": "Sam", "joined_at": date(2026, 4, 8), "left_at": None},
            {"user_name": "Dev", "joined_at": date(2026, 2, 8), "left_at": date(2026, 3, 14)},
        ]

        for m_data in memberships_data:
            user = users[m_data["user_name"]]
            membership = db.query(models.GroupMembership).filter_by(
                group_id=group.id, user_id=user.id
            ).first()
            if not membership:
                membership = models.GroupMembership(
                    group_id=group.id,
                    user_id=user.id,
                    joined_at=m_data["joined_at"],
                    left_at=m_data["left_at"]
                )
                db.add(membership)
            else:
                # Update membership dates if already exists
                membership.joined_at = m_data["joined_at"]
                membership.left_at = m_data["left_at"]
        db.commit()

        # Create person aliases
        aliases_data = [
            {"alias_name": "priya", "canonical_name": "Priya"},
            {"alias_name": "Priya S", "canonical_name": "Priya"},
            {"alias_name": "rohan", "canonical_name": "Rohan"},
            {"alias_name": "Dev's friend Kabir", "canonical_name": "Kabir"},
        ]

        for a_data in aliases_data:
            canonical_user = users[a_data["canonical_name"]]
            alias = db.query(models.PersonAlias).filter_by(alias_name=a_data["alias_name"]).first()
            if not alias:
                alias = models.PersonAlias(
                    alias_name=a_data["alias_name"],
                    canonical_user_id=canonical_user.id
                )
                db.add(alias)
        db.commit()
        print("Database successfully seeded.")
        
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
