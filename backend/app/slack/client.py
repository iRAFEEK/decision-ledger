import asyncio

import httpx
import structlog

log = structlog.get_logger()

SLACK_API = "https://slack.com/api"


async def _request(
    method: str,
    token: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    max_retries: int = 3,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{SLACK_API}/{method}"
    for attempt in range(max_retries):
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=headers, json=json, params=params)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 1))
            log.warning("slack_rate_limited", method=method, retry_after=retry_after)
            await asyncio.sleep(retry_after)
            continue
        data = resp.json()
        if not data.get("ok"):
            log.error("slack_api_error", method=method, error=data.get("error"))
        return data
    return {"ok": False, "error": "max_retries_exceeded"}


async def post_message(
    token: str,
    channel: str,
    text: str | None = None,
    blocks: list[dict] | None = None,
) -> dict:
    payload: dict = {"channel": channel}
    if text is not None:
        payload["text"] = text
    if blocks is not None:
        payload["blocks"] = blocks
    return await _request("chat.postMessage", token, json=payload)


async def update_message(
    token: str,
    channel: str,
    ts: str,
    text: str | None = None,
    blocks: list[dict] | None = None,
) -> dict:
    payload: dict = {"channel": channel, "ts": ts}
    if text is not None:
        payload["text"] = text
    if blocks is not None:
        payload["blocks"] = blocks
    return await _request("chat.update", token, json=payload)


async def conversations_history(
    token: str,
    channel: str,
    oldest: str | None = None,
    limit: int = 200,
    cursor: str | None = None,
) -> dict:
    params: dict = {"channel": channel, "limit": limit}
    if oldest is not None:
        params["oldest"] = oldest
    if cursor is not None:
        params["cursor"] = cursor
    return await _request("conversations.history", token, params=params)


async def conversations_replies(
    token: str,
    channel: str,
    ts: str,
    limit: int = 50,
) -> dict:
    params: dict = {"channel": channel, "ts": ts, "limit": limit}
    return await _request("conversations.replies", token, params=params)


async def users_info(token: str, user_id: str) -> dict:
    return await _request("users.info", token, params={"user": user_id})


async def open_modal(token: str, trigger_id: str, view: dict) -> dict:
    return await _request(
        "views.open", token, json={"trigger_id": trigger_id, "view": view}
    )
