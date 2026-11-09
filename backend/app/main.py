from fastapi import FastAPI

from app.config import get_settings
from app.paypal.webhooks import router as webhook_router

app = FastAPI(title="MilestonePay")
app.include_router(webhook_router)


@app.get("/health")
def health():
    return {"status": "ok", "paypal_environment": get_settings().paypal_environment}
