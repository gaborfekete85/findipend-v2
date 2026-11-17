"""Persisted trade records (README "Data Model"). Positions and P&L are derived, never stored."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

Quantity = Numeric(38, 18)
Usd = Numeric(28, 8)


class _Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Portfolio(_Timestamps, Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)


Index("uq_portfolios_user_id_lower_name", Portfolio.user_id, func.lower(Portfolio.name), unique=True)


class _Trade(_Timestamps):
    """Columns shared by buys and sells."""

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    asset_id: Mapped[str] = mapped_column(String)  # CoinGecko id
    asset_name: Mapped[str] = mapped_column(String)
    asset_symbol: Mapped[str] = mapped_column(String)
    quantity: Mapped[Decimal] = mapped_column(Quantity)
    total_usd: Mapped[Decimal] = mapped_column(Usd)
    fee_usd: Mapped[Decimal] = mapped_column(Usd)
    trade_date: Mapped[date] = mapped_column(Date)
    comment: Mapped[str | None] = mapped_column(Text)


class Buy(_Trade, Base):
    """One buy is one lot."""

    __tablename__ = "buys"


class Sell(_Trade, Base):
    __tablename__ = "sells"


class Allocation(Base):
    """The part of a sell's quantity drawn from one lot."""

    __tablename__ = "allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    sell_id: Mapped[int] = mapped_column(ForeignKey("sells.id", ondelete="CASCADE"))
    # Deleting an allocated buy is refused, checked at commit: a portfolio delete cascades to
    # buys before sells, so an immediate check (RESTRICT or NO ACTION) would refuse it too.
    buy_id: Mapped[int] = mapped_column(ForeignKey("buys.id", deferrable=True, initially="DEFERRED"))
    quantity: Mapped[Decimal] = mapped_column(Quantity)
