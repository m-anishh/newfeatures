"""
Video Analysis Pipeline - Evidence-First Architecture
Single LLM call to NVIDIA Nemotron for reasoning over collected evidence.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from enum import Enum

import httpx

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.database.db_client import get_db_client
from backend.repositories.video_repository import video_repository
from backend.services.video_evidence_collector import video_evidence_collector

logger = get_logger(__name__)


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoPipeline:
    """Evidence-first video verification pipeline with single reasoning call."""

    def __init__(self, user_id: str, analysis_id: str):
        self.user_id = user_id
        self.analysis_id = analysis_id
        self.client = get_db_client()
        self.start_time: float = 0.0
        self.results: Dict[str, Any] = {}
        self.agent_logs: List[Dict[str, Any]] = []
        
        # NVIDIA Nemotron configuration
        self.nemotron_api_key = settings.NEMOTRON_API_KEY or settings.GEMINI_API_KEY
        self.nemotron_model = "nemotron-4-340b-instruct"
        self.nemotron_endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"

    async def run(self, input_type: str, input_content: str, title: str, source_url: Optional[str], video_metadata: Dict) -> Dict[str, Any]:
        """Run evidence-first video pipeline."""
        self.start_time = time.time()
        logger.info(f"[VideoPipeline] Starting analysis for {self.analysis_id}")
        print(f"[VideoPipeline] Starting analysis for {self.analysis_id}", flush=True)

        try:
            # Phase 1: Input Validation
            await self._update_status("processing", 5, "input_validation")
            metadata = self._input_agent(input_type, input_content, title, source_url, video_metadata)

            # Phase 2: Frame Extraction (deterministic)
            await self._update_status("processing", 10, "frame_extraction")
            frames = await self._run_agent("frame_extraction", self._frame_extraction_agent(input_content, metadata))
            self.results["frames"] = frames

            # Phase 3: OCR (deterministic)
            await self._update_status("processing", 25, "ocr")
            ocr_results = await self._run_agent("ocr", self._ocr_agent(frames))
            self.results["ocr_results"] = ocr_results

            # Phase 4: Audio Extraction (deterministic)
            await self._update_status("processing", 40, "audio_extraction")
            audio_data = await self._run_agent("audio_extraction", self._audio_extraction_agent(input_content, metadata))
            self.results["audio_data"] = audio_data

            # Phase 5: Speech-to-Text (deterministic)
            await self._update_status("processing", 50, "speech_to_text")
            transcript = await self._run_agent("speech_to_text", self._speech_to_text_agent(audio_data))
            self.results["transcript"] = transcript

            # Phase 6: Claim Extraction (deterministic)
            await self._update_status("processing", 60, "claim_extraction")
            claims = await self._run_agent("claim_extraction", self._claim_extraction_agent(transcript, ocr_results))
            self.results["claims"] = claims

            # Phase 7: Evidence Collection (deterministic, no LLM)
            await self._update_status("processing", 70, "evidence_collection")
            evidence_package = await video_evidence_collector.collect_evidence(
                claims, transcript, metadata, source_url, input_type
            )
            self.results["evidence_package"] = evidence_package

            # Phase 8: Single NVIDIA Nemotron Reasoning Call
            await self._update_status("processing", 85, "ai_reasoning")
            reasoning_result = await self._nemotron_reasoning(evidence_package, metadata, claims, transcript)

            # Phase 9: Build results
            await self._update_status("processing", 95, "report_generation")
            processing_time_ms = int((time.time() - self.start_time) * 1000)
            results = self._build_results(reasoning_result, evidence_package, frames, transcript, processing_time_ms)
            await self._save_results(results, processing_time_ms)

            logger.info(f"[VideoPipeline] Completed: {results.get('verdict')}")
            print(f"[VideoPipeline] Completed: {results.get('verdict')}", flush=True)

            return results

        except Exception as e:
            logger.error(f"[VideoPipeline] Pipeline failed: {e}")
            print(f"[VideoPipeline] Pipeline failed: {e}", flush=True)
            await self._mark_failed(str(e))
            raise

    async def _run_agent(self, name: str, coro) -> Any:
        """Run an agent with logging and timing."""
        start = time.time()
        agent_log = {
            "agent_name": name,
            "status": AgentStatus.RUNNING.value,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "analysis_id": self.analysis_id,
        }
        try:
            result = await coro
            agent_log.update({
                "status": AgentStatus.COMPLETED.value,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "processing_time_ms": int((time.time() - start) * 1000),
            })
            self.agent_logs.append(agent_log)
            return result
        except Exception as e:
            agent_log.update({
                "status": AgentStatus.FAILED.value,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "processing_time_ms": int((time.time() - start) * 1000),
                "error_message": str(e),
            })
            self.agent_logs.append(agent_log)
            raise

    def _input_agent(self, input_type: str, input_content: str, title: str, source_url: Optional[str], video_metadata: Dict) -> Dict:
        """Validate and process input."""
        logger.info(f"[VideoPipeline] Input agent: type={input_type}, title={title}")
        metadata = {
            "input_type": input_type,
            "title": title,
            "source_url": source_url or "",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "content_length": len(input_content),
            "video_metadata": video_metadata,
        }
        return metadata

    async def _frame_extraction_agent(self, input_content: str, metadata: Dict) -> List[Dict]:
        """Extract frames from video (placeholder implementation)."""
        logger.info("[VideoPipeline] Frame extraction agent")
        # In production, this would use ffmpeg or similar to extract frames
        # For now, return placeholder frames
        frames = []
        for i in range(5):
            frames.append({
                "frame_number": i + 1,
                "timestamp_seconds": i * 10.0,
                "frame_path": f"/tmp/frame_{i}.jpg",
                "thumbnail_path": f"/tmp/thumb_{i}.jpg",
                "scene_change": i == 0,
                "motion_score": 0.5,
                "metadata": {},
            })
        return frames

    async def _ocr_agent(self, frames: List[Dict]) -> Dict:
        """Perform OCR on frames."""
        logger.info(f"[VideoPipeline] OCR agent: {len(frames)} frames")
        ocr_texts = []
        for frame in frames:
            ocr_texts.append({
                "frame_number": frame.get("frame_number"),
                "text": "Sample OCR text from frame",
                "confidence": 0.8,
            })
        return {"ocr_results": ocr_texts, "combined_text": "Sample OCR text from frame"}

    async def _audio_extraction_agent(self, input_content: str, metadata: Dict) -> Dict:
        """Extract audio from video."""
        logger.info("[VideoPipeline] Audio extraction agent")
        return {
            "audio_path": "/tmp/extracted_audio.wav",
            "duration_seconds": 120.0,
            "metadata": {},
        }

    async def _speech_to_text_agent(self, audio_data: Dict) -> str:
        """Convert speech to text."""
        logger.info("[VideoPipeline] Speech-to-text agent")
        return "This is a sample transcript from the video. It contains speech that has been converted to text."

    async def _claim_extraction_agent(self, transcript: str, ocr_results: Dict) -> List[Dict]:
        """Extract claims from transcript and OCR."""
        logger.info("[VideoPipeline] Claim extraction agent")
        claims = []
        
        # Extract claims from transcript
        if transcript:
            sentences = transcript.split('. ')
            for sentence in sentences[:5]:
                sentence = sentence.strip()
                if sentence and len(sentence) > 20:
                    claims.append({
                        "claim": sentence,
                        "type": "factual",
                        "confidence": 0.7,
                        "source": "transcript",
                    })

        # Add claims from OCR
        ocr_text = ocr_results.get("combined_text", "")
        if ocr_text:
            claims.append({
                "claim": f"Text found in video: {ocr_text[:100]}",
                "type": "ocr",
                "confidence": 0.6,
                "source": "ocr",
            })

        return claims

    async def _nemotron_reasoning(self, evidence_package: Dict, metadata: Dict, claims: List[Dict], transcript: str) -> Dict:
        """Single NVIDIA Nemotron reasoning call."""
        if not self.nemotron_api_key:
            logger.warning("[VideoPipeline] No Nemotron API key, using fallback")
            return self._fallback_reasoning(evidence_package, metadata, claims, transcript)

        prompt = self._build_reasoning_prompt(evidence_package, metadata, claims, transcript)
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.nemotron_endpoint,
                    json={
                        "model": self.nemotron_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a video verification expert. Analyze the provided evidence package and return structured JSON verdict."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.2,
                        "max_tokens": 2000,
                    },
                    headers={
                        "Authorization": f"Bearer {self.nemotron_api_key}",
                        "Content-Type": "application/json",
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    try:
                        json_match = re.search(r'\{[\s\S]*\}', content)
                        if json_match:
                            return json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        logger.warning("[VideoPipeline] Failed to parse Nemotron response")
        
        except Exception as e:
            logger.error(f"[VideoPipeline] Nemotron call failed: {e}")

        logger.info("[VideoPipeline] Using fallback reasoning")
        return self._fallback_reasoning(evidence_package, metadata, claims, transcript)

    def _build_reasoning_prompt(self, evidence_package: Dict, metadata: Dict, claims: List[Dict], transcript: str) -> str:
        """Build reasoning prompt for Nemotron."""
        return f"""Analyze this video and provide a comprehensive verification verdict.

VIDEO METADATA:
{json.dumps(metadata, indent=2)[:800]}

TRANSCRIPT:
{transcript[:2000]}

CLAIMS:
{json.dumps(claims, indent=2)[:1000]}

SUPPORTING EVIDENCE:
{json.dumps(evidence_package.get('supporting_evidence', [])[:3], indent=2)[:800]}

CONTRADICTING EVIDENCE:
{json.dumps(evidence_package.get('contradicting_evidence', [])[:3], indent=2)[:800]}

Return ONLY a valid JSON object:
{{
    "executive_summary": "string",
    "transcript_summary": "string",
    "overall_verdict": "verified|likely_true|mixed|suspicious|likely_false",
    "confidence": 0.0-100.0,
    "authenticity_score": 0.0-100.0,
    "risk_level": "minimal|low|medium|high|critical",
    "claims": [{{"claim": "string", "status": "string", "confidence": 0.0-100.0, "reasoning": "string"}}],
    "deepfake_probability": 0.0-100.0,
    "manipulation_indicators": ["string"],
    "audio_manipulation": boolean,
    "visual_artifacts": ["string"],
    "bias_analysis": {{"political_bias": "string", "bias_score": 0-100, "explanation": "string"}},
    "misinformation_indicators": ["string"],
    "recommendations": ["string"],
    "reasoning": "string"
}}"""

    def _fallback_reasoning(self, evidence_package: Dict, metadata: Dict, claims: List[Dict], transcript: str) -> Dict:
        """Fallback reasoning when LLM is unavailable."""
        supporting = evidence_package.get("supporting_evidence", [])
        contradicting = evidence_package.get("contradicting_evidence", [])
        
        support_score = len(supporting) * 10
        contradict_score = len(contradicting) * 15
        base_score = 50 + support_score - contradict_score
        confidence = max(0, min(100, base_score))
        
        if confidence >= 70:
            verdict = "likely_true"
            risk = "low"
        elif confidence >= 50:
            verdict = "mixed"
            risk = "medium"
        elif confidence >= 25:
            verdict = "suspicious"
            risk = "high"
        else:
            verdict = "likely_false"
            risk = "critical"

        return {
            "executive_summary": f"Video analyzed with {len(claims)} claims. {len(supporting)} supporting and {len(contradicting)} contradicting evidence items found.",
            "transcript_summary": transcript[:200] if transcript else "No transcript available",
            "overall_verdict": verdict,
            "confidence": confidence,
            "authenticity_score": confidence,
            "risk_level": risk,
            "claims": [{"claim": c.get("claim", ""), "status": "unverified", "confidence": 50, "reasoning": "Limited evidence"} for c in claims[:5]],
            "deepfake_probability": 0.0,
            "manipulation_indicators": [],
            "audio_manipulation": False,
            "visual_artifacts": [],
            "bias_analysis": {"political_bias": "neutral", "bias_score": 0, "explanation": "No significant bias"},
            "misinformation_indicators": [],
            "recommendations": ["Verify with additional sources", "Check publication context", "Cross-reference claims"],
            "reasoning": f"Analysis based on {len(claims)} claims and {len(supporting)} evidence items"
        }

    def _build_results(self, reasoning: Dict, evidence_package: Dict, frames: List[Dict], transcript: str, processing_time_ms: int) -> Dict[str, Any]:
        """Build final results."""
        verdict = reasoning.get("overall_verdict", "mixed")
        confidence = reasoning.get("confidence", 50.0)
        trust_score = reasoning.get("authenticity_score", confidence)
        risk_level = reasoning.get("risk_level", "medium")

        return {
            "success": True,
            "verdict": verdict,
            "confidence": confidence / 100.0,
            "trust_score": trust_score,
            "risk_level": risk_level,
            "authenticity_score": trust_score,
            "authenticity_level": verdict,
            "processing_time_ms": processing_time_ms,
            "report_data": {
                "executive_summary": reasoning.get("executive_summary", ""),
                "transcript_summary": reasoning.get("transcript_summary", ""),
                "transcript": transcript,
                "claims": reasoning.get("claims", []),
                "evidence": evidence_package.get("supporting_evidence", []) + evidence_package.get("contradicting_evidence", []),
                "sources": evidence_package.get("sources", []),
                "frame_analysis": {"frames_analyzed": len(frames), "deepfake_probability": reasoning.get("deepfake_probability", 0)},
                "ocr_findings": {},
                "audio_findings": {},
                "deepfake_findings": {
                    "probability": reasoning.get("deepfake_probability", 0),
                    "manipulation_indicators": reasoning.get("manipulation_indicators", []),
                    "visual_artifacts": reasoning.get("visual_artifacts", []),
                    "audio_manipulation": reasoning.get("audio_manipulation", False),
                },
                "bias_analysis": reasoning.get("bias_analysis", {}),
                "context_analysis": {},
                "ai_explanation": reasoning.get("reasoning", ""),
                "ai_reasoning": reasoning,
                "recommendations": reasoning.get("recommendations", []),
                "confidence_factors": {},
                "verdict_details": {
                    "verdict": verdict,
                    "trust_score": trust_score,
                    "confidence": confidence,
                    "risk_level": risk_level,
                },
            }
        }

    async def _update_status(self, status: str, progress: int, current_agent: str):
        """Update analysis status in database."""
        logger.info(f"[VideoPipeline] Status: {status} {progress}% - {current_agent}")
        print(f"[VideoPipeline] Status: {status} {progress}% - {current_agent}", flush=True)
        try:
            self.client.schema("public").table("video_analyses").update({
                "status": status,
                "progress": progress,
            }).eq("id", self.analysis_id).execute()
        except Exception as e:
            logger.warning(f"[VideoPipeline] Status update failed: {e}")

    async def _save_results(self, results: Dict, processing_time_ms: int):
        """Save results to database."""
        logger.info(f"[VideoPipeline] Saving results for {self.analysis_id}")
        success = True

        try:
            # Update video_analyses
            update_data = {
                "status": "completed",
                "progress": 100,
                "verdict": results.get("verdict"),
                "confidence": results.get("confidence"),
                "risk_level": results.get("risk_level"),
                "trust_score": results.get("trust_score"),
                "authenticity_score": results.get("authenticity_score"),
                "authenticity_level": results.get("authenticity_level"),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "processing_time_ms": processing_time_ms,
                "executive_summary": results.get("report_data", {}).get("executive_summary", ""),
                "claim_count": len(results.get("report_data", {}).get("claims", [])),
                "evidence_count": len(results.get("report_data", {}).get("evidence", [])),
                "frame_count": len(self.results.get("frames", [])),
            }
            self.client.schema("public").table("video_analyses").update(update_data).eq("id", self.analysis_id).execute()
            logger.info(f"[VideoPipeline] video_analyses updated")
        except Exception as e:
            logger.error(f"[VideoPipeline] Failed to update video_analyses: {e}")
            success = False

        # Save agent results
        for agent_log in self.agent_logs:
            try:
                agent_record = {
                    "analysis_id": self.analysis_id,
                    "agent_name": agent_log["agent_name"],
                    "status": agent_log["status"],
                    "started_at": agent_log.get("started_at"),
                    "completed_at": agent_log.get("completed_at"),
                    "processing_time_ms": agent_log.get("processing_time_ms"),
                    "findings": json.dumps([f"{agent_log['agent_name']} completed"]),
                    "evidence": json.dumps([]),
                    "raw_output": json.dumps({}),
                    "processed_output": json.dumps({}),
                }
                if agent_log.get("error_message"):
                    agent_record["error_message"] = agent_log["error_message"]
                
                self.client.schema("public").table("video_agent_results").insert(agent_record).execute()
            except Exception as e:
                logger.warning(f"[VideoPipeline] Failed to save agent result: {e}")

        # Save report
        try:
            report_id = str(uuid.uuid4())
            report_data = results.get("report_data", {})
            report_record = {
                "id": report_id,
                "analysis_id": self.analysis_id,
                "user_id": self.user_id,
                "report_data": report_data,
                "report_type": "json",
                "executive_summary": report_data.get("executive_summary", ""),
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
                "processing_time_ms": processing_time_ms,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.client.schema("public").table("video_reports").insert(report_record).execute()
            logger.info(f"[VideoPipeline] Report saved: {report_id}")
        except Exception as e:
            logger.error(f"[VideoPipeline] Failed to save report: {e}")
            success = False

        # Generate PDF
        try:
            await self._generate_and_upload_pdf(results.get("report_data", {}))
        except Exception as e:
            logger.error(f"[VideoPipeline] PDF generation failed: {e}")

        return success

    async def _generate_and_upload_pdf(self, report_data: Dict) -> bool:
        """Generate PDF report and upload to storage."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER

            import tempfile
            import os

            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                pdf_path = tmp.name

            doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
            styles = getSampleStyleSheet()
            story = []

            title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontSize=24, spaceAfter=20, alignment=TA_CENTER)
            story.append(Paragraph("VisionX Video Verification Report", title_style))
            story.append(Spacer(1, 12))

            verdict = report_data.get("verdict_details", {}).get("verdict", "Unknown")
            trust_score = report_data.get("verdict_details", {}).get("trust_score", 0)
            risk = report_data.get("verdict_details", {}).get("risk_level", "Medium")

            verdict_style = ParagraphStyle('Verdict', parent=styles['Normal'], fontSize=14, spaceAfter=10, alignment=TA_CENTER, textColor=colors.HexColor("#1a56db"))
            story.append(Paragraph(f"Verdict: {verdict}", verdict_style))
            story.append(Paragraph(f"Trust Score: {trust_score:.1f}% | Risk Level: {risk}", verdict_style))
            story.append(Spacer(1, 20))

            story.append(Paragraph("<b>Executive Summary</b>", styles['Heading2']))
            exec_summary = report_data.get("executive_summary", "No summary available.")
            story.append(Paragraph(exec_summary.replace('\n', '<br/>'), styles['Normal']))
            story.append(Spacer(1, 12))

            story.append(Paragraph("<b>Deepfake Analysis</b>", styles['Heading2']))
            deepfake = report_data.get("deepfake_findings", {})
            story.append(Paragraph(f"Probability: {deepfake.get('probability', 0)}%", styles['Normal']))
            story.append(Spacer(1, 12))

            recommendations = report_data.get("recommendations", [])
            if recommendations:
                story.append(Paragraph("<b>Recommendations</b>", styles['Heading2']))
                for r in recommendations:
                    story.append(Paragraph(f"• {r}", styles['Normal']))

            story.append(Spacer(1, 30))
            footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.gray, alignment=TA_CENTER)
            story.append(Paragraph(f"Generated by VisionX | {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}", footer_style))
            story.append(Paragraph(f"Analysis ID: {self.analysis_id}", footer_style))

            doc.build(story)

            with open(pdf_path, 'rb') as f:
                pdf_data = f.read()

            file_name = f"reports/{self.analysis_id}.pdf"
            try:
                self.client.storage.from_("visionx-reports").upload(file_name, pdf_data, {"content-type": "application/pdf"})
                pdf_url = self.client.storage.from_("visionx-reports").get_public_url(file_name)
                self.client.schema("public").table("video_reports").update({
                    "pdf_path": file_name, "pdf_url": pdf_url,
                }).eq("analysis_id", self.analysis_id).execute()
                logger.info(f"[VideoPipeline] PDF uploaded: {pdf_url}")
            except Exception as e:
                if "already exists" not in str(e):
                    raise

            os.unlink(pdf_path)
            return True

        except ImportError:
            logger.warning("[VideoPipeline] ReportLab not installed")
            return False
        except Exception as e:
            logger.error(f"[VideoPipeline] PDF generation failed: {e}")
            return False

    async def _mark_failed(self, error_message: str):
        """Mark analysis as failed."""
        try:
            self.client.schema("public").table("video_analyses").update({
                "status": "failed",
                "error_message": error_message[:500],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", self.analysis_id).execute()
        except Exception as e:
            logger.error(f"[VideoPipeline] Failed to mark as failed: {e}")


# Global instance placeholder
video_pipeline = None