from db import SessionLocal, engine
from models import Base

# データベーステーブルを作成・更新
Base.metadata.create_all(bind=engine)
print('Migration completed successfully')
