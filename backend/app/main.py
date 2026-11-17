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

app = FastAPI(title="Findipend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(portfolios_router)
app.include_router(buys_router)
app.include_router(sells_router)
app.include_router(assets.router)
app.include_router(analytics_router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/me")
def me(user_id: Annotated[str, Depends(current_user_id)]) -> dict[str, str]:
    return {"user_id": user_id}
