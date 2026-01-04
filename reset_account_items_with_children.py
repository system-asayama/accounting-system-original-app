# reset_account_items_with_children.py

from app import (
    SessionLocal,
    AccountItem,
    CashBook,         # 現金出納帳
    GeneralLedger,    # 仕訳
    OpeningBalance,   # 期首残高
    Account,          # ★ ここを追加（accounts テーブルに対応するモデル名）
)

ORGANIZATION_ID = 1  # ★削除したい組織のID

def reset_account_items_and_related():
    db = SessionLocal()
    try:
        # 1) 現金出納帳（cash_books）を削除
        cb_deleted = db.query(CashBook).filter(
            CashBook.organization_id == ORGANIZATION_ID
        ).delete(synchronize_session=False)
        print(f"cash_books: {cb_deleted} 件削除")

        # 2) 総勘定元帳（general_ledgers）を削除
        gl_deleted = db.query(GeneralLedger).filter(
            GeneralLedger.organization_id == ORGANIZATION_ID
        ).delete(synchronize_session=False)
        print(f"general_ledgers: {gl_deleted} 件削除")

        # 3) 期首残高（opening_balances）を削除
        ob_deleted = db.query(OpeningBalance).filter(
            OpeningBalance.organization_id == ORGANIZATION_ID
        ).delete(synchronize_session=False)
        print(f"opening_balances: {ob_deleted} 件削除")

        # 4) 口座マスタ（accounts）を削除
        acc_deleted = db.query(Account).filter(
            Account.organization_id == ORGANIZATION_ID
        ).delete(synchronize_session=False)
        print(f"accounts: {acc_deleted} 件削除")

        # 5) 勘定科目（account_items）を削除
        ai_deleted = db.query(AccountItem).filter(
            AccountItem.organization_id == ORGANIZATION_ID
        ).delete(synchronize_session=False)
        print(f"account_items: {ai_deleted} 件削除")

        db.commit()
        print("✅ すべて削除してコミットしました")

    except Exception as e:
        db.rollback()
        print("❌ エラーが発生したためロールバックしました:", e)

    finally:
        db.close()


if __name__ == "__main__":
    reset_account_items_and_related()
