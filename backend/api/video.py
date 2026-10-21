"""
Video Analysis API Routes
REST endpoints for video verification module.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from pydantic import BaseModel, Field

from backend.api.dependencies import get_current_user
from backend.core.logging import get_logger
from backend.core.config import settings
from backend.services.video_service import video_service
from backend.repositories.video_repository import video_repository

logger = get_logger(__name__)

router = APIRouter(prefix="/video", tags=["video"])


def _user_id(current_user: Any) -> Optional[str]:
    """get_current_user returns the user id string; accept dicts too."""
    if isinstance(current_user, dict):
        return _user_id(current_user) or current_user.get("sub")
    return current_user


# Endpoints
@router.post("/upload", response_model=Dict[str, Any])
async def upload_video(
    input_type: str = Form(...),
    input_content: str = Form(...),
    title: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
    video_metadata: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: str = Depends(get_current_user),
):
    """Upload a video for analysis."""
    try:
        user_id = _user_id(current_user)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

        # Parse metadata
        metadata = {}
        if video_metadata:
            try:
                metadata = json.loads(video_metadata)
            except json.JSONDecodeError:
                pass

        # Handle file upload if provided
        if file:
            # Validate MIME type
            if file.content_type not in settings.ALLOWED_VIDEO_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file type: {file.content_type}. Supported: {', '.join(settings.ALLOWED_VIDEO_TYPES)}"
                )

            # Validate file size (max 500MB)
            max_size = 500 * 1024 * 1024
            contents = await file.read()
            if len(contents) > max_size:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File too large. Maximum size is 500MB"
                )

            input_content = f"uploaded:{file.filename}"
            metadata["file_size"] = len(contents)
            metadata["file_type"] = file.content_type

        # Create analysis record
        record = await video_repository.create_analysis(
            user_id=UUID(user_id),
            input_type=input_type,
            input_content=input_content,
            title=title,
            source_url=source_url,
            metadata=metadata,
        )

        analysis_id = record.get("id")
        if not analysis_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create analysis")

        # Start background processing
        asyncio.create_task(
            video_service.start_analysis(
                analysis_id=analysis_id,
                user_id=user_id,
                input_type=input_type,
                input_content=input_content,
                title=title,
                source_url=source_url,
                video_metadata=metadata,
            )
        )

        return {
            "success": True,
            "analysis_id": analysis_id,
            "status": "queued",
            "message": "Video analysis started",
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"[VideoAPI] Upload failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/analysis/{analysis_id}", response_model=Dict[str, Any])
async def get_analysis(
    analysis_id: str,
    current_user: str = Depends(get_current_user),
):
    """Get video analysis details."""
    try:
        user_id = _user_id(current_user)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

        result = await video_service.get_analysis(analysis_id, user_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

        return {
            "success": True,
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VideoAPI] Get analysis failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/history", response_model=Dict[str, Any])
async def get_history(
    limit: int = 20,
    offset: int = 0,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: str = Depends(get_current_user),
):
    """Get video analysis history."""
    try:
        user_id = _user_id(current_user)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

        result = await video_service.list_analyses(user_id, limit=limit, offset=offset, status=status_filter)
        return {
            "success": True,
            "analyses": result.get("analyses", []),
            "count": result.get("count", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VideoAPI] Get history failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/report/{analysis_id}", response_model=Dict[str, Any])
async def get_report(
    analysis_id: str,
    current_user: str = Depends(get_current_user),
):
    """Get video analysis report."""
    try:
        user_id = _user_id(current_user)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

        report = await video_service.get_report(analysis_id, user_id)
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

        return {
            "success": True,
            "report": report,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VideoAPI] Get report failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/reports", response_model=Dict[str, Any])
async def list_reports(
    limit: int = 20,
    offset: int = 0,
    current_user: str = Depends(get_current_user),
):
    """List all video reports for user."""
    try:
        user_id = _user_id(current_user)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

        result = await video_service.list_reports(user_id, limit=limit, offset=offset)
        return {
            "success": True,
            "reports": result.get("reports", []),
            "count": result.get("count", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VideoAPI] List reports failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/dashboard", response_model=Dict[str, Any])
async def get_dashboard(
    current_user: str = Depends(get_current_user),
):
    """Get video analysis dashboard statistics."""
    try:
        user_id = _user_id(current_user)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

        stats = await video_service.get_dashboard_stats(user_id)
        return {
            "success": True,
            "stats": stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VideoAPI] Get dashboard failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/analysis/{analysis_id}")
async def delete_analysis(
    analysis_id: str,
    current_user: str = Depends(get_current_user),
):
    """Delete a video analysis."""
    try:
        user_id = _user_id(current_user)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

        success = await video_service.delete_analysis(analysis_id, user_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

        return {
            "success": True,
            "message": "Analysis deleted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VideoAPI] Delete analysis failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))