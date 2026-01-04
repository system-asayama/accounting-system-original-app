# import_account_items_from_csv.py

import csv
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, AccountItem
from config import settings

# ==== DB 接続設定 ====
DATABASE_URL = settings.DATABASE_URL or "sqlite:///./accounting.db"
engine = create_engine(DATABASE_URL)
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)

# ==== CSV ファイルパス ====
# プロジェクト直下に freee_account_item_20251107.csv を置いた想定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE_PATH = os.path.join(BASE_DIR, "freee_account_item_20251107.csv")


def import_data(organization_id: int = 1):
    """
    freee の勘定科目 CSV から account_items テーブルにデータを投入する
    """
    session = DBSession()
    try:
        # 必要ならここで既存データを削除
        # session.query(AccountItem).filter(
        #     AccountItem.organization_id == organization_id
        # ).delete(synchronize_session=False)
        # session.commit()

        # freee のエクスポートは SJIS(CP932) のことが多いので cp932 を指定
        with open(CSV_FILE_PATH, mode="r", encoding="cp932") as f:
            reader = csv.reader(f)
            header = next(reader, None)  # ヘッダーを読み飛ばす
            print("Header:", header)

            imported = 0

            for line_no, row in enumerate(reader, start=2):  # 2行目から
                # 空行はスキップ
                if not row or all(not c.strip() for c in row):
                    continue

                # 列不足を避けるために長さを調整
                while len(row) < 11:
                    row.append("")

                # CSV → モデルのマッピング
                data = {
                    # 必須系
                    "organization_id": organization_id,
                    "account_name": row[0].strip(),         # 勘定科目
                    "display_name": (row[1] or row[0]).strip(),  # 表示名（空なら勘定科目名）

                    # freee の列順に合わせて
                    "sub_category": row[2].strip() or None,     # 小分類
                    "mid_category": row[3].strip() or None,     # 中分類
                    "major_category": row[4].strip() or None,   # 大分類

                    "income_counterpart": row[5].strip() or None,   # 収入取引相手方勘定科目
                    "expense_counterpart": row[6].strip() or None,  # 支出取引相手方勘定科目

                    # ★ 税区分は正しく 7 列目を使う ★
                    "tax_category": row[7].strip() or None,     # 税区分

                    "shortcut1": row[8].strip() or None,        # ショートカット1
                    "shortcut2": row[9].strip() or None,        # ショートカット2

                    # freee CSV では「補助科目優先タグ」だけ（YES/空）
                    "sub_account_priority_tag": (
                        row[10].strip().upper() == "YES"
                        if row[10].strip()
                        else False
                    ),

                    # CSV に列が無いので、とりあえず全部「入力候補」にする
                    "input_candidate": True,
                }

                if not data["account_name"]:
                    print(f"行 {line_no}: 勘定科目名が空のためスキップしました。")
                    continue

                account_item = AccountItem(**data)
                session.add(account_item)
                imported += 1

            session.commit()
            print(f"{imported} 件の勘定科目をインポートしました。")

    except Exception as e:
        session.rollback()
        print("インポート中にエラーが発生したためロールバックしました:", e)
    finally:
        session.close()


if __name__ == "__main__":
    print("Starting account item import ...")
    import_data(organization_id=1)  # 必要ならここで事業所IDを変更
    print("Import finished.")
