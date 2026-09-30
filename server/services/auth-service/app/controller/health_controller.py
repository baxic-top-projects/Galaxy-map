from fastapi import APIRouter

from app.service.database_init_service import database_status

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    db = database_status()
    return {
        "status": "ok" if db["status"] in {"pending", "running", "ready"} else "degraded",
        "service": "auth-service",
        "database": db,
    }
