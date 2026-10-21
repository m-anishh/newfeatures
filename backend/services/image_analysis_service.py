"""
Image Analysis Service - Simplified synchronous image verification.
Performs real metadata extraction, ELA, Gemini Vision analysis, and report generation.
"""

from __future__ import annotations

import os
import io
import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from PIL import Image, ExifTags
from io import BytesIO

from backend.core.logging import get_logger
from backend.core.exceptions import AnalysisError, ValidationError
from backend.database.db_client import get_db_client

logger = get_logger(__name__)

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class ImageAnalysisService:
    """Simplified synchronous image analysis service."""

    def __init__(self):
        self._client = None
        self._gemini_model = None

    def _get_client(self):
        if self._client is None:
            self._client = get_db_client()
        return self._client

    def _get_gemini_model(self):
        if self._gemini_model is None and GEMINI_AVAILABLE:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                # Use gemini-2.0-flash for latest version support
                self._gemini_model = genai.GenerativeModel("gemini-2.0-flash")
        return self._gemini_model

    def analyze_image(self, user_id: str, image_path: str, title: Optional[str] = None, analysis_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform complete image analysis synchronously.
        Returns analysis results with metadata, ELA, Gemini analysis, trust score, and report.
        """
        if not analysis_id:
            analysis_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        try:
            # Create upload record first (required for analysis FK)
            upload_result = self._get_client().schema("public").table("uploads").insert({
                "user_id": user_id,
                "original_filename": title or os.path.basename(image_path),
                "storage_path": image_path,
                "public_url": image_path,
                "mime_type": "image/png",
                "file_size": os.path.getsize(image_path),
                "sha256": "",
                "status": "completed",
            }).execute()
            upload_id = upload_result.data[0]["id"] if upload_result.data else None
            
            # Create analysis record in both tables
            self._get_client().schema("public").table("analysis").insert({
                "id": analysis_id,
                "user_id": user_id,
                "upload_id": upload_id,
                "trust_score": 0,
                "authenticity_status": "unknown",
                "risk_level": "unknown",
                "summary": "Analysis in progress",
                "ai_model": "gemini-2.0-flash",
                "reasoning": {},
                "evidence_summary": [],
                "recommendations": [],
                "agent_results": {},
                "created_at": now,
            }).execute()
            
            self._get_client().schema("public").table("analysis_jobs").insert({
                "id": analysis_id,
                "user_id": user_id,
                "module_type": "image",
                "input_type": "file:image",
                "input_content": image_path,
                "title": title or os.path.basename(image_path),
                "status": "processing",
                "progress": 10,
                "created_at": now,
                "updated_at": now,
            }).execute()

            # Step 1: Extract Metadata
            logger.info(f"[Analysis {analysis_id}] Extracting metadata")
            metadata_result = self._extract_metadata(image_path)
            self._update_progress(analysis_id, 30)

            # Step 2: Perform ELA
            logger.info(f"[Analysis {analysis_id}] Performing ELA")
            ela_result = self._perform_ela(image_path)
            self._update_progress(analysis_id, 50)

            # Step 3: Gemini Vision Analysis
            logger.info(f"[Analysis {analysis_id}] Running Gemini Vision")
            gemini_result = self._analyze_with_gemini(image_path, metadata_result, ela_result)
            self._update_progress(analysis_id, 70)

            # Step 4: Calculate Trust Score
            logger.info(f"[Analysis {analysis_id}] Calculating trust score")
            trust_result = self._calculate_trust_score(metadata_result, ela_result, gemini_result)
            self._update_progress(analysis_id, 80)

            # Step 5: Generate Report
            logger.info(f"[Analysis {analysis_id}] Generating report")
            report_data = self._generate_report_data(
                analysis_id, image_path, metadata_result, ela_result, gemini_result, trust_result
            )
            pdf_path = self._generate_pdf_report(report_data, analysis_id)
            self._update_progress(analysis_id, 90)

            # Save to database
            self._save_results(analysis_id, user_id, image_path, metadata_result, ela_result, 
                             gemini_result, trust_result, report_data, pdf_path, now)

            self._update_progress(analysis_id, 100, "completed")

            logger.info(f"[Analysis {analysis_id}] Completed successfully")
            return {
                "success": True,
                "analysis_id": analysis_id,
                "status": "completed",
                "trust_score": trust_result["trust_score"],
                "confidence": trust_result["confidence"],
                "risk_level": trust_result["risk_level"],
                "verdict": trust_result["verdict"],
                "metadata": metadata_result,
                "ela": ela_result,
                "gemini": gemini_result,
                "report": report_data,
                "pdf_path": pdf_path,
            }

        except Exception as e:
            logger.error(f"[Analysis {analysis_id}] Failed: {e}")
            self._update_progress(analysis_id, 0, "failed", str(e))
            raise AnalysisError(message=f"Analysis failed: {e}") from e

    def _extract_metadata(self, image_path: str) -> Dict[str, Any]:
        """Extract EXIF metadata from image."""
        metadata = {
            "format": None,
            "mode": None,
            "width": 0,
            "height": 0,
            "size_bytes": 0,
            "exif": {},
            "has_gps": False,
            "suspicious_flags": [],
        }

        try:
            with Image.open(image_path) as img:
                metadata["format"] = img.format
                metadata["mode"] = img.mode
                metadata["width"] = img.width
                metadata["height"] = img.height
                metadata["size_bytes"] = os.path.getsize(image_path)

                # Extract EXIF
                exif_data = img._getexif()
                if exif_data:
                    exif_dict = {}
                    for tag_id, value in exif_data.items():
                        tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                        if isinstance(value, bytes):
                            try:
                                value = value.decode("utf-8", errors="replace")
                            except:
                                value = str(value)
                        exif_dict[tag_name] = value

                    metadata["exif"] = exif_dict

                    # Check for GPS
                    if "GPSInfo" in exif_dict:
                        metadata["has_gps"] = True

                    # Check for editing software
                    if "Software" in exif_dict:
                        metadata["suspicious_flags"].append(f"Editing software detected: {exif_dict['Software']}")
                else:
                    metadata["suspicious_flags"].append("No EXIF metadata found")

        except Exception as e:
            logger.error(f"Metadata extraction failed: {e}")
            metadata["error"] = str(e)

        return metadata

    def _perform_ela(self, image_path: str) -> Dict[str, Any]:
        """Perform Error Level Analysis."""
        result = {
            "ela_image_path": None,
            "avg_ela": 0.0,
            "max_ela": 0.0,
            "suspicious_regions": [],
            "compression_inconsistency": False,
            "finding": "ELA analysis completed",
        }

        if not CV2_AVAILABLE:
            result["finding"] = "ELA skipped: OpenCV not available"
            return result

        try:
            # Load image
            pil_img = Image.open(image_path)
            original = cv2.imread(image_path)
            if original is None:
                original = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

            # Resave with quality 85
            buf = BytesIO()
            if pil_img.mode in ("RGBA","LA","P"):
                pil_img = pil_img.convert("RGB")
            pil_img.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            resaved = Image.open(buf)
            resaved_cv = cv2.cvtColor(np.array(resaved), cv2.COLOR_RGB2BGR)

            # Calculate difference
            diff = cv2.absdiff(original, resaved_cv)
            diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

            # Statistics
            result["avg_ela"] = float(np.mean(diff_gray))
            result["max_ela"] = float(np.max(diff_gray))

            # Save ELA visualization
            ela_path = image_path.replace(".", "_ela.")
            ela_color = cv2.applyColorMap(diff_gray * 5, cv2.COLORMAP_JET)
            cv2.imwrite(ela_path, ela_color)
            result["ela_image_path"] = ela_path

            # Detect suspicious regions (high ELA areas)
            if result["max_ela"] > 50:
                result["compression_inconsistency"] = True
                result["finding"] = f"Suspicious ELA patterns detected (max={result['max_ela']:.1f})"
            elif result["avg_ela"] > 20:
                result["finding"] = f"Moderate ELA variations (avg={result['avg_ela']:.1f})"
            else:
                result["finding"] = f"Normal ELA patterns (avg={result['avg_ela']:.1f})"

        except Exception as e:
            logger.error(f"ELA failed: {e}")
            result["finding"] = f"ELA failed: {e}"

        return result

    def _analyze_with_gemini(self, image_path: str, metadata: Dict, ela: Dict) -> Dict[str, Any]:
        """Analyze image with Gemini Vision API."""
        result = {
            "authenticity_assessment": "unknown",
            "manipulation_indicators": [],
            "ai_generated_indicators": [],
            "visual_inconsistencies": [],
            "confidence": 0.0,
            "risk_level": "medium",
            "explanation": "",
            "recommendations": [],
        }

        model = self._get_gemini_model()
        if not model:
            result["explanation"] = "Gemini Vision API not available"
            return result

        try:
            # Prepare image with proper MIME type
            from PIL import Image as PILImage
            import mimetypes
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type or not mime_type.startswith("image/"):
                mime_type = "image/jpeg"  # Default fallback
            
            # Load and convert image
            pil_img = PILImage.open(image_path)
            
            # Convert to RGB if necessary (Gemini requires RGB)
            if pil_img.mode in ("RGBA", "LA", "P", "L"):
                pil_img = pil_img.convert("RGB")
            
            # Build prompt
            prompt = f"""You are a digital forensics expert. Analyze this image and respond with ONLY valid JSON:

{{
  "authenticity_assessment": "authentic" | "possibly_edited" | "suspicious" | "likely_ai_generated" | "manipulated",
  "manipulation_indicators": ["list of specific manipulation signs"],
  "ai_generated_indicators": ["list of AI generation artifacts"],
  "visual_inconsistencies": ["list of visual inconsistencies"],
  "confidence": 0.0-1.0,
  "risk_level": "minimal" | "low" | "medium" | "high" | "critical",
  "explanation": "detailed reasoning",
  "recommendations": ["list of recommendations"]
}}

Context:
- Metadata: {metadata.get('suspicious_flags', [])}
- ELA: {ela.get('finding', 'N/A')}
- ELA Max: {ela.get('max_ela', 0):.1f}

Analyze for: pixel anomalies, compression artifacts, lighting inconsistencies, edge misalignment, cloning, AI patterns."""

            response = model.generate_content([prompt, pil_img])
            response_text = response.text.strip()

            # Parse JSON
            import json
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(response_text[json_start:json_end])
                result.update(parsed)
            else:
                result["explanation"] = response_text[:500]

        except Exception as e:
            logger.error(f"Gemini analysis failed: {e}")
            result["explanation"] = f"Gemini analysis failed: {e}"

        return result

    def _calculate_trust_score(self, metadata: Dict, ela: Dict, gemini: Dict) -> Dict[str, Any]:
        """Calculate trust score from all analysis components."""
        # Weights
        weights = {
            "metadata": 0.25,
            "ela": 0.25,
            "gemini": 0.50,
        }

        scores = {}

        # Metadata score (0-100)
        meta_score = 100
        if metadata.get("suspicious_flags"):
            meta_score -= len(metadata["suspicious_flags"]) * 15
        if not metadata.get("exif"):
            meta_score -= 20
        if metadata.get("has_gps"):
            meta_score += 5  # GPS presence is positive
        scores["metadata"] = max(0, min(100, meta_score))

        # ELA score (0-100)
        ela_score = 100
        max_ela = ela.get("max_ela", 0)
        if max_ela > 50:
            ela_score = 30
        elif max_ela > 30:
            ela_score = 50
        elif max_ela > 15:
            ela_score = 70
        else:
            ela_score = 90
        if ela.get("compression_inconsistency"):
            ela_score -= 20
        scores["ela"] = max(0, min(100, ela_score))

        # Gemini score (0-100)
        gemini_score = gemini.get("confidence", 0.5) * 100
        if gemini.get("authenticity_assessment") == "authentic":
            gemini_score = max(gemini_score, 80)
        elif gemini.get("authenticity_assessment") in ["suspicious", "manipulated", "likely_ai_generated"]:
            gemini_score = min(gemini_score, 40)
        scores["gemini"] = max(0, min(100, gemini_score))

        # Weighted average
        trust_score = sum(scores[k] * weights[k] for k in weights)
        trust_score = int(round(trust_score))

        # Determine risk and verdict
        if trust_score >= 80:
            risk_level = "minimal"
            verdict = "likely_authentic"
        elif trust_score >= 60:
            risk_level = "low"
            verdict = "mostly_authentic"
        elif trust_score >= 40:
            risk_level = "medium"
            verdict = "needs_verification"
        elif trust_score >= 20:
            risk_level = "high"
            verdict = "likely_manipulated"
        else:
            risk_level = "critical"
            verdict = "likely_manipulated"

        confidence = trust_score / 100.0

        return {
            "trust_score": trust_score,
            "confidence": confidence,
            "risk_level": risk_level,
            "verdict": verdict,
            "score_components": scores,
            "weights": weights,
        }

    def _generate_report_data(self, analysis_id: str, image_path: str, metadata: Dict, 
                            ela: Dict, gemini: Dict, trust: Dict) -> Dict[str, Any]:
        """Generate structured report data."""
        return {
            "report_id": f"VX-{analysis_id[:8].upper()}",
            "analysis_id": analysis_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "image_path": image_path,
            "executive_summary": {
                "trust_score": trust["trust_score"],
                "confidence": round(trust["confidence"] * 100, 1),
                "risk_level": trust["risk_level"],
                "verdict": trust["verdict"],
                "explanation": gemini.get("explanation", ""),
            },
            "metadata_analysis": {
                "format": metadata.get("format"),
                "dimensions": f"{metadata.get('width')}x{metadata.get('height')}",
                "size_bytes": metadata.get("size_bytes"),
                "has_gps": metadata.get("has_gps", False),
                "exif_count": len(metadata.get("exif", {})),
                "suspicious_flags": metadata.get("suspicious_flags", []),
            },
            "ela_analysis": {
                "avg_ela": round(ela.get("avg_ela", 0), 2),
                "max_ela": round(ela.get("max_ela", 0), 2),
                "compression_inconsistency": ela.get("compression_inconsistency", False),
                "finding": ela.get("finding"),
                "ela_image_path": ela.get("ela_image_path"),
            },
            "gemini_analysis": {
                "authenticity_assessment": gemini.get("authenticity_assessment"),
                "manipulation_indicators": gemini.get("manipulation_indicators", []),
                "ai_generated_indicators": gemini.get("ai_generated_indicators", []),
                "visual_inconsistencies": gemini.get("visual_inconsistencies", []),
                "recommendations": gemini.get("recommendations", []),
            },
            "trust_score_breakdown": trust.get("score_components", {}),
            "recommendations": gemini.get("recommendations", []) + self._generate_recommendations(trust),
        }

    def _generate_recommendations(self, trust: Dict) -> List[str]:
        """Generate recommendations based on trust score."""
        recs = []
        score = trust.get("trust_score", 50)
        if score >= 80:
            recs.append("Image appears authentic - no further action required")
        elif score >= 60:
            recs.append("Image appears mostly authentic - manual review recommended")
        elif score >= 40:
            recs.append("Image requires verification - additional forensic analysis recommended")
        else:
            recs.append("Image shows strong signs of manipulation - immediate investigation required")
        if trust.get("risk_level") in ["high", "critical"]:
            recs.append("Flag this image for security review")
            recs.append("Do not use this image as evidence without further verification")
        return recs

    def _generate_pdf_report(self, report_data: Dict, analysis_id: str) -> str:
        """Generate PDF report using ReportLab."""
        if not REPORTLAB_AVAILABLE:
            return ""

        try:
            buf = BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=letter)
            styles = getSampleStyleSheet()
            elements = []

            # Title
            title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=20, spaceAfter=12)
            elements.append(Paragraph("VisionX Forensic Report", title_style))
            elements.append(Paragraph(f"Report ID: {report_data['report_id']}", styles["Normal"]))
            elements.append(Paragraph(f"Generated: {report_data['generated_at']}", styles["Normal"]))
            elements.append(Spacer(1, 0.25 * inch))

            # Executive Summary
            elements.append(Paragraph("Executive Summary", styles["Heading2"]))
            es = report_data["executive_summary"]
            summary_data = [
                ["Metric", "Value"],
                ["Trust Score", f"{es['trust_score']}%"],
                ["Risk Level", es["risk_level"].upper()],
                ["Verdict", es["verdict"].replace("_", " ").title()],
                ["Confidence", f"{es['confidence']}%"],
            ]
            t = Table(summary_data, colWidths=[2 * inch, 3 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2563EB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor("#F8FAFC")]),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 0.15 * inch))

            # Metadata
            elements.append(Paragraph("Metadata Analysis", styles["Heading2"]))
            meta = report_data["metadata_analysis"]
            for k, v in meta.items():
                elements.append(Paragraph(f"<b>{k}:</b> {v}", styles["Normal"]))
            elements.append(Spacer(1, 0.15 * inch))

            # ELA
            elements.append(Paragraph("Error Level Analysis", styles["Heading2"]))
            ela = report_data["ela_analysis"]
            for k, v in ela.items():
                if k != "ela_image_path":
                    elements.append(Paragraph(f"<b>{k}:</b> {v}", styles["Normal"]))
            elements.append(Spacer(1, 0.15 * inch))

            # Gemini Analysis
            elements.append(Paragraph("AI Vision Analysis", styles["Heading2"]))
            gemini = report_data["gemini_analysis"]
            elements.append(Paragraph(f"<b>Assessment:</b> {gemini.get('authenticity_assessment')}", styles["Normal"]))
            elements.append(Paragraph(f"<b>Explanation:</b> {es.get('explanation', 'N/A')}", styles["Normal"]))
            elements.append(Spacer(1, 0.15 * inch))

            # Recommendations
            elements.append(Paragraph("Recommendations", styles["Heading2"]))
            for rec in report_data.get("recommendations", []):
                elements.append(Paragraph(f"• {rec}", styles["Normal"]))

            doc.build(elements)
            pdf_bytes = buf.getvalue()

            # Save
            reports_dir = os.path.join(os.getcwd(), "reports")
            os.makedirs(reports_dir, exist_ok=True)
            pdf_path = os.path.join(reports_dir, f"report_{analysis_id}.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            return pdf_path

        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            return ""

    def _save_results(self, analysis_id: str, user_id: str, image_path: str,
                     metadata: Dict, ela: Dict, gemini: Dict, trust: Dict,
                     report_data: Dict, pdf_path: str, now: str) -> None:
        """Save all results to database."""
        # Update analysis job - CRITICAL, must not fail silently
        try:
            self._get_client().schema("public").table("analysis_jobs").update({
                "status": "completed",
                "overall_confidence": trust["confidence"],
                "overall_verdict": trust["verdict"],
                "risk_level": trust["risk_level"],
                "current_stage": "completed",
                "completed_at": now,
                "updated_at": now,
                "extra_metadata": {
                    "metadata": metadata,
                    "ela": ela,
                    "gemini": gemini,
                }
            }).eq("id", analysis_id).execute()
            logger.info(f"[Analysis {analysis_id}] Updated analysis_jobs with results")
        except Exception as e:
            logger.error(f"[Analysis {analysis_id}] CRITICAL: Failed to update analysis_jobs: {e}")
            # Don't continue if we can't save the main analysis record
            raise

        # Save evidence - non-critical
        try:
            evidence_items = []
            for key, value in metadata.items():
                if key != "exif":
                    evidence_items.append({
                        "analysis_id": analysis_id,
                        "agent_name": "metadata",
                        "evidence_type": "metadata",
                        "key": key,
                        "value": str(value),
                        "confidence": 0.9,
                    })

            evidence_items.append({
                "analysis_id": analysis_id,
                "agent_name": "ela",
                "evidence_type": "forensics",
                "key": "ela_analysis",
                "value": ela.get("finding", ""),
                "confidence": 0.8,
            })

            evidence_items.append({
                "analysis_id": analysis_id,
                "agent_name": "gemini",
                "evidence_type": "ai_analysis",
                "key": "gemini_analysis",
                "value": gemini.get("explanation", ""),
                "confidence": gemini.get("confidence", 0.5),
            })

            if evidence_items:
                self._get_client().schema("public").table("evidence_items").insert(evidence_items).execute()
        except Exception as e:
            logger.warning(f"[Analysis {analysis_id}] Failed to save evidence: {e}")

        # Save report - non-critical
        try:
            self._get_client().schema("public").table("reports").insert({
                "user_id": user_id,
                "analysis_id": analysis_id,
                "title": report_data.get("executive_summary", {}).get("verdict", "Analysis Report"),
                "trust_score": trust["trust_score"],
                "authenticity_status": trust["verdict"],
                "risk_level": trust["risk_level"],
                "verdict": trust["verdict"],
                "report_data": report_data,
                "pdf_url": pdf_path,
                "pdf_path": pdf_path,
                "created_at": now,
                "updated_at": now,
            }).execute()
            logger.info(f"[Analysis {analysis_id}] Saved report to database")
        except Exception as e:
            logger.warning(f"[Analysis {analysis_id}] Failed to save report: {e}")

    def _update_progress(self, analysis_id: str, progress: int, status: Optional[str] = None, error: Optional[str] = None) -> None:
        """Update analysis progress."""
        try:
            update_data = {"progress": progress, "updated_at": datetime.now(timezone.utc).isoformat()}
            if status:
                update_data["status"] = status
            if error:
                update_data["error_message"] = error
            self._get_client().schema("public").table("analysis_jobs").update(update_data).eq("id", analysis_id).execute()
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")


# Global instance
image_analysis_service = ImageAnalysisService()
