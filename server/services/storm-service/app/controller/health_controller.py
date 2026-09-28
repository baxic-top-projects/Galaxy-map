from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    from app.main import simulator
    from app.service.storm_broadcast_service import storm_broadcast

    return {
        "status": "ok",
        "service": "storm-service",
        "tick": simulator.tick if simulator else 0,
        "stormCount": len(simulator.storms) if simulator else 0,
        "wsClients": storm_broadcast.client_count,
    }
