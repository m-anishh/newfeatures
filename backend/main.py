"""
VisionX Backend - Unified Entry Point
Combines V3 and V4 into a single clean entry point.
"""

import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load root and backend .env files before importing settings or dependent modules.
ROOT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
BACKEND_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ROOT_ENV_PATH, override=True)
load_dotenv(BACKEND_ENV_PATH, override=True)
# Load backend/.env before importing settings or any module that depends on settings.
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH, override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.api.analysis import router as analysis_router
from backend.api.reports import router as reports_router
from backend.api.dashboard import router as dashboard_router
from backend.api.incidents import router as incidents_router
from backend.api.news import router as news_router
from backend.api.video import router as video_router
from backend.api.auth import router as auth_router
from backend.api.analysis import uploads_router
from backend.events.event_bus import event_bus
from backend.core.exceptions import VisionXError
from backend.database.pg_client import storage_root
from backend.database.db_client import init_schema

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    logger.info("VisionX Backend Starting...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Database: {settings.database_url_safe}")
    logger.info(f"AI Provider: {settings.LLM_PROVIDER}")

    try:
        init_schema()
    except Exception as e:
        logger.error(f"Database setup failed - check DATABASE_URL in backend/.env: {e}")

    yield

    logger.info("VisionX Backend Shutting Down...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="VisionX API",
        description="AI-Powered Digital Trust Platform",
        version="4.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(analysis_router)
    app.include_router(reports_router)
    app.include_router(dashboard_router)
    app.include_router(incidents_router)
    app.include_router(news_router)
    app.include_router(video_router)
    app.include_router(uploads_router)

    # Locally stored files (uploads, reports)
    app.mount("/storage", StaticFiles(directory=str(storage_root())), name="storage")

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "version": "4.0.0",
            "environment": settings.ENVIRONMENT,
        }

    @app.exception_handler(VisionXError)
    async def visionx_exception_handler(request, exc: VisionXError):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=settings.DEBUG,
    )
