#!/usr/bin/env python3.11
"""
journal_entriesテーブルの振替伝票データをgeneral_ledgerテーブルに移行するスクリプト

このスクリプトは、取引明細に関連付けられていないjournal_entriesのデータ（純粋な振替伝票）を
general_ledgerテーブルに移行します。
"""

from db import SessionLocal
from models import JournalEntry, GeneralLedger, ImportedTransaction
from datetime import datetime

def migrate_journal_entries_to_general_ledger():
    """振替伝票からgeneral_ledgerへデータを移行"""
    db = SessionLocal()
    try:
        # imported_transactionsに関連付けられているjournal_entry_idを取得
        imported_journal_entry_ids = [
            it.journal_entry_id 
            for it in db.query(ImportedTransaction.journal_entry_id).filter(
                ImportedTransaction.journal_entry_id.isnot(None)
            ).all()
        ]
        
        print(f"取引明細に関連付けられているjournal_entry_id: {imported_journal_entry_ids}")
        
        # 取引明細に関連付けられていないjournal_entries（純粋な振替伝票）を取得
        journal_entries = db.query(JournalEntry).filter(
            ~JournalEntry.id.in_(imported_journal_entry_ids)
        ).all()
        
        print(f"処理対象の振替伝票: {len(journal_entries)}件")
        
        migrated_count = 0
        skipped_count = 0
        
        for je in journal_entries:
            # 既にgeneral_ledgerに存在するか確認
            existing_gl = db.query(GeneralLedger).filter(
                GeneralLedger.source_type == 'journal_entry',
                GeneralLedger.source_id == je.id
            ).first()
            
            if existing_gl:
                print(f"  スキップ: journal_entry ID {je.id} (既に移行済み)")
                skipped_count += 1
                continue
            
            # general_ledgerに新規レコードを作成
            new_gl = GeneralLedger(
                organization_id=je.organization_id,
                transaction_date=je.transaction_date,
                debit_account_item_id=je.debit_account_item_id,
                debit_amount=je.debit_amount,
                debit_tax_category_id=je.debit_tax_category_id,
                credit_account_item_id=je.credit_account_item_id,
                credit_amount=je.credit_amount,
                credit_tax_category_id=je.credit_tax_category_id,
                summary=je.summary,
                remarks=je.remarks,
                source_type='journal_entry',
                source_id=je.id,
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            db.add(new_gl)
            
            print(f"  移行: journal_entry ID {je.id} ({je.transaction_date}, {je.summary})")
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
    print("振替伝票からgeneral_ledgerへのデータ移行を開始します...")
    migrate_journal_entries_to_general_ledger()
    print("データ移行が完了しました。")
