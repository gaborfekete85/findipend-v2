from datetime import date

import pytest
from sqlalchemy import Engine, text

from tests.conftest import ALICE, BOB

BTC = {"asset_id": "bitcoin", "asset_name": "Bitcoin", "asset_symbol": "btc"}


def _portfolio(api, user: str = ALICE, name: str = "Main") -> int:
    return api.as_user(user).post("/api/v1/portfolios", json={"name": name}).json()["id"]


def _buys_url(portfolio_id: int) -> str:
    return f"/api/v1/portfolios/{portfolio_id}/buys"


def _buy(**fields) -> dict:
    return {**BTC, "quantity": "1", "total_usd": "1000", "trade_date": "2026-03-01", **fields}


def _post(api, portfolio_id: int, body: dict, user: str = ALICE):
    return api.as_user(user).post(_buys_url(portfolio_id), json=body)


def _put(api, portfolio_id: int, buy_id: int, body: dict, user: str = ALICE):
    return api.as_user(user).put(f"{_buys_url(portfolio_id)}/{buy_id}", json=body)


def _delete(api, portfolio_id: int, buy_id: int, user: str = ALICE):
    return api.as_user(user).delete(f"{_buys_url(portfolio_id)}/{buy_id}")


def _sell_from(engine: Engine, portfolio_id: int, buy_id: int, quantity: str, on: date) -> int:
    """Insert a sell of `quantity` dated `on` with one allocation from `buy_id`."""
    sell = {
        "portfolio_id": portfolio_id, "asset_id": "bitcoin", "asset_name": "Bitcoin",
        "asset_symbol": "btc", "quantity": quantity, "total_usd": "900", "fee_usd": "0.9",
        "trade_date": on,
    }
    columns = ", ".join(sell)
    params = ", ".join(f":{name}" for name in sell)
    with engine.begin() as conn:
        sell_id = conn.execute(
            text(f"INSERT INTO sells ({columns}) VALUES ({params}) RETURNING id"), sell
        ).scalar_one()
        conn.execute(
            text("INSERT INTO allocations (sell_id, buy_id, quantity) VALUES (:s, :b, :q)"),
            {"s": sell_id, "b": buy_id, "q": quantity},
        )
    return sell_id


def _buy_count(engine: Engine, portfolio_id: int) -> int:
    with engine.connect() as conn:
        sql = "SELECT count(*) FROM buys WHERE portfolio_id = :id"
        return conn.execute(text(sql), {"id": portfolio_id}).scalar_one()


# AC1: total "1000" and no fee stores fee "1.00000000", trade date today, decimals as strings


def test_post_buy_defaults_fee_and_trade_date_and_returns_decimal_strings(api):
    pid = _portfolio(api)
    body = {**BTC, "quantity": "0.5", "total_usd": "1000", "comment": "first"}

    response = _post(api, pid, body)

    assert response.status_code == 201
    buy = response.json()
    assert buy["fee_usd"] == "1.00000000"
    assert buy["trade_date"] == date.today().isoformat()
    assert buy["quantity"] == "0.500000000000000000"
    assert buy["total_usd"] == "1000.00000000"
    assert {k: buy[k] for k in ("asset_id", "asset_name", "asset_symbol", "comment")} == {
        **BTC, "comment": "first",
    }
    assert set(buy) == {
        "id", "portfolio_id", "asset_id", "asset_name", "asset_symbol", "quantity",
        "total_usd", "fee_usd", "trade_date", "comment", "created_at", "updated_at",
    }
    assert buy["portfolio_id"] == pid

    listed = api.as_user(ALICE).get(_buys_url(pid))
    assert listed.status_code == 200
    assert listed.json() == [buy]


def test_post_buy_keeps_given_fee_and_trade_date(api):
    pid = _portfolio(api)

    response = _post(api, pid, _buy(fee_usd="2.5", trade_date="2025-12-31"))

    assert response.status_code == 201
    assert response.json()["fee_usd"] == "2.50000000"
    assert response.json()["trade_date"] == "2025-12-31"


@pytest.mark.parametrize("fee", ["0", "1000"])
def test_post_buy_accepts_fee_from_zero_to_total(api, fee):
    pid = _portfolio(api)

    response = _post(api, pid, _buy(fee_usd=fee))

    assert response.status_code == 201
    assert response.json()["fee_usd"] == f"{fee}.00000000"


# AC2: quantity "0" or a negative total is 422; total "0" is 201 (zero-cost lot)


@pytest.mark.parametrize(
    "fields",
    [
        {"quantity": "0"},
        {"quantity": "-1"},
        {"total_usd": "-1"},
        {"total_usd": "-0.00000001"},
        {"fee_usd": "-1"},
        {"fee_usd": "1000.00000001"},
        {"quantity": None},
        {"total_usd": None},
    ],
)
def test_post_invalid_buy_returns_422_and_stores_nothing(api, db_engine, fields):
    pid = _portfolio(api)

    response = _post(api, pid, _buy(**fields))

    assert response.status_code == 422
    assert _buy_count(db_engine, pid) == 0


def test_post_zero_total_buy_returns_201_with_zero_fee(api):
    pid = _portfolio(api)

    response = _post(api, pid, {**BTC, "quantity": "0.1", "total_usd": "0"})

    assert response.status_code == 201
    assert response.json()["total_usd"] == "0.00000000"
    assert response.json()["fee_usd"] == "0.00000000"


# AC3: sell allocating 0.6 from a 1.0 lot: quantity 0.5 is 409, 0.6 is 200, delete is 409


def test_edit_quantity_below_allocated_returns_409_naming_the_sell(api, db_engine):
    pid = _portfolio(api)
    buy = _post(api, pid, _buy()).json()
    sell_id = _sell_from(db_engine, pid, buy["id"], "0.6", date(2026, 3, 10))

    response = _put(api, pid, buy["id"], _buy(quantity="0.5"))

    assert response.status_code == 409
    assert f"sell {sell_id}" in response.json()["detail"]
    assert api.as_user(ALICE).get(_buys_url(pid)).json() == [buy]


@pytest.mark.parametrize(
    ("quantity", "stored"), [("0.6", "0.600000000000000000"), ("2", "2.000000000000000000")]
)
def test_edit_quantity_at_or_above_allocated_returns_200(api, db_engine, quantity, stored):
    pid = _portfolio(api)
    buy = _post(api, pid, _buy()).json()
    _sell_from(db_engine, pid, buy["id"], "0.6", date(2026, 3, 10))

    response = _put(api, pid, buy["id"], _buy(quantity=quantity, comment="edited"))

    assert response.status_code == 200
    edited = response.json()
    assert edited["id"] == buy["id"]
    assert edited["quantity"] == stored
    assert edited["comment"] == "edited"
    assert api.as_user(ALICE).get(_buys_url(pid)).json() == [edited]


def test_delete_allocated_buy_returns_409_naming_the_sell(api, db_engine):
    pid = _portfolio(api)
    buy = _post(api, pid, _buy()).json()
    sell_id = _sell_from(db_engine, pid, buy["id"], "0.6", date(2026, 3, 10))

    response = _delete(api, pid, buy["id"])

    assert response.status_code == 409
    assert f"sell {sell_id}" in response.json()["detail"]
    assert _buy_count(db_engine, pid) == 1


def test_delete_unallocated_buy_returns_204(api, db_engine):
    pid = _portfolio(api)
    keep = _post(api, pid, _buy()).json()
    gone = _post(api, pid, _buy()).json()

    response = _delete(api, pid, gone["id"])

    assert response.status_code == 204
    assert response.content == b""
    assert api.as_user(ALICE).get(_buys_url(pid)).json() == [keep]


# AC4: sell dated 2026-03-10: trade date 2026-03-11 is 409, 2026-03-10 is 200


def test_edit_trade_date_after_sell_returns_409_naming_the_sell(api, db_engine):
    pid = _portfolio(api)
    buy = _post(api, pid, _buy()).json()
    sell_id = _sell_from(db_engine, pid, buy["id"], "0.6", date(2026, 3, 10))

    response = _put(api, pid, buy["id"], _buy(trade_date="2026-03-11"))

    assert response.status_code == 409
    assert f"sell {sell_id}" in response.json()["detail"]
    assert api.as_user(ALICE).get(_buys_url(pid)).json()[0]["trade_date"] == "2026-03-01"


@pytest.mark.parametrize("trade_date", ["2026-03-10", "2026-02-01"])
def test_edit_trade_date_on_or_before_sell_returns_200(api, db_engine, trade_date):
    pid = _portfolio(api)
    buy = _post(api, pid, _buy()).json()
    _sell_from(db_engine, pid, buy["id"], "0.6", date(2026, 3, 10))

    response = _put(api, pid, buy["id"], _buy(trade_date=trade_date))

    assert response.status_code == 200
    assert response.json()["trade_date"] == trade_date


def test_edit_asset_of_allocated_buy_returns_409(api, db_engine):
    pid = _portfolio(api)
    buy = _post(api, pid, _buy()).json()
    sell_id = _sell_from(db_engine, pid, buy["id"], "0.6", date(2026, 3, 10))
    eth = {"asset_id": "ethereum", "asset_name": "Ethereum", "asset_symbol": "eth"}

    response = _put(api, pid, buy["id"], _buy(**eth))

    assert response.status_code == 409
    assert f"sell {sell_id}" in response.json()["detail"]


# AC5: buy endpoints on another user's portfolio return 404


def test_buy_endpoints_on_another_users_portfolio_return_404(api, db_engine):
    pid = _portfolio(api)
    buy = _post(api, pid, _buy()).json()

    assert api.as_user(BOB).get(_buys_url(pid)).status_code == 404
    assert _post(api, pid, _buy(), user=BOB).status_code == 404
    assert _put(api, pid, buy["id"], _buy(quantity="5"), user=BOB).status_code == 404
    assert _delete(api, pid, buy["id"], user=BOB).status_code == 404

    assert api.as_user(ALICE).get(_buys_url(pid)).json() == [buy]


def test_buy_from_another_portfolio_returns_404(api, db_engine):
    main = _portfolio(api, name="Main")
    savings = _portfolio(api, name="Savings")
    buy = _post(api, main, _buy()).json()

    assert _put(api, savings, buy["id"], _buy(quantity="5")).status_code == 404
    assert _delete(api, savings, buy["id"]).status_code == 404
    assert _buy_count(db_engine, main) == 1
