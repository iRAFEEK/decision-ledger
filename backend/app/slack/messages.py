from app.db.models import Decision


def build_confirmation_blocks(decision: Decision) -> list[dict]:
    tags_text = ", ".join(decision.tags) if decision.tags else "none"
    confidence_pct = f"{decision.confidence * 100:.0f}%" if decision.confidence else "N/A"

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "\U0001f4cb Decision Detected"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{decision.title}*\n{decision.summary or ''}",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*Owner:* {decision.owner_name or 'Unknown'} | "
                        f"*Channel:* #{decision.source_channel_name or 'unknown'} | "
                        f"*Tags:* {tags_text} | "
                        f"*Confidence:* {confidence_pct}"
                    ),
                }
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Confirm"},
                    "style": "primary",
                    "action_id": "confirm_decision",
                    "value": str(decision.id),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Edit"},
                    "action_id": "edit_decision",
                    "value": str(decision.id),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Ignore"},
                    "style": "danger",
                    "action_id": "ignore_decision",
                    "value": str(decision.id),
                },
            ],
        },
    ]


def build_confirmed_blocks(decision: Decision) -> list[dict]:
    tags_text = ", ".join(decision.tags) if decision.tags else "none"

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "\u2705 Decision Confirmed"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{decision.title}*\n{decision.summary or ''}",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*Owner:* {decision.owner_name or 'Unknown'} | "
                        f"*Tags:* {tags_text} | "
                        f"*Confirmed by:* <@{decision.confirmed_by}>"
                    ),
                }
            ],
        },
    ]


def build_ignored_blocks(decision: Decision) -> list[dict]:
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "\u274c Decision Ignored"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"~{decision.title}~",
            },
        },
    ]


def build_search_result_blocks(
    answer: str, decisions: list[dict]
) -> list[dict]:
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": answer},
        },
    ]

    if decisions:
        blocks.append({"type": "divider"})
        for d in decisions[:5]:
            tags = d.get("tags") or []
            tags_text = ", ".join(tags) if tags else ""
            title = d.get("title", "Untitled")
            summary = d.get("summary") or ""
            line = f"*{title}*"
            if summary:
                line += f"\n{summary[:200]}"
            if tags_text:
                line += f"\n_Tags: {tags_text}_"
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": line},
                }
            )

    return blocks
