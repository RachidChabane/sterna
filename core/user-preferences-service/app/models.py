"""SQLAlchemy models for user preferences."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class UserPreference(Base):
    """User preference model."""

    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    preference_key = Column(String(255), nullable=False)
    preference_value = Column(JSONB, nullable=False)
    category = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'preference_key', name='unique_user_preference'),
        Index('idx_user_category', 'user_id', 'category'),
    )

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "preference_key": self.preference_key,
            "preference_value": self.preference_value,
            "category": self.category,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
