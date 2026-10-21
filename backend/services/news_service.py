"""
News Service - Coordinates news verification workflows.
Uses the database client directly instead of a repository dependency.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List

from backend.core.logging import get_logger
from backend.core.exceptions import AnalysisError
from backend.database.db_client import get_db_client

logger = get_logger(__name__)


class NewsService:
    """
    Service for news verification workflows.
    Uses the database client directly for database operations.
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = get_db_client()
        return self._client

    def _table(self, name: str):
        return self._get_client().schema("public").table(name)

    async def get_dashboard_stats(self, user_id: str) -> Dict[str, Any]:
        """Get news dashboard statistics."""
        try:
            # Get news analyses
            analyses_result = self._table("news_analyses")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()
            
            # Get news reports
            reports_result = self._table("news_reports")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()
            
            analyses = analyses_result.data or []
            reports = reports_result.data or []
            
            # Calculate stats
            total = len(analyses)
            completed = sum(1 for a in analyses if a.get("status") == "completed")
            failed = sum(1 for a in analyses if a.get("status") == "failed")
            
            # Average authenticity score
            scores = [a.get("authenticity_score", 0) or 0 for a in analyses if a.get("status") == "completed"]
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0
            
            # Distribution
            risk_dist = {"minimal": 0, "low": 0, "medium": 0, "high": 0, "critical": 0}
            for a in analyses:
                rl = a.get("risk_level", "medium")
                if rl in risk_dist:
                    risk_dist[rl] += 1
            
            return {
                "total_analyses": total,
                "completed_analyses": completed,
                "failed_analyses": failed,
                "total_reports": len(reports),
                "average_authenticity_score": avg_score,
                "risk_distribution": risk_dist,
            }
        except Exception as e:
            logger.error(f"[NewsService] Failed to get news dashboard stats: {e}")
            return {
                "total_analyses": 0,
                "completed_analyses": 0,
                "failed_analyses": 0,
                "total_reports": 0,
                "average_authenticity_score": 0,
                "risk_distribution": {"minimal": 0, "low": 0, "medium": 0, "high": 0, "critical": 0},
            }

    async def list_analyses(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List news analyses for user."""
        try:
            result = self._table("news_analyses")\
                .select("*")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .offset(offset)\
                .execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[NewsService] Failed to list news analyses: {e}")
            raise AnalysisError(message=f"Failed to list news analyses: {e}") from e

    async def get_report(self, report_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get news report by ID."""
        try:
            result = self._table("news_reports").select("*").eq("id", report_id).eq("user_id", user_id).execute()
            if result.data:
                return {"report": result.data[0]}
            return None
        except Exception as e:
            logger.error(f"[NewsService] Failed to get news report {report_id}: {e}")
            raise AnalysisError(message=f"Failed to get news report: {e}") from e

    async def get_report_by_analysis_id(self, analysis_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get news report by analysis ID."""
        try:
            result = self._table("news_reports").select("*").eq("analysis_id", analysis_id).eq("user_id", user_id).execute()
            if result.data:
                return {"report": result.data[0]}
            return None
        except Exception as e:
            logger.error(f"[NewsService] Failed to get news report by analysis {analysis_id}: {e}")
            raise AnalysisError(message=f"Failed to get news report: {e}") from e

    async def list_reports(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List news reports for user."""
        try:
            result = self._table("news_reports")\
                .select("*")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .offset(offset)\
                .execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[NewsService] Failed to list news reports: {e}")
            raise AnalysisError(message=f"Failed to list news reports: {e}") from e


# Global service instance
news_service = NewsService()