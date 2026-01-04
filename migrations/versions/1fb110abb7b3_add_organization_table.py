"""add_organization_table

Revision ID: 1fb110abb7b3
Revises: d0d33162fbe9
Create Date: 2025-11-10 01:xx:xx.xxxxxx
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1fb110abb7b3"
down_revision: Union[str, Sequence[str], None] = "d0d33162fbe9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    organizations テーブルを追加するが、
    すでに存在する場合は何もしない（安全対応）。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = inspector.get_table_names()
    if "organizations" in existing_tables:
        # すでにテーブルがある場合はスキップ
        return

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema.

    organizations テーブルがある場合のみ削除。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = inspector.get_table_names()
    if "organizations" not in existing_tables:
        return

    op.drop_table("organizations")
