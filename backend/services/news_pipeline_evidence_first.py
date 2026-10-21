"""
News Verification Pipeline - Evidence-First Architecture
Single LLM call to NVIDIA Nemotron for reasoning over collected evidence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

import httpx

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.database.db_client import get_db_client
from backend.services.news_evidence_collector import news_evidence_collector

logger = get_logger(__name__)


class NewsPipelineEvidenceFirst:
    """Evidence-first news verification pipeline with single reasoning call."""

    def __init__(self, user_id: str, analysis_id: str):
        self.user_id = user_id
        self.analysis_id = analysis_id
        self.client = get_db_client()
        self.start_time: float = 0.0
        
        # NVIDIA Nemotron configuration
        self.nemotron_api_key = settings.NEMOTRON_API_KEY or settings.GEMINI_API_KEY
        self.nemotron_model = "nemotron-4-340b-instruct"  # or similar
        self.nemotron_endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"

    async def run(self, input_type: str, input_content: str, title: str, source_url: Optional[str]) -> Dict[str, Any]:
        """Run evidence-first pipeline."""
        self.start_time = time.time()
        logger.info(f"[NewsPipeline-EvidenceFirst] Starting for {self.analysis_id}")
        print(f"[NewsPipeline-EvidenceFirst] Starting for {self.analysis_id}", flush=True)

        try:
            # Phase 1: Input Validation
            await self._update_status("processing", 5, "input_validation")
            content, metadata = self._input_agent(input_type, input_content, title, source_url)

            # Phase 2: Content Extraction
            await self._update_status("processing", 10, "content_extraction")
            extracted = self._content_extraction_agent(content)

            # Phase 3: Claim Extraction (deterministic, no LLM)
            await self._update_status("processing", 20, "claim_extraction")
            claims = self._claim_extraction_agent(extracted.get("body", ""))

            # Phase 4: Entity Extraction (deterministic, no LLM)
            await self._update_status("processing", 30, "entity_extraction")
            entities = self._entity_recognition_agent(extracted.get("body", ""))

            # Phase 5-10: Evidence Collection (deterministic, no LLM)
            await self._update_status("processing", 40, "evidence_collection")
            evidence_package = await news_evidence_collector.collect_evidence(
                claims, entities, content, source_url, input_type
            )

            # Phase 11: Single NVIDIA Nemotron Reasoning Call
            await self._update_status("processing", 85, "ai_reasoning")
            reasoning_result = await self._nemotron_reasoning(evidence_package)

            # Phase 12: Build results
            await self._update_status("processing", 95, "report_generation")
            processing_time_ms = int((time.time() - self.start_time) * 1000)
            results = self._build_results(reasoning_result, evidence_package, processing_time_ms)
            await self._save_results(results, processing_time_ms)

            logger.info(f"[NewsPipeline-EvidenceFirst] Completed: {results.get('verdict')}")
            print(f"[NewsPipeline-EvidenceFirst] Completed: {results.get('verdict')}", flush=True)

            return results

        except Exception as e:
            logger.error(f"[NewsPipeline-EvidenceFirst] Failed: {e}")
            print(f"[NewsPipeline-EvidenceFirst] Failed: {e}", flush=True)
            await self._mark_failed(str(e))
            raise

    def _input_agent(self, input_type: str, input_content: str, title: str, source_url: Optional[str]) -> Tuple[str, Dict]:
        """Validate and process input."""
        metadata = {
            "input_type": input_type,
            "title": title,
            "source_url": source_url or "",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "content_length": len(input_content),
            "word_count": len(input_content.split()) if input_content else 0,
        }
        return input_content, metadata

    def _content_extraction_agent(self, content: str) -> Dict:
        """Extract and structure content."""
        return {
            "headline": content[:200] if content else "",
            "body": content,
            "word_count": len(content.split()) if content else 0,
            "char_count": len(content) if content else 0,
        }

    def _claim_extraction_agent(self, text: str) -> List[Dict]:
        """Extract claims using deterministic rules."""
        if not text or len(text) < 20:
            return []

        claims = []
        sentences = re.split(r'[.!?]+', text)
        for sentence in sentences[:10]:
            sentence = sentence.strip()
            if sentence and len(sentence) > 20:
                claims.append({
                    "claim": sentence,
                    "type": "factual",
                    "confidence": 0.7,
                })
        return claims[:5]  # Limit to top 5

    def _entity_recognition_agent(self, text: str) -> Dict:
        """Extract entities using deterministic methods."""
        if not text:
            return {"people": [], "organizations": [], "locations": [], "dates": [], "events": []}

        # Extract proper nouns (simplified)
        people = re.findall(r'\b(?:Dr|Mr|Mrs|Ms)\.\s+[A-Z][a-z]+\b', text)
        orgs = re.findall(r'\b[A-Z]{2,}(?:\s+[A-Z][a-z]+)*\s+(?:Inc|Corp|LLC|Foundation|Institute|University|Organization)\b', text)
        locations = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:City|County|State|Country|Province)\b', text)
        dates = re.findall(r'\b(?:\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2})\s+\d{4}\b', text)

        return {
            "people": people[:5],
            "organizations": orgs[:5],
            "locations": locations[:5],
            "dates": dates[:5],
            "events": [],
        }

    async def _nemotron_reasoning(self, evidence_package: Dict) -> Dict:
        """Single NVIDIA Nemotron reasoning call."""
        if not self.nemotron_api_key:
            logger.warning("[NewsPipeline] No Nemotron API key, using fallback")
            return self._fallback_reasoning(evidence_package)

        # Build reasoning prompt
        prompt = self._build_reasoning_prompt(evidence_package)
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.nemotron_endpoint,
                    json={
                        "model": self.nemotron_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a news verification expert. Analyze the provided evidence package and return structured JSON verdict."
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
                        # Extract JSON from response
                        json_match = re.search(r'\{[\s\S]*\}', content)
                        if json_match:
                            return json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        logger.warning("[NewsPipeline] Failed to parse Nemotron response")
        
        except Exception as e:
            logger.error(f"[NewsPipeline] Nemotron call failed: {e}")

        logger.info("[NewsPipeline] Using fallback reasoning")
        return self._fallback_reasoning(evidence_package)

    def _build_reasoning_prompt(self, evidence_package: Dict) -> str:
        """Build structured reasoning prompt for Nemotron."""
        return f"""Analyze this news article and provide a comprehensive verification verdict.

ARTICLE:
{evidence_package.get('article', '')[:2000]}

CLAIMS:
{json.dumps(evidence_package.get('claims', []), indent=2)[:1000]}

SUPPORTING EVIDENCE:
{json.dumps(evidence_package.get('supporting_evidence', [])[:3], indent=2)[:800]}

CONTRADICTING EVIDENCE:
{json.dumps(evidence_package.get('contradicting_evidence', [])[:3], indent=2)[:800]}

TRUSTED SOURCE COVERAGE (20 sources searched; a match means the source covered the same topic):
{json.dumps({k: v for k, v in evidence_package.get('source_coverage', {}).items() if k != 'per_source'}, indent=2)[:600]}

Return ONLY a valid JSON object with this exact structure:
{{
    "executive_summary": "string",
    "overall_verdict": "verified|likely_true|mixed|suspicious|likely_false",
    "confidence": 0.0-100.0,
    "authenticity_score": 0.0-100.0,
    "risk_level": "minimal|low|medium|high|critical",
    "claims": [{{"claim": "string", "status": "string", "confidence": 0.0-100.0, "reasoning": "string"}}],
    "bias_analysis": {{"political_bias": "string", "bias_score": 0-100, "explanation": "string"}},
    "misinformation_indicators": ["string"],
    "recommendations": ["string"],
    "reasoning": "string"
}}"""

    def _fallback_reasoning(self, evidence_package: Dict) -> Dict:
        """Rule-based verdict from trusted-source coverage when no LLM is available.

        - Fact-check debunks lower the score.
        - Each distinct trusted source reporting the same story raises it.
        - No coverage at all stays "mixed": absence of coverage is not proof either way.
        """
        claims = evidence_package.get("claims", [])
        supporting = evidence_package.get("supporting_evidence", [])
        contradicting = evidence_package.get("contradicting_evidence", [])
        coverage = evidence_package.get("source_coverage", {})
        total = coverage.get("sources_total", 20)
        reachable = coverage.get("sources_reachable", 0)
        support_sources = sorted({e.get("publisher", "") for e in supporting})
        debunk_sources = sorted({e.get("publisher", "") for e in contradicting})

        if debunk_sources:
            score = max(5, 35 - 12 * len(debunk_sources) + 4 * len(support_sources))
        elif support_sources:
            score = min(95, 55 + 10 * len(support_sources))
        else:
            score = 45

        if score >= 85:
            verdict, risk = "verified", "minimal"
        elif score >= 65:
            verdict, risk = "likely_true", "low"
        elif score >= 45:
            verdict, risk = "mixed", "medium"
        elif score >= 25:
            verdict, risk = "suspicious", "high"
        else:
            verdict, risk = "likely_false", "critical"

        if debunk_sources:
            summary = f"Fact-check coverage that questions this story was found from: {', '.join(debunk_sources)}."
        elif support_sources:
            summary = (f"{len(support_sources)} of {total} trusted sources reported the same story: "
                       f"{', '.join(support_sources)}.")
        else:
            summary = (f"No coverage found in {total} trusted sources ({reachable} reachable). "
                       "The claim could not be corroborated; this is not proof that it is false.")

        recommendations = []
        if not support_sources:
            recommendations.append("No trusted outlet reported this yet - wait for confirmation before sharing.")
        if debunk_sources:
            recommendations.append("Read the linked fact-check articles before sharing.")
        recommendations += ["Check the publication date and original context",
                            "Open the linked source articles to confirm the details match"]

        return {
            "executive_summary": summary,
            "overall_verdict": verdict,
            "confidence": score,
            "authenticity_score": score,
            "risk_level": risk,
            "claims": [{"claim": c.get("claim", ""),
                        "status": "corroborated" if support_sources else ("disputed" if debunk_sources else "unverified"),
                        "confidence": score,
                        "reasoning": summary} for c in claims[:5]],
            "bias_analysis": {"political_bias": "not assessed", "bias_score": 0,
                              "explanation": "Bias is not assessed without an AI model"},
            "misinformation_indicators": [f"Fact-check: {e.get('title', '')}" for e in contradicting[:3]],
            "recommendations": recommendations,
            "reasoning": (f"Searched {total} trusted sources for: {', '.join(coverage.get('search_terms', []))}. "
                          f"{len(supporting)} supporting article(s) from {len(support_sources)} source(s); "
                          f"{len(contradicting)} fact-check article(s)."),
        }

    def _build_results(self, reasoning: Dict, evidence_package: Dict, processing_time_ms: int) -> Dict[str, Any]:
        """Build final results from reasoning output."""
        verdict = reasoning.get("overall_verdict", "mixed")
        confidence = reasoning.get("confidence", 50.0)
        trust_score = reasoning.get("authenticity_score", confidence)
        risk_level = reasoning.get("risk_level", "medium")

        return {
            "success": True,
            "verdict": verdict,
            "confidence": confidence / 100.0,  # Normalize to 0-1
            "trust_score": trust_score,
            "risk_level": risk_level,
            "authenticity_score": trust_score,
            "authenticity_level": verdict,
            "processing_time_ms": processing_time_ms,
            "report_data": {
                "executive_summary": reasoning.get("executive_summary", ""),
                "claims": reasoning.get("claims", []),
                "evidence": evidence_package.get("supporting_evidence", []) + evidence_package.get("contradicting_evidence", []),
                "sources": evidence_package.get("sources", []),
                "bias_analysis": reasoning.get("bias_analysis", {}),
                "context_analysis": {},
                "ai_explanation": reasoning.get("reasoning", ""),
                "ai_reasoning": reasoning,
                "entities": evidence_package.get("entities", {}),
                "source_credibility": evidence_package.get("source_coverage", {}),
                "source_coverage": evidence_package.get("source_coverage", {}),
                "missing_information": evidence_package.get("missing_information", []),
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
        logger.info(f"[NewsPipeline-EvidenceFirst] Status: {status} {progress}% - {current_agent}")
        try:
            self.client.schema("public").table("news_analyses").update({
                "status": status,
                "progress": progress,
            }).eq("id", self.analysis_id).execute()
        except Exception as e:
            logger.warning(f"[NewsPipeline-EvidenceFirst] Status update failed: {e}")

    async def _save_results(self, results: Dict, processing_time_ms: int):
        """Save results to database."""
        logger.info(f"[NewsPipeline-EvidenceFirst] Saving results for {self.analysis_id}")
        success = True

        try:
            # Update news_analyses
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
            }
            self.client.schema("public").table("news_analyses").update(update_data).eq("id", self.analysis_id).execute()
            logger.info(f"[NewsPipeline-EvidenceFirst] news_analyses updated")
        except Exception as e:
            logger.error(f"[NewsPipeline-EvidenceFirst] Failed to update news_analyses: {e}")
            success = False

        # Save agent results
        try:
            agent_record = {
                "analysis_id": self.analysis_id,
                "agent_name": "evidence_collection",
                "status": "completed",
                "confidence": 0.8,
                "processing_time_ms": processing_time_ms,
                "findings": json.dumps(["Evidence collection completed"]),
                "evidence": json.dumps([]),
                "raw_output": json.dumps(results.get("report_data", {})),
                "processed_output": json.dumps(results.get("report_data", {})),
            }
            self.client.schema("public").table("news_agent_results").insert(agent_record).execute()
            logger.info(f"[NewsPipeline-EvidenceFirst] Agent result saved")
        except Exception as e:
            logger.warning(f"[NewsPipeline-EvidenceFirst] Failed to save agent result: {e}")

        # Save evidence items
        try:
            evidence_items = results.get("report_data", {}).get("evidence", [])
            for idx, ev in enumerate(evidence_items):
                evidence_record = {
                    "analysis_id": self.analysis_id,
                    "agent_name": "evidence_collection",
                    "evidence_type": "text",
                    "key": f"evidence_{idx}",
                    "value": ev.get("claim", "")[:500],
                    "reference_url": ev.get("url", ""),
                    "confidence": ev.get("credibility", 0.5),
                    "claim": ev.get("claim", ""),
                    "source": ev.get("source", ""),
                    "url": ev.get("url", ""),
                    "excerpt": ev.get("excerpt", ""),
                    "credibility": ev.get("credibility", 0.5),
                    "supports_claim": ev.get("supports_claim", True),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                self.client.schema("public").table("news_evidence").insert(evidence_record).execute()
            logger.info(f"[NewsPipeline-EvidenceFirst] Saved {len(evidence_items)} evidence items")
        except Exception as e:
            logger.warning(f"[NewsPipeline-EvidenceFirst] Failed to save evidence: {e}")

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
                "bias_analysis": json.dumps(report_data.get("bias_analysis", {})),
                "context_analysis": json.dumps(report_data.get("context_analysis", {})),
                "ai_explanation": report_data.get("ai_explanation", ""),
                "processing_time_ms": processing_time_ms,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.client.schema("public").table("news_reports").insert(report_record).execute()
            logger.info(f"[NewsPipeline-EvidenceFirst] Report saved: {report_id}")
        except Exception as e:
            logger.error(f"[NewsPipeline-EvidenceFirst] Failed to save report: {e}")
            success = False

        # Generate PDF
        try:
            await self._generate_and_upload_pdf(results.get("report_data", {}))
        except Exception as e:
            logger.error(f"[NewsPipeline-EvidenceFirst] PDF generation failed: {e}")

        return success

    async def _generate_and_upload_pdf(self, report_data: Dict) -> bool:
        """Generate PDF report (same as original)."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch, mm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

            import tempfile
            import os

            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                pdf_path = tmp.name

            doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                                     rightMargin=50, leftMargin=50,
                                     topMargin=50, bottomMargin=50)

            styles = getSampleStyleSheet()
            story = []

            # Title
            title_style = ParagraphStyle('CustomTitle', parent=styles['Title'],
                                          fontSize=24, spaceAfter=20, alignment=TA_CENTER)
            story.append(Paragraph("VisionX News Verification Report", title_style))
            story.append(Spacer(1, 12))

            verdict = report_data.get("verdict_details", {}).get("verdict", "Unknown")
            trust_score = report_data.get("verdict_details", {}).get("trust_score", 0)
            risk = report_data.get("verdict_details", {}).get("risk_level", "Medium")

            verdict_style = ParagraphStyle('Verdict', parent=styles['Normal'],
                                            fontSize=14, spaceAfter=10, alignment=TA_CENTER,
                                            textColor=colors.HexColor("#1a56db"))
            story.append(Paragraph(f"Verdict: {verdict}", verdict_style))
            story.append(Paragraph(f"Trust Score: {trust_score:.1f}% | Risk Level: {risk}", verdict_style))
            story.append(Spacer(1, 20))

            story.append(Paragraph("<b>Executive Summary</b>", styles['Heading2']))
            exec_summary = report_data.get("executive_summary", "No summary available.")
            story.append(Paragraph(exec_summary.replace('\n', '<br/>'), styles['Normal']))
            story.append(Spacer(1, 12))

            claims = report_data.get("claims", [])
            if claims:
                story.append(Paragraph(f"<b>Claims Analyzed ({len(claims)})</b>", styles['Heading2']))
                for i, c in enumerate(claims[:10]):
                    claim_text = c.get("claim", "")[:200]
                    story.append(Paragraph(f"{i+1}. {claim_text}", styles['Normal']))
                story.append(Spacer(1, 12))

            recommendations = report_data.get("recommendations", [])
            if recommendations:
                story.append(Paragraph("<b>Recommendations</b>", styles['Heading2']))
                for r in recommendations:
                    story.append(Paragraph(f"• {r}", styles['Normal']))
                story.append(Spacer(1, 12))

            story.append(Spacer(1, 30))
            footer_style = ParagraphStyle('Footer', parent=styles['Normal'],
                                           fontSize=8, textColor=colors.gray, alignment=TA_CENTER)
            story.append(Paragraph(f"Generated by VisionX | {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}", footer_style))
            story.append(Paragraph(f"Analysis ID: {self.analysis_id}", footer_style))

            doc.build(story)

            with open(pdf_path, 'rb') as f:
                pdf_data = f.read()

            file_name = f"reports/{self.analysis_id}.pdf"
            try:
                self.client.storage.from_("visionx-reports").upload(
                    file_name, pdf_data, {"content-type": "application/pdf"}
                )
                pdf_url = self.client.storage.from_("visionx-reports").get_public_url(file_name)
                self.client.schema("public").table("news_reports").update({
                    "pdf_path": file_name, "pdf_url": pdf_url,
                }).eq("analysis_id", self.analysis_id).execute()
                logger.info(f"[NewsPipeline-EvidenceFirst] PDF uploaded: {pdf_url}")
            except Exception as e:
                if "already exists" in str(e):
                    pass  # PDF already exists
                else:
                    raise

            os.unlink(pdf_path)
            return True

        except ImportError:
            logger.warning("[NewsPipeline-EvidenceFirst] ReportLab not installed")
            return False
        except Exception as e:
            logger.error(f"[NewsPipeline-EvidenceFirst] PDF generation failed: {e}")
            return False

    async def _mark_failed(self, error_message: str):
        """Mark analysis as failed."""
        try:
            self.client.schema("public").table("news_analyses").update({
                "status": "failed",
                "error_message": error_message[:500],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", self.analysis_id).execute()
        except Exception as e:
            logger.error(f"[NewsPipeline-EvidenceFirst] Failed to mark as failed: {e}")


# Global instance placeholder
news_pipeline_evidence_first = None