from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])

from app.auth import oauth  # noqa: E402, F401
