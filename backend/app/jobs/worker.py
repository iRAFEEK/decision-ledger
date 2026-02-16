from arq import cron
from arq.connections import RedisSettings

from app.config import settings
from app.jobs.tasks import (
    backfill_history,
    enrich_decision,
    expire_confirmations,
    generate_embedding_task,
    process_message,
    process_query,
)


class WorkerSettings:
    functions = [
        process_message,
        process_query,
        enrich_decision,
        generate_embedding_task,
        backfill_history,
    ]
    cron_jobs = [
        cron(expire_confirmations, hour=None, minute=0),  # every hour
    ]
    max_jobs = 10
    job_timeout = 60
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
