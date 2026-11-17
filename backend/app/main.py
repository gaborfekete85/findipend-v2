from typing import Annotated

from fastapi import Depends, FastAPI

from app.api import assets
from app.core.auth import current_user_id

app = FastAPI(title="Findipend")
app.include_router(assets.router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/me")
def me(user_id: Annotated[str, Depends(current_user_id)]) -> dict[str, str]:
    return {"user_id": user_id}
