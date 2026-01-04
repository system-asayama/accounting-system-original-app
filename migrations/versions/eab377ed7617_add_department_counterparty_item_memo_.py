"""add department, counterparty, item, memo_tag models

Revision ID: eab377ed7617
Revises: 839ad96c8e8a
Create Date: 2025-11-09 19:34:15.517793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eab377ed7617'
down_revision: Union[str, Sequence[str], None] = '839ad96c8e8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # すでに departments がある = この migration は適用済みなのでスキップ
    if "departments" in existing_tables:
        return

    # departments テーブル作成
    op.create_table(
        'departments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # counterparties テーブル作成
    op.create_table(
        'counterparties',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # items テーブル作成
    op.create_table(
        'items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # memo_tags テーブル作成
    op.create_table(
        'memo_tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # cash_book_masters テーブル作成
    op.create_table(
        'cash_book_masters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(length=19), nullable=True),
        sa.Column('updated_at', sa.String(length=19), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('cash_book_masters')
    op.drop_table('memo_tags')
    op.drop_table('items')
    op.drop_table('counterparties')
    op.drop_table('departments')
