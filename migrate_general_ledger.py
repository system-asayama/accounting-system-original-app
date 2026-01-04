from models import Base, GeneralLedger
from db import engine

# テーブルを作成
Base.metadata.create_all(engine)
print("GeneralLedgerテーブルを作成しました")
