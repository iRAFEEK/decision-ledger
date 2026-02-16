from fastapi import Cookie, Depends, HTTPException, Request
from jose import JWTError, jwt

from app.config import settings


def _extract_token(request: Request, session: str | None = Cookie(default=None)) -> str | None:
    if session:
        return session
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _decode_token(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return {
        "user_id": payload["sub"],
        "workspace_id": payload["workspace_id"],
        "slack_user_id": payload["slack_user_id"],
        "is_admin": payload.get("is_admin", False),
    }


async def get_current_user(
    request: Request, session: str | None = Cookie(default=None)
) -> dict:
    token = _extract_token(request, session)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return _decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_optional_user(
    request: Request, session: str | None = Cookie(default=None)
) -> dict | None:
    token = _extract_token(request, session)
    if not token:
        return None
    try:
        return _decode_token(token)
    except JWTError:
        return None
