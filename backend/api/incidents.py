"""
Incidents Routes - REST endpoints for incidents.
"""

from __future__ import annotations

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.api.dependencies import get_current_user
from backend.database.db_client import get_db_client

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def _client():
    return get_db_client().schema("public")


class IncidentCreate(BaseModel):
    title: str
    description: str = ""
    severity: str = "medium"
    status: str = "open"
    metadata: Optional[dict] = None


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict] = None


@router.get("/")
async def list_incidents(
    user_id: str = Depends(get_current_user),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List incidents for current user."""
    try:
        query = _client().table("incidents").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).offset(offset)
        if status:
            query = query.eq("status", status)
        result = query.execute()
        return {
            "success": True,
            "incidents": result.data or [],
            "count": len(result.data or []),
        }
    except Exception as e:
        logger.error(f"Failed to list incidents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{incident_id}")
async def get_incident(
    incident_id: str,
    user_id: str = Depends(get_current_user),
):
    """Get incident by ID."""
    try:
        result = _client().table("incidents").select("*").eq("id", incident_id).execute()
        if not result.data:
            raise NotFoundError(resource="Incident", resource_id=incident_id)
        incident = result.data[0]
        if incident.get("user_id") != user_id:
            raise NotFoundError(resource="Incident", resource_id=incident_id)
        return {
            "success": True,
            "incident": incident,
        }
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to get incident {incident_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_incident(
    data: IncidentCreate,
    user_id: str = Depends(get_current_user),
):
    """Create a new incident."""
    try:
        now = datetime.utcnow().isoformat()
        result = _client().table("incidents").insert({
            "user_id": user_id,
            "title": data.title,
            "description": data.description,
            "severity": data.severity,
            "status": data.status,
            "metadata": data.metadata or {},
            "created_at": now,
            "updated_at": now,
        }).execute()
        return {
            "success": True,
            "incident": result.data[0] if result.data else None,
        }
    except Exception as e:
        logger.error(f"Failed to create incident: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{incident_id}")
async def update_incident(
    incident_id: str,
    data: IncidentUpdate,
    user_id: str = Depends(get_current_user),
):
    """Update an existing incident."""
    try:
        update_data = {"updated_at": datetime.utcnow().isoformat()}
        if data.title is not None:
            update_data["title"] = data.title
        if data.description is not None:
            update_data["description"] = data.description
        if data.severity is not None:
            update_data["severity"] = data.severity
        if data.status is not None:
            update_data["status"] = data.status
        if data.metadata is not None:
            update_data["metadata"] = data.metadata

        result = _client().table("incidents").update(update_data).eq("id", incident_id).eq("user_id", user_id).execute()
        if not result.data:
            raise NotFoundError(resource="Incident", resource_id=incident_id)
        return {
            "success": True,
            "incident": result.data[0],
        }
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to update incident {incident_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{incident_id}")
async def delete_incident(
    incident_id: str,
    user_id: str = Depends(get_current_user),
):
    """Delete incident."""
    try:
        _client().table("incidents").delete().eq("id", incident_id).eq("user_id", user_id).execute()
        return {
            "success": True,
            "message": f"Incident {incident_id} deleted",
        }
    except Exception as e:
        logger.error(f"Failed to delete incident {incident_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))