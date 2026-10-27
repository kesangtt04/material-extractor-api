"""Material Extractor - Main FastAPI Application

Web UI cho pipeline extractor - chay local hoac mang noi bo (LAN).

Chay:
    py -m uvicorn app:app --reload --host 0.0.0.0 --port 8000

Sau do mo trong browser:
    http://localhost:8000            (may local)
    http://<IP-may-nay>:8000         (may khac trong LAN)

Version: 2.0 - Refactored structure
"""

import os
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from api.routers import file_router, text_router
from api.dependencies import get_warmed_model, get_text_parser_service, get_health_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = SCRIPT_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preload ML model and text parser when server starts to eliminate cold-start latency."""
    logger.info("Server started, warming up models...")

    # ML model loads in background thread (heavy sklearn/joblib load)
    ml_thread = threading.Thread(target=get_warmed_model, daemon=True)
    ml_thread.start()

    # Text parser loads synchronously so it's ready before the first /chat request
    try:
        logger.info("Loading text parser service...")
        get_text_parser_service()
        logger.info("Text parser service ready")
    except Exception as e:
        logger.error(f"Failed to load text parser: {e}", exc_info=True)

    yield  # application runs here

    # Shutdown: nothing to clean up currently


app = FastAPI(title="Material Extractor Demo", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=os.path.join(SCRIPT_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve unified chat + file upload interface."""
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )


@app.get("/health")
async def health_check():
    """Check if server, ML model, and text parser are ready."""
    health_status = get_health_status()
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(status_code=status_code, content=health_status)


# Include routers
app.include_router(file_router.router)
app.include_router(text_router.router)
