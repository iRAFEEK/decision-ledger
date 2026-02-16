import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.detector import detect_decision


@pytest.mark.asyncio
async def test_detect_decision_returns_expected_format():
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "is_decision": True,
                    "confidence": 0.92,
                    "reasoning": "Team agreed to use PostgreSQL",
                }
            )
        )
    ]

    with patch("app.ai.detector._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await detect_decision(
            [{"user_name": "alice", "text": "Let's go with PostgreSQL", "timestamp": "1234"}]
        )

    assert isinstance(result, dict)
    assert "is_decision" in result
    assert "confidence" in result
    assert "reasoning" in result
    assert result["is_decision"] is True
    assert result["confidence"] == 0.92
    assert result["reasoning"] == "Team agreed to use PostgreSQL"


@pytest.mark.asyncio
async def test_detect_decision_with_mock_response():
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "is_decision": False,
                    "confidence": 0.15,
                    "reasoning": "Just a question, not a decision",
                }
            )
        )
    ]

    with patch("app.ai.detector._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await detect_decision(
            [{"user_name": "bob", "text": "Should we use Redis?", "timestamp": "5678"}]
        )

    assert result["is_decision"] is False
    assert result["confidence"] == 0.15


@pytest.mark.asyncio
async def test_detect_decision_empty_messages():
    result = await detect_decision([])
    assert result["is_decision"] is False
    assert result["confidence"] == 0.0
    assert "No messages" in result["reasoning"]


@pytest.mark.asyncio
async def test_detect_decision_malformed_json():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="this is not valid json {{{")]

    with patch("app.ai.detector._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await detect_decision(
            [{"user_name": "carol", "text": "We decided on REST", "timestamp": "9999"}]
        )

    assert result["is_decision"] is False
    assert result["confidence"] == 0.0
    assert "Failed to parse" in result["reasoning"]
