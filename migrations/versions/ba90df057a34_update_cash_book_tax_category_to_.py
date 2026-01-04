"""update_cash_book_tax_category_to_foreign_key

Revision ID: ba90df057a34
Revises: 3304009966e9
Create Date: 2025-11-09 23:16:24.050861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ba90df057a34"
down_revision: Union[str, Sequence[str], None] = "3304009966e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    cash_books.tax_category (文字列) を tax_categories への外部キー tax_category_id に変更する。
    すでに tax_category_id が存在する場合は「適用済み」とみなして何もしない。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # cash_books テーブルのカラム一覧を取得
    columns = [c["name"] for c in inspector.get_columns("cash_books")]

    # すでに tax_category_id カラムがある → 以前にこの変更は適用済みとして何もしない
    if "tax_category_id" in columns:
        return

    with op.batch_alter_table("cash_books", schema=None) as batch_op:
        # tax_category_id カラムがなければ追加
        if "tax_category_id" not in columns:
            batch_op.add_column(
                sa.Column("tax_category_id", sa.Integer(), nullable=True)
            )

        # 外部キー制約を追加（既に存在していた場合に備えて try/except）
        try:
            batch_op.create_foreign_key(
                "fk_cash_books_tax_category_id",
                "tax_categories",
                ["tax_category_id"],
                ["id"],
            )
        except Exception:
            # すでに同名の制約がある場合などは無視
            pass

        # 旧カラム tax_category があるなら削除
        if "tax_category" in columns:
            batch_op.drop_column("tax_category")


def downgrade() -> None:
    """Downgrade schema.

    tax_category_id を削除し、元の tax_category (文字列) に戻す。
    実運用で downgrade することはほぼ無い想定。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = [c["name"] for c in inspector.get_columns("cash_books")]

    # tax_category_id が無ければ何もしない
    if "tax_category_id" not in columns:
        return

    with op.batch_alter_table("cash_books", schema=None) as batch_op:
        # 旧カラム tax_category が無ければ一応作っておく
        if "tax_category" not in columns:
            batch_op.add_column(
                sa.Column("tax_category", sa.String(length=50), nullable=True)
            )

        # 外部キー制約を削除（存在しない可能性もあるので try/except）
        try:
            batch_op.drop_constraint(
                "fk_cash_books_tax_category_id", type_="foreignkey"
            )
        except Exception:
            pass

        # tax_category_id カラムのみ削除（tax_category は残す）
        batch_op.drop_column("tax_category_id")
