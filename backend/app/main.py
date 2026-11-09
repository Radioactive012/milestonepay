from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.contracts import router as contracts_router
from app.api.portal import router as portal_router
from app.config import get_settings
from app.db import init_db
from app.milestones import InvalidTransition
from app.paypal.client import PayPalError
from app.paypal.webhooks import router as webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="MilestonePay", lifespan=lifespan)
app.include_router(contracts_router)
app.include_router(portal_router)
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
