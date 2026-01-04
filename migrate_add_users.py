#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ユーザー認証テーブルを追加するマイグレーションスクリプト
"""
from db import SessionLocal, engine
from sqlalchemy import text

def migrate():
    """usersテーブルとuser_organizationsテーブルを作成"""
    db = SessionLocal()
    try:
        # usersテーブルを作成
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                login_id VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'admin',
                organization_id INTEGER REFERENCES organizations(id),
                active BOOLEAN DEFAULT TRUE,
                is_owner BOOLEAN DEFAULT FALSE,
                can_manage_admins BOOLEAN DEFAULT FALSE,
                openai_api_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # user_organizationsテーブルを作成（多対多関係）
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_organizations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) NOT NULL,
                organization_id INTEGER REFERENCES organizations(id) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, organization_id)
            )
        """))
        
        db.commit()
        print("✅ マイグレーション完了: usersテーブルとuser_organizationsテーブルを作成しました")
        
    except Exception as e:
        db.rollback()
        print(f"❌ マイグレーションエラー: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
