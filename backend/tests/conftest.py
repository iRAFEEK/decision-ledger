import pytest


@pytest.fixture(autouse=True)
def isolate_ai_credentials(monkeypatch):
    # Never let a developer's .env turn mocked tests into live AI requests.
    from app.config import settings
    monkeypatch.setattr(settings, 'gemini_api_key', '')
    monkeypatch.setattr(settings, 'anthropic_api_key', '')
    monkeypatch.setattr(settings, 'voyage_api_key', '')


def pytest_addoption(parser):
    parser.addoption('--integration', action='store_true', help='Run tests against disposable PostgreSQL/Redis services')


def pytest_collection_modifyitems(config, items):
    if config.getoption('--integration'):
        return
    skip = pytest.mark.skip(reason='Use --integration with TEST_DATABASE_URL and TEST_REDIS_URL')
    for item in items:
        if 'integration' in item.keywords:
            item.add_marker(skip)
