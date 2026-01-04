from models import JournalEntry, GeneralLedger
from db import SessionLocal
from datetime import datetime

db = SessionLocal()

try:
    # すべての振替伝票を取得
    journal_entries = db.query(JournalEntry).all()
    
    migrated_count = 0
    
    for entry in journal_entries:
        # 既に仕訳帳マスタに登録されているかチェック
        existing = db.query(GeneralLedger).filter(
            GeneralLedger.source_type == 'journal_entry',
            GeneralLedger.source_id == entry.id
        ).first()
        
        if not existing:
            # 仕訳帳マスタに登録
            general_ledger_entry = GeneralLedger(
                organization_id=entry.organization_id,
                transaction_date=entry.transaction_date,
                debit_account_item_id=entry.debit_account_item_id,
                debit_amount=entry.debit_amount,
                debit_tax_category_id=entry.debit_tax_category_id,
                credit_account_item_id=entry.credit_account_item_id,
                credit_amount=entry.credit_amount,
                credit_tax_category_id=entry.credit_tax_category_id,
                summary=entry.summary,
                remarks=entry.remarks,
                source_type='journal_entry',
                source_id=entry.id,
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.add(general_ledger_entry)
            migrated_count += 1
    
    db.commit()
    print(f"{migrated_count}件の振替伝票を仕訳帳マスタに移行しました")
    
except Exception as e:
    db.rollback()
    print(f"エラーが発生しました: {str(e)}")
finally:
    db.close()
