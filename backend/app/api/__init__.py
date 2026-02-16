from fastapi import APIRouter

from app.api.analytics import router as analytics_router
from app.api.decisions import router as decisions_router
from app.api.search import router as search_router
from app.api.workspace import router as workspace_router

router = APIRouter(prefix="/api", tags=["api"])
router.include_router(decisions_router)
router.include_router(search_router)
router.include_router(workspace_router)
router.include_router(analytics_router)
