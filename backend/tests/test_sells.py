import pytest
from sqlalchemy import Engine, text

from tests.conftest import ALICE, BOB

BTC = {"asset_id": "bitcoin", "asset_name": "Bitcoin", "asset_symbol": "btc"}
ETH = {"asset_id": "ethereum", "asset_name": "Ethereum", "asset_symbol": "eth"}


def _portfolio(api, user: str = ALICE, name: str = "Main") -> int:
    return api.as_user(user).post("/api/v1/portfolios", json={"name": name}).json()["id"]


def _buy(api, pid: int, total: str, on: str, quantity: str = "1", asset=BTC, user=ALICE) -> int:
    body = {**asset, "quantity": quantity, "total_usd": total, "trade_date": on}
    response = api.as_user(user).post(f"/api/v1/portfolios/{pid}/buys", json=body)
    assert response.status_code == 201
    return response.json()["id"]


def _lots_ab(api, pid: int) -> tuple[int, int]:
    """Lot A (1 BTC, $30000, 2026-01-01) and lot B (1 BTC, $50000, 2026-02-01)."""
    return _buy(api, pid, "30000", "2026-01-01"), _buy(api, pid, "50000", "2026-02-01")


def _sell(api, pid: int, allocations: list[tuple[int, str]], **fields):
    body = {
        **BTC, "quantity": "1", "total_usd": "60000", "trade_date": "2026-03-01",
        "allocations": [{"buy_id": b, "quantity": q} for b, q in allocations], **fields,
    }
    return api.as_user(ALICE).post(f"/api/v1/portfolios/{pid}/sells", json=body)


def _sells(api, pid: int) -> list[dict]:
    response = api.as_user(ALICE).get(f"/api/v1/portfolios/{pid}/sells")
    assert response.status_code == 200
    return response.json()


def _sell_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM sells")).scalar_one()


def _lots(api, pid: int, **params) -> list[dict]:
    response = api.as_user(ALICE).get(f"/api/v1/portfolios/{pid}/lots", params=params)
    assert response.status_code == 200
    return response.json()


# AC1: lots A and B; open lots as of 2026-01-15 is only lot A with unsold "1"


def test_open_lots_as_of_date_lists_only_earlier_lot_with_unsold(api):
    pid = _portfolio(api)
    lot_a, lot_b = _lots_ab(api, pid)

    lots = _lots(api, pid, asset_id="bitcoin", open="true", as_of="2026-01-15")

    assert [(lot["id"], lot["unsold"]) for lot in lots] == [(lot_a, "1")]
    on_b = _lots(api, pid, asset_id="bitcoin", open="true", as_of="2026-02-01")
    assert [lot["id"] for lot in on_b] == [lot_a, lot_b]


def test_open_lots_filters_asset_and_hides_sold_out_lots(api):
    pid = _portfolio(api)
    lot_a, lot_b = _lots_ab(api, pid)
    _buy(api, pid, "2000", "2026-01-01", asset=ETH)
    assert _sell(api, pid, [(lot_a, "1")]).status_code == 201
    assert _sell(api, pid, [(lot_b, "0.25")], quantity="0.25").status_code == 201

    assert [(lot["id"], lot["unsold"]) for lot in _lots(api, pid, asset_id="bitcoin")] == [
        (lot_a, "0"), (lot_b, "0.75"),
    ]
    open_lots = _lots(api, pid, asset_id="bitcoin", open="true", as_of="2026-03-01")
    assert [(lot["id"], lot["unsold"]) for lot in open_lots] == [(lot_b, "0.75")]


def test_lots_of_another_users_portfolio_return_404(api):
    pid = _portfolio(api, user=BOB)

    assert api.as_user(ALICE).get(f"/api/v1/portfolios/{pid}/lots").status_code == 404


# AC2: sell 1 BTC for $60000 from lot A returns 201; GET sells shows P&L "30000.00000000"


def test_sell_allocated_to_lot_a_lists_realized_pnl(api):
    pid = _portfolio(api)
    lot_a, _ = _lots_ab(api, pid)

    response = _sell(api, pid, [(lot_a, "1")])

    assert response.status_code == 201
    [sell] = _sells(api, pid)
    assert sell["id"] == response.json()["id"]
    assert sell["total_usd"] == "60000.00000000"
    assert [(a["buy_id"], a["realized_pnl_usd"]) for a in sell["allocations"]] == [
        (lot_a, "30000.00000000"),
    ]


# AC3: allocations not summing to the sell quantity are 422; 1.5 from a 1.0 lot is 409


@pytest.mark.parametrize("quantity", ["0.99", "1.01"])
def test_allocations_not_summing_to_sell_quantity_return_422(api, db_engine, quantity):
    pid = _portfolio(api)
    lot_a, _ = _lots_ab(api, pid)

    assert _sell(api, pid, [(lot_a, quantity)]).status_code == 422
    assert _sell_count(db_engine) == 0


def test_allocating_more_than_unsold_returns_409_naming_the_lot(api, db_engine):
    pid = _portfolio(api)
    lot_a, _ = _lots_ab(api, pid)

    response = _sell(api, pid, [(lot_a, "1.5")], quantity="1.5")

    assert response.status_code == 409
    assert f"lot {lot_a}" in response.json()["detail"]
    assert _sell_count(db_engine) == 0


def test_allocating_from_a_partly_sold_lot_counts_earlier_sells(api, db_engine):
    pid = _portfolio(api)
    lot_a, _ = _lots_ab(api, pid)
    assert _sell(api, pid, [(lot_a, "0.6")], quantity="0.6").status_code == 201

    response = _sell(api, pid, [(lot_a, "0.5")], quantity="0.5")

    assert response.status_code == 409
    assert f"lot {lot_a}" in response.json()["detail"]
    assert _sell_count(db_engine) == 1
    assert _sell(api, pid, [(lot_a, "0.4")], quantity="0.4").status_code == 201


# AC4: a lot of another asset, another portfolio, or dated after the sell is 409


def test_allocating_from_ineligible_lot_returns_409(api, db_engine):
    pid = _portfolio(api)
    other = _portfolio(api, name="Other")
    eth_lot = _buy(api, pid, "2000", "2026-01-01", asset=ETH)
    other_lot = _buy(api, other, "30000", "2026-01-01")
    late_lot = _buy(api, pid, "30000", "2026-03-02")
    bobs_lot = _buy(api, _portfolio(api, user=BOB), "30000", "2026-01-01", user=BOB)

    for lot in (eth_lot, other_lot, late_lot, bobs_lot):
        response = _sell(api, pid, [(lot, "1")])
        assert response.status_code == 409, lot
        assert f"lot {lot}" in response.json()["detail"]
    assert _sell_count(db_engine) == 0


def test_allocating_from_lot_dated_on_the_sell_date_returns_201(api):
    pid = _portfolio(api)
    lot = _buy(api, pid, "30000", "2026-03-01")

    assert _sell(api, pid, [(lot, "1")]).status_code == 201


# AC5: 0.5 + 0.5 from lots A and B of a $60000 sell give "15000.00000000" and "5000.00000000"


def test_split_sell_gives_per_allocation_realized_pnl(api):
    pid = _portfolio(api)
    lot_a, lot_b = _lots_ab(api, pid)

    response = _sell(api, pid, [(lot_a, "0.5"), (lot_b, "0.5")])

    assert response.status_code == 201
    expected = [(lot_a, "0.500000000000000000", "15000.00000000"),
                (lot_b, "0.500000000000000000", "5000.00000000")]
    for sell in (response.json(), _sells(api, pid)[0]):
        assert [
            (a["buy_id"], a["quantity"], a["realized_pnl_usd"]) for a in sell["allocations"]
        ] == expected


def test_realized_pnl_of_a_loss_is_negative(api):
    pid = _portfolio(api)
    _, lot_b = _lots_ab(api, pid)

    _sell(api, pid, [(lot_b, "1")], total_usd="40000")

    assert _sells(api, pid)[0]["allocations"][0]["realized_pnl_usd"] == "-10000.00000000"
