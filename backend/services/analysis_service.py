"""
Analysis Service - Coordinates analysis workflows.
Uses the database client directly instead of a repository dependency.
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from backend.core.logging import get_logger
from backend.core.exceptions import AnalysisError, ValidationError
from backend.events.event_bus import event_bus
from backend.database.db_client import get_db_client
from backend.services.agents.pipeline_orchestrator import pipeline_orchestrator
from backend.services.video_analysis_service import video_analysis_service

logger = get_logger(__name__)


class AnalysisService:
    """
    Service for managing analysis workflows.
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

    async def start_analysis(
        self,
        user_id: str,
        module: str,
        input_content: str,
        input_type: str,
        source_url: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a new analysis."""
        logger.info(f"[AnalysisService] Starting {module} analysis for user {user_id}")

        analysis_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        try:
            # Publish created event
            await event_bus.publish_analysis_created(
                analysis_id=analysis_id,
                module=module,
                user_id=user_id,
                input_type=input_type,
                source_url=source_url,
                title=title,
            )

            # Save to database
            data = {
                "id": analysis_id,
                "user_id": user_id,
                "module_type": module,
                "input_type": input_type,
                "source_url": source_url or "",
                "title": title or "",
                "status": "queued",
                "progress": 0,
                "created_at": now,
                "updated_at": now,
            }
            # Avoid sending columns that may not exist in the current schema cache
            self._table("analysis_jobs").insert(data).execute()

            # Start pipeline in background
            import asyncio
            asyncio.create_task(
                self._run_pipeline(
                    analysis_id=analysis_id,
                    user_id=user_id,
                    module=module,
                    input_content=input_content,
                    input_type=input_type,
                    source_url=source_url,
                    title=title,
                    created_at=now,
                )
            )

            logger.info(f"[AnalysisService] Analysis {analysis_id} queued")
            return analysis_id

        except Exception as e:
            logger.error(f"[AnalysisService] Failed to start analysis: {e}")
            raise AnalysisError(message=f"Failed to start analysis: {e}") from e

    async def _run_pipeline(
        self,
        analysis_id: str,
        user_id: str,
        module: str,
        input_content: str,
        input_type: str,
        source_url: Optional[str],
        title: Optional[str],
        created_at: str,
    ) -> None:
        """Run analysis pipeline in background."""
        try:
            # Update status to processing
            self._table("analysis_jobs").update({
                "status": "processing",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", analysis_id).execute()

            # Publish started event
            await event_bus.publish_analysis_started(
                analysis_id=analysis_id,
                module=module,
                user_id=user_id,
                total_agents=5 if module == "image" else 6,
            )

            # Run real pipeline
            try:
                if module == "video":
                    pipeline_result = await video_analysis_service.analyze_video(
                        user_id=user_id,
                        video_path=input_content,
                        title=title,
                        analysis_id=analysis_id,
                    )
                else:
                    pipeline_result = await pipeline_orchestrator.run(
                        analysis_id=analysis_id,
                        module=module,
                        user_id=user_id,
                        input_content=input_content,
                        input_type=input_type,
                        source_url=source_url,
                        title=title,
                    )

                # Update to completed
                now = datetime.now(timezone.utc).isoformat()
                self._table("analysis_jobs").update({
                    "status": "completed",
                    "overall_confidence": pipeline_result.get("confidence", 0.0),
                    "overall_verdict": pipeline_result.get("verdict", "unknown"),
                    "risk_level": pipeline_result.get("risk_level", "medium"),
                    "completed_at": now,
                    "updated_at": now,
                    "agent_results": pipeline_result.get("agents", {}),
                }).eq("id", analysis_id).execute()

                # Save evidence items
                await self._save_evidence(analysis_id, pipeline_result.get("evidence", []))

                # Save report to database
                report_data = pipeline_result.get("report_data")
                pdf_path = pipeline_result.get("pdf_path")
                if report_data:
                    try:
                        # Build pdf_url from pdf_path if available
                        pdf_url = None
                        if pdf_path:
                            pdf_url = f"/api/reports/{analysis_id}/pdf"
                        
                        self._table("reports").insert({
                            "user_id": user_id,
                            "analysis_id": analysis_id,
                            "title": title or f"Analysis {analysis_id[:8]}",
                            "trust_score": report_data.get("executive_summary", {}).get("trust_score", 0),
                            "authenticity_status": report_data.get("executive_summary", {}).get("verdict", "unknown"),
                            "risk_level": report_data.get("executive_summary", {}).get("risk_level", "medium"),
                            "verdict": report_data.get("executive_summary", {}).get("verdict"),
                            "report_data": report_data,
                            "pdf_path": pdf_path,
                            "pdf_url": pdf_url,
                            "created_at": now,
                            "updated_at": now,
                        }).execute()
                        logger.info(f"[AnalysisService] Report saved for analysis {analysis_id}")
                    except Exception as e:
                        logger.warning(f"[AnalysisService] Report save failed: {e}")

                # Publish completed event
                await event_bus.publish_analysis_completed(
                    analysis_id=analysis_id,
                    verdict=pipeline_result.get("verdict", "unknown"),
                    confidence=pipeline_result.get("confidence", 0.0),
                    processing_time_ms=pipeline_result.get("processing_time_ms", 0.0),
                )

            except Exception as pipeline_error:
                logger.error(f"[AnalysisService] Pipeline execution failed: {pipeline_error}")
                raise

            logger.info(f"[AnalysisService] Analysis {analysis_id} completed")

        except Exception as e:
            logger.error(f"[AnalysisService] Pipeline failed for {analysis_id}: {e}")
            
            # Publish failed event
            await event_bus.publish_analysis_failed(
                analysis_id=analysis_id,
                error=str(e),
            )

            # Update analysis status
            try:
                self._table("analysis_jobs").update({
                    "status": "failed",
                    "error_message": str(e),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", analysis_id).execute()
            except Exception:
                pass

    async def get_analysis(self, analysis_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get analysis by ID."""
        try:
            result = self._table("analysis_jobs").select("*").eq("id", analysis_id).eq("user_id", user_id).execute()
            if not result.data:
                return None

            analysis = result.data[0]

            # Get evidence
            evidence_result = self._table("evidence_items").select("*").eq("analysis_id", analysis_id).execute()
            evidence_data = {}
            if evidence_result.data:
                for e in evidence_result.data:
                    etype = e.get("evidence_type", "general")
                    if etype not in evidence_data:
                        evidence_data[etype] = []
                    evidence_data[etype].append(e)

            # Get report
            report_result = self._table("reports").select("*").eq("analysis_id", analysis_id).eq("user_id", user_id).execute()
            report = report_result.data[0] if report_result.data else None

            return {
                "analysis": analysis,
                "evidence": evidence_data,
                "report": report,
            }
        except Exception as e:
            logger.error(f"[AnalysisService] Failed to get analysis {analysis_id}: {e}")
            raise AnalysisError(message=f"Failed to get analysis: {e}") from e

    async def get_analysis_status(self, analysis_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get analysis status."""
        try:
            result = self._table("analysis_jobs").select("*").eq("id", analysis_id).eq("user_id", user_id).execute()
            if not result.data:
                return None

            a = result.data[0]
            return {
                "id": analysis_id,
                "status": a.get("status"),
                "module": a.get("module_type"),
                "trust_score": a.get("overall_confidence"),
                "risk_level": a.get("risk_level"),
                "confidence": a.get("overall_confidence"),
                "verdict": a.get("overall_verdict"),
                "created_at": a.get("created_at"),
                "completed_at": a.get("completed_at"),
                "error_message": a.get("error_message"),
            }
        except Exception as e:
            logger.error(f"[AnalysisService] Failed to get status for {analysis_id}: {e}")
            raise AnalysisError(message=f"Failed to get analysis status: {e}") from e

    async def list_analyses(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        module: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List analyses for user."""
        try:
            query = self._table("analysis_jobs").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).offset(offset)
            
            if module:
                query = query.eq("module_type", module)
            if status:
                query = query.eq("status", status)

            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[AnalysisService] Failed to list analyses: {e}")
            raise AnalysisError(message=f"Failed to list analyses: {e}") from e

    async def _save_evidence(self, analysis_id: str, evidence_list: List[Dict[str, Any]]) -> None:
        """Save evidence items to database."""
        if not evidence_list:
            return
        try:
            items = []
            for ev in evidence_list:
                items.append({
                    "analysis_id": analysis_id,
                    "agent_name": ev.get("agent_name", "unknown"),
                    "evidence_type": ev.get("type", "general"),
                    "key": ev.get("key", ""),
                    "value": ev.get("value", ""),
                    "reference_url": ev.get("reference_url"),
                    "confidence": ev.get("confidence", 0.0),
                })
            if items:
                self._table("evidence_items").insert(items).execute()
        except Exception as e:
            logger.error(f"[AnalysisService] Failed to save evidence: {e}")
            # Non-critical: continue even if evidence save fails

    async def delete_analysis(self, analysis_id: str, user_id: str) -> bool:
        """Delete analysis."""
        try:
            self._table("analysis_jobs").delete().eq("id", analysis_id).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.error(f"[AnalysisService] Failed to delete analysis {analysis_id}: {e}")
            raise AnalysisError(message=f"Failed to delete analysis: {e}") from e


# Global service instance
analysis_service = AnalysisService()
