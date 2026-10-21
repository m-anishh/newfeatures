"""
Incident Service - Coordinates incident management.
Uses the database client directly instead of a repository dependency.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from backend.core.logging import get_logger
from backend.core.exceptions import AnalysisError
from backend.database.db_client import get_db_client

logger = get_logger(__name__)


class IncidentService:
    """
    Service for managing incidents.
    Uses the database client directly for database operations.
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = get_db_client()
        return self._client

    def _table(self):
        return self._get_client().schema("visionx").table("incidents")

    async def get_incident(self, incident_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get incident by ID."""
        try:
            result = self._table().select("*").eq("id", incident_id).eq("user_id", user_id).execute()
            if result.data:
                return {"incident": result.data[0]}
            return None
        except Exception as e:
            logger.error(f"[IncidentService] Failed to get incident {incident_id}: {e}")
            raise AnalysisError(message=f"Failed to get incident: {e}") from e

    async def list_incidents(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List incidents for user."""
        try:
            query = self._table()\
                .select("*")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .offset(offset)

            if status:
                query = query.eq("status", status)

            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[IncidentService] Failed to list incidents: {e}")
            raise AnalysisError(message=f"Failed to list incidents: {e}") from e

    async def create_incident(
        self,
        user_id: str,
        title: str,
        description: str,
        severity: str = "medium",
        status: str = "open",
        metadata: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Create a new incident."""
        try:
            import uuid
            data = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "title": title,
                "description": description,
                "severity": severity,
                "status": status,
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            result = self._table().insert(data).execute()
            if result.data:
                return result.data[0]
            return data
        except Exception as e:
            logger.error(f"[IncidentService] Failed to create incident: {e}")
            raise AnalysisError(message=f"Failed to create incident: {e}") from e

    async def update_incident(
        self,
        incident_id: str,
        user_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update an existing incident."""
        try:
            updates = {"updated_at": datetime.utcnow().isoformat()}
            if title is not None:
                updates["title"] = title
            if description is not None:
                updates["description"] = description
            if severity is not None:
                updates["severity"] = severity
            if status is not None:
                updates["status"] = status
            if metadata is not None:
                updates["metadata"] = metadata

            result = self._table().update(updates).eq("id", incident_id).eq("user_id", user_id).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"[IncidentService] Failed to update incident {incident_id}: {e}")
            raise AnalysisError(message=f"Failed to update incident: {e}") from e

    async def delete_incident(self, incident_id: str, user_id: str) -> bool:
        """Delete incident."""
        try:
            self._table().delete().eq("id", incident_id).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.error(f"[IncidentService] Failed to delete incident {incident_id}: {e}")
            raise AnalysisError(message=f"Failed to delete incident: {e}") from e


# Global service instance
incident_service = IncidentService()