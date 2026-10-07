import os
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.db.models import Base, Workspace
from app.db.session import get_db
from app.main import app


@pytest_asyncio.fixture
async def database(monkeypatch):
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.fail('--integration requires TEST_DATABASE_URL pointing to a disposable database')
    schema = 'ledger_test_' + uuid.uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    async with admin.begin() as connection:
        await connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        await connection.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_async_engine(url, poolclass=NullPool, connect_args={'server_settings': {'search_path': f'{schema},public'}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, checkfirst=False))
        async with factory() as session:
            ws = Workspace(slack_team_id='T_TEST', team_name='Test workspace', bot_access_token='test-only-token')
            other = Workspace(slack_team_id='T_OTHER', team_name='Other workspace')
            session.add_all([ws, other])
            await session.commit()
        for module in ('app.main', 'app.jobs.tasks', 'app.slack.events', 'app.slack.interactive', 'app.auth.oauth'):
            monkeypatch.setattr(f'{module}.async_session_factory', factory)
        async def db_override():
            async with factory() as session:
                yield session
        app.dependency_overrides[get_db] = db_override
        yield SimpleNamespace(factory=factory, workspace=ws, other=other, engine=engine)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        await admin.dispose()
