import structlog
from anthropic import AsyncAnthropic

from app.ai.prompts import ANSWER_SYNTHESIS_SYSTEM_PROMPT
from app.config import settings

log = structlog.get_logger()

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)


def _format_context(decisions: list[dict]) -> str:
    if not decisions:
        return "No relevant decisions found."

    blocks = []
    for i, d in enumerate(decisions, 1):
        lines = [f"Decision #{i}: {d.get('title', 'Untitled')}"]
        if d.get("summary"):
            lines.append(f"  Summary: {d['summary']}")
        if d.get("rationale"):
            lines.append(f"  Rationale: {d['rationale']}")
        if d.get("owner_name"):
            lines.append(f"  Owner: {d['owner_name']}")
        if d.get("decision_made_at"):
            lines.append(f"  Date: {d['decision_made_at']}")
        if d.get("source_url"):
            lines.append(f"  Source: {d['source_url']}")

        artifacts = []
        for ticket in d.get("referenced_tickets") or []:
            artifacts.append(ticket)
        for pr in d.get("referenced_prs") or []:
            artifacts.append(f"PR {pr}")
        for url in d.get("referenced_urls") or []:
            artifacts.append(url)
        if artifacts:
            lines.append(f"  Linked: {', '.join(artifacts)}")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


async def synthesize_answer(query: str, decisions: list[dict]) -> str:
    context = _format_context(decisions)
    user_message = f"Context — retrieved decisions:\n{context}\n\nQuestion: {query}"

    try:
        response = await _client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            system=ANSWER_SYNTHESIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        log.error("synthesizer_error", error=str(exc))
        return "Sorry, I encountered an error while searching decisions. Please try again."
