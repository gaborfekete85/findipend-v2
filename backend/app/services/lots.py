"""Lot edit rules (README "Editing and deleting"): no change may uncover an allocation."""

from datetime import date
from decimal import Decimal, localcontext

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Buy, Sell

# NUMERIC(38,18) values have up to 38 digits, beyond Decimal's default 28-digit context;
# 60 keeps sums of up to 10^22 of them exact.
SUM_PRECISION = 60


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _draws(db: Session, buy_id: int) -> list[tuple[Sell, Decimal]]:
    """Each sell drawing from the lot, with the quantity it draws, oldest first."""
    rows = db.execute(
        select(Sell, Allocation.quantity)
        .join(Allocation, Allocation.sell_id == Sell.id)
        .where(Allocation.buy_id == buy_id)
        .order_by(Sell.trade_date, Sell.id)
    )
    return [(sell, quantity) for sell, quantity in rows]


def _names(draws: list[tuple[Sell, Decimal]]) -> str:
    return ", ".join(
        f"sell {sell.id} ({sell.trade_date.isoformat()}, {_plain(quantity)})"
        for sell, quantity in draws
    )


def edit_conflict(
    db: Session, buy: Buy, asset_id: str, quantity: Decimal, trade_date: date
) -> str | None:
    """Why the edit would uncover an allocation from this lot, or None when it is allowed."""
    draws = _draws(db, buy.id)
    if not draws:
        return None
    if asset_id != buy.asset_id:
        return f"Cannot change the asset of a lot that {_names(draws)} draws from"
    with localcontext(prec=SUM_PRECISION):
        allocated = sum((q for _, q in draws), Decimal(0))
        if quantity < allocated:
            return (
                f"Quantity {_plain(quantity)} is below the {_plain(allocated)} already "
                f"allocated from this lot by {_names(draws)}"
            )
    earlier = [(sell, q) for sell, q in draws if sell.trade_date < trade_date]
    if earlier:
        return f"Trade date {trade_date.isoformat()} is after {_names(earlier)}, drawing from this lot"
    return None


def delete_conflict(db: Session, buy: Buy) -> str | None:
    """Why the lot cannot be deleted (it has allocations), or None."""
    draws = _draws(db, buy.id)
    if not draws:
        return None
    return f"Cannot delete a lot that {_names(draws)} draws from; delete or re-allocate it first"
