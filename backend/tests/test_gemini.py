from unittest.mock import AsyncMock, patch
import httpx
import pytest
from app.ai import gemini, detector, extractor, synthesizer
from app.config import settings

@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, 'gemini_api_key', 'test-key')

@pytest.mark.asyncio
async def test_request(configured):
    with patch('app.ai.gemini.httpx.AsyncClient') as client:
        post = client.return_value.__aenter__.return_value.post
        post.return_value = httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'hidden', 'thought': True}, {'text': 'answer'}]}}]})
        assert await gemini.generate('instructions', 'question') == 'answer'
        assert post.call_args.kwargs['headers'] == {'x-goog-api-key': 'test-key'}
        assert post.call_args.kwargs['json']['contents'][0]['parts'][0]['text'] == 'question'

@pytest.mark.asyncio
@pytest.mark.parametrize('status,payload', [(401, {}), (429, {}), (200, {}), (200, {'candidates': [{'finishReason': 'MAX_TOKENS'}]})])
async def test_errors(configured, status, payload):
    with patch('app.ai.gemini.httpx.AsyncClient') as client:
        client.return_value.__aenter__.return_value.post.return_value = httpx.Response(status, json=payload)
        with pytest.raises(RuntimeError):
            await gemini.generate('system', 'question')

@pytest.mark.asyncio
async def test_all_paths(configured):
    with patch('app.ai.gemini.generate', new_callable=AsyncMock) as generate:
        generate.return_value = '{"is_decision":true,"confidence":0.95}'
        assert (await detector.detect_decision([{'text': 'We chose Postgres'}]))['is_decision']
        generate.return_value = '{"title":"Use Postgres","category":"architecture"}'
        assert (await extractor.extract_decision([{'text': 'We chose Postgres'}]))['title'] == 'Use Postgres'
        generate.return_value = 'The team chose Postgres.'
        assert await synthesizer.synthesize_answer('Database?', [{'title': 'Use Postgres'}]) == generate.return_value
        assert generate.await_count == 3

def test_unconfigured(monkeypatch):
    for key in ['', ' ', 'your-key-here']:
        monkeypatch.setattr(settings, 'gemini_api_key', key)
        assert not gemini.enabled()

@pytest.mark.asyncio
async def test_temporary_failure_retried(configured):
    with patch('app.ai.gemini.httpx.AsyncClient') as client, patch('app.ai.gemini.asyncio.sleep', new_callable=AsyncMock):
        post = client.return_value.__aenter__.return_value.post
        post.side_effect = [httpx.Response(503), httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'recovered'}]}}]})]
        assert await gemini.generate('system', 'question') == 'recovered'
        assert post.await_count == 2
