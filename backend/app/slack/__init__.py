from fastapi import APIRouter

router = APIRouter(prefix="/slack", tags=["slack"])

# Import route modules to register endpoints on the router
from app.slack import commands, events, interactive  # noqa: E402, F401
