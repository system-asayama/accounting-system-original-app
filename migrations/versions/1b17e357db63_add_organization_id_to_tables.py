"""add_organization_id_to_tables

Revision ID: 1b17e357db63
Revises: 1fb110abb7b3
Create Date: 2025-11-10 08:41:30.576020

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1b17e357db63"
down_revision: Union[str, Sequence[str], None] = "1fb110abb7b3"
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

    # --- cash_books テーブル ---
    if _has_table(inspector, "cash_books") and not _has_column(
        inspector, "cash_books", "organization_id"
    ):
        with op.batch_alter_table("cash_books", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            batch_op.create_foreign_key(
                "fk_cash_books_organization",
                "organizations",
                ["organization_id"],
                ["id"],
            )

    # --- accounts テーブル（unique制約を削除するため recreate='always'） ---
    if _has_table(inspector, "accounts") and not _has_column(
        inspector, "accounts", "organization_id"
    ):
        with op.batch_alter_table("accounts", schema=None, recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            batch_op.create_foreign_key(
                "fk_accounts_organization",
                "organizations",
                ["organization_id"],
                ["id"],
            )

    # --- departments テーブル ---
    if _has_table(inspector, "departments") and not _has_column(
        inspector, "departments", "organization_id"
    ):
        with op.batch_alter_table(
            "departments", schema=None, recreate="always"
        ) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            batch_op.create_foreign_key(
                "fk_departments_organization",
                "organizations",
                ["organization_id"],
                ["id"],
            )

    # --- counterparties テーブル ---
    if _has_table(inspector, "counterparties") and not _has_column(
        inspector, "counterparties", "organization_id"
    ):
        with op.batch_alter_table(
            "counterparties", schema=None, recreate="always"
        ) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            batch_op.create_foreign_key(
                "fk_counterparties_organization",
                "organizations",
                ["organization_id"],
                ["id"],
            )

    # --- items テーブル ---
    if _has_table(inspector, "items") and not _has_column(
        inspector, "items", "organization_id"
    ):
        with op.batch_alter_table("items", schema=None, recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            batch_op.create_foreign_key(
                "fk_items_organization",
                "organizations",
                ["organization_id"],
                ["id"],
            )

    # --- memo_tags テーブル ---
    if _has_table(inspector, "memo_tags") and not _has_column(
        inspector, "memo_tags", "organization_id"
    ):
        with op.batch_alter_table("memo_tags", schema=None, recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            batch_op.create_foreign_key(
                "fk_memo_tags_organization",
                "organizations",
                ["organization_id"],
                ["id"],
            )

    # --- journal_entries テーブル ---
    if _has_table(inspector, "journal_entries") and not _has_column(
        inspector, "journal_entries", "organization_id"
    ):
        with op.batch_alter_table("journal_entries", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            batch_op.create_foreign_key(
                "fk_journal_entries_organization",
                "organizations",
                ["organization_id"],
                ["id"],
            )

    # --- cash_book_masters テーブル ---
    if _has_table(inspector, "cash_book_masters") and not _has_column(
        inspector, "cash_book_masters", "organization_id"
    ):
        with op.batch_alter_table(
            "cash_book_masters", schema=None, recreate="always"
        ) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            batch_op.create_foreign_key(
                "fk_cash_book_masters_organization",
                "organizations",
                ["organization_id"],
                ["id"],
            )

    # --- fiscal_periods テーブル ---
    if _has_table(inspector, "fiscal_periods") and not _has_column(
        inspector, "fiscal_periods", "organization_id"
    ):
        with op.batch_alter_table("fiscal_periods", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            batch_op.create_foreign_key(
                "fk_fiscal_periods_organization",
                "organizations",
                ["organization_id"],
                ["id"],
            )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # fiscal_periods
    if _has_table(inspector, "fiscal_periods") and _has_column(
        inspector, "fiscal_periods", "organization_id"
    ):
        with op.batch_alter_table("fiscal_periods", schema=None) as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_fiscal_periods_organization", type_="foreignkey"
                )
            except Exception:
                pass
            batch_op.drop_column("organization_id")

    # cash_book_masters
    if _has_table(inspector, "cash_book_masters") and _has_column(
        inspector, "cash_book_masters", "organization_id"
    ):
        with op.batch_alter_table(
            "cash_book_masters", schema=None, recreate="always"
        ) as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_cash_book_masters_organization", type_="foreignkey"
                )
            except Exception:
                pass
            batch_op.drop_column("organization_id")
            # もともとの unique を復元（必要なら）
            batch_op.create_unique_constraint("cash_book_masters_name_key", ["name"])

    # journal_entries
    if _has_table(inspector, "journal_entries") and _has_column(
        inspector, "journal_entries", "organization_id"
    ):
        with op.batch_alter_table("journal_entries", schema=None) as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_journal_entries_organization", type_="foreignkey"
                )
            except Exception:
                pass
            batch_op.drop_column("organization_id")

    # memo_tags
    if _has_table(inspector, "memo_tags") and _has_column(
        inspector, "memo_tags", "organization_id"
    ):
        with op.batch_alter_table("memo_tags", schema=None, recreate="always") as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_memo_tags_organization", type_="foreignkey"
                )
            except Exception:
                pass
            batch_op.drop_column("organization_id")
            batch_op.create_unique_constraint("memo_tags_name_key", ["name"])

    # items
    if _has_table(inspector, "items") and _has_column(
        inspector, "items", "organization_id"
    ):
        with op.batch_alter_table("items", schema=None, recreate="always") as batch_op:
            try:
                batch_op.drop_constraint("fk_items_organization", type_="foreignkey")
            except Exception:
                pass
            batch_op.drop_column("organization_id")
            batch_op.create_unique_constraint("items_name_key", ["name"])

    # counterparties
    if _has_table(inspector, "counterparties") and _has_column(
        inspector, "counterparties", "organization_id"
    ):
        with op.batch_alter_table(
            "counterparties", schema=None, recreate="always"
        ) as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_counterparties_organization", type_="foreignkey"
                )
            except Exception:
                pass
            batch_op.drop_column("organization_id")
            batch_op.create_unique_constraint("counterparties_name_key", ["name"])

    # departments
    if _has_table(inspector, "departments") and _has_column(
        inspector, "departments", "organization_id"
    ):
        with op.batch_alter_table(
            "departments", schema=None, recreate="always"
        ) as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_departments_organization", type_="foreignkey"
                )
            except Exception:
                pass
            batch_op.drop_column("organization_id")
            batch_op.create_unique_constraint("departments_name_key", ["name"])

    # accounts
    if _has_table(inspector, "accounts") and _has_column(
        inspector, "accounts", "organization_id"
    ):
        with op.batch_alter_table("accounts", schema=None, recreate="always") as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_accounts_organization", type_="foreignkey"
                )
            except Exception:
                pass
            batch_op.drop_column("organization_id")
            # もともとの unique(account_name) を復元
            batch_op.create_unique_constraint(None, ["account_name"])

    # cash_books
    if _has_table(inspector, "cash_books") and _has_column(
        inspector, "cash_books", "organization_id"
    ):
        with op.batch_alter_table("cash_books", schema=None) as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_cash_books_organization", type_="foreignkey"
                )
            except Exception:
                pass
            batch_op.drop_column("organization_id")
