from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.assets import coingecko
from app.api.portfolios import Db, UserId, _owned
from app.models import Portfolio
from app.schemas.analytics import OverviewOut, PositionsOut, SummaryOut
from app.services.analytics import asset_pnl, totals
from app.services.prices import CoinGecko

router = APIRouter(prefix="/api/v1", tags=["analytics"])

Prices = Annotated[CoinGecko, Depends(coingecko)]


@router.get("/portfolios/{portfolio_id}/positions")
def list_positions(portfolio_id: int, user_id: UserId, db: Db, prices: Prices) -> PositionsOut:
    """Open positions (unsold quantity > 0) and closed ones (every lot fully sold)."""
    _owned(db, user_id, portfolio_id)
    rows = asset_pnl(db, [portfolio_id], prices)
    return PositionsOut(
        open=[row for row in rows if row.quantity > 0],
        closed=[row for row in rows if row.quantity == 0],
    )


@router.get("/portfolios/{portfolio_id}/summary")
def portfolio_summary(portfolio_id: int, user_id: UserId, db: Db, prices: Prices) -> SummaryOut:
    _owned(db, user_id, portfolio_id)
    return SummaryOut(**totals(asset_pnl(db, [portfolio_id], prices)))


@router.get("/summary")
def overview(user_id: UserId, db: Db, prices: Prices) -> OverviewOut:
    """Totals over all the caller's portfolios, with one row per asset across them."""
    ids = list(db.scalars(select(Portfolio.id).where(Portfolio.user_id == user_id)))
    rows = asset_pnl(db, ids, prices)
    return OverviewOut(**totals(rows), assets=rows)
