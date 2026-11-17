from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.assets import coingecko
from app.core.auth import current_user_id
from app.main import app
from app.services.prices import CoinGecko, Price

T0 = 1_700_000_000.0


class FakeClock:
    def __init__(self, now: float = T0):
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeTransport:
    """Serves canned CoinGecko JSON and records every URL requested."""

    def __init__(self, coins=(), prices=None):
        self.coins = list(coins)
        self.prices = prices or {}
        self.calls: list[str] = []
        self.error: Exception | None = None

    def __call__(self, url: str):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        if "/coins/list" in url:
            return self.coins
        return self.prices


def _coin(id_: str, symbol: str, name: str) -> dict:
    return {"id": id_, "symbol": symbol, "name": name}


# -- get_prices -------------------------------------------------------------


def test_get_prices_returns_decimal_price_and_fetch_time():
    transport = FakeTransport(prices={"bitcoin": {"usd": Decimal("60000.12")}})
    client = CoinGecko(transport=transport, clock=FakeClock())

    prices = client.get_prices(["bitcoin"])

    assert prices == {
        "bitcoin": Price(price=Decimal("60000.12"), as_of=datetime.fromtimestamp(T0, UTC))
    }
    assert isinstance(prices["bitcoin"].price, Decimal)


def test_get_prices_hits_transport_once_within_60s_and_again_after_61s():
    transport = FakeTransport(prices={"bitcoin": {"usd": Decimal(60000)}})
    clock = FakeClock()
    client = CoinGecko(transport=transport, clock=clock)

    client.get_prices(["bitcoin"])
    clock.now = T0 + 59
    client.get_prices(["bitcoin"])
    assert len(transport.calls) == 1

    clock.now = T0 + 61
    client.get_prices(["bitcoin"])
    assert len(transport.calls) == 2


def test_get_prices_returns_last_price_with_original_as_of_when_transport_fails():
    transport = FakeTransport(prices={"bitcoin": {"usd": Decimal(60000)}})
    clock = FakeClock()
    client = CoinGecko(transport=transport, clock=clock)
    client.get_prices(["bitcoin"])

    transport.error = OSError("CoinGecko down")
    clock.now = T0 + 120
    prices = client.get_prices(["bitcoin"])

    assert prices == {"bitcoin": Price(price=Decimal(60000), as_of=datetime.fromtimestamp(T0, UTC))}
    assert len(transport.calls) == 2


def test_get_prices_returns_none_when_transport_fails_with_no_prior_fetch():
    transport = FakeTransport()
    transport.error = OSError("CoinGecko down")
    client = CoinGecko(transport=transport, clock=FakeClock())

    assert client.get_prices(["bitcoin"]) == {"bitcoin": None}


def test_get_prices_mixes_last_known_and_none_when_transport_fails():
    transport = FakeTransport(prices={"bitcoin": {"usd": Decimal(60000)}})
    clock = FakeClock()
    client = CoinGecko(transport=transport, clock=clock)
    client.get_prices(["bitcoin"])

    transport.error = ValueError("not JSON")
    clock.now = T0 + 120
    prices = client.get_prices(["bitcoin", "ethereum"])

    assert prices == {
        "bitcoin": Price(price=Decimal(60000), as_of=datetime.fromtimestamp(T0, UTC)),
        "ethereum": None,
    }



@pytest.mark.parametrize(
    "bad", [float("inf"), float("-inf"), float("nan"), Decimal("Infinity"), Decimal("NaN")]
)
def test_get_prices_treats_non_finite_price_as_unavailable(bad):
    transport = FakeTransport(
        prices={"bitcoin": {"usd": bad}, "ethereum": {"usd": Decimal("3000")}}
    )
    client = CoinGecko(transport=transport, clock=FakeClock())

    assert client.get_prices(["bitcoin", "ethereum"]) == {
        "bitcoin": None,
        "ethereum": Price(price=Decimal("3000"), as_of=datetime.fromtimestamp(T0, UTC)),
    }

# -- GET /api/v1/assets -------------------------------------------------------


@pytest.fixture
def assets_api():
    """An authenticated test client whose CoinGecko client uses a fake transport."""
    transport = FakeTransport()
    client = CoinGecko(transport=transport, clock=FakeClock())
    app.dependency_overrides[current_user_id] = lambda: "user_2abc"
    app.dependency_overrides[coingecko] = lambda: client
    yield TestClient(app), transport
    app.dependency_overrides.clear()


def test_assets_search_returns_bitcoin_first_among_matches(assets_api):
    api, transport = assets_api
    transport.coins = [
        _coin("bitcoin-avalanche-bridged-btc-b", "btc.b", "Bitcoin Avalanche Bridged (BTC.b)"),
        _coin("ethereum", "eth", "Ethereum"),
        _coin("wrapped-bitcoin", "wbtc", "Wrapped Bitcoin"),
        _coin("bitcoin", "btc", "Bitcoin"),
        _coin("btcpx", "BTCPX", "BTC Proxy"),
    ]

    response = api.get("/api/v1/assets", params={"query": "btc"})

    assert response.status_code == 200
    assert response.json() == [
        _coin("bitcoin", "btc", "Bitcoin"),
        _coin("bitcoin-avalanche-bridged-btc-b", "btc.b", "Bitcoin Avalanche Bridged (BTC.b)"),
        _coin("wrapped-bitcoin", "wbtc", "Wrapped Bitcoin"),
        _coin("btcpx", "BTCPX", "BTC Proxy"),
    ]


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        pytest.param("BITCOIN", "bitcoin", id="id-upper-case"),
        pytest.param("Btc", "bitcoin", id="symbol-mixed-case"),
        pytest.param("ether", "ethereum", id="name-substring"),
        pytest.param("lido staked", "staked-ether", id="name-only"),
    ],
)
def test_assets_search_matches_id_symbol_or_name_case_insensitively(assets_api, query, expected_id):
    api, transport = assets_api
    transport.coins = [
        _coin("bitcoin", "btc", "Bitcoin"),
        _coin("ethereum", "eth", "Ethereum"),
        _coin("staked-ether", "steth", "Lido Staked Ether"),
    ]

    response = api.get("/api/v1/assets", params={"query": query})

    assert response.status_code == 200
    assert [coin["id"] for coin in response.json()][:1] == [expected_id]


def test_assets_search_returns_at_most_20_results(assets_api):
    api, transport = assets_api
    transport.coins = [_coin(f"btc-{i}", f"btc{i}", f"BTC {i}") for i in range(25)]

    response = api.get("/api/v1/assets", params={"query": "btc"})

    assert response.status_code == 200
    assert [coin["id"] for coin in response.json()] == [f"btc-{i}" for i in range(20)]


def test_assets_search_excludes_non_matching_assets(assets_api):
    api, transport = assets_api
    transport.coins = [_coin("bitcoin", "btc", "Bitcoin"), _coin("ethereum", "eth", "Ethereum")]

    response = api.get("/api/v1/assets", params={"query": "eth"})

    assert response.json() == [_coin("ethereum", "eth", "Ethereum")]


def test_assets_list_is_cached_for_24_hours():
    transport = FakeTransport(coins=[_coin("bitcoin", "btc", "Bitcoin")])
    clock = FakeClock()
    client = CoinGecko(transport=transport, clock=clock)

    client.search_assets("btc")
    clock.now = T0 + 24 * 3600 - 1
    client.search_assets("btc")
    assert len(transport.calls) == 1

    clock.now = T0 + 24 * 3600 + 1
    client.search_assets("btc")
    assert len(transport.calls) == 2


def test_assets_without_token_returns_401():
    response = TestClient(app).get("/api/v1/assets", params={"query": "btc"})

    assert response.status_code == 401
