"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.logging_config import configure_logging
from app.routers import feedback, health, ignore, metrics_router, webhook

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import create_tables

    try:
        await create_tables()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"DB not available at startup: {exc}")
    yield


app = FastAPI(title="AI Code Review Bot", version="1.0.0", lifespan=lifespan)

app.include_router(webhook.router)
app.include_router(feedback.router)
app.include_router(health.router)
app.include_router(metrics_router.router)
app.include_router(ignore.router)
