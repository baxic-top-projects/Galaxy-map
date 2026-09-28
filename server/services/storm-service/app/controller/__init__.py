from app.controller.health_controller import router as health_router
from app.controller.storm_controller import router as storm_router

__all__ = ["health_router", "storm_router"]
