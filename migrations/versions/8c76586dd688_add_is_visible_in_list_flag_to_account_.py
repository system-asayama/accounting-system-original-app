"""Add is_visible_in_list flag to Account model

Revision ID: 8c76586dd688
Revises: ba90df057a34
Create Date: 2025-11-10 01:44:56.539331

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c76586dd688'
down_revision: Union[str, Sequence[str], None] = 'ba90df057a34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    accounts テーブルに is_visible_in_list カラムを追加する。
    すでに存在する場合はスキップする（安全対応）。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 既存カラムを確認
    columns = [col["name"] for col in inspector.get_columns("accounts")]

    # すでにカラムがある場合はスキップ
    if "is_visible_in_list" in columns:
        return

    # カラムが存在しない場合にのみ追加
    op.add_column(
        "accounts",
        sa.Column(
            "is_visible_in_list",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    """Downgrade schema.

    is_visible_in_list カラムがある場合のみ削除。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = [col["name"] for col in inspector.get_columns("accounts")]

    if "is_visible_in_list" not in columns:
        return

    op.drop_column("accounts", "is_visible_in_list")
