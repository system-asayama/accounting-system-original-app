import os
import sys
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# パスを追加してモジュールをインポートできるようにする
sys.path.append(os.path.dirname(__file__))

from models import Organization, Base
from db import SessionLocal, engine

def delete_all_organizations():
    """データベースからすべてのOrganizationレコードを削除する"""
    db = SessionLocal()
    try:
        # Organizationテーブルの全レコードを削除
        num_deleted = db.query(Organization).delete()
        db.commit()
        print(f"成功: {num_deleted} 件の事業所レコードを削除しました。")
    except Exception as e:
        db.rollback()
        print(f"エラー: 事業所レコードの削除中にエラーが発生しました: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    delete_all_organizations()
