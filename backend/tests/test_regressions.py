import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.main import app
from app.auth.middleware import get_current_user
from app.auth.oauth import _session_response
from app.config import settings
from app.db.session import get_db
from app.api.schemas import SearchRequest
from app.ai.detector import detect_decision
from app.ai.embeddings import generate_query_embedding
from app.ai.synthesizer import synthesize_answer
from app.slack.verify import verify_slack_signature


@pytest.mark.asyncio
async def test_search_forwards_options_and_total():
    app.dependency_overrides[get_current_user] = lambda: {'workspace_id': 'test', 'slack_user_id': 'U_TEST'}
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with patch('app.api.search.handle_decision_query', new_callable=AsyncMock) as query:
            query.return_value = {'answer': 'test', 'decisions': [], 'response_time_ms': 1, 'total_count': 23}
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                r = await client.post('/api/search', json={'query': ' database ', 'filters': {'categories': ['schema']}, 'limit': 1, 'offset': 10})
            assert r.status_code == 200
            assert r.json()['total_count'] == 23
            assert query.call_args.kwargs['filters'] == {'categories': ['schema']}
            assert query.call_args.kwargs['limit'] == 1
            assert query.call_args.kwargs['offset'] == 10
            assert query.call_args.args[2] == 'database'
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('body', [
    {'query': '   '}, {'query': 'db', 'limit': 0}, {'query': 'db', 'offset': -1},
    {'query': 'db', 'filters': {'date_from': 'nonsense'}},
    {'query': 'db', 'filters': {'date_from': '2026-02-01', 'date_to': '2026-01-01'}},
    {'query': 'db', 'filters': {'status': 'deleted'}},
])
def test_search_rejects_invalid_input(body):
    with pytest.raises(ValidationError):
        SearchRequest.model_validate(body)


def test_date_only_filter_uses_utc():
    req = SearchRequest(query='db', filters={'date_from': '2026-01-01'})
    assert req.filters.date_from == datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize('flag,confidence', [('false', .95), (True, '0.9'), (True, 1.5), (True, -1), (True, True), (True, float('nan'))])
async def test_detector_rejects_invalid_types_and_confidence(flag, confidence):
    response = MagicMock(content=[MagicMock(text=json.dumps({'is_decision': flag, 'confidence': confidence}))])
    with patch('app.ai.detector._client') as client:
        client.messages.create = AsyncMock(return_value=response)
        result = await detect_decision([{'text': 'Test input'}])
    assert result['is_decision'] is False
    assert result['confidence'] == 0


@pytest.mark.asyncio
async def test_missing_voyage_key_makes_no_network_request(monkeypatch):
    monkeypatch.setattr(settings, 'voyage_api_key', '')
    with patch('app.ai.embeddings.httpx.AsyncClient') as client:
        assert await generate_query_embedding('postgres') == []
        client.assert_not_called()


@pytest.mark.asyncio
async def test_synthesis_failure_preserves_readable_fallback(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-only-key")
    with patch('app.ai.synthesizer._client') as client:
        client.messages.create = AsyncMock(side_effect=RuntimeError('offline'))
        answer = await synthesize_answer('db', [{'title': 'Use PostgreSQL'}])
    assert 'matching decisions are listed below' in answer


@pytest.mark.asyncio
async def test_empty_search_skips_model():
    with patch('app.ai.synthesizer._client') as client:
        assert 'recorded decisions' in await synthesize_answer('db', [])
        client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_oauth_redirect_has_state_and_validates_callback(monkeypatch):
    monkeypatch.setattr(settings, 'api_url', 'https://api.ledger.example')
    monkeypatch.setattr(settings, 'app_url', 'https://ledger.example')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://api.ledger.example') as client:
        r = await client.get('/auth/slack')
        params = parse_qs(urlparse(r.headers['location']).query)
        assert params['redirect_uri'] == ['https://api.ledger.example/auth/callback']
        assert params['state'][0] == client.cookies['oauth_state']
        with patch('app.auth.oauth.httpx.AsyncClient') as external:
            r = await client.get('/auth/callback?code=fake&state=wrong')
            external.assert_not_called()
        assert r.headers['location'] == 'https://ledger.example?error=invalid_state'


@pytest.mark.parametrize('api_url,secure', [('http://localhost:8000', False), ('https://api.ledger.example', True)])
def test_session_cookie_and_redirect_follow_configuration(monkeypatch, api_url, secure):
    monkeypatch.setattr(settings, 'api_url', api_url)
    monkeypatch.setattr(settings, 'app_url', 'https://ledger.example')
    r = _session_response('test-session')
    assert r.headers['location'] == 'https://ledger.example/dashboard'
    cookie = r.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=lax' in cookie
    assert ('secure' in cookie) == secure
    assert 'test-session' not in r.headers['location']


def test_malformed_signature_timestamp_is_rejected():
    assert not verify_slack_signature('test', '', b'{}', 'invalid')
