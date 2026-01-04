# delete_account_items.py

from app import SessionLocal, AccountItem

# ★ 直接 organization_id を指定
ORGANIZATION_ID = 1

def delete_all_account_items():
    db = SessionLocal()
    try:
        deleted_count = db.query(AccountItem).filter(
            AccountItem.organization_id == ORGANIZATION_ID
        ).delete(synchronize_session=False)

        db.commit()
        print(f"{deleted_count} 件の勘定科目を削除しました（organization_id={ORGANIZATION_ID}）")

    except Exception as e:
        db.rollback()
        print("エラーが発生したためロールバックしました:", e)

    finally:
        db.close()


if __name__ == "__main__":
    delete_all_account_items()
