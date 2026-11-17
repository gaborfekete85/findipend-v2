from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.portfolios import Db, UserId, _owned
from app.models import Buy
from app.schemas.buys import BuyIn, BuyOut
from app.services.lots import delete_conflict, edit_conflict

router = APIRouter(prefix="/api/v1/portfolios/{portfolio_id}/buys", tags=["buys"])


def _owned_buy(db: Session, user_id: str, portfolio_id: int, buy_id: int) -> Buy:
    """A buy in the caller's portfolio; anything else is a 404."""
    _owned(db, user_id, portfolio_id)
    buy = db.scalar(select(Buy).where(Buy.id == buy_id, Buy.portfolio_id == portfolio_id))
    if buy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buy not found")
    return buy


def _save(db: Session, buy: Buy, body: BuyIn) -> Buy:
    for field, value in body.model_dump().items():
        setattr(buy, field, value)
    db.add(buy)
    db.commit()
    db.refresh(buy)
    return buy


@router.post("", status_code=status.HTTP_201_CREATED)
def create_buy(portfolio_id: int, body: BuyIn, user_id: UserId, db: Db) -> BuyOut:
    _owned(db, user_id, portfolio_id)
    return _save(db, Buy(portfolio_id=portfolio_id), body)


@router.get("")
def list_buys(portfolio_id: int, user_id: UserId, db: Db) -> list[BuyOut]:
    _owned(db, user_id, portfolio_id)
    return db.scalars(
        select(Buy).where(Buy.portfolio_id == portfolio_id).order_by(Buy.trade_date, Buy.id)
    ).all()


@router.put("/{buy_id}")
def edit_buy(portfolio_id: int, buy_id: int, body: BuyIn, user_id: UserId, db: Db) -> BuyOut:
    buy = _owned_buy(db, user_id, portfolio_id, buy_id)
    conflict = edit_conflict(db, buy, body.asset_id, body.quantity, body.trade_date)
    if conflict:
        raise HTTPException(status.HTTP_409_CONFLICT, conflict)
    return _save(db, buy, body)


@router.delete("/{buy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_buy(portfolio_id: int, buy_id: int, user_id: UserId, db: Db) -> Response:
    buy = _owned_buy(db, user_id, portfolio_id, buy_id)
    conflict = delete_conflict(db, buy)
    if conflict:
        raise HTTPException(status.HTTP_409_CONFLICT, conflict)
    db.delete(buy)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
