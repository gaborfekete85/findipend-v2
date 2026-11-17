from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text

from tests.conftest import ALICE, BOB


def _create(api, user: str, name: str):
    return api.as_user(user).post("/api/v1/portfolios", json={"name": name})


def _delete(api, user: str, portfolio_id: int, confirm_name: str):
    return api.as_user(user).request(
        "DELETE", f"/api/v1/portfolios/{portfolio_id}", json={"confirm_name": confirm_name}
    )


def _count(engine: Engine, table: str, portfolio_id: int) -> int:
    column = "id" if table == "portfolios" else "portfolio_id"
    with engine.connect() as conn:
        sql = f"SELECT count(*) FROM {table} WHERE {column} = :id"
        return conn.execute(text(sql), {"id": portfolio_id}).scalar_one()


# AC1: create then list returns the new portfolio for its owner; another user sees nothing


def test_create_then_list_returns_portfolio_for_owner_only(api):
    created = _create(api, ALICE, "  Main  ")

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Main"
    assert set(body) == {"id", "name", "created_at", "updated_at"}

    listed = api.as_user(ALICE).get("/api/v1/portfolios")
    assert listed.status_code == 200
    assert [(p["id"], p["name"]) for p in listed.json()] == [(body["id"], "Main")]

    fetched = api.as_user(ALICE).get(f"/api/v1/portfolios/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body

    other = api.as_user(BOB).get("/api/v1/portfolios")
    assert other.status_code == 200
    assert other.json() == []


# AC2: case-insensitive duplicate per user is 409 on create and rename; other user gets 201


@pytest.mark.parametrize("duplicate", ["Main", "main", "MAIN", " mAiN "])
def test_create_duplicate_name_ignoring_case_returns_409(api, duplicate):
    assert _create(api, ALICE, "Main").status_code == 201

    response = _create(api, ALICE, duplicate)

    assert response.status_code == 409
    assert [p["name"] for p in api.as_user(ALICE).get("/api/v1/portfolios").json()] == ["Main"]


@pytest.mark.parametrize("duplicate", ["Main", "main", "MAIN"])
def test_rename_to_duplicate_name_ignoring_case_returns_409(api, duplicate):
    assert _create(api, ALICE, "Main").status_code == 201
    savings = _create(api, ALICE, "Savings").json()

    response = api.as_user(ALICE).patch(
        f"/api/v1/portfolios/{savings['id']}", json={"name": duplicate}
    )

    assert response.status_code == 409
    fetched = api.as_user(ALICE).get(f"/api/v1/portfolios/{savings['id']}").json()
    assert fetched["name"] == "Savings"


def test_same_name_for_another_user_returns_201(api):
    assert _create(api, ALICE, "Main").status_code == 201

    response = _create(api, BOB, "main")

    assert response.status_code == 201
    assert response.json()["name"] == "main"


def test_rename_changes_the_name(api):
    main = _create(api, ALICE, "Main").json()

    response = api.as_user(ALICE).patch(f"/api/v1/portfolios/{main['id']}", json={"name": " Long "})

    assert response.status_code == 200
    assert response.json()["name"] == "Long"
    assert api.as_user(ALICE).get(f"/api/v1/portfolios/{main['id']}").json()["name"] == "Long"


def test_rename_to_own_name_in_other_case_returns_200(api):
    main = _create(api, ALICE, "Main").json()

    response = api.as_user(ALICE).patch(f"/api/v1/portfolios/{main['id']}", json={"name": "MAIN"})

    assert response.status_code == 200
    assert response.json()["name"] == "MAIN"


# AC3: name length 0 after trim and 51 are 422; 50 is 201


@pytest.mark.parametrize("name", ["", "   ", "x" * 51, " " + "x" * 51 + " "])
def test_create_with_invalid_name_length_returns_422(api, name):
    response = _create(api, ALICE, name)

    assert response.status_code == 422
    assert api.as_user(ALICE).get("/api/v1/portfolios").json() == []


@pytest.mark.parametrize("body", [{}, {"name": None}])
def test_create_without_name_returns_422(api, body):
    response = api.as_user(ALICE).post("/api/v1/portfolios", json=body)

    assert response.status_code == 422


@pytest.mark.parametrize("name", ["", "   ", "x" * 51])
def test_rename_with_invalid_name_length_returns_422(api, name):
    main = _create(api, ALICE, "Main").json()

    response = api.as_user(ALICE).patch(f"/api/v1/portfolios/{main['id']}", json={"name": name})

    assert response.status_code == 422
    assert api.as_user(ALICE).get(f"/api/v1/portfolios/{main['id']}").json()["name"] == "Main"


@pytest.mark.parametrize("name", ["x" * 50, "  " + "x" * 50 + "  ", "x"])
def test_create_with_name_of_1_to_50_chars_returns_201(api, name):
    response = _create(api, ALICE, name)

    assert response.status_code == 201
    assert response.json()["name"] == name.strip()


def test_rename_to_50_chars_returns_200(api):
    main = _create(api, ALICE, "Main").json()

    response = api.as_user(ALICE).patch(
        f"/api/v1/portfolios/{main['id']}", json={"name": "y" * 50}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "y" * 50


# AC4: GET, PATCH and DELETE on another user's portfolio id return 404


def test_other_users_portfolio_returns_404_and_is_untouched(api, db_engine):
    main = _create(api, ALICE, "Main").json()
    url = f"/api/v1/portfolios/{main['id']}"

    bob = api.as_user(BOB)
    assert bob.get(url).status_code == 404
    assert bob.patch(url, json={"name": "Stolen"}).status_code == 404
    assert _delete(api, BOB, main["id"], "Main").status_code == 404

    assert api.as_user(ALICE).get(url).json() == main
    assert _count(db_engine, "portfolios", main["id"]) == 1


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_missing_portfolio_id_returns_404(api, method):
    body = {"GET": None, "PATCH": {"name": "X"}, "DELETE": {"confirm_name": "X"}}[method]

    response = api.as_user(ALICE).request(method, "/api/v1/portfolios/999999", json=body)

    assert response.status_code == 404


# AC5: DELETE needs confirm_name equal to the stored name; then removes buys and sells too


def _add_trades(engine: Engine, portfolio_id: int) -> None:
    trade = {
        "portfolio_id": portfolio_id, "asset_id": "bitcoin", "asset_name": "Bitcoin",
        "asset_symbol": "btc", "quantity": Decimal(1), "total_usd": Decimal(100),
        "fee_usd": Decimal(0), "trade_date": date(2026, 1, 2),
    }
    columns = ", ".join(trade)
    params = ", ".join(f":{name}" for name in trade)
    with engine.begin() as conn:
        buy_id = conn.execute(
            text(f"INSERT INTO buys ({columns}) VALUES ({params}) RETURNING id"), trade
        ).scalar_one()
        sell_id = conn.execute(
            text(f"INSERT INTO sells ({columns}) VALUES ({params}) RETURNING id"), trade
        ).scalar_one()
        conn.execute(
            text("INSERT INTO allocations (sell_id, buy_id, quantity) VALUES (:s, :b, 1)"),
            {"s": sell_id, "b": buy_id},
        )


@pytest.mark.parametrize("confirm_name", ["main", "Main ", "Other", ""])
def test_delete_with_wrong_confirm_name_returns_422_and_keeps_portfolio(
    api, db_engine, confirm_name
):
    main = _create(api, ALICE, "Main").json()
    _add_trades(db_engine, main["id"])

    response = _delete(api, ALICE, main["id"], confirm_name)

    assert response.status_code == 422
    assert api.as_user(ALICE).get(f"/api/v1/portfolios/{main['id']}").status_code == 200
    assert [_count(db_engine, t, main["id"]) for t in ("portfolios", "buys", "sells")] == [1, 1, 1]


@pytest.mark.parametrize("body", [None, {}])
def test_delete_without_confirm_name_returns_422_and_keeps_portfolio(api, db_engine, body):
    main = _create(api, ALICE, "Main").json()

    response = api.as_user(ALICE).request("DELETE", f"/api/v1/portfolios/{main['id']}", json=body)

    assert response.status_code == 422
    assert _count(db_engine, "portfolios", main["id"]) == 1


def test_delete_with_right_confirm_name_returns_204_and_removes_contents(api, db_engine):
    main = _create(api, ALICE, "Main").json()
    savings = _create(api, ALICE, "Savings").json()
    _add_trades(db_engine, main["id"])
    _add_trades(db_engine, savings["id"])

    response = _delete(api, ALICE, main["id"], "Main")

    assert response.status_code == 204
    assert response.content == b""
    assert api.as_user(ALICE).get(f"/api/v1/portfolios/{main['id']}").status_code == 404
    assert [_count(db_engine, t, main["id"]) for t in ("portfolios", "buys", "sells")] == [0, 0, 0]
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM allocations")).scalar_one() == 1
    assert [_count(db_engine, t, savings["id"]) for t in ("portfolios", "buys", "sells")] == [
        1, 1, 1,
    ]
