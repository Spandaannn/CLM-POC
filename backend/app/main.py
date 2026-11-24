"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.router import api_router
from app.core.exceptions import (
    sqlalchemy_exception_handler,
    validation_exception_handler,
)


def create_app() -> FastAPI:
    application = FastAPI(
        title="CLM API",
        version="0.1.0",
        description=(
            "Contract Lifecycle Management POC API. This phase provides "
            "health checks, session-based authentication, contract "
            "metadata management, versioned contract documents, AI-assisted reviews, and a contract approval workflow."
        ),
    )

    application.include_router(api_router)

    application.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )
    application.add_exception_handler(
        SQLAlchemyError, sqlalchemy_exception_handler
    )

    @application.middleware("http")
    async def disable_auth_response_caching(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(
            ("/api/auth", "/api/contracts", "/api/documents", "/api/reviews", "/api/ai", "/api/approvals")
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    return application


app = create_app()
