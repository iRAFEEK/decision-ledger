import uuid
import secrets
import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import httpx
import structlog
from fastapi import Request
from fastapi.responses import RedirectResponse
from jose import jwt

from app.auth import router
from app.config import settings
from app.db.models import User, Workspace
from app.db.session import async_session_factory
from sqlalchemy import select

log = structlog.get_logger()

SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"

BOT_SCOPES = ",".join([
    "channels:history",
    "channels:read",
    "chat:write",
    "commands",
    "groups:history",
    "groups:read",
    "users:read",
    "users:read.email",
])

USER_SCOPES = ",".join([
    "channels:history",
    "groups:history",
    "search:read",
])


@router.get("/slack")
async def slack_oauth_redirect():
    state = secrets.token_urlsafe(32)
    params = urlencode({
        "state": state,
        "client_id": settings.slack_client_id,
        "scope": BOT_SCOPES,
        "user_scope": USER_SCOPES,
        "redirect_uri": f"{settings.api_url}/auth/callback",
    })
    response = RedirectResponse(url=f"{SLACK_AUTHORIZE_URL}?{params}")
    response.set_cookie("oauth_state", state, httponly=True,
                        secure=settings.api_url.startswith("https://"),
                        samesite="lax", max_age=600)
    return response


@router.get("/callback")
async def slack_oauth_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse(url=f"{settings.app_url}?error=missing_code")

    state = request.query_params.get("state", "")
    expected = request.cookies.get("oauth_state", "")
    if not expected or not hmac.compare_digest(state, expected):
        return RedirectResponse(url=f"{settings.app_url}?error=invalid_state")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            SLACK_TOKEN_URL,
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
                "redirect_uri": f"{settings.api_url}/auth/callback",
            },
        )
    data = resp.json()

    if not data.get("ok"):
        log.error("oauth_token_exchange_failed", error=data.get("error"))
        return RedirectResponse(url=f"{settings.app_url}?error=oauth_failed")

    team = data.get("team", {})
    team_id = team.get("id")
    team_name = team.get("name", "")
    bot_token = data.get("access_token", "")
    authed_user = data.get("authed_user", {})
    user_token = authed_user.get("access_token", "")
    user_slack_id = authed_user.get("id", "")

    # Fetch user info
    user_info = {}
    if bot_token and user_slack_id:
        async with httpx.AsyncClient(timeout=10) as client:
            user_resp = await client.get(
                "https://slack.com/api/users.info",
                params={"user": user_slack_id},
                headers={"Authorization": f"Bearer {bot_token}"},
            )
            user_data = user_resp.json()
            if user_data.get("ok"):
                profile = user_data.get("user", {}).get("profile", {})
                user_info = {
                    "display_name": profile.get("real_name") or profile.get("display_name", ""),
                    "email": profile.get("email", ""),
                    "avatar_url": profile.get("image_192", ""),
                }

    async with async_session_factory() as session:
        # Upsert workspace
        workspace = (
            await session.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
        ).scalar_one_or_none()

        if workspace is None:
            workspace = Workspace(
                id=uuid.uuid4(),
                slack_team_id=team_id,
                team_name=team_name,
                bot_access_token=bot_token,
                user_access_token=user_token,
            )
            session.add(workspace)
            await session.flush()
        else:
            workspace.team_name = team_name
            workspace.bot_access_token = bot_token
            if user_token:
                workspace.user_access_token = user_token

        # Upsert user
        user = (
            await session.execute(
                select(User).where(
                    User.workspace_id == workspace.id,
                    User.slack_user_id == user_slack_id,
                )
            )
        ).scalar_one_or_none()

        if user is None:
            user = User(
                id=uuid.uuid4(),
                workspace_id=workspace.id,
                slack_user_id=user_slack_id,
                display_name=user_info.get("display_name", ""),
                email=user_info.get("email", ""),
                avatar_url=user_info.get("avatar_url", ""),
                is_admin=True,
            )
            session.add(user)
            await session.flush()
        else:
            if user_info.get("display_name"):
                user.display_name = user_info["display_name"]
            if user_info.get("email"):
                user.email = user_info["email"]
            if user_info.get("avatar_url"):
                user.avatar_url = user_info["avatar_url"]

        await session.commit()

        # Generate JWT
        token = jwt.encode(
            {
                "sub": str(user.id),
                "workspace_id": str(workspace.id),
                "slack_user_id": user.slack_user_id,
                "is_admin": user.is_admin,
                "exp": datetime.now(timezone.utc) + timedelta(days=7),
            },
            settings.jwt_secret,
            algorithm="HS256",
        )

    response = _session_response(token)
    response.delete_cookie("oauth_state", secure=settings.api_url.startswith("https://"),
                           httponly=True, samesite="lax")
    log.info("oauth_complete", team_id=team_id, user_id=user_slack_id)
    return response


def _session_response(token: str) -> RedirectResponse:
    # Set the cookie on the API origin that serves the callback. No JWT in a URL.
    response = RedirectResponse(url=f"{settings.app_url.rstrip('/')}/dashboard")
    response.set_cookie(
        key="session", value=token, httponly=True,
        secure=settings.api_url.startswith("https://"),
        samesite="lax", max_age=7 * 24 * 3600,
    )
    return response


@router.get("/dev-login")
async def dev_login():
    if urlparse(settings.app_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")

    async with async_session_factory() as session:
        workspace = (
            await session.execute(
                select(Workspace).where(Workspace.slack_team_id == "T_DEMO")
            )
        ).scalar_one_or_none()

        if workspace is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Demo workspace not found. Run seed_demo.py first.")

        user = (
            await session.execute(
                select(User).where(User.workspace_id == workspace.id)
            )
        ).scalar_one_or_none()

        if user is None:
            user = User(
                id=uuid.uuid4(),
                workspace_id=workspace.id,
                slack_user_id="U_DEMO",
                display_name="Demo User",
                email="demo@localhost",
                is_admin=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        token = jwt.encode(
            {
                "sub": str(user.id),
                "workspace_id": str(workspace.id),
                "slack_user_id": user.slack_user_id,
                "is_admin": user.is_admin,
                "exp": datetime.now(timezone.utc) + timedelta(days=7),
            },
            settings.jwt_secret,
            algorithm="HS256",
        )

    response = _session_response(token)

    log.info("dev_login", workspace_id=str(workspace.id), user_id=str(user.id))
    return response
