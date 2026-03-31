"""GET /metrics — Prometheus metrics endpoint."""
from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.metrics import REGISTRY

router = APIRouter()


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
