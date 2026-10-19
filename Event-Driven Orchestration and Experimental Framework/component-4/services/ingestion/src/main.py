"""FastAPI Application entry point for API Documentation Ingestion Service."""

import logging
import time
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .api.routes import router as ingestion_router
from .api.dependencies import get_repository
from .models.schemas import HealthResponse
from .persistence.repository import MongoDocumentRepository

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("ingestion-service")

START_TIME = time.time()

app = FastAPI(
    title="Component 4 — API Documentation Ingestion Service",
    description=(
        "Ingests OpenAPI 3.x and Swagger 2.0 specifications, validates structural contracts, "
        "and extracts normalized service endpoints for event intelligence and downstream adaptive caching."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include ingestion API router
app.include_router(ingestion_router)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
def health_check() -> HealthResponse:
    """Returns service health status, version, uptime, and database connectivity."""
    repo = get_repository()
    mongo_connected = False
    if isinstance(repo, MongoDocumentRepository):
        mongo_connected = repo.is_connected()

    return HealthResponse(
        status="healthy",
        service=settings.SERVICE_NAME,
        version="0.1.0",
        uptime_seconds=round(time.time() - START_TIME, 2),
        mongodb_connected=mongo_connected,
    )


# ── Global Centralized Exception Handlers ──────────────────────────────────────


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Formats all HTTP exceptions into a standard JSON response structure."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "statusCode": exc.status_code,
            "message": exc.detail,
            "path": request.url.path,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Formats Pydantic request validation errors."""
    error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "statusCode": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "message": "Validation failed for request parameters.",
            "issues": error_messages,
            "path": request.url.path,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catches unhandled errors and returns sanitized 500 responses."""
    logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "statusCode": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": "Internal server error occurred while processing specification.",
            "path": request.url.path,
        },
    )


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Ingestion Service on {settings.HOST}:{settings.PORT}")
    uvicorn.run("src.main:app", host=settings.HOST, port=settings.PORT, reload=True)
