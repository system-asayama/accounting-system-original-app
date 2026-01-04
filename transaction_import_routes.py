# 取引明細インポート機能のルート

import csv
import io
from datetime import datetime
from flask import request, render_template, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import openpyxl
from db import SessionLocal
from models import ImportedTransaction, Account, AccountItem, JournalEntry, Organization

def get_current_organization():
    """現在の事業所を取得（仮実装）"""
    db = SessionLocal()
    try:
        org = db.query(Organization).first()
        return org
    finally:
        db.close()

# ========== 取引明細インポート ==========
def transaction_import_page():
    """取引明細インポートページ"""
    db = SessionLocal()
    try:
        # 登録済み口座を取得
        accounts = db.query(Account).filter(
            Account.is_visible_in_list == 1
        ).order_by(Account.id.asc()).all()
        
        return render_template(
            'transactions/import.html',
            accounts=accounts
        )
    finally:
        db.close()

def transaction_import_upload():
    """取引明細のアップロード処理"""
    db = SessionLocal()
    try:
        # フォームデータの取得
        account_id = request.form.get('account_id', type=int)
        file = request.files.get('file')
        
        if not account_id or not file:
            flash('口座とファイルを選択してください', 'error')
            return redirect(url_for('transaction_import'))
        
        # 口座情報を取得
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            flash('選択された口座が見つかりません', 'error')
            return redirect(url_for('transaction_import'))
        
        # ファイルの拡張子を確認
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        # 現在の事業所を取得
        current_org = get_current_organization()
        if not current_org:
            flash('事業所が見つかりません', 'error')
            return redirect(url_for('transaction_import'))
        
        imported_count = 0
        
        # CSVファイルの処理
        if file_ext == 'csv':
            # CSVファイルを読み込み
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'), newline=None)
            csv_reader = csv.DictReader(stream)
            
            for row in csv_reader:
                # 取引日のパース
                transaction_date = row.get('取引日', '').strip()
                if not transaction_date:
                    continue
                
                # 日付フォーマットの変換（YYYY-MM-DD形式に統一）
                try:
                    date_obj = datetime.strptime(transaction_date, '%Y-%m-%d')
                    transaction_date = date_obj.strftime('%Y-%m-%d')
                except:
                    try:
                        date_obj = datetime.strptime(transaction_date, '%Y/%m/%d')
                        transaction_date = date_obj.strftime('%Y-%m-%d')
                    except:
                        continue
                
                # 摘要
                description = row.get('摘要', '').strip()
                
                # 入金金額
                income_str = row.get('入金金額', '0').strip().replace(',', '')
                income_amount = int(income_str) if income_str and income_str != '' else 0
                
                # 出金金額
                expense_str = row.get('出金金額', '0').strip().replace(',', '')
                expense_amount = int(expense_str) if expense_str and expense_str != '' else 0
                
                # ImportedTransactionを作成
                imported_transaction = ImportedTransaction(
                    organization_id=current_org.id,
                    account_name=account.account_name,
                    transaction_date=transaction_date,
                    description=description,
                    income_amount=income_amount,
                    expense_amount=expense_amount,
                    status=0,  # 未処理
                    imported_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                )
                db.add(imported_transaction)
                imported_count += 1
        
        # Excelファイルの処理
        elif file_ext in ['xlsx', 'xls']:
            # Excelファイルを読み込み
            workbook = openpyxl.load_workbook(file)
            sheet = workbook.active
            
            # ヘッダー行を取得（1行目）
            headers = [cell.value for cell in sheet[1]]
            
            # データ行を処理（2行目以降）
            for row in sheet.iter_rows(min_row=2, values_only=True):
                row_dict = dict(zip(headers, row))
                
                # 取引日のパース
                transaction_date = row_dict.get('取引日', '')
                if not transaction_date:
                    continue
                
                # 日付型の場合はstrftimeで変換
                if isinstance(transaction_date, datetime):
                    transaction_date = transaction_date.strftime('%Y-%m-%d')
                else:
                    transaction_date = str(transaction_date).strip()
                    try:
                        date_obj = datetime.strptime(transaction_date, '%Y-%m-%d')
                        transaction_date = date_obj.strftime('%Y-%m-%d')
                    except:
                        try:
                            date_obj = datetime.strptime(transaction_date, '%Y/%m/%d')
                            transaction_date = date_obj.strftime('%Y-%m-%d')
                        except:
                            continue
                
                # 摘要
                description = str(row_dict.get('摘要', '')).strip()
                
                # 入金金額
                income_amount = int(row_dict.get('入金金額', 0) or 0)
                
                # 出金金額
                expense_amount = int(row_dict.get('出金金額', 0) or 0)
                
                # ImportedTransactionを作成
                imported_transaction = ImportedTransaction(
                    organization_id=current_org.id,
                    account_name=account.account_name,
                    transaction_date=transaction_date,
                    description=description,
                    income_amount=income_amount,
                    expense_amount=expense_amount,
                    status=0,  # 未処理
                    imported_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                )
                db.add(imported_transaction)
                imported_count += 1
        
        else:
            flash('CSVまたはExcelファイルを選択してください', 'error')
            return redirect(url_for('transaction_import'))
        
        # データベースにコミット
        db.commit()
        
        flash(f'{imported_count}件の取引明細をインポートしました', 'success')
        return redirect(url_for('imported_transactions_list'))
    
    except Exception as e:
        db.rollback()
        flash(f'インポート中にエラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('transaction_import'))
    finally:
        db.close()
