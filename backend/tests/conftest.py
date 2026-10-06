import pytest


def pytest_addoption(parser):
    parser.addoption('--integration', action='store_true', help='Run tests against disposable PostgreSQL/Redis services')


def pytest_collection_modifyitems(config, items):
    if config.getoption('--integration'):
        return
    skip = pytest.mark.skip(reason='Use --integration with TEST_DATABASE_URL and TEST_REDIS_URL')
    for item in items:
        if 'integration' in item.keywords:
            item.add_marker(skip)
