"""
News Verification Service - Production-grade orchestrator for the news verification pipeline.
Handles background execution, database persistence, and error recovery.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from backend.core.logging import get_logger
from backend.core.config import settings
from backend.database.db_client import get_db_client
from backend.services.news_pipeline_evidence_first import NewsPipelineEvidenceFirst

logger = get_logger(__name__)


class NewsVerificationService:
    """Production-grade service for news verification workflows."""

    def __init__(self):
        self._client = None
        self._active_tasks: Dict[str, asyncio.Task] = {}

    def _get_client(self):
        if self._client is None:
            self._client = get_db_client()
        return self._client

    async def start_verification(
        self,
        analysis_id: str,
        user_id: str,
        input_type: str,
        input_content: str,
        title: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start news verification pipeline in background."""
        logger.info(f"[NewsVerification] Starting pipeline for analysis {analysis_id}")
        print(f"[NewsVerification] Starting pipeline for analysis {analysis_id}", flush=True)
        
        try:
            client = self._get_client()
            
            # Update status to processing
            client.schema("public").table("news_analyses").update({
                "status": "processing",
                "progress": 5,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", analysis_id).execute()
            
            logger.info(f"[NewsVerification] Status updated to processing for {analysis_id}")
            print(f"[NewsVerification] Status updated to processing for {analysis_id}", flush=True)
            
            # Run the evidence-first pipeline
            print(f"[NewsVerification] Creating NewsPipelineEvidenceFirst instance", flush=True)
            pipeline = NewsPipelineEvidenceFirst(user_id=user_id, analysis_id=analysis_id)
            print(f"[NewsVerification] Starting pipeline.run()", flush=True)
            
            result = await pipeline.run(
                input_type=input_type,
                input_content=input_content,
                title=title or "",
                source_url=source_url,
            )
            
            print(f"[NewsVerification] pipeline.run() returned: {json.dumps(result, default=str)[:500]}", flush=True)
            logger.info(f"[NewsVerification] Pipeline completed for {analysis_id}: {result.get('verdict')}")
            
            return {
                "success": True,
                "analysis_id": analysis_id,
                "verdict": result.get("verdict", "unknown"),
                "confidence": result.get("confidence", 0.0),
                "trust_score": result.get("trust_score", 0),
                "risk_level": result.get("risk_level", "medium"),
                "processing_time_ms": result.get("processing_time_ms", 0),
            }
            
        except Exception as e:
            logger.error(f"[NewsVerification] Pipeline failed for {analysis_id}: {e}")
            print(f"[NewsVerification] Pipeline failed: {e}", flush=True)
            
            # Update status to failed
            try:
                client = self._get_client()
                client.schema("public").table("news_analyses").update({
                    "status": "failed",
                    "error_message": str(e)[:500],
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", analysis_id).execute()
            except Exception as update_error:
                logger.error(f"[NewsVerification] Failed to update error status: {update_error}")
            
            raise

    async def get_analysis(self, analysis_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a single news analysis with all related data."""
        try:
            client = self._get_client()
            
            # Get analysis
            result = client.schema("public").table("news_analyses").select("*").eq("id", analysis_id).execute()
            if not result.data:
                return None
            
            analysis = result.data[0]
            if analysis.get("user_id") != user_id:
                return None
            
            # Get related data
            agent_results = client.schema("public").table("news_agent_results").select("*").eq("analysis_id", analysis_id).execute()
            evidence = client.schema("public").table("news_evidence").select("*").eq("analysis_id", analysis_id).execute()
            report_result = client.schema("public").table("news_reports").select("*").eq("analysis_id", analysis_id).execute()
            
            return {
                "analysis": analysis,
                "agent_results": agent_results.data or [],
                "evidence": evidence.data or [],
                "report": report_result.data[0] if report_result.data else None,
            }
        except Exception as e:
            logger.error(f"[NewsVerification] Failed to get analysis {analysis_id}: {e}")
            return None

    async def list_analyses(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List news analyses for user."""
        try:
            client = self._get_client()
            query = client.schema("public").table("news_analyses").select("*", count="exact").eq("user_id", user_id).order("created_at", desc=True).limit(limit).offset(offset)
            if status:
                query = query.eq("status", status)
            result = query.execute()
            
            return {
                "analyses": result.data or [],
                "count": result.count if hasattr(result, 'count') else len(result.data or []),
            }
        except Exception as e:
            logger.error(f"[NewsVerification] Failed to list analyses: {e}")
            return {"analyses": [], "count": 0}

    async def get_dashboard_stats(self, user_id: str) -> Dict[str, Any]:
        """Get dashboard statistics."""
        try:
            client = self._get_client()
            
            # Get all analyses for user
            result = client.schema("public").table("news_analyses").select("*", count="exact").eq("user_id", user_id).execute()
            analyses = result.data or []
            
            total = len(analyses)
            completed = sum(1 for a in analyses if a.get("status") == "completed")
            processing = sum(1 for a in analyses if a.get("status") == "processing")
            queued = sum(1 for a in analyses if a.get("status") == "queued")
            failed = sum(1 for a in analyses if a.get("status") == "failed")
            
            # Average trust score
            scores = [a.get("trust_score", 0) or 0 for a in analyses if a.get("status") == "completed" and a.get("trust_score") is not None]
            avg_trust_score = round(sum(scores) / len(scores), 1) if scores else 0
            
            # Average confidence
            confidences = [a.get("confidence", 0) or 0 for a in analyses if a.get("status") == "completed" and a.get("confidence") is not None]
            avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0
            
            # Risk distribution
            risk_dist = {"minimal": 0, "low": 0, "medium": 0, "high": 0, "critical": 0}
            for a in analyses:
                rl = a.get("risk_level", "medium")
                if rl in risk_dist:
                    risk_dist[rl] += 1
            
            # Report count
            reports_result = client.schema("public").table("news_reports").select("id", count="exact").eq("user_id", user_id).execute()
            total_reports = reports_result.count if hasattr(reports_result, 'count') else len(reports_result.data or [])
            
            return {
                "total_analyses": total,
                "completed_analyses": completed,
                "processing_analyses": processing,
                "queued_analyses": queued,
                "failed_analyses": failed,
                "total_reports": total_reports,
                "average_trust_score": avg_trust_score,
                "average_confidence": avg_confidence,
                "risk_distribution": risk_dist,
            }
        except Exception as e:
            logger.error(f"[NewsVerification] Failed to get dashboard stats: {e}")
            return {
                "total_analyses": 0, "completed_analyses": 0, "processing_analyses": 0,
                "queued_analyses": 0, "failed_analyses": 0, "total_reports": 0,
                "average_trust_score": 0, "average_confidence": 0,
                "risk_distribution": {"minimal": 0, "low": 0, "medium": 0, "high": 0, "critical": 0},
            }

    async def delete_analysis(self, analysis_id: str, user_id: str) -> bool:
        """Delete a news analysis and all related data."""
        try:
            client = self._get_client()
            
            # Delete related data first (cascade should handle this, but be explicit)
            for table in ["news_evidence", "news_agent_results", "news_reports"]:
                try:
                    client.schema("public").table(table).delete().eq("analysis_id", analysis_id).execute()
                except:
                    pass
            
            # Delete analysis
            client.schema("public").table("news_analyses").delete().eq("id", analysis_id).eq("user_id", user_id).execute()
            
            # Clean up storage
            try:
                client.storage.from_("visionx-reports").remove([f"reports/{analysis_id}.pdf"])
            except:
                pass
            
            return True
        except Exception as e:
            logger.error(f"[NewsVerification] Failed to delete analysis {analysis_id}: {e}")
            return False

    async def get_report(self, analysis_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get report for an analysis."""
        try:
            client = self._get_client()
            result = client.schema("public").table("news_reports").select("*").eq("analysis_id", analysis_id).execute()
            if not result.data:
                return None
            report = result.data[0]
            if report.get("user_id") != user_id:
                return None
            return report
        except Exception as e:
            logger.error(f"[NewsVerification] Failed to get report: {e}")
            return None

    async def list_reports(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List reports for user."""
        try:
            client = self._get_client()
            result = client.schema("public").table("news_reports").select("*", count="exact").eq("user_id", user_id).order("created_at", desc=True).limit(limit).offset(offset).execute()
            return {
                "reports": result.data or [],
                "count": result.count if hasattr(result, 'count') else len(result.data or []),
            }
        except Exception as e:
            logger.error(f"[NewsVerification] Failed to list reports: {e}")
            return {"reports": [], "count": 0}

    async def cleanup_stuck_analyses(self) -> Dict[str, Any]:
        """Clean up analyses stuck in queued/processing for too long."""
        try:
            client = self._get_client()
            from datetime import timedelta
            
            # Find stuck analyses (older than 30 minutes)
            result = client.schema("public").table("news_analyses").select("*").in_("status", ["queued", "processing"]).execute()
            stuck = result.data or []
            
            cleaned = 0
            now = datetime.now(timezone.utc)
            
            for analysis in stuck:
                created = analysis.get("created_at")
                if created:
                    if isinstance(created, str):
                        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age_minutes = (now - created).total_seconds() / 60
                    
                    if age_minutes > 30:
                        client.schema("public").table("news_analyses").update({
                            "status": "failed",
                            "error_message": "Analysis timed out after 30 minutes",
                            "completed_at": now.isoformat(),
                        }).eq("id", analysis["id"]).execute()
                        cleaned += 1
                        logger.info(f"[NewsVerification] Cleaned up stuck analysis {analysis['id']} (age: {age_minutes:.0f} min)")
            
            return {"cleaned": cleaned, "total_stuck": len(stuck)}
        except Exception as e:
            logger.error(f"[NewsVerification] Cleanup failed: {e}")
            return {"cleaned": 0, "total_stuck": 0, "error": str(e)}


# Global service instance
news_verification_service = NewsVerificationService()