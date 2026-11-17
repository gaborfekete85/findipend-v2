from datetime import date

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.portfolios import Db, UserId, _is_db_id, _owned
from app.models import Allocation, Buy, Sell
from app.schemas.buys import BuyOut
from app.schemas.sells import AllocationOut, LotOut, SellIn, SellOut
from app.services.allocations import allocation_conflict, realized_pnl, unsold_by_lot
from app.services.lots import _plain

router = APIRouter(prefix="/api/v1/portfolios/{portfolio_id}", tags=["sells"])


@router.get("/lots")
def list_lots(
    portfolio_id: int,
    user_id: UserId,
    db: Db,
    asset_id: str | None = None,
    open: bool = False,
    as_of: date | None = None,
) -> list[LotOut]:
    """Lots with their unsold quantity; `open` keeps unsold > 0, `as_of` keeps trade date ≤ it."""
    _owned(db, user_id, portfolio_id)
    query = select(Buy).where(Buy.portfolio_id == portfolio_id)
    if asset_id is not None:
        query = query.where(Buy.asset_id == asset_id)
    if as_of is not None:
        query = query.where(Buy.trade_date <= as_of)
    buys = db.scalars(query.order_by(Buy.trade_date, Buy.id)).all()
    unsold = unsold_by_lot(db, [buy.id for buy in buys])
    return [
        LotOut(**BuyOut.model_validate(buy).model_dump(), unsold=_plain(unsold[buy.id]))
        for buy in buys
        if not open or unsold[buy.id] > 0
    ]


def _sell_out(db: Session, sell: Sell) -> SellOut:
    rows = db.execute(
        select(Allocation, Buy)
        .join(Buy, Buy.id == Allocation.buy_id)
        .where(Allocation.sell_id == sell.id)
        .order_by(Allocation.id)
    )
    allocations = [
        AllocationOut(
            id=allocation.id,
            buy_id=allocation.buy_id,
            quantity=allocation.quantity,
            realized_pnl_usd=realized_pnl(sell, lot, allocation.quantity),
        )
        for allocation, lot in rows
    ]
    return SellOut(**BuyOut.model_validate(sell).model_dump(), allocations=allocations)


def _owned_sell(db: Session, user_id: str, portfolio_id: int, sell_id: int) -> Sell:
    """A sell in the caller's portfolio, locked until commit; anything else is a 404."""
    _owned(db, user_id, portfolio_id)
    if not _is_db_id(sell_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sell not found")
    query = select(Sell).where(Sell.id == sell_id, Sell.portfolio_id == portfolio_id)
    sell = db.scalar(query.with_for_update())
    if sell is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sell not found")
    return sell


def _record(db: Session, portfolio_id: int, sell: Sell, body: SellIn) -> SellOut:
    """Validate the allocations, then write the sell and them in one commit; 409 changes nothing."""
    conflict = allocation_conflict(
        db, portfolio_id, body.asset_id, body.trade_date, body.allocations
    )
    if conflict:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, conflict)
    for field, value in body.model_dump(exclude={"allocations"}).items():
        setattr(sell, field, value)
    db.add(sell)
    db.flush()
    db.add_all(
        Allocation(sell_id=sell.id, buy_id=a.buy_id, quantity=a.quantity) for a in body.allocations
    )
    db.commit()
    db.refresh(sell)
    return _sell_out(db, sell)


@router.post("/sells", status_code=status.HTTP_201_CREATED)
def create_sell(portfolio_id: int, body: SellIn, user_id: UserId, db: Db) -> SellOut:
    _owned(db, user_id, portfolio_id)
    return _record(db, portfolio_id, Sell(portfolio_id=portfolio_id), body)


@router.get("/sells")
def list_sells(portfolio_id: int, user_id: UserId, db: Db) -> list[SellOut]:
    _owned(db, user_id, portfolio_id)
    sells = db.scalars(
        select(Sell).where(Sell.portfolio_id == portfolio_id).order_by(Sell.trade_date, Sell.id)
    ).all()
    return [_sell_out(db, sell) for sell in sells]


@router.put("/sells/{sell_id}")
def edit_sell(portfolio_id: int, sell_id: int, body: SellIn, user_id: UserId, db: Db) -> SellOut:
    """Replace the sell and its allocations; its old allocations count as unsold while validating."""
    sell = _owned_sell(db, user_id, portfolio_id, sell_id)
    db.execute(delete(Allocation).where(Allocation.sell_id == sell.id))
    return _record(db, portfolio_id, sell, body)


@router.delete("/sells/{sell_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sell(portfolio_id: int, sell_id: int, user_id: UserId, db: Db) -> Response:
    """Delete the sell; its allocations cascade, releasing their quantity back to the lots."""
    db.delete(_owned_sell(db, user_id, portfolio_id, sell_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
