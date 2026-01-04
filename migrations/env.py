from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic Config オブジェクト
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# アプリ側のメタデータを読み込む
from models import Base
target_metadata = Base.metadata


def get_url() -> str:
    """
    DATABASE_URL（Heroku）を最優先で取得し、
    postgres:// → postgresql:// に変換する。
    無ければ alembic.ini の sqlalchemy.url を使う。
    """
    # 1) Heroku / .env の DATABASE_URL を優先
    url = os.getenv("DATABASE_URL")

    # 2) 無ければ alembic.ini を見る（ローカル用）
    if not url:
        url = config.get_main_option("sqlalchemy.url")

    if not url:
        raise RuntimeError("DATABASE_URL and sqlalchemy.url are both not set")

    # 3) Heroku 形式 postgres:// を SQLAlchemy 2 用に変換
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


def run_migrations_offline():
    """'offline' モードでのマイグレーション."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """'online' モードでのマイグレーション."""
    # engine_from_config に渡す設定 dict を作成
    configuration = {
        "sqlalchemy.url": get_url(),
    }

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
