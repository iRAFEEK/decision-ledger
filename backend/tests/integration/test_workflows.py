import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import pytest
from arq.connections import RedisSettings, create_pool
from arq.worker import Worker
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func

from app.config import settings
from app.main import app, lifespan
from app.auth.middleware import get_current_user
from app.db.models import Decision, MonitoredChannel, RawMessage, PendingConfirmation, User
from app.search.engine import hybrid_search
from app.jobs import tasks

pytestmark = pytest.mark.integration
VECTOR = [1.0] + [0.0] * 1023


def sign(body):
    timestamp = str(int(time.time()))
    signature = 'v0=' + hmac.new(b'test-signing-secret', f'v0:{timestamp}:'.encode() + body, hashlib.sha256).hexdigest()
    return {'X-Slack-Request-Timestamp': timestamp, 'X-Slack-Signature': signature}


def edit_payload(decision_id, title='Use Redis for cache', team='T_TEST', user='U_OWNER'):
    return {'type': 'view_submission', 'team': {'id': team}, 'user': {'id': user}, 'view': {
        'callback_id': 'edit_decision_modal', 'private_metadata': str(decision_id),
        'state': {'values': {f'{key}_block': {f'{key}_input': {'value': value}} for key, value in {
            'title': title, 'summary': 'Cache responses', 'rationale': 'Lower latency', 'tags': 'Cache, Redis, cache',
        }.items()}},
    }}


async def submit_edit(client, payload):
    body = urlencode({'payload': json.dumps(payload)}).encode()
    return await client.post('/slack/interactive', content=body, headers={**sign(body), 'Content-Type': 'application/x-www-form-urlencoded'})


async def add_decision(database, **kwargs):
    async with database.factory() as session:
        decision = Decision(workspace_id=database.workspace.id, title='Postgres database', status='active', owner_slack_id='U_OWNER', **kwargs)
        session.add(decision)
        await session.commit()
        return decision.id


async def test_real_health_and_queue_startup(database, monkeypatch):
    redis_url = os.environ.get('TEST_REDIS_URL')
    assert redis_url, '--integration requires TEST_REDIS_URL'
    monkeypatch.setattr(settings, 'redis_url', redis_url)
    async with lifespan(app):
        assert await app.state.arq_pool.ping()
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            r = await client.get('/health')
        assert r.json() == {'status': 'ok'}


async def test_filters_pagination_isolation_and_empty_page(database, monkeypatch):
    monkeypatch.setattr('app.search.engine.generate_query_embedding', AsyncMock(return_value=[]))
    async with database.factory() as session:
        for i in range(25):
            session.add(Decision(workspace_id=database.workspace.id, title=f'Postgres database {i}', status='active', owner_slack_id='U_OWNER', tags=['db'], category='schema', created_at=datetime(2026, 1, 10, tzinfo=timezone.utc)))
        session.add_all([
            Decision(workspace_id=database.workspace.id, title='Postgres pending', status='pending'),
            Decision(workspace_id=database.other.id, title='Postgres private', status='active'),
            Decision(workspace_id=database.workspace.id, title='Postgres deleted', status='deleted'),
        ])
        await session.commit()
        filters = {'owner_slack_id': 'U_OWNER', 'categories': ['schema'], 'tags': ['db'], 'date_from': datetime(2026,1,1,tzinfo=timezone.utc), 'date_to': datetime(2026,1,31,tzinfo=timezone.utc)}
        first = await hybrid_search(session, str(database.workspace.id), 'postgres', filters, 10, 0)
        second = await hybrid_search(session, str(database.workspace.id), 'postgres', filters, 10, 10)
        third = await hybrid_search(session, str(database.workspace.id), 'postgres', filters, 10, 20)
        empty = await hybrid_search(session, str(database.workspace.id), 'postgres', filters, 10, 99)
        again = await hybrid_search(session, str(database.workspace.id), 'postgres', filters, 10, 0)
        ids = [d['id'] for p in (first, second, third) for d in p.decisions]
        assert len(ids) == len(set(ids)) == 25
        assert first.decisions == again.decisions
        assert all(p.total_count == 25 for p in (first, second, third, empty))
        assert empty.decisions == []
        assert (await hybrid_search(session, str(database.workspace.id), 'absent-term')).total_count == 0
        pending = await hybrid_search(session, str(database.workspace.id), 'postgres', {'status': 'pending'})
        assert pending.total_count == 1 and pending.decisions[0]['title'] == 'Postgres pending'


async def test_vector_search_applies_filters_before_ranking(database, monkeypatch):
    monkeypatch.setattr('app.search.engine.generate_query_embedding', AsyncMock(return_value=VECTOR))
    async with database.factory() as session:
        for _ in range(25):
            session.add(Decision(workspace_id=database.workspace.id, title='Other category', status='active', category='process', embedding=VECTOR))
        target = Decision(workspace_id=database.workspace.id, title='Architecture choice', status='active', category='architecture', embedding=VECTOR)
        session.add(target)
        await session.commit()
        result = await hybrid_search(session, str(database.workspace.id), 'unrelated wording', {'categories':['architecture']})
        assert result.total_count == 1
        assert result.decisions[0]['id'] == str(target.id)


@pytest.mark.parametrize('team,user,title,error', [
    ('T_TEST','U_OWNER','Updated database',False),
    ('T_OTHER','U_OWNER','Updated database',True),
    ('T_TEST','U_STRANGER','Updated database',True),
    ('T_TEST','U_OWNER','   ',True),
])
async def test_edit_persistence_and_access(database, monkeypatch, team, user, title, error):
    monkeypatch.setattr(settings, 'slack_signing_secret', 'test-signing-secret')
    decision_id = await add_decision(database, embedding=VECTOR)
    pool = AsyncMock()
    app.state.arq_pool = pool
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        r = await submit_edit(client, edit_payload(decision_id, title, team, user))
    assert r.status_code == 200
    async with database.factory() as session:
        persisted = await session.get(Decision, decision_id)
        if error:
            assert r.json()['response_action'] == 'errors'
            assert persisted.title == 'Postgres database'
            pool.enqueue_job.assert_not_called()
        else:
            assert persisted.title == title
            assert persisted.tags == ['cache','redis']
            assert persisted.embedding is None
            pool.enqueue_job.assert_awaited_once_with('refresh_edited_decision', str(decision_id))


async def test_admin_can_edit_unowned_decision(database, monkeypatch):
    monkeypatch.setattr(settings, 'slack_signing_secret', 'test-signing-secret')
    decision_id = await add_decision(database)
    async with database.factory() as session:
        session.add(User(workspace_id=database.workspace.id, slack_user_id='U_ADMIN', is_admin=True))
        await session.commit()
    app.state.arq_pool = AsyncMock()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        r = await submit_edit(client, edit_payload(decision_id, user='U_ADMIN'))
    assert r.status_code == 200 and r.content == b''


async def test_edit_queue_failure_is_visible_and_saved(database, monkeypatch):
    monkeypatch.setattr(settings, 'slack_signing_secret', 'test-signing-secret')
    decision_id = await add_decision(database)
    app.state.arq_pool = AsyncMock()
    app.state.arq_pool.enqueue_job.side_effect = RuntimeError('Queue offline')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        r = await submit_edit(client, edit_payload(decision_id))
    assert 'saved' in r.json()['errors']['title_block']
    async with database.factory() as session:
        assert (await session.get(Decision, decision_id)).title == 'Use Redis for cache'


@pytest.mark.parametrize('flag,confidence', [(False,.99),(True,.3),(True,float('nan'))])
async def test_non_decisions_never_reach_extraction(database, monkeypatch, flag, confidence):
    async with database.factory() as session:
        session.add(MonitoredChannel(workspace_id=database.workspace.id, channel_id='C_TEST'))
        raw = RawMessage(workspace_id=database.workspace.id, channel_id='C_TEST', message_ts='123', text='Question')
        session.add(raw)
        await session.commit()
    monkeypatch.setattr(tasks.slack_client, 'conversations_replies', AsyncMock(return_value={'messages':[]}))
    monkeypatch.setattr(tasks, 'detect_decision', AsyncMock(return_value={'is_decision':flag,'confidence':confidence}))
    extract = AsyncMock()
    monkeypatch.setattr(tasks, 'extract_decision', extract)
    await tasks.process_message({}, str(raw.id))
    extract.assert_not_called()
    async with database.factory() as session:
        assert (await session.get(RawMessage, raw.id)).processed


async def test_ingest_confirm_search_edit_and_ignore(database, monkeypatch):
    monkeypatch.setattr(settings, 'slack_signing_secret', 'test-signing-secret')
    monkeypatch.setattr(tasks.slack_client, 'conversations_replies', AsyncMock(return_value={'messages':[]}))
    monkeypatch.setattr(tasks.slack_client, 'post_message', AsyncMock(return_value={'ok':True,'ts':'456'}))
    update_message = AsyncMock(return_value={'ok': True})
    monkeypatch.setattr(tasks.slack_client, 'update_message', update_message)
    monkeypatch.setattr(tasks, 'detect_decision', AsyncMock(return_value={'is_decision':True,'confidence':.95}))
    monkeypatch.setattr(tasks, 'extract_decision', AsyncMock(return_value={'title':'Use Postgres','summary':'Durable storage','rationale':'Reliable','owner_slack_id':'U_OWNER','owner_name':'Owner','tags':['postgres'],'impact_area':['backend'],'category':'schema'}))
    monkeypatch.setattr(tasks, 'generate_embedding', AsyncMock(return_value=VECTOR))
    monkeypatch.setattr('app.search.engine.generate_query_embedding', AsyncMock(return_value=[]))
    monkeypatch.setattr('app.search.query_handler.synthesize_answer', AsyncMock(return_value='Recorded decision'))
    async with database.factory() as session:
        session.add(MonitoredChannel(workspace_id=database.workspace.id, channel_id='C_TEST'))
        await session.commit()
    redis_url = os.environ['TEST_REDIS_URL']
    pool = await create_pool(RedisSettings.from_dsn(redis_url))
    queue = 'ledger-test-' + uuid.uuid4().hex
    # Use a unique queue; never clear another application's Redis data.
    pool.default_queue_name = queue
    app.state.arq_pool = pool
    app.dependency_overrides[get_current_user] = lambda: {'workspace_id':str(database.workspace.id),'slack_user_id':'U_OWNER','user_id':str(uuid.uuid4())}
    async def drain():
        worker = Worker([tasks.process_message,tasks.enrich_decision,tasks.generate_embedding_task,tasks.refresh_edited_decision],redis_pool=pool,queue_name=queue,burst=True,handle_signals=False,poll_delay=.01)
        await worker.async_run()
        assert worker.jobs_failed == 0
        await worker.close()
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            body = json.dumps({'team_id':'T_TEST','event':{'type':'message','channel':'C_TEST','user':'U_OWNER','ts':'123','text':'We decided on Postgres'}}).encode()
            for _ in range(2):
                assert (await client.post('/slack/events',content=body,headers=sign(body))).status_code == 200
            await drain()
            async with database.factory() as session:
                assert (await session.scalar(select(func.count()).select_from(RawMessage))) == 1
                decision = (await session.execute(select(Decision))).scalar_one()
                assert decision.status == 'pending'
                decision_id = decision.id
            r = await client.post(f'/api/decisions/{decision_id}/confirm')
            assert r.status_code == 200
            await drain()
            r = await client.post('/api/search',json={'query':'postgres'})
            assert r.status_code == 200 and r.json()['total_count'] == 1
            async with database.factory() as session:
                assert (await session.get(Decision,decision_id)).embedding is not None
            assert (await submit_edit(client,edit_payload(decision_id))).status_code == 200
            await drain()
            r = await client.post('/api/search',json={'query':'redis'})
            assert r.json()['decisions'][0]['title'] == 'Use Redis for cache'
            assert (await client.post('/api/search',json={'query':'postgres'})).json()['total_count'] == 0
            update_message.assert_awaited()
            assert (await client.post(f'/api/decisions/{decision_id}/ignore')).status_code == 200
            assert (await client.post('/api/search',json={'query':'redis'})).json()['total_count'] == 0
    finally:
        await pool.aclose()

@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['slack', 'ai'])
async def test_backfill_failure_is_not_complete(database, monkeypatch, failure):
    from app.db.models import Workspace
    async with database.factory() as session:
        session.add(MonitoredChannel(workspace_id=database.workspace.id, channel_id='C_SCAN'))
        await session.commit()
    response = {'ok': False, 'error': 'not_in_channel'} if failure == 'slack' else {'ok': True, 'messages': [{'ts': '123', 'text': 'We chose Postgres', 'user': 'U_TEST'}]}
    monkeypatch.setattr(tasks.slack_client, 'conversations_history', AsyncMock(return_value=response))
    monkeypatch.setattr(tasks, 'detect_decision', AsyncMock(return_value={'is_decision': False, 'confidence': 0, 'reasoning': 'Error: Gemini unavailable'}))
    await tasks.backfill_history({}, str(database.workspace.id))
    async with database.factory() as session:
        workspace = await session.get(Workspace, database.workspace.id)
        assert workspace.backfill_status == 'failed'
        assert await session.scalar(select(func.count()).select_from(Decision)) == 0
