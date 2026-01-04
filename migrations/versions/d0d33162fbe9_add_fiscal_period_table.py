"""add_fiscal_period_table

Revision ID: d0d33162fbe9
Revises: 8c76586dd688
Create Date: 2025-11-10 01:xx:xx.xxxxxx
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d0d33162fbe9"
down_revision: Union[str, Sequence[str], None] = "8c76586dd688"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    fiscal_periods テーブルを追加するが、
    すでに存在する場合は何もしない（安全対応）。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = inspector.get_table_names()
    if "fiscal_periods" in existing_tables:
        # すでにテーブルがある場合はスキップ
        return

    op.create_table(
        "fiscal_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("start_date", sa.String(length=10), nullable=False),
        sa.Column("end_date", sa.String(length=10), nullable=False),
        sa.Column("business_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=19), nullable=True),
        sa.Column("updated_at", sa.String(length=19), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema.

    fiscal_periods テーブルがある場合のみ削除。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = inspector.get_table_names()
    if "fiscal_periods" not in existing_tables:
        return

    op.drop_table("fiscal_periods")
