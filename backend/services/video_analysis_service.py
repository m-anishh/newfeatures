"""
Video Analysis Service

Coordinates the video analysis pipeline and persists generated artifacts.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from backend.core.exceptions import AnalysisError
from backend.core.logging import get_logger
from backend.database.db_client import get_db_client
from backend.repositories.storage_repository import StorageRepository
from backend.video.pipeline import video_pipeline

logger = get_logger(__name__)


class VideoAnalysisService:
    """Run the video analysis pipeline and persist its output."""

    def __init__(self) -> None:
        self._client = None
        self._storage = StorageRepository()

    def _get_client(self):
        if self._client is None:
            self._client = get_db_client()
        return self._client

    def _table(self, name: str):
        return self._get_client().schema("public").table(name)

    def _json_safe(self, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return self._json_safe(value.model_dump())
        if isinstance(value, dict):
            return {key: self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        return value

    async def _persist_report_file(
        self,
        user_id: str,
        analysis_id: str,
        report_bytes: bytes,
    ) -> tuple[str, str]:
        report_path = f"{user_id}/{analysis_id}/report.json"
        try:
            report_url = await self._storage.upload(
                file=report_bytes,
                bucket="visionx-video-reports",
                path=report_path,
                content_type="application/json",
            )
            return report_path, report_url
        except Exception as exc:
            logger.warning("[VideoAnalysis] Storage upload failed, saving report locally: %s", exc)
            local_dir = Path("uploads") / "video" / analysis_id
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / "report.json"
            local_path.write_bytes(report_bytes)
            return str(local_path), str(local_path)

    async def analyze_video(
        self,
        user_id: str,
        video_path: str,
        title: Optional[str] = None,
        analysis_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run video analysis and save the resulting report/artifacts."""
        if not analysis_id:
            analysis_id = str(uuid.uuid4())

        now = datetime.now(timezone.utc).isoformat()
        video_name = title or Path(video_path).name

        try:
            existing = self._table("analysis_jobs").select("id").eq("id", analysis_id).execute()
            job_data = {
                "user_id": user_id,
                "module_type": "video",
                "input_type": "file:video",
                "input_content": video_path,
                "title": video_name,
                "status": "processing",
                "progress": 10,
                "updated_at": now,
            }
            if existing.data:
                self._table("analysis_jobs").update(job_data).eq("id", analysis_id).execute()
            else:
                self._table("analysis_jobs").insert({
                    "id": analysis_id,
                    **job_data,
                    "created_at": now,
                }).execute()

            logger.info("[VideoAnalysis] Starting analysis %s for %s", analysis_id, video_name)
            pipeline_result = await video_pipeline.analyze(video_path=video_path, analysis_id=analysis_id)

            pipeline_result = self._json_safe(pipeline_result)
            score = pipeline_result.get("score")
            report = pipeline_result.get("report", {})
            report_payload = {
                "analysis_id": analysis_id,
                "title": video_name,
                "generated_at": now,
                "report": report,
                "score": score or {},
                "metadata": pipeline_result.get("metadata", {}),
                "faces": pipeline_result.get("faces", {}),
                "deepfake": pipeline_result.get("deepfake", {}),
                "ocr": pipeline_result.get("ocr", {}),
                "whisper": pipeline_result.get("whisper", {}),
            }

            report_bytes = json.dumps(report_payload, indent=2, default=str).encode("utf-8")
            report_path, report_url = await self._persist_report_file(user_id, analysis_id, report_bytes)

            transcript_path = f"{user_id}/{analysis_id}/transcript.txt"
            transcript_text = pipeline_result.get("whisper", {}).get("whisper_result", {}).get("transcript", "")
            transcript_bytes = transcript_text.encode("utf-8")
            try:
                await self._storage.upload(
                    file=transcript_bytes,
                    bucket="visionx-video-reports",
                    path=transcript_path,
                    content_type="text/plain",
                )
            except Exception as exc:
                logger.warning("[VideoAnalysis] Transcript upload skipped: %s", exc)

            risk_level = report.get("risk_level", "medium") if isinstance(report, dict) else "medium"
            overall_score = float(score.get("overall_score", 0) if isinstance(score, dict) else 0)
            verdict = "real" if overall_score >= 70 else "unknown"
            confidence = float(score.get("confidence", 0.0) if isinstance(score, dict) else 0.0)

            self._table("analysis_jobs").update({
                "status": "completed",
                "overall_confidence": confidence,
                "overall_verdict": verdict,
                "risk_level": risk_level,
                "completed_at": now,
                "updated_at": now,
            }).eq("id", analysis_id).execute()

            self._table("reports").insert({
                "user_id": user_id,
                "analysis_id": analysis_id,
                "title": video_name,
                "trust_score": int(overall_score),
                "authenticity_status": verdict,
                "risk_level": risk_level,
                "verdict": verdict,
                "report_data": report_payload,
                "pdf_path": report_path,
                "pdf_url": report_url,
                "created_at": now,
                "updated_at": now,
            }).execute()

            return {
                "success": True,
                "analysis_id": analysis_id,
                "status": "completed",
                "trust_score": int(overall_score),
                "confidence": confidence,
                "risk_level": risk_level,
                "verdict": verdict,
                "report_data": report_payload,
                "pdf_path": report_path,
                "pdf_url": report_url,
            }

        except Exception as exc:
            logger.exception("[VideoAnalysis] Video analysis failed for %s", analysis_id)
            self._table("analysis_jobs").update({
                "status": "failed",
                "error_message": str(exc),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", analysis_id).execute()
            raise AnalysisError(message=f"Video analysis failed: {exc}") from exc


video_analysis_service = VideoAnalysisService()
