from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import current_user_id
from app.core.db import get_session
from app.models import Portfolio
from app.schemas.portfolios import PortfolioDelete, PortfolioIn, PortfolioOut

router = APIRouter(prefix="/api/v1/portfolios", tags=["portfolios"])

UserId = Annotated[str, Depends(current_user_id)]
Db = Annotated[Session, Depends(get_session)]


def _owned(db: Session, user_id: str, portfolio_id: int) -> Portfolio:
    """The caller's portfolio; another user's id is a 404, never a 403."""
    portfolio = db.scalar(
        select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
    )
    if portfolio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found")
    return portfolio


def _commit_name(db: Session, portfolio: Portfolio, name: str) -> Portfolio:
    """Save the name; the unique (user_id, lower(name)) index turns a duplicate into a 409."""
    portfolio.name = name
    db.add(portfolio)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"You already have a portfolio named {name!r}"
        ) from None
    db.refresh(portfolio)
    return portfolio


@router.post("", status_code=status.HTTP_201_CREATED)
def create_portfolio(body: PortfolioIn, user_id: UserId, db: Db) -> PortfolioOut:
    return _commit_name(db, Portfolio(user_id=user_id), body.name)


@router.get("")
def list_portfolios(user_id: UserId, db: Db) -> list[PortfolioOut]:
    return db.scalars(
        select(Portfolio).where(Portfolio.user_id == user_id).order_by(Portfolio.id)
    ).all()


@router.get("/{portfolio_id}")
def get_portfolio(portfolio_id: int, user_id: UserId, db: Db) -> PortfolioOut:
    return _owned(db, user_id, portfolio_id)


@router.patch("/{portfolio_id}")
def rename_portfolio(portfolio_id: int, body: PortfolioIn, user_id: UserId, db: Db) -> PortfolioOut:
    return _commit_name(db, _owned(db, user_id, portfolio_id), body.name)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(portfolio_id: int, body: PortfolioDelete, user_id: UserId, db: Db) -> Response:
    """Delete with all buys, sells and allocations (DB cascade) once the name is confirmed."""
    portfolio = _owned(db, user_id, portfolio_id)
    if body.confirm_name != portfolio.name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "confirm_name does not match the portfolio name"
        )
    db.delete(portfolio)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
