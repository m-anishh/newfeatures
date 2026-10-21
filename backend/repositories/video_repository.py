"""
Video Analysis Repository
Data access layer for video analysis module.
"""
from __future__ import annotations

import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import UUID

from backend.database.db_client import get_db_client
from backend.core.logging import get_logger

logger = get_logger(__name__)


class VideoRepository:
    """Repository for video analysis data access."""

    def __init__(self):
        self.client = get_db_client()

    async def create_analysis(self, user_id: UUID, input_type: str, input_content: str,
                             title: Optional[str] = None, source_url: Optional[str] = None,
                             metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a new video analysis record."""
        try:
            record = {
                "user_id": str(user_id),
                "input_type": input_type,
                "input_content": input_content,
                "title": title or "",
                "source_url": source_url or "",
                "status": "queued",
                "progress": 0,
                "metadata": json.dumps(metadata) if metadata else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            result = self.client.schema("public").table("video_analyses").insert(record).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to create analysis: {e}")
            raise

    async def get_analysis(self, analysis_id: UUID, user_id: UUID) -> Optional[Dict[str, Any]]:
        """Get a video analysis by ID."""
        try:
            result = self.client.schema("public").table("video_analyses").select("*").eq("id", str(analysis_id)).eq("user_id", str(user_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to get analysis {analysis_id}: {e}")
            return None

    async def list_analyses(self, user_id: UUID, limit: int = 20, offset: int = 0,
                           status: Optional[str] = None) -> Dict[str, Any]:
        """List video analyses for a user."""
        try:
            query = self.client.schema("public").table("video_analyses").select("*", count="exact").eq("user_id", str(user_id)).order("created_at", desc=True).limit(limit).offset(offset)
            if status:
                query = query.eq("status", status)
            result = query.execute()
            return {
                "analyses": result.data or [],
                "count": result.count if hasattr(result, 'count') else len(result.data or []),
            }
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to list analyses: {e}")
            return {"analyses": [], "count": 0}

    async def update_analysis(self, analysis_id: UUID, **updates) -> bool:
        """Update a video analysis."""
        try:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            result = self.client.schema("public").table("video_analyses").update(updates).eq("id", str(analysis_id)).execute()
            return True
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to update analysis {analysis_id}: {e}")
            return False

    async def update_status(self, analysis_id: UUID, status: str, progress: int = 0) -> bool:
        """Update analysis status and progress."""
        return await self.update_analysis(analysis_id, status=status, progress=progress)

    async def save_frame(self, analysis_id: UUID, frame_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a video frame."""
        try:
            record = {
                "analysis_id": str(analysis_id),
                "frame_number": frame_data.get("frame_number", 0),
                "timestamp_seconds": frame_data.get("timestamp_seconds", 0),
                "frame_path": frame_data.get("frame_path", ""),
                "thumbnail_path": frame_data.get("thumbnail_path", ""),
                "scene_change": frame_data.get("scene_change", False),
                "motion_score": frame_data.get("motion_score"),
                "ocr_text": frame_data.get("ocr_text", ""),
                "objects_detected": json.dumps(frame_data.get("objects_detected", [])),
                "faces_detected": json.dumps(frame_data.get("faces_detected", [])),
                "deepfake_score": frame_data.get("deepfake_score"),
                "manipulation_indicators": json.dumps(frame_data.get("manipulation_indicators", [])),
                "metadata": json.dumps(frame_data.get("metadata", {})),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            result = self.client.schema("public").table("video_frames").insert(record).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to save frame: {e}")
            return {}

    async def get_frames(self, analysis_id: UUID) -> List[Dict[str, Any]]:
        """Get all frames for an analysis."""
        try:
            result = self.client.schema("public").table("video_frames").select("*").eq("analysis_id", str(analysis_id)).order("frame_number").execute()
            return result.data or []
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to get frames: {e}")
            return []

    async def save_evidence(self, analysis_id: UUID, evidence_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a video evidence item."""
        try:
            record = {
                "analysis_id": str(analysis_id),
                "agent_name": evidence_data.get("agent_name", "unknown"),
                "evidence_type": evidence_data.get("evidence_type", "general"),
                "key": evidence_data.get("key", "general"),
                "value": evidence_data.get("value", ""),
                "reference_url": evidence_data.get("reference_url", ""),
                "confidence": evidence_data.get("confidence"),
                "claim": evidence_data.get("claim", ""),
                "source": evidence_data.get("source", ""),
                "url": evidence_data.get("url", ""),
                "excerpt": evidence_data.get("excerpt", ""),
                "credibility": evidence_data.get("credibility"),
                "supports_claim": evidence_data.get("supports_claim", True),
                "metadata": json.dumps(evidence_data.get("metadata", {})),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            result = self.client.schema("public").table("video_evidence").insert(record).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to save evidence: {e}")
            return {}

    async def get_evidence(self, analysis_id: UUID) -> List[Dict[str, Any]]:
        """Get all evidence for an analysis."""
        try:
            result = self.client.schema("public").table("video_evidence").select("*").eq("analysis_id", str(analysis_id)).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to get evidence: {e}")
            return []

    async def save_audio(self, analysis_id: UUID, audio_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save audio analysis results."""
        try:
            record = {
                "analysis_id": str(analysis_id),
                "audio_path": audio_data.get("audio_path", ""),
                "transcript": audio_data.get("transcript", ""),
                "language_detected": audio_data.get("language_detected"),
                "confidence": audio_data.get("confidence"),
                "speaker_segments": json.dumps(audio_data.get("speaker_segments", [])),
                "silence_periods": json.dumps(audio_data.get("silence_periods", [])),
                "audio_manipulation_indicators": json.dumps(audio_data.get("audio_manipulation_indicators", [])),
                "metadata": json.dumps(audio_data.get("metadata", {})),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            result = self.client.schema("public").table("video_audio").insert(record).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to save audio: {e}")
            return {}

    async def get_audio(self, analysis_id: UUID) -> Optional[Dict[str, Any]]:
        """Get audio analysis results."""
        try:
            result = self.client.schema("public").table("video_audio").select("*").eq("analysis_id", str(analysis_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to get audio: {e}")
            return None

    async def save_report(self, user_id: UUID, analysis_id: UUID, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save video analysis report."""
        try:
            record = {
                "analysis_id": str(analysis_id),
                "user_id": str(user_id),
                "report_data": report_data,
                "report_type": "json",
                "executive_summary": report_data.get("executive_summary", ""),
                "executive_summary_short": report_data.get("executive_summary_short", ""),
                "recommendations": json.dumps(report_data.get("recommendations", [])),
                "claims": json.dumps(report_data.get("claims", [])),
                "evidence": json.dumps(report_data.get("evidence", [])),
                "sources": json.dumps(report_data.get("sources", [])),
                "frame_analysis": json.dumps(report_data.get("frame_analysis", {})),
                "ocr_findings": json.dumps(report_data.get("ocr_findings", {})),
                "audio_findings": json.dumps(report_data.get("audio_findings", {})),
                "deepfake_findings": json.dumps(report_data.get("deepfake_findings", {})),
                "bias_analysis": json.dumps(report_data.get("bias_analysis", {})),
                "context_analysis": json.dumps(report_data.get("context_analysis", {})),
                "ai_explanation": report_data.get("ai_explanation", ""),
                "processing_time_ms": report_data.get("processing_time_ms", 0),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            result = self.client.schema("public").table("video_reports").insert(record).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to save report: {e}")
            return {}

    async def get_report(self, analysis_id: UUID, user_id: UUID) -> Optional[Dict[str, Any]]:
        """Get video analysis report."""
        try:
            result = self.client.schema("public").table("video_reports").select("*").eq("analysis_id", str(analysis_id)).eq("user_id", str(user_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to get report: {e}")
            return None

    async def save_agent_result(self, analysis_id: UUID, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save agent execution result."""
        try:
            record = {
                "analysis_id": str(analysis_id),
                "agent_name": agent_data.get("agent_name", "unknown"),
                "agent_order": agent_data.get("agent_order", 0),
                "status": agent_data.get("status", "completed"),
                "started_at": agent_data.get("started_at", datetime.now(timezone.utc).isoformat()),
                "completed_at": agent_data.get("completed_at", datetime.now(timezone.utc).isoformat()),
                "duration_ms": agent_data.get("duration_ms"),
                "confidence": agent_data.get("confidence"),
                "reasoning": agent_data.get("reasoning", ""),
                "summary": agent_data.get("summary", ""),
                "raw_output": json.dumps(agent_data.get("raw_output", {})),
                "evidence": json.dumps(agent_data.get("evidence", [])),
                "error_message": agent_data.get("error_message"),
                "retry_count": agent_data.get("retry_count", 0),
                "findings": json.dumps(agent_data.get("findings", [])),
                "processing_time_ms": agent_data.get("processing_time_ms"),
                "processed_output": json.dumps(agent_data.get("processed_output", {})),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            result = self.client.schema("public").table("video_agent_results").insert(record).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to save agent result: {e}")
            return {}

    async def get_agent_results(self, analysis_id: UUID) -> List[Dict[str, Any]]:
        """Get all agent results for an analysis."""
        try:
            result = self.client.schema("public").table("video_agent_results").select("*").eq("analysis_id", str(analysis_id)).order("agent_order").execute()
            return result.data or []
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to get agent results: {e}")
            return []

    async def delete_analysis(self, analysis_id: UUID, user_id: UUID) -> bool:
        """Delete a video analysis and all related data."""
        try:
            # Delete related data first
            self.client.schema("public").table("video_agent_results").delete().eq("analysis_id", str(analysis_id)).execute()
            self.client.schema("public").table("video_frames").delete().eq("analysis_id", str(analysis_id)).execute()
            self.client.schema("public").table("video_evidence").delete().eq("analysis_id", str(analysis_id)).execute()
            self.client.schema("public").table("video_audio").delete().eq("analysis_id", str(analysis_id)).execute()
            self.client.schema("public").table("video_reports").delete().eq("analysis_id", str(analysis_id)).execute()
            self.client.schema("public").table("video_analyses").delete().eq("id", str(analysis_id)).eq("user_id", str(user_id)).execute()
            return True
        except Exception as e:
            logger.error(f"[VideoRepository] Failed to delete analysis {analysis_id}: {e}")
            return False


# Global instance
video_repository = VideoRepository()