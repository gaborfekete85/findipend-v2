from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

PortfolioName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class PortfolioIn(BaseModel):
    """Body of create and rename: the name is trimmed, then must be 1-50 characters."""

    name: PortfolioName


class PortfolioDelete(BaseModel):
    confirm_name: str


class PortfolioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
