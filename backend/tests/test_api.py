import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_200():
    # The real connectivity check is covered by the integration suite.
    with patch("app.main.async_session_factory") as factory:
        session = AsyncMock()
        factory.return_value.__aenter__.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_database_failure_is_not_success():
    with patch("app.main.async_session_factory") as factory:
        factory.return_value.__aenter__.return_value.execute = AsyncMock(side_effect=RuntimeError("Database offline"))
        async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 500


@pytest.mark.asyncio
async def test_decisions_returns_401_without_auth():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/decisions")
    assert response.status_code == 401
