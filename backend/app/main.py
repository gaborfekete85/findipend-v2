from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import assets
from app.api.analytics import router as analytics_router
from app.api.buys import router as buys_router
from app.api.portfolios import router as portfolios_router
from app.api.sells import router as sells_router
from app.core.auth import current_user_id
from app.core.config import cors_allowed_origins


def health() -> dict[str, str]:
    return {"status": "ok"}


def me(user_id: Annotated[str, Depends(current_user_id)]) -> dict[str, str]:
    return {"user_id": user_id}


def create_app() -> FastAPI:
    """Build the API with CORS origins read from CORS_ALLOWED_ORIGINS at call time."""
    application = FastAPI(title="Findipend")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allowed_origins(),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(portfolios_router)
    application.include_router(buys_router)
    application.include_router(sells_router)
    application.include_router(assets.router)
    application.include_router(analytics_router)
    application.add_api_route("/api/v1/health", health, methods=["GET"])
    application.add_api_route("/api/v1/me", me, methods=["GET"])
    return application


app = create_app()
