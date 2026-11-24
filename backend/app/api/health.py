"""Operational health endpoints."""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.db.health import ping_database
from app.schemas.common import ErrorResponse
from app.schemas.health import DatabaseHealthResponse, HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check that the API process is running",
)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/health/db",
    response_model=DatabaseHealthResponse,
    summary="Check that the API can reach PostgreSQL",
    responses={503: {"model": ErrorResponse}},
)
def database_health() -> DatabaseHealthResponse:
    try:
        ping_database()
    except SQLAlchemyError as exc:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unreachable",
        ) from exc

    return DatabaseHealthResponse(status="ok", database="ok")
