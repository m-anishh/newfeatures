"""
Dashboard Service - Coordinates dashboard statistics.
Uses the database client directly for database operations.
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from backend.core.logging import get_logger
from backend.database.db_client import get_db_client

logger = get_logger(__name__)


class DashboardService:
    """
    Service for dashboard statistics.
    Uses the database client directly for database operations.
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = get_db_client()
        return self._client

    def get_dashboard_stats(self, user_id: str) -> Dict[str, Any]:
        """Get dashboard statistics for user."""
        try:
            client = self._get_client()
            
            # Get image analysis counts
            analyses_result = client.schema("public").table("analysis_jobs")\
                .select("*", count="exact")\
                .eq("user_id", user_id)\
                .execute()
            
            # Get report counts (image reports)
            reports_result = client.schema("public").table("reports")\
                .select("*", count="exact")\
                .eq("user_id", user_id)\
                .execute()
            
            # Get news analyses
            news_analyses_result = client.schema("public").table("news_analyses")\
                .select("*", count="exact")\
                .eq("user_id", user_id)\
                .execute()
            
            # Get news reports
            news_reports_result = client.schema("public").table("news_reports")\
                .select("*", count="exact")\
                .eq("user_id", user_id)\
                .execute()
            
            # Get incident counts
            incidents_result = client.schema("public").table("incidents")\
                .select("*", count="exact")\
                .eq("user_id", user_id)\
                .execute()
            
            analyses = analyses_result.data or []
            reports = reports_result.data or []
            news_analyses = news_analyses_result.data or []
            news_reports = news_reports_result.data or []
            
            # Combine image and news analyses
            all_analyses = analyses + news_analyses
            
            # Calculate statistics
            total_analyses = len(all_analyses)
            completed = sum(1 for a in all_analyses if a.get("status") == "completed")
            failed = sum(1 for a in all_analyses if a.get("status") == "failed")
            in_progress = sum(1 for a in all_analyses if a.get("status") in ("processing", "queued"))
            
            # Calculate average trust score from completed (both image and news)
            image_trust_scores = [(a.get("overall_confidence", 0) or 0) * 100 for a in analyses if a.get("status") == "completed"]
            news_trust_scores = [a.get("trust_score", 0) or 0 for a in news_analyses if a.get("status") == "completed"]
            all_trust_scores = image_trust_scores + news_trust_scores
            avg_trust_score = round(sum(all_trust_scores) / len(all_trust_scores), 1) if all_trust_scores else 0
            
            # Get recent analyses (last 5 from both)
            recent = sorted(all_analyses, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
            
            # Count by status (combined)
            status_counts = {}
            for a in all_analyses:
                status = a.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # Count by module
            module_counts = {
                "image": len(analyses),
                "news": len(news_analyses),
            }
            
            # Total reports (image + news)
            total_reports = len(reports) + len(news_reports)
            
            # Count high risk incidents
            high_risk_incidents = sum(1 for i in (incidents_result.data or []) if i.get("severity") in ("high", "critical"))
            
            return {
                "total_analyses": total_analyses,
                "total_scans": total_analyses,
                "completed_analyses": completed,
                "total_reports": total_reports,
                "completed_reports": total_reports,
                "failed_analyses": failed,
                "processing_analyses": in_progress,
                "total_incidents": len(incidents_result.data or []),
                "high_risk_incidents": high_risk_incidents,
                "average_trust_score": avg_trust_score,
                "status_distribution": status_counts,
                "module_distribution": module_counts,
                "recent_scans": [
                    {
                        "id": a.get("id"),
                        "filename": a.get("title") or (a.get("input_content") or "")[:50],
                        "title": a.get("title"),
                        "module": a.get("module_type") or "news",
                        "status": a.get("status"),
                        "trust_score": round((a.get("overall_confidence", a.get("trust_score", 0)) or 0) * 100, 1),
                        "created_at": a.get("created_at"),
                    }
                    for a in recent
                ],
                "recent_analyses": [
                    {
                        "id": a.get("id"),
                        "title": a.get("title"),
                        "module": a.get("module_type") or "news",
                        "status": a.get("status"),
                        "trust_score": round((a.get("overall_confidence", a.get("trust_score", 0)) or 0) * 100, 1),
                        "created_at": a.get("created_at"),
                    }
                    for a in recent
                ],
                "running_jobs": status_counts.get("processing", 0) + status_counts.get("queued", 0),
                "completed_jobs": completed,
            }
        except Exception as e:
            logger.error(f"[DashboardService] Failed to get dashboard stats: {e}")
            return {
                "total_analyses": 0,
                "completed_analyses": 0,
                "failed_analyses": 0,
                "in_progress_analyses": 0,
                "total_reports": 0,
                "total_incidents": 0,
                "high_risk_incidents": 0,
                "average_trust_score": 0,
                "status_distribution": {},
                "module_distribution": {},
                "recent_analyses": [],
            }


# Global service instance
dashboard_service = DashboardService()