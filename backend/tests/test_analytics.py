import pytest

from app.api.assets import coingecko
from app.main import app
from app.services.prices import CoinGecko
from tests.conftest import ALICE, BOB

BTC = {"asset_id": "bitcoin", "asset_name": "Bitcoin", "asset_symbol": "btc"}
ETH = {"asset_id": "ethereum", "asset_name": "Ethereum", "asset_symbol": "eth"}
T0 = 1_700_000_000.0  # 2023-11-14T22:13:20Z


@pytest.fixture
def prices(api):
    """USD price per asset id served by a fake CoinGecko; a missing id has no price."""
    served: dict[str, str] = {}

    def transport(url: str):
        return {i: {"usd": p} for i, p in served.items()}

    app.dependency_overrides[coingecko] = lambda: client
    client = CoinGecko(transport=transport, clock=lambda: T0)
    return served


def _portfolio(api, user: str = ALICE, name: str = "Main") -> int:
    return api.as_user(user).post("/api/v1/portfolios", json={"name": name}).json()["id"]


def _buy(api, pid: int, total: str, on: str, quantity: str = "1", asset=BTC, user=ALICE) -> int:
    body = {**asset, "quantity": quantity, "total_usd": total, "trade_date": on}
    response = api.as_user(user).post(f"/api/v1/portfolios/{pid}/buys", json=body)
    assert response.status_code == 201
    return response.json()["id"]


def _sell(api, pid: int, lot: int, quantity: str, total: str, asset=BTC, user=ALICE) -> None:
    body = {
        **asset, "quantity": quantity, "total_usd": total, "trade_date": "2026-03-01",
        "allocations": [{"buy_id": lot, "quantity": quantity}],
    }
    assert api.as_user(user).post(f"/api/v1/portfolios/{pid}/sells", json=body).status_code == 201


def _readme_example(api, pid: int, user: str = ALICE) -> None:
    """Lot A 1 BTC $30k, lot B 1 BTC $50k; lot A sold for $60k."""
    lot_a = _buy(api, pid, "30000", "2026-01-01", user=user)
    _buy(api, pid, "50000", "2026-02-01", user=user)
    _sell(api, pid, lot_a, "1", "60000", user=user)


def _get(api, path: str) -> dict:
    response = api.as_user(ALICE).get(path)
    assert response.status_code == 200, response.text
    return response.json()


def _totals(body: dict) -> dict:
    keys = (
        "total_invested_usd", "cost_basis_usd", "realized_pnl_usd", "market_value_usd",
        "unrealized_pnl_usd", "total_pnl_usd", "partial",
    )
    return {k: body[k] for k in keys}


# AC1: the README example gives realized 30000, invested 80000, cost basis 50000,
# unrealized 10000, total P&L 40000


def test_portfolio_summary_matches_readme_example(api, prices):
    prices["bitcoin"] = "60000"
    pid = _portfolio(api)
    _readme_example(api, pid)

    assert _totals(_get(api, f"/api/v1/portfolios/{pid}/summary")) == {
        "total_invested_usd": "80000", "cost_basis_usd": "50000", "realized_pnl_usd": "30000",
        "market_value_usd": "60000", "unrealized_pnl_usd": "10000", "total_pnl_usd": "40000",
        "partial": False,
    }


def test_portfolio_summary_uses_unsold_part_of_a_partly_sold_lot(api, prices):
    prices["bitcoin"] = "40000"
    pid = _portfolio(api)
    _buy(api, pid, "30000", "2026-01-01")
    lot_b = _buy(api, pid, "50000", "2026-02-01")
    _sell(api, pid, lot_b, "0.5", "30000")

    assert _totals(_get(api, f"/api/v1/portfolios/{pid}/summary")) == {
        "total_invested_usd": "80000", "cost_basis_usd": "55000", "realized_pnl_usd": "5000",
        "market_value_usd": "60000", "unrealized_pnl_usd": "5000", "total_pnl_usd": "10000",
        "partial": False,
    }
    [btc] = _get(api, f"/api/v1/portfolios/{pid}/positions")["open"]
    assert (btc["quantity"], btc["average_buy_price_usd"]) == ("1.5", "36666.66666667")


# AC2: BTC is open with average buy price 50000; a fully sold asset is closed with its realized P&L


def test_positions_list_open_and_closed_assets(api, prices):
    prices.update(bitcoin="60000", ethereum="9999")
    pid = _portfolio(api)
    _readme_example(api, pid)
    eth = _buy(api, pid, "2000", "2026-01-01", asset=ETH)
    _sell(api, pid, eth, "1", "3000", asset=ETH)

    body = _get(api, f"/api/v1/portfolios/{pid}/positions")

    assert body["open"] == [{
        **BTC, "quantity": "1", "total_invested_usd": "80000", "cost_basis_usd": "50000",
        "average_buy_price_usd": "50000", "realized_pnl_usd": "30000",
        "price_usd": "60000", "price_as_of": "2023-11-14T22:13:20Z", "price_unavailable": False,
        "market_value_usd": "60000", "unrealized_pnl_usd": "10000", "total_pnl_usd": "40000",
    }]
    assert body["closed"] == [{
        **ETH, "quantity": "0", "total_invested_usd": "2000", "cost_basis_usd": "0",
        "average_buy_price_usd": None, "realized_pnl_usd": "1000",
        "price_usd": None, "price_as_of": None, "price_unavailable": False,
        "market_value_usd": "0", "unrealized_pnl_usd": "0", "total_pnl_usd": "1000",
    }]


# AC3: with two portfolios holding BTC, /summary totals both and its BTC row sums them


def test_all_portfolios_summary_totals_both_portfolios_and_sums_btc_row(api, prices):
    prices["bitcoin"] = "60000"
    main = _portfolio(api)
    _readme_example(api, main)
    _buy(api, _portfolio(api, name="Cold"), "20000", "2026-01-05")
    _readme_example(api, _portfolio(api, user=BOB), user=BOB)  # another user's: never counted

    body = _get(api, "/api/v1/summary")

    assert _totals(body) == {
        "total_invested_usd": "100000", "cost_basis_usd": "70000", "realized_pnl_usd": "30000",
        "market_value_usd": "120000", "unrealized_pnl_usd": "50000", "total_pnl_usd": "80000",
        "partial": False,
    }
    [btc] = body["assets"]
    assert btc == {
        **BTC, "quantity": "2", "total_invested_usd": "100000", "cost_basis_usd": "70000",
        "average_buy_price_usd": "35000", "realized_pnl_usd": "30000",
        "price_usd": "60000", "price_as_of": "2023-11-14T22:13:20Z", "price_unavailable": False,
        "market_value_usd": "120000", "unrealized_pnl_usd": "50000", "total_pnl_usd": "80000",
    }


def test_all_portfolios_summary_without_portfolios_is_zero(api, prices):
    body = _get(api, "/api/v1/summary")

    assert body["assets"] == []
    assert _totals(body) == {
        "total_invested_usd": "0", "cost_basis_usd": "0", "realized_pnl_usd": "0",
        "market_value_usd": "0", "unrealized_pnl_usd": "0", "total_pnl_usd": "0",
        "partial": False,
    }


# AC4: without a price the asset's unrealized P&L is null, price_unavailable is true,
# realized P&L is still returned, and the summary is partial


def test_unavailable_price_nulls_unrealized_and_marks_summary_partial(api, prices):
    prices["ethereum"] = "3000"  # no bitcoin price
    pid = _portfolio(api)
    _readme_example(api, pid)
    _buy(api, pid, "2000", "2026-01-01", asset=ETH)

    btc, eth = _get(api, f"/api/v1/portfolios/{pid}/positions")["open"]

    assert {k: btc[k] for k in (
        "asset_id", "price_usd", "price_as_of", "price_unavailable", "market_value_usd",
        "unrealized_pnl_usd", "total_pnl_usd", "realized_pnl_usd", "cost_basis_usd",
    )} == {
        "asset_id": "bitcoin", "price_usd": None, "price_as_of": None, "price_unavailable": True,
        "market_value_usd": None, "unrealized_pnl_usd": None, "total_pnl_usd": None,
        "realized_pnl_usd": "30000", "cost_basis_usd": "50000",
    }
    assert (eth["asset_id"], eth["price_unavailable"], eth["unrealized_pnl_usd"]) == (
        "ethereum", False, "1000",
    )
    assert _totals(_get(api, f"/api/v1/portfolios/{pid}/summary")) == {
        "total_invested_usd": "82000", "cost_basis_usd": "52000", "realized_pnl_usd": "30000",
        "market_value_usd": "3000", "unrealized_pnl_usd": "1000", "total_pnl_usd": "31000",
        "partial": True,
    }
    assert _get(api, "/api/v1/summary")["partial"] is True


# AC5: analytics for another user's portfolio return 404


@pytest.mark.parametrize("path", ["positions", "summary"])
def test_analytics_of_another_users_portfolio_return_404(api, prices, path):
    prices["bitcoin"] = "60000"
    pid = _portfolio(api, user=BOB)
    _readme_example(api, pid, user=BOB)

    response = api.as_user(ALICE).get(f"/api/v1/portfolios/{pid}/{path}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Portfolio not found"}
