from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.portfolios import Db, UserId, _is_db_id, _owned
from app.models import Buy
from app.schemas.buys import BuyEdit, BuyIn, BuyOut
from app.services.lots import delete_conflict, edit_conflict

router = APIRouter(prefix="/api/v1/portfolios/{portfolio_id}/buys", tags=["buys"])


def _owned_buy(db: Session, user_id: str, portfolio_id: int, buy_id: int) -> Buy:
    """A buy in the caller's portfolio; anything else is a 404."""
    _owned(db, user_id, portfolio_id)
    if not _is_db_id(buy_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buy not found")
    buy = db.scalar(select(Buy).where(Buy.id == buy_id, Buy.portfolio_id == portfolio_id))
    if buy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buy not found")
    return buy


def _save(db: Session, buy: Buy, values: dict) -> Buy:
    for field, value in values.items():
        setattr(buy, field, value)
    db.add(buy)
    db.commit()
    db.refresh(buy)
    return buy


@router.post("", status_code=status.HTTP_201_CREATED)
def create_buy(portfolio_id: int, body: BuyIn, user_id: UserId, db: Db) -> BuyOut:
    _owned(db, user_id, portfolio_id)
    return _save(db, Buy(portfolio_id=portfolio_id), body.model_dump())


@router.get("")
def list_buys(portfolio_id: int, user_id: UserId, db: Db) -> list[BuyOut]:
    _owned(db, user_id, portfolio_id)
    return db.scalars(
        select(Buy).where(Buy.portfolio_id == portfolio_id).order_by(Buy.trade_date, Buy.id)
    ).all()


@router.get("/{buy_id}")
def get_buy(portfolio_id: int, buy_id: int, user_id: UserId, db: Db) -> BuyOut:
    return _owned_buy(db, user_id, portfolio_id, buy_id)


@router.put("/{buy_id}")
def edit_buy(portfolio_id: int, buy_id: int, body: BuyEdit, user_id: UserId, db: Db) -> BuyOut:
    buy = _owned_buy(db, user_id, portfolio_id, buy_id)
    trade_date = body.trade_date or buy.trade_date
    fee_usd = buy.fee_usd if body.fee_usd is None else body.fee_usd
    if fee_usd > body.total_usd:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "fee_usd must not exceed total_usd"
        )
    conflict = edit_conflict(db, buy, body.asset_id, body.quantity, trade_date)
    if conflict:
        raise HTTPException(status.HTTP_409_CONFLICT, conflict)
    values = body.model_dump(exclude_unset=True) | {"trade_date": trade_date, "fee_usd": fee_usd}
    return _save(db, buy, values)


@router.delete("/{buy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_buy(portfolio_id: int, buy_id: int, user_id: UserId, db: Db) -> Response:
    buy = _owned_buy(db, user_id, portfolio_id, buy_id)
    conflict = delete_conflict(db, buy)
    if conflict:
        raise HTTPException(status.HTTP_409_CONFLICT, conflict)
    db.delete(buy)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
