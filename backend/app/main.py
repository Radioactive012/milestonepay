import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from app import clock
from app.api.contracts import router as contracts_router
from app.api.demo import router as demo_router
from app.api.portal import router as portal_router
from app.config import get_settings
from app.db import engine, init_db
from app.jobs import run_daily_jobs
from app.milestones import InvalidTransition
from app.paypal.client import PayPalError, get_paypal_client
from app.paypal.webhooks import router as webhook_router

log = logging.getLogger("milestonepay.jobs")


def run_jobs_once() -> dict:
    with Session(engine) as session:
        return run_daily_jobs(session, get_paypal_client(), clock.today(session))


async def run_jobs_forever(interval_minutes: int) -> None:
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            summary = await run_in_threadpool(run_jobs_once)
            log.info("Daily jobs: %s", summary)
        except Exception:
            # keep the loop alive; the next run tries again
            log.exception("Daily jobs failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    interval = get_settings().jobs_interval_minutes
    task = asyncio.create_task(run_jobs_forever(interval)) if interval > 0 else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="MilestonePay", lifespan=lifespan)
app.include_router(contracts_router)
app.include_router(portal_router)
app.include_router(demo_router)
app.include_router(webhook_router)


@app.exception_handler(InvalidTransition)
def invalid_transition(request: Request, error: InvalidTransition):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(PayPalError)
def paypal_error(request: Request, error: PayPalError):
    # PayPal retries webhooks that get a non-2xx answer, so a 502 here is safe
    return JSONResponse(status_code=502, content={"detail": str(error)[:300]})


@app.get("/health")
def health():
    return {"status": "ok", "paypal_environment": get_settings().paypal_environment}
