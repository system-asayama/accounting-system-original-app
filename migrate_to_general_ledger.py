#!/usr/bin/env python3.11
"""
journal_entriesテーブルのデータをgeneral_ledgerテーブルに移行するスクリプト

このスクリプトは、imported_transactionsから登録されたjournal_entriesのデータを
general_ledgerテーブルに移行します。
"""

from db import SessionLocal
from models import JournalEntry, GeneralLedger, ImportedTransaction
from datetime import datetime

def migrate_journal_entries_to_general_ledger():
    """journal_entriesからgeneral_ledgerへデータを移行"""
    db = SessionLocal()
    try:
        # imported_transactionsから登録されたjournal_entry_idを取得
        imported_transactions = db.query(ImportedTransaction).filter(
            ImportedTransaction.journal_entry_id.isnot(None)
        ).all()
        
        print(f"処理対象の取引明細: {len(imported_transactions)}件")
        
        migrated_count = 0
        skipped_count = 0
        
        for imported_tx in imported_transactions:
            journal_entry_id = imported_tx.journal_entry_id
            
            # 既にgeneral_ledgerに存在するか確認
            existing_gl = db.query(GeneralLedger).filter(
                GeneralLedger.source_type == 'imported_transaction',
                GeneralLedger.source_id == imported_tx.id
            ).first()
            
            if existing_gl:
                print(f"  スキップ: 取引ID {imported_tx.id} (既に移行済み)")
                skipped_count += 1
                continue
            
            # journal_entriesからデータを取得
            journal_entry = db.query(JournalEntry).filter(
                JournalEntry.id == journal_entry_id
            ).first()
            
            if not journal_entry:
                print(f"  エラー: journal_entry_id {journal_entry_id} が見つかりません")
                continue
            
            # general_ledgerに新規レコードを作成
            new_gl = GeneralLedger(
                organization_id=journal_entry.organization_id,
                transaction_date=journal_entry.transaction_date,
                debit_account_item_id=journal_entry.debit_account_item_id,
                debit_amount=journal_entry.debit_amount,
                debit_tax_category_id=journal_entry.debit_tax_category_id,
                credit_account_item_id=journal_entry.credit_account_item_id,
                credit_amount=journal_entry.credit_amount,
                credit_tax_category_id=journal_entry.credit_tax_category_id,
                summary=journal_entry.summary,
                remarks=journal_entry.remarks,
                source_type='imported_transaction',
                source_id=imported_tx.id,
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            db.add(new_gl)
            
            print(f"  移行: 取引ID {imported_tx.id} ({imported_tx.transaction_date})")
            migrated_count += 1
        
        # コミット
        db.commit()
        
        print(f"\n移行完了:")
        print(f"  移行件数: {migrated_count}件")
        print(f"  スキップ件数: {skipped_count}件")
        
    except Exception as e:
        db.rollback()
        print(f"エラーが発生しました: {e}")
        raise
    finally:
        db.close()

if __name__ == '__main__':
    print("journal_entriesからgeneral_ledgerへのデータ移行を開始します...")
    migrate_journal_entries_to_general_ledger()
    print("データ移行が完了しました。")
