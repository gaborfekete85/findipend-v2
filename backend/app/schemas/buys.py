from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

# Decimals go out as plain strings ("1.00000000", never "1E+0" or a JSON number).
DecimalStr = PlainSerializer(lambda value: format(value, "f"), return_type=str)
Quantity = Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18), DecimalStr]
Usd = Annotated[Decimal, Field(ge=0, max_digits=28, decimal_places=8), DecimalStr]
NonEmpty = Annotated[str, Field(min_length=1)]

DEFAULT_FEE_RATE = Decimal("0.001")
USD_STEP = Decimal("0.00000001")


class BuyIn(BaseModel):
    """Body of create and edit. Fee defaults to 0.1% of the total; trade date to today."""

    asset_id: NonEmpty
    asset_name: NonEmpty
    asset_symbol: NonEmpty
    quantity: Quantity
    total_usd: Usd
    fee_usd: Usd | None = None
    trade_date: date = Field(default_factory=date.today)
    comment: str | None = None

    @model_validator(mode="after")
    def _fee_within_total(self) -> "BuyIn":
        if self.fee_usd is None:
            self.fee_usd = (self.total_usd * DEFAULT_FEE_RATE).quantize(USD_STEP)
        elif self.fee_usd > self.total_usd:
            raise ValueError("fee_usd must not exceed total_usd")
        return self


class BuyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    portfolio_id: int
    asset_id: str
    asset_name: str
    asset_symbol: str
    quantity: Annotated[Decimal, DecimalStr]
    total_usd: Annotated[Decimal, DecimalStr]
    fee_usd: Annotated[Decimal, DecimalStr]
    trade_date: date
    comment: str | None
    created_at: datetime
    updated_at: datetime
