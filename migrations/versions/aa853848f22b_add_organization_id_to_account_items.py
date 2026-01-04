"""add_organization_id_to_account_items

Revision ID: aa853848f22b
Revises: 1b17e357db63
Create Date: 2025-11-10 09:12:34.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "aa853848f22b"
down_revision: Union[str, Sequence[str], None] = "1b17e357db63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector, table_name: str) -> bool:
    """テーブルが存在するかチェック"""
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    """指定カラムが存在するかチェック"""
    cols = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in cols


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # account_items テーブルが存在し、まだ organization_id カラムが無いときだけ実行
    if _has_table(inspector, "account_items") and not _has_column(
        inspector, "account_items", "organization_id"
    ):
        with op.batch_alter_table("account_items", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            batch_op.create_foreign_key(
                "fk_account_items_organization",
                "organizations",
                ["organization_id"],
                ["id"],
            )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # account_items に organization_id がある場合のみ元に戻す
    if _has_table(inspector, "account_items") and _has_column(
        inspector, "account_items", "organization_id"
    ):
        with op.batch_alter_table("account_items", schema=None) as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_account_items_organization", type_="foreignkey"
                )
            except Exception:
                # 既に制約が無い場合でもエラーで止まらないようにする
                pass
            batch_op.drop_column("organization_id")
