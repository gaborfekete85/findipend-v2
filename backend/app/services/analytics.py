"""Positions and P&L (README "Calculations"), derived on read; nothing is stored (ADR-0002)."""

from decimal import Decimal, localcontext

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Buy, Sell
from app.schemas.analytics import AssetPnlOut
from app.services.allocations import realized_pnl
from app.services.lots import SUM_PRECISION
from app.services.prices import CoinGecko, Price

ZERO = Decimal(0)


def asset_pnl(db: Session, portfolio_ids: list[int], prices: CoinGecko) -> list[AssetPnlOut]:
    """Per-asset metrics over the given portfolios, by asset id; USD values exact (README:
    round only at display)."""
    buys = db.scalars(
        select(Buy).where(Buy.portfolio_id.in_(portfolio_ids)).order_by(Buy.asset_id, Buy.id)
    ).all()
    lots = {buy.id: buy for buy in buys}
    draws = db.execute(
        select(Allocation.buy_id, Allocation.quantity, Sell)
        .join(Sell, Sell.id == Allocation.sell_id)
        .where(Sell.portfolio_id.in_(portfolio_ids))
    ).all()
    rows: dict[str, dict] = {}
    with localcontext(prec=SUM_PRECISION):
        unsold = {buy.id: buy.quantity for buy in buys}
        realized: dict[str, Decimal] = {}
        for buy_id, quantity, sell in draws:
            lot = lots[buy_id]
            unsold[buy_id] -= quantity
            realized[lot.asset_id] = realized.get(lot.asset_id, ZERO) + realized_pnl(
                sell, lot, quantity
            )
        for buy in buys:
            row = rows.setdefault(buy.asset_id, {
                "asset_id": buy.asset_id, "asset_name": buy.asset_name,
                "asset_symbol": buy.asset_symbol, "quantity": ZERO, "total_invested_usd": ZERO,
                "cost_basis_usd": ZERO, "realized_pnl_usd": realized.get(buy.asset_id, ZERO),
            })
            row["quantity"] += unsold[buy.id]
            row["total_invested_usd"] += buy.total_usd
            # Lot cost per unit × unsold quantity, as one exact division.
            row["cost_basis_usd"] += buy.total_usd * unsold[buy.id] / buy.quantity
        open_ids = [asset_id for asset_id, row in rows.items() if row["quantity"] > 0]
        quotes = prices.get_prices(open_ids) if open_ids else {}
        return [_with_price(row, quotes.get(row["asset_id"])) for row in rows.values()]


def _with_price(row: dict, quote: Price | None) -> AssetPnlOut:
    """Adds market value and unrealized P&L; both are null when an open asset has no price."""
    quantity, cost_basis = row["quantity"], row["cost_basis_usd"]
    if quantity == 0:
        return AssetPnlOut(
            **row, average_buy_price_usd=None, price_usd=None, price_as_of=None,
            price_unavailable=False, market_value_usd=ZERO, unrealized_pnl_usd=ZERO,
            total_pnl_usd=row["realized_pnl_usd"],
        )
    priced = {"price_usd": None, "price_as_of": None, "price_unavailable": True,
              "market_value_usd": None, "unrealized_pnl_usd": None, "total_pnl_usd": None}
    if quote is not None:
        market_value = quantity * quote.price
        unrealized = market_value - cost_basis
        priced = {"price_usd": quote.price, "price_as_of": quote.as_of, "price_unavailable": False,
                  "market_value_usd": market_value, "unrealized_pnl_usd": unrealized,
                  "total_pnl_usd": row["realized_pnl_usd"] + unrealized}
    return AssetPnlOut(**row, average_buy_price_usd=cost_basis / quantity, **priced)


def totals(rows: list[AssetPnlOut]) -> dict:
    """Sums of the per-asset metrics; assets without a price are left out of market value and
    unrealized P&L, and make the totals `partial`."""
    with localcontext(prec=SUM_PRECISION):
        priced = [row for row in rows if not row.price_unavailable]
        realized = sum((row.realized_pnl_usd for row in rows), ZERO)
        unrealized = sum((row.unrealized_pnl_usd for row in priced), ZERO)
        return {
            "total_invested_usd": sum((row.total_invested_usd for row in rows), ZERO),
            "cost_basis_usd": sum((row.cost_basis_usd for row in rows), ZERO),
            "realized_pnl_usd": realized,
            "market_value_usd": sum((row.market_value_usd for row in priced), ZERO),
            "unrealized_pnl_usd": unrealized,
            "total_pnl_usd": realized + unrealized,
            "partial": len(priced) < len(rows),
        }
