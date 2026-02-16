import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.config import settings
from app.slack import router
from app.slack.verify import verify_slack_signature

log = structlog.get_logger()

USAGE_TEXT = (
    "*Usage:* `/decision <query>`\n"
    "Search your team's decision history.\n\n"
    "*Examples:*\n"
    "\u2022 `/decision why did we choose Postgres?`\n"
    "\u2022 `/decision authentication approach`\n"
    "\u2022 `/decision pricing model changes`"
)


@router.post("/commands")
async def slack_commands(request: Request) -> Response:
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if settings.slack_signing_secret and not verify_slack_signature(
        settings.slack_signing_secret, timestamp, body, signature
    ):
        return Response(status_code=401)

    form = await request.form()
    command = form.get("command", "")
    text = (form.get("text") or "").strip()
    team_id = form.get("team_id", "")
    user_id = form.get("user_id", "")
    channel_id = form.get("channel_id", "")
    response_url = form.get("response_url", "")

    if command == "/decision" and not text:
        return JSONResponse({"response_type": "ephemeral", "text": USAGE_TEXT})

    log.info(
        "slash_command",
        command=command,
        team_id=team_id,
        user_id=user_id,
        channel_id=channel_id,
        query=text,
    )

    # Enqueue search job via arq
    # await arq_pool.enqueue_job(
    #     "process_query", team_id, user_id, channel_id, text, response_url
    # )

    return JSONResponse(
        {"response_type": "ephemeral", "text": "\U0001f50d Searching decisions..."}
    )
