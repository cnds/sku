from __future__ import annotations

from fastapi import APIRouter

from controllers.analytics import router as analytics_router
from controllers.diagnosis import router as diagnosis_router
from controllers.ingestion import router as ingestion_router
from controllers.shopify import router as shopify_router

api_router = APIRouter()
api_router.include_router(analytics_router)
api_router.include_router(diagnosis_router)
api_router.include_router(ingestion_router)
api_router.include_router(shopify_router)
