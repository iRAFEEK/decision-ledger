import json
import re

import structlog
from anthropic import AsyncAnthropic

from app.ai.prompts import DECISION_EXTRACTION_SYSTEM_PROMPT
from app.config import settings

log = structlog.get_logger()

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

EMPTY_EXTRACTION = {
    "title": "Untitled Decision",
    "summary": None,
    "rationale": None,
    "owner_slack_id": None,
    "owner_name": None,
    "tags": [],
    "category": None,
    "impact_area": [],
    "referenced_tickets": [],
    "referenced_prs": [],
    "referenced_urls": [],
}


def _format_conversation(messages: list[dict]) -> str:
    lines = []
    for msg in messages:
        name = msg.get("user_name") or msg.get("user_slack_id") or "unknown"
        ts = msg.get("timestamp") or msg.get("message_ts") or ""
        text = msg.get("text", "")
        lines.append(f"[{ts}] {name}: {text}")
    return "\n".join(lines)


async def extract_decision(messages: list[dict]) -> dict:
    if not messages:
        return {**EMPTY_EXTRACTION}

    conversation = _format_conversation(messages)

    try:
        response = await _client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            system=DECISION_EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": conversation}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", raw, re.DOTALL)
        if fence:
            raw = fence.group(1).strip()
        result = json.loads(raw)

        valid_categories = {
            "architecture", "schema", "api", "infrastructure", "deprecation",
            "dependency", "naming", "process", "security", "performance", "tooling",
        }
        category = result.get("category")
        if category not in valid_categories:
            category = None

        return {
            "title": str(result.get("title", "Untitled Decision"))[:100],
            "summary": result.get("summary"),
            "rationale": result.get("rationale"),
            "owner_slack_id": result.get("owner_slack_id"),
            "owner_name": result.get("owner_name"),
            "tags": result.get("tags") or [],
            "category": category,
            "impact_area": result.get("impact_area") or [],
            "referenced_tickets": result.get("referenced_tickets") or [],
            "referenced_prs": result.get("referenced_prs") or [],
            "referenced_urls": result.get("referenced_urls") or [],
        }
    except json.JSONDecodeError:
        log.warning("extractor_json_parse_error", raw=raw[:200])
        return {**EMPTY_EXTRACTION}
    except Exception as exc:
        log.error("extractor_error", error=str(exc))
        return {**EMPTY_EXTRACTION}
