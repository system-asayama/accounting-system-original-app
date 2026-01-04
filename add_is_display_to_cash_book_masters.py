from db import SessionLocal
from sqlalchemy import text

def add_is_display_column():
    db = SessionLocal()
    try:
        # is_displayカラムを追加（デフォルト値は1=True）
        db.execute(text('ALTER TABLE cash_book_masters ADD COLUMN is_display INTEGER DEFAULT 1'))
        db.commit()
        print("is_display column added successfully")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == '__main__':
    add_is_display_column()
