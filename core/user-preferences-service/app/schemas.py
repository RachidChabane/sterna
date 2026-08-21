"""Pydantic schemas for request/response validation."""

from typing import Any, Dict, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class PreferenceBase(BaseModel):
    """Base preference schema."""

    preference_key: str = Field(..., min_length=1, max_length=255)
    preference_value: Any
    category: Optional[str] = Field(None, max_length=100)


class PreferenceCreate(PreferenceBase):
    """Schema for creating a preference."""

    pass


class PreferenceUpdate(BaseModel):
    """Schema for updating a preference."""

    preference_value: Any
    category: Optional[str] = Field(None, max_length=100)


class PreferenceResponse(PreferenceBase):
    """Schema for preference response."""

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PreferenceBulkUpdate(BaseModel):
    """Schema for bulk updating preferences."""

    preferences: Dict[str, Any] = Field(..., description="Dictionary of key-value pairs to update")


class PreferenceListResponse(BaseModel):
    """Schema for list of preferences response."""

    preferences: Dict[str, Any]
    count: int


class HealthResponse(BaseModel):
    """Schema for health check response."""

    status: str
    version: str
    timestamp: datetime
