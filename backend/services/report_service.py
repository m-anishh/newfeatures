"""
Report Service - Coordinates report generation and retrieval.
Uses the database client directly instead of a repository dependency.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

import os
from backend.core.logging import get_logger
from backend.core.exceptions import AnalysisError
from backend.database.db_client import get_db_client

# API base URL for constructing full PDF URLs
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

logger = get_logger(__name__)


class ReportService:
    """
    Service for managing reports.
    Uses the database client directly for database operations.
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = get_db_client()
        return self._client

    def _table(self):
        return self._get_client().schema("public").table("reports")

    async def get_report(self, report_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get report by ID."""
        try:
            result = self._table().select("*").eq("id", report_id).eq("user_id", user_id).execute()
            if result.data:
                return {"report": result.data[0]}
            return None
        except Exception as e:
            logger.error(f"[ReportService] Failed to get report {report_id}: {e}")
            raise AnalysisError(message=f"Failed to get report: {e}") from e

    async def get_report_by_analysis_id(self, analysis_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get report by analysis ID."""
        try:
            result = self._table().select("*").eq("analysis_id", analysis_id).eq("user_id", user_id).execute()
            if result.data:
                return {"report": result.data[0]}
            return None
        except Exception as e:
            logger.error(f"[ReportService] Failed to get report by analysis {analysis_id}: {e}")
            raise AnalysisError(message=f"Failed to get report: {e}") from e

    async def list_reports(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List reports for user."""
        try:
            # Fetch reports with upload info via foreign key
            # reports.upload_id -> uploads.id
            result = self._table()\
                .select("*, uploads(original_filename, public_url, mime_type, file_size)")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .offset(offset)\
                .execute()
            
            reports = []
            for r in (result.data or []):
                upload = r.get("uploads") or {}
                pdf_url = r.get("pdf_url")
                # Ensure pdf_url is a full URL
                if pdf_url and not pdf_url.startswith("http"):
                    pdf_url = f"{API_BASE_URL}{pdf_url}"
                
                reports.append({
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "trust_score": r.get("trust_score"),
                    "authenticity_status": r.get("authenticity_status"),
                    "risk_level": r.get("risk_level"),
                    "pdf_url": pdf_url,
                    "created_at": r.get("created_at"),
                    "analysis_id": r.get("analysis_id"),
                    "report_data": r.get("report_data"),
                    "download_count": r.get("download_count"),
                    "upload": {
                        "original_filename": upload.get("original_filename"),
                        "public_url": upload.get("public_url"),
                        "content_type": upload.get("mime_type"),
                        "file_size": upload.get("file_size"),
                    } if upload else None,
                })
            return reports
        except Exception as e:
            logger.error(f"[ReportService] Failed to list reports: {e}")
            raise AnalysisError(message=f"Failed to list reports: {e}") from e

    async def delete_report(self, report_id: str, user_id: str) -> bool:
        """Delete report."""
        try:
            self._table().delete().eq("id", report_id).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.error(f"[ReportService] Failed to delete report {report_id}: {e}")
            raise AnalysisError(message=f"Failed to delete report: {e}") from e


# Global service instance
report_service = ReportService()