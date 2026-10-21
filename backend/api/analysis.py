"""
Analysis Routes - REST endpoints for analysis operations.
Unified endpoint layer using ImageAnalysisService for all image analysis.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse

from backend.core.exceptions import NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.api.dependencies import get_current_user
from backend.api.deps import get_user_from_query_token
from backend.database.db_client import get_db_client
from backend.events.event_bus import event_bus
from backend.services.image_analysis_service import image_analysis_service
from backend.services.video_analysis_service import video_analysis_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


def _client():
    return get_db_client().schema("public")


@router.post("/analyze")
async def start_analysis(
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """
    Start a new analysis.
    
    Request body should contain:
    - module: str (image, news, etc.)
    - input_content: str (file path or URL)
    - input_type: str
    - source_url: Optional[str]
    - title: Optional[str]
    """
    try:
        body = await request.json()
        module = body.get("module", "image")
        input_content = body.get("input_content", "")
        input_type = body.get("input_type", "text")
        source_url = body.get("source_url")
        title = body.get("title")

        if not input_content:
            raise ValidationError(message="No input content provided")

        # For file-based analysis, dispatch to the correct service
        if input_type and input_type.startswith("file:"):
            if module == "video" or input_type == "file:video":
                result = await video_analysis_service.analyze_video(
                    user_id=user_id,
                    video_path=input_content,
                    title=title,
                )
            else:
                result = image_analysis_service.analyze_image(
                    user_id=user_id,
                    image_path=input_content,
                    title=title,
                )
            return {
                "success": True,
                "analysis_id": result["analysis_id"],
                "status": result.get("status", "completed"),
                "trust_score": result.get("trust_score"),
                "confidence": result.get("confidence"),
                "risk_level": result.get("risk_level"),
                "verdict": result.get("verdict"),
                "message": "Analysis completed",
            }

        # For non-file analysis, return error
        return {
            "success": False,
            "status": "error",
            "message": "Only file-based analysis is supported via this endpoint. Use /analyze/upload instead.",
        }
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to start analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/upload")
async def upload_and_analyze(
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """
    Upload file and perform synchronous analysis.
    
    Form data:
    - module: str
    - file: UploadFile
    - title: Optional[str]
    - source_url: Optional[str]
    """
    try:
        form = await request.form()
        module = form.get("module", "image")
        file = form.get("file")
        title = form.get("title")
        source_url = form.get("source_url")

        if not file:
            raise ValidationError(message="No file provided")

        # Read file content
        content = await file.read()
        content_size = len(content)
        content_type = file.content_type or "application/octet-stream"

        # Validate file size (max 50MB)
        if content_size > 50 * 1024 * 1024:
            raise ValidationError(message="File too large (max 50MB)")

        # Compute SHA-256 hash
        sha256_hash = hashlib.sha256(content).hexdigest()

        # Save file to uploads directory for pipeline access
        upload_dir = os.path.join(os.getcwd(), "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        original_filename = Path(file.filename or "upload.bin").name
        safe_filename = f"{user_id[:8]}_{int(datetime.now().timestamp())}_{original_filename}"
        file_path = os.path.join(upload_dir, safe_filename)
        with open(file_path, "wb") as f:
            f.write(content)

        # Create upload record
        try:
            _client().table("uploads").insert({
                "user_id": user_id,
                "original_filename": original_filename,
                "storage_path": file_path,
                "public_url": file_path,
                "mime_type": content_type,
                "file_size": content_size,
                "sha256": sha256_hash,
                "status": "completed",
            }).execute()
        except Exception as e:
            logger.warning(f"Upload record creation failed: {e}")

        # Perform analysis synchronously
        if module == "video" or (content_type and "video" in content_type):
            result = await video_analysis_service.analyze_video(
                user_id=user_id,
                video_path=file_path,
                title=title or original_filename,
            )
        else:
            result = image_analysis_service.analyze_image(
                user_id=user_id,
                image_path=file_path,
                title=title or original_filename,
            )

        return {
            "success": True,
            "analysis_id": result["analysis_id"],
            "status": "completed",
            "trust_score": result["trust_score"],
            "confidence": result["confidence"],
            "risk_level": result["risk_level"],
            "verdict": result["verdict"],
            "message": f"File '{original_filename}' analyzed successfully",
        }
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to upload and analyze: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyses/{analysis_id}")
async def get_analysis(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    """Get analysis details with evidence and report."""
    try:
        # Get analysis job
        result = _client().table("analysis_jobs").select("*").eq("id", analysis_id).eq("user_id", user_id).execute()
        if not result.data:
            raise NotFoundError(resource="Analysis", resource_id=analysis_id)
        analysis = result.data[0]

        # Get evidence
        evidence_result = _client().table("evidence_items").select("*").eq("analysis_id", analysis_id).execute()
        evidence_data = {}
        if evidence_result.data:
            for e in evidence_result.data:
                etype = e.get("evidence_type", "general")
                if etype not in evidence_data:
                    evidence_data[etype] = []
                evidence_data[etype].append(e)

        # Get report
        report_result = _client().table("reports").select("*").eq("analysis_id", analysis_id).execute()
        report = report_result.data[0] if report_result.data else None

        return {
            "success": True,
            "analysis": analysis,
            "evidence": evidence_data,
            "report": report,
        }
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to get analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyses/{analysis_id}/status")
async def get_analysis_status(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    """Get analysis status."""
    try:
        result = _client().table("analysis_jobs").select("*").eq("id", analysis_id).eq("user_id", user_id).execute()
        if not result.data:
            raise NotFoundError(resource="Analysis", resource_id=analysis_id)
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
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to get status for {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs")
@router.get("/analyses")
async def list_jobs(
    user_id: str = Depends(get_current_user),
    module: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List analysis jobs for current user."""
    try:
        query = _client().table("analysis_jobs").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).offset(offset)
        if module:
            query = query.eq("module_type", module)
        if status:
            query = query.eq("status", status)
        result = query.execute()
        return {
            "success": True,
            "analyses": result.data or [],
            "count": len(result.data or []),
        }
    except Exception as e:
        logger.error(f"Failed to list analyses: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/v2")
async def list_jobs_v2(
    user_id: str = Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List analysis jobs v2 with pagination."""
    try:
        offset = (page - 1) * limit
        query = _client().table("analysis_jobs").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).offset(offset)
        result = query.execute()
        return {
            "success": True,
            "analyses": result.data or [],
            "page": page,
            "limit": limit,
            "count": len(result.data or []),
        }
    except Exception as e:
        logger.error(f"Failed to list analyses v2: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/analyses/{analysis_id}")
async def delete_analysis(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    """Delete analysis."""
    try:
        _client().table("analysis_jobs").delete().eq("id", analysis_id).eq("user_id", user_id).execute()
        return {
            "success": True,
            "message": f"Analysis {analysis_id} deleted",
        }
    except Exception as e:
        logger.error(f"Failed to delete analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyses/{analysis_id}/cancel")
async def cancel_analysis(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    """Cancel running analysis."""
    try:
        _client().table("analysis_jobs").delete().eq("id", analysis_id).eq("user_id", user_id).execute()
        return {
            "success": True,
            "message": f"Analysis {analysis_id} cancelled",
        }
    except Exception as e:
        logger.error(f"Failed to cancel analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyses/{analysis_id}/events")
async def stream_analysis_events(
    analysis_id: str,
    request: Request,
    token: Optional[str] = Query(None),
):
    """Server-Sent Events for analysis progress."""
    user = await get_user_from_query_token(token)
    user_id = user["sub"]

    result = _client().table("analysis_jobs").select("id").eq("id", analysis_id).eq("user_id", user_id).execute()
    if not result.data:
        raise NotFoundError(resource="Analysis", resource_id=analysis_id)

    async def event_generator():
        yield f"event: connected\ndata: {analysis_id}\n\n"
        queue = await event_bus.subscribe_sse(analysis_id)
        try:
            while not await request.is_disconnected():
                yield await queue.get()
        finally:
            await event_bus.unsubscribe_sse(analysis_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# Uploads endpoints
uploads_router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])

@uploads_router.get("/")
async def list_uploads(
    user_id: str = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
):
    """List uploads for current user."""
    try:
        result = _client().table("uploads")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .offset(offset)\
            .execute()
        return {
            "success": True,
            "uploads": result.data or [],
            "count": len(result.data or []),
        }
    except Exception as e:
        logger.error(f"Failed to list uploads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@uploads_router.delete("/{upload_id}")
async def delete_upload(
    upload_id: str,
    user_id: str = Depends(get_current_user),
):
    """Delete upload."""
    try:
        _client().table("uploads").delete().eq("id", upload_id).eq("user_id", user_id).execute()
        return {"success": True, "message": f"Upload {upload_id} deleted"}
    except Exception as e:
        logger.error(f"Failed to delete upload {upload_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@uploads_router.post("/{upload_id}/reanalyze")
async def reanalyze_upload(
    upload_id: str,
    user_id: str = Depends(get_current_user),
):
    """Start a new analysis using the same file."""
    try:
        upload_result = _client().table("uploads").select("*").eq("id", upload_id).eq("user_id", user_id).execute()
        if not upload_result.data:
            raise NotFoundError(resource="Upload", resource_id=upload_id)
        
        upload = upload_result.data[0]
        file_path = upload.get("storage_path")
        
        if not file_path or not os.path.exists(file_path):
            raise ValidationError(message=f"Upload file not found at {file_path}")

        result = image_analysis_service.analyze_image(
            user_id=user_id,
            image_path=file_path,
            title=upload.get("original_filename"),
        )

        return {
            "success": True,
            "message": "Re-analysis completed",
            "analysis_id": result["analysis_id"],
            "trust_score": result["trust_score"],
            "verdict": result["verdict"],
        }
    except NotFoundError:
        raise
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to reanalyze upload {upload_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
