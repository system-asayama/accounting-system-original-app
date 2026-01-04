#!/usr/bin/env python3
"""
login-system-appのテーブル構造をHerokuに作成
"""
from utils.db import get_db

if __name__ == "__main__":
    print("login-system-appのテーブル構造を作成中...")
    conn = get_db()
    print("✅ テーブル作成完了")
    conn.close()
