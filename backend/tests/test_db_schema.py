from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from tests.conftest import alembic_config

ALL_TABLES = ["alembic_version", "allocations", "buys", "portfolios", "sells"]


def _tables(url: str) -> list[str]:
    engine = create_engine(url)
    tables = sorted(inspect(engine).get_table_names())
    engine.dispose()
    return tables


def _insert(conn, table: str, **values) -> int:
    columns, params = ", ".join(values), ", ".join(f":{name}" for name in values)
    sql = f"INSERT INTO {table} ({columns}) VALUES ({params}) RETURNING id"
    return conn.execute(text(sql), values).scalar_one()


def _portfolio(conn, user_id: str = "user_a", name: str = "Main") -> int:
    return _insert(conn, "portfolios", user_id=user_id, name=name)


def _trade(conn, table: str, portfolio_id: int, quantity="1", total="100") -> int:
    return _insert(
        conn, table, portfolio_id=portfolio_id, asset_id="bitcoin", asset_name="Bitcoin",
        asset_symbol="btc", quantity=Decimal(quantity), total_usd=Decimal(total),
        fee_usd=Decimal(0), trade_date=date(2026, 1, 2),
    )


def _allocation(conn, sell_id: int, buy_id: int) -> int:
    return _insert(conn, "allocations", sell_id=sell_id, buy_id=buy_id, quantity=Decimal(1))


def _ids(conn, table: str) -> list[int]:
    return list(conn.execute(text(f"SELECT id FROM {table} ORDER BY id")).scalars())


def test_upgrade_head_creates_exactly_the_four_tables(database_url):
    command.upgrade(alembic_config(database_url), "head")

    assert _tables(database_url) == ALL_TABLES


def test_portfolio_name_is_unique_per_user_ignoring_case(db_engine: Engine):
    with db_engine.begin() as conn:
        _portfolio(conn, "user_a", "Main")
        _portfolio(conn, "user_b", "main")  # another user may reuse the name
        _portfolio(conn, "user_a", "Savings")

    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        _portfolio(conn, "user_a", "main")


def test_buy_round_trips_exact_decimals(db_engine: Engine):
    with db_engine.begin() as conn:
        buy_id = _trade(
            conn, "buys", _portfolio(conn), quantity="0.123456789012345678", total="12345.12345678"
        )
        row = conn.execute(
            text("SELECT quantity, total_usd, trade_date FROM buys WHERE id = :id"), {"id": buy_id}
        ).one()

    assert type(row.quantity) is Decimal and type(row.total_usd) is Decimal
    assert str(row.quantity) == "0.123456789012345678"
    assert str(row.total_usd) == "12345.12345678"
    assert row.trade_date == date(2026, 1, 2)


@pytest.mark.parametrize("table", ["buys", "sells", "allocations"])
def test_amount_columns_have_the_readme_types(db_engine: Engine, table: str):
    columns = {c["name"]: c["type"] for c in inspect(db_engine).get_columns(table)}
    expected = {"quantity": (38, 18)}
    if table != "allocations":
        expected |= {"total_usd": (28, 8), "fee_usd": (28, 8)}
        assert str(columns["trade_date"]) == "DATE"

    assert {name: (columns[name].precision, columns[name].scale) for name in expected} == expected


def test_deleting_a_portfolio_deletes_its_buys_sells_and_allocations(db_engine: Engine):
    with db_engine.begin() as conn:
        doomed = _portfolio(conn, name="Doomed")
        kept = _portfolio(conn, name="Kept")
        doomed_buy = _trade(conn, "buys", doomed)
        _allocation(conn, _trade(conn, "sells", doomed), doomed_buy)
        kept_buy = _trade(conn, "buys", kept)
        kept_sell = _trade(conn, "sells", kept)
        kept_allocation = _allocation(conn, kept_sell, kept_buy)

    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM portfolios WHERE id = :id"), {"id": doomed})

    with db_engine.connect() as conn:
        assert _ids(conn, "portfolios") == [kept]
        assert _ids(conn, "buys") == [kept_buy]
        assert _ids(conn, "sells") == [kept_sell]
        assert _ids(conn, "allocations") == [kept_allocation]
        conn.execute(text("DELETE FROM sells WHERE id = :id"), {"id": kept_sell})
        assert _ids(conn, "allocations") == []  # a sell takes its allocations with it
        assert _ids(conn, "buys") == [kept_buy]


def test_deleting_an_allocated_buy_raises_integrity_error(db_engine: Engine):
    with db_engine.begin() as conn:
        portfolio = _portfolio(conn)
        buy = _trade(conn, "buys", portfolio)
        _allocation(conn, _trade(conn, "sells", portfolio), buy)

    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(text("DELETE FROM buys WHERE id = :id"), {"id": buy})

    with db_engine.connect() as conn:
        assert _ids(conn, "buys") == [buy]


def test_downgrade_base_then_upgrade_head_succeeds(database_url):
    config = alembic_config(database_url)
    command.upgrade(config, "head")

    command.downgrade(config, "base")
    assert _tables(database_url) == ["alembic_version"]

    command.upgrade(config, "head")
    assert _tables(database_url) == ALL_TABLES
