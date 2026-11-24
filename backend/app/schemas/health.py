"""Health-check response schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(description="API process status.")


class DatabaseHealthResponse(HealthResponse):
    database: Literal["ok"] = Field(description="PostgreSQL reachability status.")
