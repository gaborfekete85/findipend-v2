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
    try:
        return sorted(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _portfolio(conn, user_id: str = "user_a", name: str = "Main") -> int:
    return conn.execute(
        text("INSERT INTO portfolios (user_id, name) VALUES (:u, :n) RETURNING id"),
        {"u": user_id, "n": name},
    ).scalar_one()


def _trade(conn, table: str, portfolio_id: int, quantity="1", total="100") -> int:
    return conn.execute(
        text(
            f"INSERT INTO {table} (portfolio_id, asset_id, asset_name, asset_symbol,"
            " quantity, total_usd, fee_usd, trade_date)"
            " VALUES (:p, 'bitcoin', 'Bitcoin', 'btc', :q, :t, 0, :d) RETURNING id"
        ),
        {"p": portfolio_id, "q": Decimal(quantity), "t": Decimal(total), "d": date(2026, 1, 2)},
    ).scalar_one()


def _allocation(conn, sell_id: int, buy_id: int) -> int:
    return conn.execute(
        text("INSERT INTO allocations (sell_id, buy_id, quantity) VALUES (:s, :b, 1) RETURNING id"),
        {"s": sell_id, "b": buy_id},
    ).scalar_one()


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


@pytest.mark.parametrize("table", ["buys", "sells"])
def test_trade_columns_have_the_readme_types(db_engine: Engine, table: str):
    columns = {c["name"]: c["type"] for c in inspect(db_engine).get_columns(table)}

    assert (columns["quantity"].precision, columns["quantity"].scale) == (38, 18)
    for name in ("total_usd", "fee_usd"):
        assert (columns[name].precision, columns[name].scale) == (28, 8), name
    assert str(columns["trade_date"]) == "DATE"


def test_allocation_quantity_has_the_readme_type(db_engine: Engine):
    columns = {c["name"]: c["type"] for c in inspect(db_engine).get_columns("allocations")}

    assert (columns["quantity"].precision, columns["quantity"].scale) == (38, 18)


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


def test_deleting_a_sell_deletes_its_allocations(db_engine: Engine):
    with db_engine.begin() as conn:
        portfolio = _portfolio(conn)
        buy = _trade(conn, "buys", portfolio)
        sell = _trade(conn, "sells", portfolio)
        _allocation(conn, sell, buy)
        conn.execute(text("DELETE FROM sells WHERE id = :id"), {"id": sell})

        assert _ids(conn, "allocations") == []
        assert _ids(conn, "buys") == [buy]


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
