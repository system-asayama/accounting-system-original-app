"""create journal_entries table

Revision ID: 839ad96c8e8a
Revises: 39b00bf70153
Create Date: 2025-11-09 02:44:03.357852

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "839ad96c8e8a"
down_revision: Union[str, Sequence[str], None] = "39b00bf70153"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema (safe for existing tables)."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # ---- accounts ----
    if "accounts" not in existing_tables:
        op.create_table(
            "accounts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("account_name", sa.String(length=255), nullable=False),
            sa.Column("account_type", sa.String(length=50), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("bank_name", sa.String(length=255), nullable=True),
            sa.Column("branch_name", sa.String(length=255), nullable=True),
            sa.Column("account_number", sa.String(length=50), nullable=True),
            sa.Column("memo", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("account_name"),
        )

    # ---- tax_categories ----
    if "tax_categories" not in existing_tables:
        op.create_table(
            "tax_categories",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=50), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    # ---- journal_entries ----
    if "journal_entries" not in existing_tables:
        op.create_table(
            "journal_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("transaction_date", sa.String(length=10), nullable=False),
            sa.Column("debit_account_item_id", sa.Integer(), nullable=False),
            sa.Column("debit_amount", sa.Integer(), nullable=False),
            sa.Column("debit_tax_category_id", sa.Integer(), nullable=True),
            sa.Column("credit_account_item_id", sa.Integer(), nullable=False),
            sa.Column("credit_amount", sa.Integer(), nullable=False),
            sa.Column("credit_tax_category_id", sa.Integer(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(length=19), nullable=True),
            sa.Column("updated_at", sa.String(length=19), nullable=True),
            sa.ForeignKeyConstraint(
                ["credit_account_item_id"], ["account_items.id"]
            ),
            sa.ForeignKeyConstraint(
                ["credit_tax_category_id"], ["tax_categories.id"]
            ),
            sa.ForeignKeyConstraint(
                ["debit_account_item_id"], ["account_items.id"]
            ),
            sa.ForeignKeyConstraint(
                ["debit_tax_category_id"], ["tax_categories.id"]
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    # ---- expenses は、この段階であれば削除する ----
    if "expenses" in existing_tables:
        op.drop_table("expenses")


def downgrade() -> None:
    """Downgrade schema."""
    # 元の状態に戻すロジックはそのまま残しておきます
    op.create_table(
        "expenses",
        sa.Column("id", sa.INTEGER(), nullable=False),
        sa.Column("spent_on", sa.DATE(), nullable=False),
        sa.Column("vendor", sa.VARCHAR(length=120), nullable=False),
        sa.Column("amount", sa.NUMERIC(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.VARCHAR(length=8), nullable=False),
        sa.Column("memo", sa.VARCHAR(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.drop_table("journal_entries")
    op.drop_table("tax_categories")
    op.drop_table("accounts")
