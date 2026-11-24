"""Aggregate API router.

Add future CLM module routers (contracts, documents, reviews, and so on) here
so app/main.py only has to include one router.
"""

from fastapi import APIRouter

from app.api import auth, contracts, documents, health, reviews

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(contracts.router)
api_router.include_router(documents.router)
api_router.include_router(reviews.router)
