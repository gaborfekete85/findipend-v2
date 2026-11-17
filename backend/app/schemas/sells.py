from decimal import Decimal, localcontext
from typing import Annotated

from pydantic import BaseModel, Field, StrictInt, model_validator

from app.schemas.buys import BuyIn, BuyOut, DecimalStr, Quantity
from app.services.lots import SUM_PRECISION


class AllocationIn(BaseModel):
    buy_id: Annotated[StrictInt, Field(ge=1, lt=2**31)]  # Postgres INTEGER; larger ids would 500
    quantity: Quantity


class SellIn(BuyIn):
    """Body of create: the buy fields plus the lots the user chose to sell from."""

    allocations: list[AllocationIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _allocations_cover_quantity(self) -> "SellIn":
        buy_ids = [a.buy_id for a in self.allocations]
        if len(set(buy_ids)) != len(buy_ids):
            raise ValueError("each lot may appear only once in allocations")
        with localcontext(prec=SUM_PRECISION):
            if sum((a.quantity for a in self.allocations), Decimal(0)) != self.quantity:
                raise ValueError("allocation quantities must sum exactly to the sell quantity")
        return self


class AllocationOut(BaseModel):
    id: int
    buy_id: int
    quantity: Annotated[Decimal, DecimalStr]
    realized_pnl_usd: Annotated[Decimal, DecimalStr]


class SellOut(BuyOut):
    allocations: list[AllocationOut]


class LotOut(BuyOut):
    """A buy with its unsold quantity, normalized ("1", "0.75")."""

    unsold: str
