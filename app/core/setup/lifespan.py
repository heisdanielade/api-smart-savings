# app/core/setup/lifespan.py

from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from app.core.config import settings



# =======================================
# LIFESPAN EVENTS
# =======================================
@asynccontextmanager
async def run_lifespan(app: FastAPI):
    """
    FastAPI lifespan context:
    - Startup: initialize test accounts (dev), soft-delete simulation, set timezone, start scheduler
    - Shutdown: stop scheduler
    """
    from app.infra.database.init_db import init_test_accounts
    from app.core.middleware.logging import cleanup_old_logs
    from app.core.tasks.cron_jobs import anonymize_soft_deleted_users
    from app.infra.database.session import set_utc_timezone
    from app.core.setup.redis import redis_client

    print(f"\n[STARTUP INFO] (i) Environment: {settings.APP_ENV}\n", flush=True)

    app.state.redis = redis_client

    if settings.APP_ENV == "development":
        # 1. Initialize test accounts if missing
        await init_test_accounts()
        # 2. Soft-delete test users 14 days ago for testing anonymization
        # await soft_delete_test_users(grace_days=14)
        # 3. Run anonymization immediately to verify
        # await anonymize_soft_deleted_users()

    # --- General startup tasks ---
    await cleanup_old_logs()
    await set_utc_timezone()  # Ensure DB session uses UTC timezone

    # --- Scheduler for production / recurring jobs ---
    scheduler = AsyncIOScheduler()
    async def run_anonymize_job():
        await anonymize_soft_deleted_users()
    scheduler.add_job(
        run_anonymize_job,
        trigger="interval",
        hours=settings.HARD_DELETE_CRON_INTERVAL_HOURS,
        id="anonymize_soft_deleted_users",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.start()
    print(
        f"[STARTUP INFO] (i) User anonymization cron job scheduled every "
        f"{settings.HARD_DELETE_CRON_INTERVAL_HOURS} hour(s)\n", flush=True
    )

    # --- Yield control to app ---
    yield

    # --- Shutdown tasks ---
    scheduler.shutdown()
    await app.state.redis.close()
    print("[SHUTDOWN INFO] Scheduler shut down\n", flush=True)
