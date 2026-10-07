
import json
import re
import math

import structlog
from anthropic import AsyncAnthropic

from app.ai.prompts import DECISION_DETECTION_SYSTEM_PROMPT
from app.config import settings
from app.ai import gemini

log = structlog.get_logger()

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

NO_DECISION = {"is_decision": False, "confidence": 0.0, "reasoning": ""}


def _format_conversation(messages: list[dict]) -> str:
    lines = []
    for msg in messages:
        name = msg.get("user_name") or msg.get("user_slack_id") or "unknown"
        ts = msg.get("timestamp") or msg.get("message_ts") or ""
        text = msg.get("text", "")
        lines.append(f"[{ts}] {name}: {text}")
    return "\n".join(lines)


async def detect_decision(messages: list[dict], system_prompt: str | None = None) -> dict:
    if not messages:
        return {**NO_DECISION, "reasoning": "No messages provided"}

    conversation = _format_conversation(messages)

    try:
        if gemini.enabled():
            raw = await gemini.generate(system_prompt or DECISION_DETECTION_SYSTEM_PROMPT, conversation)
        else:
            response = await _client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=512,
                system=system_prompt or DECISION_DETECTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": conversation}],
            )
            raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", raw, re.DOTALL)
        if fence:
            raw = fence.group(1).strip()
        result = json.loads(raw)
        flag = result.get("is_decision")
        confidence = result.get("confidence")
        if (
            type(flag) is not bool
            or type(confidence) not in (int, float)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("Invalid decision flag or confidence")
        return {
            "is_decision": flag,
            "confidence": float(confidence),
            "reasoning": str(result.get("reasoning", "")),
        }
    except json.JSONDecodeError:
        log.warning("detector_json_parse_error", raw=raw[:200])
        return {**NO_DECISION, "reasoning": f"Failed to parse response: {raw[:100]}"}
    except Exception as exc:
        log.error("detector_error", error=str(exc))
        return {**NO_DECISION, "reasoning": f"Error: {exc}"}
