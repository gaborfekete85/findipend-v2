"""Sell allocation rules and realized P&L (README "Sells and allocations", "Calculations")."""

from datetime import date
from decimal import Decimal, localcontext

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Allocation, Buy, Sell
from app.schemas.buys import USD_STEP
from app.schemas.sells import AllocationIn
from app.services.lots import SUM_PRECISION, _plain


def unsold_by_lot(db: Session, buy_ids: list[int]) -> dict[int, Decimal]:
    """Buy quantity minus everything allocated from it, per lot (exact NUMERIC in Postgres)."""
    allocated = func.coalesce(func.sum(Allocation.quantity), 0)
    rows = db.execute(
        select(Buy.id, Buy.quantity - allocated)
        .outerjoin(Allocation, Allocation.buy_id == Buy.id)
        .where(Buy.id.in_(buy_ids))
        .group_by(Buy.id)
    )
    return {buy_id: unsold for buy_id, unsold in rows}


def allocation_conflict(
    db: Session, portfolio_id: int, asset_id: str, trade_date: date, allocations: list[AllocationIn]
) -> str | None:
    """Why the allocations cannot be recorded, naming the lot, or None when they are allowed.

    Locks the chosen lots until commit, so no other sell or buy edit can race this one.
    """
    ids = sorted(a.buy_id for a in allocations)
    lots = {
        buy.id: buy
        for buy in db.scalars(
            select(Buy)
            .where(Buy.id.in_(ids), Buy.portfolio_id == portfolio_id)
            .order_by(Buy.id)
            .with_for_update()
        )
    }
    unsold = unsold_by_lot(db, ids)
    for allocation in allocations:
        lot = lots.get(allocation.buy_id)
        name = f"lot {allocation.buy_id}"
        if lot is None:
            return f"{name} is not in this portfolio"
        if lot.asset_id != asset_id:
            return f"{name} is {lot.asset_id}, not {asset_id}"
        if lot.trade_date > trade_date:
            return f"{name} was bought on {lot.trade_date.isoformat()}, after the sell"
        if allocation.quantity > unsold[lot.id]:
            return (
                f"{name} has {_plain(unsold[lot.id])} unsold, "
                f"less than the {_plain(allocation.quantity)} allocated"
            )
    return None


def realized_pnl(sell: Sell, lot: Buy, quantity: Decimal) -> Decimal:
    """Allocation proceeds minus allocation cost, rounded once to the USD step (8 places)."""
    with localcontext(prec=SUM_PRECISION):
        # One division: (sell total × q × lot qty − lot total × q × sell qty) ÷ (sell qty × lot qty)
        numerator = quantity * (sell.total_usd * lot.quantity - lot.total_usd * sell.quantity)
        return (numerator / (sell.quantity * lot.quantity)).quantize(USD_STEP)
