"""FastAPI application for User Preferences Microservice."""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import __version__
from app.config import settings
from app.database import get_db, init_db
from app.auth import CurrentUser
from app import crud, schemas
from app._observability import RequestIDMiddleware, init_observability

init_observability(service="user-preferences", app_loggers=("app",))
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="A standalone microservice for managing user preferences",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Read/mint X-Request-ID and expose it to the log filters (cross-service
# correlation with Django / api-gateway).
app.add_middleware(RequestIDMiddleware)


# Startup event
@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_db()


# Health check endpoint (no authentication required)
@app.get("/health", response_model=schemas.HealthResponse)
async def health_check():
    """Health check endpoint."""
    return schemas.HealthResponse(
        status="healthy",
        version=__version__,
        timestamp=datetime.utcnow(),
    )


# Get all user preferences
@app.get(
    "/api/v1/preferences",
    response_model=schemas.PreferenceListResponse,
    summary="Get all user preferences",
)
async def get_preferences(
    category: Optional[str] = None,
    user_id: UUID = Depends(CurrentUser),
    db: Session = Depends(get_db),
):
    """
    Get all preferences for the authenticated user.

    - **category**: Optional filter by category (e.g., 'ui', 'models')
    """
    preferences = crud.get_user_preferences(db, user_id, category)

    # Convert to dict format {key: value}
    prefs_dict = {pref.preference_key: pref.preference_value for pref in preferences}

    return schemas.PreferenceListResponse(preferences=prefs_dict, count=len(prefs_dict))


# Get a specific preference
@app.get(
    "/api/v1/preferences/{preference_key}",
    summary="Get a specific preference",
)
async def get_preference(
    preference_key: str,
    user_id: UUID = Depends(CurrentUser),
    db: Session = Depends(get_db),
):
    """
    Get a specific preference by key.

    - **preference_key**: The preference key (e.g., 'ui.theme', 'models.favorites')
    """
    preference = crud.get_user_preference(db, user_id, preference_key)

    if not preference:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preference '{preference_key}' not found",
        )

    return {
        "preference_key": preference.preference_key,
        "preference_value": preference.preference_value,
        "category": preference.category,
    }


# Update or create a single preference
@app.put(
    "/api/v1/preferences/{preference_key}",
    response_model=schemas.PreferenceResponse,
    summary="Update or create a preference",
)
async def update_preference(
    preference_key: str,
    preference_data: schemas.PreferenceUpdate,
    user_id: UUID = Depends(CurrentUser),
    db: Session = Depends(get_db),
):
    """
    Update or create a specific preference.

    - **preference_key**: The preference key
    - **preference_value**: The value to set (can be any JSON-compatible type)
    - **category**: Optional category for organization
    """
    preference = crud.update_preference(db, user_id, preference_key, preference_data)
    return schemas.PreferenceResponse(**preference.to_dict())


# Bulk update preferences
@app.put(
    "/api/v1/preferences",
    summary="Bulk update preferences",
)
async def bulk_update_preferences(
    bulk_data: schemas.PreferenceBulkUpdate,
    user_id: UUID = Depends(CurrentUser),
    db: Session = Depends(get_db),
):
    """
    Bulk update or create multiple preferences.

    - **preferences**: Dictionary of {key: value} pairs
    """
    preferences = crud.bulk_update_preferences(db, user_id, bulk_data.preferences)

    return {
        "message": f"Successfully updated {len(preferences)} preferences",
        "updated_keys": list(bulk_data.preferences.keys()),
    }


# Delete a preference
@app.delete(
    "/api/v1/preferences/{preference_key}",
    summary="Delete a preference",
)
async def delete_preference(
    preference_key: str,
    user_id: UUID = Depends(CurrentUser),
    db: Session = Depends(get_db),
):
    """
    Delete a specific preference.

    - **preference_key**: The preference key to delete
    """
    deleted = crud.delete_preference(db, user_id, preference_key)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preference '{preference_key}' not found",
        )

    return {"message": f"Preference '{preference_key}' deleted successfully"}


# Delete all user preferences (use with caution)
@app.delete(
    "/api/v1/preferences",
    summary="Delete all preferences",
)
async def delete_all_preferences(
    user_id: UUID = Depends(CurrentUser),
    db: Session = Depends(get_db),
):
    """
    Delete all preferences for the authenticated user.

    **Warning**: This action cannot be undone!
    """
    deleted_count = crud.delete_all_user_preferences(db, user_id)

    return {
        "message": f"Successfully deleted {deleted_count} preferences",
        "deleted_count": deleted_count,
    }


# Root endpoint
@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint - redirects to docs."""
    return {
        "message": "User Preferences Microservice",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }
