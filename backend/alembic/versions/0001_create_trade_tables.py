"""create portfolios, buys, sells and allocations"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def _trade_columns() -> list[sa.Column]:
    fk = sa.ForeignKey("portfolios.id", ondelete="CASCADE")
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(), fk, nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("asset_name", sa.String(), nullable=False),
        sa.Column("asset_symbol", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("total_usd", sa.Numeric(28, 8), nullable=False),
        sa.Column("fee_usd", sa.Numeric(28, 8), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        *_timestamps(),
    ]


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        *_timestamps(),
    )
    op.create_index(
        "uq_portfolios_user_id_lower_name", "portfolios", ["user_id", sa.text("lower(name)")],
        unique=True,
    )
    op.create_table("buys", *_trade_columns())
    op.create_table("sells", *_trade_columns())
    # Deferred: see the comment on Allocation.buy_id in app/models.
    buy_fk = sa.ForeignKey("buys.id", deferrable=True, initially="DEFERRED")
    op.create_table(
        "allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sell_id", sa.Integer(), sa.ForeignKey("sells.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("buy_id", sa.Integer(), buy_fk, nullable=False),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("allocations")
    op.drop_table("sells")
    op.drop_table("buys")
    op.drop_table("portfolios")  # drops its index too
