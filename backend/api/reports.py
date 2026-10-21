"""
Reports Routes - REST endpoints for reports.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse

from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.api.dependencies import get_current_user
from backend.database.db_client import get_db_client

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _client():
    return get_db_client().schema("public")


@router.get("/")
async def list_reports(
    user_id: str = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List reports for current user."""
    try:
        result = _client().table("reports")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .offset(offset)\
            .execute()
        return {
            "success": True,
            "reports": result.data or [],
            "count": len(result.data or []),
        }
    except Exception as e:
        logger.error(f"Failed to list reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    user_id: str = Depends(get_current_user),
):
    """Get report by ID."""
    try:
        result = _client().table("reports").select("*").eq("id", report_id).execute()
        if not result.data:
            raise NotFoundError(resource="Report", resource_id=report_id)
        report = result.data[0]
        # Verify ownership
        if report.get("user_id") != user_id:
            raise NotFoundError(resource="Report", resource_id=report_id)
        return {
            "success": True,
            "report": report,
        }
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to get report {report_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/{analysis_id}")
async def get_report_by_analysis(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    """Get report by analysis ID."""
    try:
        result = _client().table("reports").select("*").eq("analysis_id", analysis_id).execute()
        if not result.data:
            raise NotFoundError(resource="Report", resource_id=analysis_id)
        report = result.data[0]
        if report.get("user_id") != user_id:
            raise NotFoundError(resource="Report", resource_id=analysis_id)
        return {
            "success": True,
            "report": report,
        }
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to get report for analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{report_id}/pdf")
async def get_report_pdf(
    report_id: str,
    user_id: str = Depends(get_current_user),
):
    """Download report PDF."""
    try:
        result = _client().table("reports").select("*").eq("id", report_id).execute()
        if not result.data:
            raise NotFoundError(resource="Report", resource_id=report_id)
        report = result.data[0]
        if report.get("user_id") != user_id:
            raise NotFoundError(resource="Report", resource_id=report_id)
        
        pdf_path = report.get("pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="PDF file not found")
        
        return FileResponse(
            path=pdf_path,
            filename=f"report_{report_id}.pdf",
            media_type="application/pdf",
        )
    except NotFoundError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get PDF for report {report_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to download PDF")


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    user_id: str = Depends(get_current_user),
):
    """Delete report."""
    try:
        _client().table("reports").delete().eq("id", report_id).eq("user_id", user_id).execute()
        return {
            "success": True,
            "message": f"Report {report_id} deleted",
        }
    except Exception as e:
        logger.error(f"Failed to delete report {report_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    user_id: str = Depends(get_current_user),
):
    """Download report as JSON."""
    try:
        result = _client().table("reports").select("*").eq("id", report_id).execute()
        if not result.data:
            raise NotFoundError(resource="Report", resource_id=report_id)
        report = result.data[0]
        if report.get("user_id") != user_id:
            raise NotFoundError(resource="Report", resource_id=report_id)
        
        return JSONResponse(
            content=report,
            headers={
                "Content-Disposition": f"attachment; filename=report_{report_id}.json",
                "Content-Type": "application/json",
            }
        )
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to download report {report_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to download report")