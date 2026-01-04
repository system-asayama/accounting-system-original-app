#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSVファイルから勘定科目マスターを更新するスクリプト
"""
import csv
import os
from datetime import datetime
from db import SessionLocal
from models import AccountItem, Organization

def update_account_items_from_csv(csv_file_path, organization_id=1):
    """
    CSVファイルから勘定科目マスターを更新する
    
    Args:
        csv_file_path: CSVファイルのパス
        organization_id: 事業所ID（デフォルト: 1）
    """
    db = SessionLocal()
    
    try:
        # 既存の勘定科目を削除（organization_idに紐づくもの）
        print(f"既存の勘定科目（organization_id={organization_id}）を削除中...")
        deleted_count = db.query(AccountItem).filter(
            AccountItem.organization_id == organization_id
        ).delete()
        print(f"削除した勘定科目数: {deleted_count}")
        
        # CSVファイルを読み込み
        print(f"\nCSVファイルを読み込み中: {csv_file_path}")
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # ヘッダーを確認
            fieldnames = reader.fieldnames
            print(f"CSVヘッダー: {fieldnames}")
            
            # 各行を処理
            count = 0
            for row in reader:
                # 勘定科目名が空の場合はスキップ
                if not row.get('勘定科目', '').strip():
                    continue
                
                # AccountItemオブジェクトを作成
                account_item = AccountItem(
                    organization_id=organization_id,
                    account_name=row.get('勘定科目', '').strip(),
                    display_name=row.get('表示名（決算書）', '').strip() or None,
                    sub_category=row.get('小分類', '').strip() or None,
                    mid_category=row.get('中分類', '').strip() or None,
                    major_category=row.get('大分類', '').strip() or None,
                    income_counterpart=row.get('収入取引相手方勘定科目', '').strip() or None,
                    expense_counterpart=row.get('支出取引相手方勘定科目', '').strip() or None,
                    tax_category=row.get('税区分', '').strip() or None,
                    shortcut1=row.get('ショートカット1', '').strip() or None,
                    shortcut2=row.get('ショートカット2', '').strip() or None,
                    # 補助科目優先タグは空欄の場合False、YESの場合True
                    sub_account_priority_tag=row.get('補助科目優先タグ', '').strip().upper() == 'YES'
                )
                
                db.add(account_item)
                count += 1
                
                if count % 50 == 0:
                    print(f"処理中... {count}件")
        
        # コミット
        db.commit()
        print(f"\n完了: {count}件の勘定科目を登録しました")
        
        # 登録結果を確認
        print("\n登録結果の確認:")
        total = db.query(AccountItem).filter(
            AccountItem.organization_id == organization_id
        ).count()
        print(f"総勘定科目数: {total}")
        
        # 利益剰余金の小分類を確認
        print("\n「利益剰余金」の小分類:")
        profit_items = db.query(AccountItem).filter(
            AccountItem.organization_id == organization_id,
            AccountItem.mid_category == '利益剰余金'
        ).all()
        
        for item in profit_items:
            print(f"  - {item.account_name}: 小分類={item.sub_category}, 中分類={item.mid_category}, 大分類={item.major_category}")
        
    except Exception as e:
        db.rollback()
        print(f"\nエラーが発生しました: {e}")
        raise
    finally:
        db.close()

if __name__ == '__main__':
    # CSVファイルのパス
    csv_file = '/home/ubuntu/freee_account_item_utf8.csv'
    
    # 事業所IDを取得（最初の事業所を使用）
    db = SessionLocal()
    try:
        org = db.query(Organization).first()
        if org:
            org_id = org.id
            print(f"事業所ID {org_id} ({org.name}) の勘定科目を更新します")
        else:
            # 事業所が存在しない場合はデフォルトの事業所を作成
            print("事業所が存在しないため、デフォルト事業所を作成します")
            org = Organization(
                name='デフォルト事業所',
                business_type='corporate',
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.add(org)
            db.commit()
            org_id = org.id
            print(f"事業所ID {org_id} を作成しました")
    finally:
        db.close()
    
    # インポート実行
    update_account_items_from_csv(csv_file, org_id)
