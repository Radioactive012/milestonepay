from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.contracts import router as contracts_router
from app.config import get_settings
from app.db import init_db
from app.milestones import InvalidTransition
from app.paypal.webhooks import router as webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="MilestonePay", lifespan=lifespan)
app.include_router(contracts_router)
app.include_router(webhook_router)


@app.exception_handler(InvalidTransition)
def invalid_transition(request: Request, error: InvalidTransition):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.get("/health")
def health():
    return {"status": "ok", "paypal_environment": get_settings().paypal_environment}
