"""Add import_templates table

Revision ID: 39b00bf70153
Revises: 7379a6cf1148
Create Date: 2025-11-06 20:50:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "39b00bf70153"
down_revision: Union[str, Sequence[str], None] = "7379a6cf1148"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema (safe for existing import_templates)."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # すでに import_templates テーブルがある場合は何もしない
    if "import_templates" in existing_tables:
        return

    op.create_table(
        "import_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("mapping_json", sa.Text(), nullable=False),
        sa.Column("skip_rows", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("import_templates")
