"""CoinGecko client: asset list (cached 24 h) and USD prices (cached 60 s, last-known fallback)."""

import http.client
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

BASE_URL = "https://api.coingecko.com/api/v3"
ASSET_LIST_TTL = 24 * 3600
PRICE_TTL = 60
SEARCH_LIMIT = 20

Transport = Callable[[str], Any]
"""Fetches a URL and returns the parsed JSON body; raises on any failure."""


def urllib_transport(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response, parse_float=Decimal)


@dataclass(frozen=True)
class Price:
    price: Decimal
    as_of: datetime


class CoinGecko:
    # simplest: in-memory, per-process caches; a restart starts empty.
    def __init__(
        self, transport: Transport = urllib_transport, clock: Callable[[], float] = time.time
    ):
        self._transport = transport
        self._clock = clock
        self._assets: list[dict] = []
        self._assets_fetched_at: float | None = None
        self._prices: dict[str, tuple[float, Price]] = {}

    def _asset_list(self) -> list[dict]:
        now = self._clock()
        if self._assets_fetched_at is None or now - self._assets_fetched_at > ASSET_LIST_TTL:
            self._assets = self._transport(f"{BASE_URL}/coins/list")
            self._assets_fetched_at = now
        return self._assets

    def search_assets(self, query: str) -> list[dict]:
        """Assets whose id, symbol or name contains `query` (any case); exact matches first."""
        needle = query.lower()
        matches = [
            asset
            for asset in self._asset_list()
            if any(needle in asset[key].lower() for key in ("id", "symbol", "name"))
        ]
        # sorted is stable: list order is kept within exact and partial matches.
        matches.sort(
            key=lambda asset: needle not in {asset[k].lower() for k in ("id", "symbol", "name")}
        )
        return matches[:SEARCH_LIMIT]

    def get_prices(self, asset_ids: Iterable[str]) -> dict[str, Price | None]:
        """USD price per asset; the last known price if CoinGecko fails, None if none is known."""
        ids = list(asset_ids)
        now = self._clock()
        stale = [i for i in ids if i not in self._prices or now - self._prices[i][0] > PRICE_TTL]
        if stale:
            query = urllib.parse.urlencode({"ids": ",".join(stale), "vs_currencies": "usd"})
            try:
                body = self._transport(f"{BASE_URL}/simple/price?{query}")
                quotes = {i: Decimal(str(body[i]["usd"])) for i in stale if i in body}
                # Infinity or NaN is not a price: treat it like a missing one.
                fetched = {
                    i: Price(price, datetime.fromtimestamp(now, UTC))
                    for i, price in quotes.items()
                    if price.is_finite()
                }
            # OSError: network error or timeout; http.client.HTTPException: broken HTTP
            # response; ValueError: not JSON; TypeError, KeyError, ArithmeticError
            # (decimal.InvalidOperation): JSON that is not a price map.
            except (
                OSError,
                http.client.HTTPException,
                ValueError,
                TypeError,
                KeyError,
                ArithmeticError,
            ):
                fetched = {}
            for i, price in fetched.items():
                self._prices[i] = (now, price)
        return {i: self._prices[i][1] if i in self._prices else None for i in ids}
