# -*- coding: utf-8 -*-
"""
データベースマイグレーション
アプリケーション起動時に自動的に実行される
"""

from sqlalchemy import text
from app.db import SessionLocal
import logging

logger = logging.getLogger(__name__)


def check_column_exists(db, table_name, column_name):
    """カラムが存在するかチェック"""
    try:
        result = db.execute(text(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = CURRENT_SCHEMA() "
            "AND TABLE_NAME = :table_name "
            "AND COLUMN_NAME = :column_name"
        ), {"table_name": table_name, "column_name": column_name})
        count = result.scalar()
        return count > 0
    except Exception as e:
        logger.error(f"カラム存在チェックエラー: {e}")
        return False


def add_column_if_not_exists(db, table_name, column_name, column_definition):
    """カラムが存在しない場合は追加（PostgreSQL用）"""
    try:
        if not check_column_exists(db, table_name, column_name):
            # PostgreSQLではダブルクォートを使用し、AFTER句は使用しない
            sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_definition}'
            logger.info(f"カラムを追加: {table_name}.{column_name}")
            db.execute(text(sql))
            db.commit()
            logger.info(f"カラム追加完了: {table_name}.{column_name}")
            return True
        else:
            logger.info(f"カラムは既に存在: {table_name}.{column_name}")
            return False
    except Exception as e:
        logger.error(f"カラム追加エラー: {table_name}.{column_name} - {e}")
        db.rollback()
        return False


def run_migrations():
    """すべてのマイグレーションを実行"""
    logger.info("マイグレーション開始")
    db = SessionLocal()
    
    try:
        # T_店舗テーブルに新しいカラムを追加
        # PostgreSQLでは AFTER 句を使わず、カラムは末尾に追加される
        migrations = [
            ("T_店舗", "郵便番号", "VARCHAR(10) NULL"),
            ("T_店舗", "住所", "VARCHAR(500) NULL"),
            ("T_店舗", "電話番号", "VARCHAR(20) NULL"),
            ("T_店舗", "email", "VARCHAR(255) NULL"),
            ("T_店舗", "openai_api_key", "VARCHAR(255) NULL"),
            ("T_店舗", "updated_at", "TIMESTAMP NULL"),
        ]
        
        added_count = 0
        for table_name, column_name, column_def in migrations:
            if add_column_if_not_exists(db, table_name, column_name, column_def):
                added_count += 1
        
        if added_count > 0:
            logger.info(f"マイグレーション完了: {added_count}個のカラムを追加しました")
        else:
            logger.info("マイグレーション完了: 追加するカラムはありませんでした")
            
    except Exception as e:
        logger.error(f"マイグレーション実行エラー: {e}")
        db.rollback()
    finally:
        db.close()
