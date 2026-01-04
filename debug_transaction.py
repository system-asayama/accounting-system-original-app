#!/usr/bin/env python3.11
import sys
sys.path.insert(0, '/home/ubuntu/accounting-system-app')

from db import SessionLocal
from models import ImportedTransaction, AccountItem

db = SessionLocal()

try:
    # ID 7の取引を取得
    transaction = db.query(ImportedTransaction).filter(ImportedTransaction.id == 7).first()
    
    if transaction:
        print(f"Transaction ID: {transaction.id}")
        print(f"Account Name: {transaction.account_name}")
        print(f"Description: {transaction.description}")
        print(f"Status: {transaction.status}")
        print(f"account_item_id: {transaction.account_item_id}")
        print(f"account_item_id type: {type(transaction.account_item_id)}")
        
        if transaction.account_item_id:
            account_item = db.query(AccountItem).filter(AccountItem.id == transaction.account_item_id).first()
            if account_item:
                print(f"Account Item Name: {account_item.account_name}")
        
        # すべての勘定科目を取得
        print("\nAll Account Items:")
        account_items = db.query(AccountItem).order_by(AccountItem.id.asc()).all()
        for item in account_items:
            selected = "*** SELECTED ***" if transaction.account_item_id == item.id else ""
            print(f"  ID: {item.id}, Name: {item.account_name} {selected}")
    else:
        print("Transaction not found")
        
finally:
    db.close()
