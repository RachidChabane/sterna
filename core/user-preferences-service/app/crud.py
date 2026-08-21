"""CRUD operations for user preferences."""

from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import UserPreference
from app.schemas import PreferenceCreate, PreferenceUpdate


def get_user_preference(
    db: Session, user_id: UUID, preference_key: str
) -> Optional[UserPreference]:
    """Get a specific preference for a user."""
    return (
        db.query(UserPreference)
        .filter(
            and_(
                UserPreference.user_id == user_id,
                UserPreference.preference_key == preference_key,
            )
        )
        .first()
    )


def get_user_preferences(
    db: Session, user_id: UUID, category: Optional[str] = None
) -> List[UserPreference]:
    """Get all preferences for a user, optionally filtered by category."""
    query = db.query(UserPreference).filter(UserPreference.user_id == user_id)

    if category:
        query = query.filter(UserPreference.category == category)

    return query.all()


def create_preference(
    db: Session, user_id: UUID, preference: PreferenceCreate
) -> UserPreference:
    """Create a new preference."""
    db_preference = UserPreference(
        user_id=user_id,
        preference_key=preference.preference_key,
        preference_value=preference.preference_value,
        category=preference.category,
    )
    db.add(db_preference)
    db.commit()
    db.refresh(db_preference)
    return db_preference


def update_preference(
    db: Session,
    user_id: UUID,
    preference_key: str,
    preference_update: PreferenceUpdate,
) -> Optional[UserPreference]:
    """Update an existing preference or create if it doesn't exist."""
    db_preference = get_user_preference(db, user_id, preference_key)

    if db_preference:
        # Update existing
        db_preference.preference_value = preference_update.preference_value
        if preference_update.category is not None:
            db_preference.category = preference_update.category
    else:
        # Create new
        db_preference = UserPreference(
            user_id=user_id,
            preference_key=preference_key,
            preference_value=preference_update.preference_value,
            category=preference_update.category,
        )
        db.add(db_preference)

    db.commit()
    db.refresh(db_preference)
    return db_preference


def bulk_update_preferences(
    db: Session, user_id: UUID, preferences: Dict[str, Any]
) -> List[UserPreference]:
    """Bulk update or create multiple preferences."""
    updated_preferences = []

    for key, value in preferences.items():
        db_preference = get_user_preference(db, user_id, key)

        if db_preference:
            # Update existing
            db_preference.preference_value = value
        else:
            # Create new - infer category from key prefix (e.g., "ui.theme" -> "ui")
            category = key.split(".")[0] if "." in key else None
            db_preference = UserPreference(
                user_id=user_id,
                preference_key=key,
                preference_value=value,
                category=category,
            )
            db.add(db_preference)

        updated_preferences.append(db_preference)

    db.commit()

    # Refresh all preferences
    for pref in updated_preferences:
        db.refresh(pref)

    return updated_preferences


def delete_preference(db: Session, user_id: UUID, preference_key: str) -> bool:
    """Delete a preference."""
    db_preference = get_user_preference(db, user_id, preference_key)

    if db_preference:
        db.delete(db_preference)
        db.commit()
        return True

    return False


def delete_all_user_preferences(db: Session, user_id: UUID) -> int:
    """Delete all preferences for a user. Returns count of deleted preferences."""
    deleted_count = (
        db.query(UserPreference).filter(UserPreference.user_id == user_id).delete()
    )
    db.commit()
    return deleted_count
