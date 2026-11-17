from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import current_user_id
from app.services.prices import CoinGecko

router = APIRouter(dependencies=[Depends(current_user_id)])

_coingecko = CoinGecko()


def coingecko() -> CoinGecko:
    """The process-wide CoinGecko client; tests override this dependency."""
    return _coingecko


@router.get("/api/v1/assets")
def search_assets(
    client: Annotated[CoinGecko, Depends(coingecko)], query: str = ""
) -> list[dict[str, str]]:
    return client.search_assets(query)
