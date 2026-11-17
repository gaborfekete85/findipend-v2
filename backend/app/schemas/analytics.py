from datetime import datetime
from decimal import Decimal, localcontext
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

from app.services.lots import SUM_PRECISION


def _plain(value: Decimal) -> str:
    """Normalized decimal string ("50000", "1.5"), exact up to SUM_PRECISION digits."""
    with localcontext(prec=SUM_PRECISION):
        return format(value.normalize(), "f")


Plain = Annotated[Decimal, PlainSerializer(_plain, return_type=str)]


class AssetPnlOut(BaseModel):
    """One asset's position and P&L; the price fields are null for a closed position."""

    asset_id: str
    asset_name: str
    asset_symbol: str
    quantity: Plain  # unsold
    total_invested_usd: Plain
    cost_basis_usd: Plain
    average_buy_price_usd: Plain | None
    realized_pnl_usd: Plain
    price_usd: Plain | None
    price_as_of: datetime | None
    price_unavailable: bool
    market_value_usd: Plain | None
    unrealized_pnl_usd: Plain | None
    total_pnl_usd: Plain | None


class PositionsOut(BaseModel):
    open: list[AssetPnlOut]
    closed: list[AssetPnlOut]


class SummaryOut(BaseModel):
    """Totals; `partial` means some asset had no price and is left out of unrealized P&L."""

    total_invested_usd: Plain
    cost_basis_usd: Plain
    realized_pnl_usd: Plain
    market_value_usd: Plain
    unrealized_pnl_usd: Plain
    total_pnl_usd: Plain
    partial: bool


class OverviewOut(SummaryOut):
    assets: list[AssetPnlOut]
