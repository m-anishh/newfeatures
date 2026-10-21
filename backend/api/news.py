"""
News Routes - Production-grade REST endpoints for news verification.
All endpoints use authenticated user, proper error handling, and the new service layer.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query, BackgroundTasks

from backend.core.exceptions import NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.api.dependencies import get_current_user
from backend.database.db_client import get_db_client
from backend.services.news_verification_service import news_verification_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/news", tags=["news"])


def _client():
    return get_db_client().schema("public")


@router.post("/analyze")
async def analyze_news(
    input_type: str = Form(...),
    input_content: str = Form(...),
    title: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user_id: str = Depends(get_current_user),
):
    """Analyze news content for credibility. Runs the full 11-agent pipeline."""
    try:
        valid_input_types = ["url", "article", "screenshot", "headline", "text", "pdf"]
        if input_type not in valid_input_types:
            raise ValidationError(
                message=f"Invalid input type. Must be one of: {valid_input_types}"
            )

        # Handle file upload if provided
        if file and input_type in ["screenshot", "pdf"]:
            if not file.filename:
                raise ValidationError(message="No file provided")

            allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp", "application/pdf"]
            if file.content_type and file.content_type not in allowed_types:
                raise ValidationError(
                    message=f"Unsupported file type: {file.content_type}. Supported: {allowed_types}"
                )

            image_data = await file.read()
            if len(image_data) == 0:
                raise ValidationError(message="Empty file")
            if len(image_data) > 20 * 1024 * 1024:
                raise ValidationError(message="File too large (max 20MB)")

            # Upload file to storage
            try:
                file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
                storage_path = f"uploads/{user_id}/{uuid.uuid4()}.{file_ext}"
                client = get_db_client()
                client.storage.from_("visionx-news").upload(storage_path, image_data, {"content-type": file.content_type or "image/jpeg"})
                input_content = f"[File: {file.filename}, Storage: {storage_path}]"
            except Exception as upload_error:
                logger.warning(f"File upload failed, continuing with metadata: {upload_error}")
                input_content = f"[File: {file.filename}, Size: {len(image_data)} bytes]"

        # Create analysis record
        analysis_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        _client().table("news_analyses").insert({
            "id": analysis_id,
            "user_id": user_id,
            "input_type": input_type,
            "input_content": input_content,
            "source_url": source_url or "",
            "title": title or input_content[:100],
            "status": "queued",
            "progress": 0,
            "risk_level": "medium",
            "created_at": now,
            "updated_at": now,
        }).execute()

        # Start pipeline in background
        background_tasks.add_task(
            news_verification_service.start_verification,
            analysis_id=analysis_id,
            user_id=user_id,
            input_type=input_type,
            input_content=input_content,
            title=title or input_content[:100],
            source_url=source_url,
        )

        return {
            "success": True,
            "analysis_id": analysis_id,
            "status": "queued",
            "message": "News verification started. The pipeline will process through 11 AI agents.",
        }
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"News analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis")
async def list_news_analyses(
    user_id: str = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
):
    """List news analyses for the authenticated user."""
    try:
        result = await news_verification_service.list_analyses(
            user_id=user_id, limit=limit, offset=offset, status=status
        )
        return {
            "success": True,
            "analyses": result.get("analyses", []),
            "count": result.get("count", 0),
        }
    except Exception as e:
        logger.error(f"List news analyses failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/{analysis_id}")
async def get_news_analysis(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    """Get a single news analysis with agent results, evidence, and report."""
    try:
        result = await news_verification_service.get_analysis(analysis_id, user_id)
        if not result:
            raise NotFoundError(resource="News Analysis", resource_id=analysis_id)
        
        return {
            "success": True,
            "analysis": result["analysis"],
            "agent_results": result["agent_results"],
            "evidence": result["evidence"],
            "report": result["report"],
        }
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Get news analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/analysis/{analysis_id}")
async def delete_news_analysis(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    """Delete a news analysis and all related data."""
    try:
        success = await news_verification_service.delete_analysis(analysis_id, user_id)
        if not success:
            raise NotFoundError(resource="News Analysis", resource_id=analysis_id)
        return {"success": True, "message": "News analysis deleted"}
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Delete news analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/{analysis_id}/status")
async def get_news_analysis_status(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    """Get news analysis status for polling."""
    try:
        result = _client().table("news_analyses").select("*").eq("id", analysis_id).execute()
        if not result.data:
            raise NotFoundError(resource="News Analysis", resource_id=analysis_id)
        a = result.data[0]
        if a.get("user_id") != user_id:
            raise NotFoundError(resource="News Analysis", resource_id=analysis_id)
        return {
            "success": True,
            "status": a.get("status"),
            "progress": a.get("progress", 0),
            "trust_score": a.get("trust_score"),
            "authenticity_score": a.get("authenticity_score"),
            "risk_level": a.get("risk_level"),
            "confidence": a.get("confidence"),
            "verdict": a.get("verdict"),
            "created_at": a.get("created_at"),
            "started_at": a.get("started_at"),
            "completed_at": a.get("completed_at"),
            "error_message": a.get("error_message"),
            "processing_time_ms": a.get("processing_time_ms"),
        }
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"News status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports")
async def list_news_reports(
    user_id: str = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List news reports for the authenticated user."""
    try:
        result = await news_verification_service.list_reports(
            user_id=user_id, limit=limit, offset=offset
        )
        return {
            "success": True,
            "reports": result.get("reports", []),
            "count": result.get("count", 0),
        }
    except Exception as e:
        logger.error(f"List news reports failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{analysis_id}")
async def get_news_report(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    """Get the report for a specific news analysis."""
    try:
        report = await news_verification_service.get_report(analysis_id, user_id)
        if not report:
            raise NotFoundError(resource="News Report", resource_id=analysis_id)
        return {
            "success": True,
            "report": report,
        }
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Get news report failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
async def get_news_dashboard(user_id: str = Depends(get_current_user)):
    """Get dashboard statistics for news verification."""
    try:
        stats = await news_verification_service.get_dashboard_stats(user_id)
        return {
            "success": True,
            "stats": stats,
        }
    except Exception as e:
        logger.error(f"News dashboard failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get news dashboard stats")


@router.post("/cleanup")
async def cleanup_stuck_analyses(user_id: str = Depends(get_current_user)):
    """Clean up analyses stuck in queued/processing for too long."""
    try:
        result = await news_verification_service.cleanup_stuck_analyses()
        return {
            "success": True,
            "message": f"Cleaned up {result.get('cleaned', 0)} stuck analyses",
            "details": result,
        }
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))