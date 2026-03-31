"""GET /health — check Postgres and Redis connectivity."""
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


async def _check_redis() -> bool:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(REDIS_URL, socket_connect_timeout=2)
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False


@router.get("/health")
async def health_check() -> JSONResponse:
    from app.database import check_db_health

    db_ok = await check_db_health()
    redis_ok = await _check_redis()

    status = "ok" if (db_ok and redis_ok) else "degraded"
    code = 200 if status == "ok" else 503
    return JSONResponse(
        status_code=code,
        content={
            "status": status,
            "postgres": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    )
