"""Create account_items table

Revision ID: c396cdc809e0
Revises: d5502863913f
Create Date: 2025-11-06 20:38:40.930933

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c396cdc809e0"
down_revision: Union[str, Sequence[str], None] = "d5502863913f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema (safe for existing tables)."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # ---- account_items ----
    if "account_items" not in existing_tables:
        op.create_table(
            "account_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("account_name", sa.String(length=255), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("sub_category", sa.String(length=255), nullable=True),
            sa.Column("mid_category", sa.String(length=255), nullable=True),
            sa.Column("major_category", sa.String(length=255), nullable=True),
            sa.Column("income_counterpart", sa.String(length=255), nullable=True),
            sa.Column("expense_counterpart", sa.String(length=255), nullable=True),
            sa.Column("tax_category", sa.String(length=255), nullable=True),
            sa.Column("shortcut1", sa.String(length=50), nullable=True),
            sa.Column("shortcut2", sa.String(length=50), nullable=True),
            sa.Column("input_candidate", sa.Boolean(), nullable=True),
            sa.Column("sub_account_priority_tag", sa.Boolean(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("account_name"),
        )

    # ---- users ----
    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("users")
    op.drop_table("account_items")
