"""Create cash_books table

Revision ID: 7379a6cf1148
Revises: c396cdc809e0
Create Date: 2025-11-06 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7379a6cf1148"
down_revision: Union[str, Sequence[str], None] = "c396cdc809e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema (safe for existing cash_books)."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # すでに cash_books テーブルがある場合は何もしない
    if "cash_books" in existing_tables:
        return

    op.create_table(
        "cash_books",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.String(length=10), nullable=False),
        sa.Column("account_item_id", sa.Integer(), nullable=False),
        sa.Column("tax_category", sa.String(length=50), nullable=True),
        sa.Column("tax_rate", sa.String(length=10), nullable=True),
        sa.Column("counterparty", sa.String(length=255), nullable=True),
        sa.Column("item_name", sa.String(length=255), nullable=True),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("memo_tag", sa.String(length=255), nullable=True),
        sa.Column("payment_account", sa.String(length=255), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("amount_with_tax", sa.Integer(), nullable=False),
        sa.Column("amount_without_tax", sa.Integer(), nullable=True),
        sa.Column("tax_amount", sa.Integer(), nullable=True),
        sa.Column("balance", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(length=19), nullable=True),
        sa.Column("updated_at", sa.String(length=19), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_item_id"], ["account_items.id"]),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("cash_books")
