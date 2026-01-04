"""
cash_books Blueprint
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from db import SessionLocal, engine
from models import Base, AccountItem, CashBook, ImportTemplate, Account, TaxCategory, JournalEntry, Department, Counterparty, Item, ProjectTag, MemoTag, CashBookMaster, FiscalPeriod, Organization, ImportedTransaction, GeneralLedger, OpeningBalance, Template, User, UserOrganization
from app.models_login import TKanrisha, TJugyoin, TTenant, TTenpo, TTenantAdminTenant, TKanrishaTenpo, TJugyoinTenpo, TTenantAppSetting, TTenpoAppSetting
import os
from datetime import datetime
import json
from import_utils import ImportProcessor
from functools import wraps
import csv
import io

bp = Blueprint('cash_books', __name__, url_prefix='')

# ヘルパー関数
def login_required(f):
    """ログインが必要なルートに付与するデコレーター"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if 'organization_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_organization():
    """現在ログイン中の事業所情報を取得"""
    if 'organization_id' not in session:
        return None
    db = SessionLocal()
    org = db.query(Organization).filter(Organization.id == session['organization_id']).first()
    db.close()
    return org

def get_current_organization_id():
    """現在ログイン中の事業所IDを取得"""
    return session.get('organization_id')


@bp.route('/cash-books/batch', methods=['GET'])
def batch_create_cash_books_page():
    """連続仕訳登録ページ"""
    db = SessionLocal()
    
    try:
        # 口座フィルター（動定科目ID）
        account_item_id = request.args.get('account_item_id', type=int)
        
        # 登録済みの出納帳データを取得（最新50件）
        cash_books_query = db.query(CashBook).join(
            AccountItem, CashBook.account_item_id == AccountItem.id, isouter=True
        ).join(
            TaxCategory, CashBook.tax_category_id == TaxCategory.id, isouter=True
        )
        
        # 口座フィルターを適用（account_item_idから口座名を取得してpayment_accountでフィルタ）
        if account_item_id:
            # account_item_idから口座を取得
            account = db.query(Account).filter(Account.account_item_id == account_item_id).first()
            if account:
                cash_books_query = cash_books_query.filter(
                    CashBook.payment_account == account.account_name
                )
        
        cash_books_query = cash_books_query.order_by(
            CashBook.transaction_date.desc(), CashBook.id.desc()
        ).limit(50).all()
        
        cash_books = []
        for cb in cash_books_query:
            # amount_with_taxが正の値なら入金、負の値なら出金
            deposit_amount = cb.amount_with_tax if cb.amount_with_tax > 0 else None
            withdrawal_amount = abs(cb.amount_with_tax) if cb.amount_with_tax < 0 else None
            
            cash_books.append({
                'id': cb.id,
                'transaction_date': cb.transaction_date,
                'account_name': cb.payment_account or '',
                'account_item_name': cb.account_item.account_name if cb.account_item else '',
                'tax_category': cb.tax_category.name if cb.tax_category else cb.tax_rate or '',
                'counterparty': cb.counterparty,
                'item_name': cb.item_name,
                'deposit_amount': deposit_amount,
                'withdrawal_amount': withdrawal_amount,
                'tax_amount': cb.tax_amount,
                'remarks': cb.remarks
            })
        
        return render_template('cash_books/batch_form.html', cash_books=cash_books, account_item_id=account_item_id)
    finally:
        db.close()

# 出納帳新規追加ページ


@bp.route('/cash-books/new', methods=['GET', 'POST'])
def cash_book_create():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # フォームデータを取得
            transaction_date = request.form.get('transaction_date', '').strip()
            account_item_id = request.form.get('account_item_id', type=int)
            tax_category_id = request.form.get('tax_category_id', type=int) # 新しいフィールド
            tax_rate = request.form.get('tax_rate', '').strip()
            counterparty = request.form.get('counterparty', '').strip()
            item_name = request.form.get('item_name', '').strip()
            department = request.form.get('department', '').strip()
            memo_tag = request.form.get('memo_tag', '').strip()
            payment_account = request.form.get('payment_account', '').strip()
            remarks = request.form.get('remarks', '').strip()
            amount_with_tax = request.form.get('amount_with_tax', type=int)
            amount_without_tax = request.form.get('amount_without_tax', type=int)
            tax_amount = request.form.get('tax_amount', type=int)
            
            # バリデーション
            if not transaction_date:
                flash('取引日は必須です', 'error')
                return redirect(url_for('cash_book_create'))
            
            if not account_item_id:
                flash('勘定科目は必須です', 'error')
                return redirect(url_for('cash_book_create'))
            
            # 新規作成
            new_item = CashBook(
                transaction_date=datetime.strptime(transaction_date, '%Y-%m-%d').date(),
                account_item_id=account_item_id,
                tax_category_id=tax_category_id, # 新しいフィールド
                tax_rate=tax_rate,
                counterparty=counterparty,
                item_name=item_name,
                department=department,
                memo_tag=memo_tag,
                payment_account=payment_account,
                remarks=remarks,
                amount_with_tax=amount_with_tax,
                amount_without_tax=amount_without_tax,
                tax_amount=tax_amount
            )
            
            db.add(new_item)
            db.commit()
            
            # 仕訳帳マスタにも登録
            account = None
            
            # payment_accountが指定されている場合、口座マスタから口座を検索
            if payment_account:
                # 口座マスタから口座を検索
                account = db.query(Account).filter(
                    Account.organization_id == get_current_organization_id(),
                    Account.name == payment_account
                ).first()
            else:
                account = db.query(Account).filter(
                    Account.organization_id == get_current_organization_id()
                ).first()
            
            if account:
                # 口座の勘定科目IDを取得
                account_item_id_for_account = account.account_item_id
                
                # account_item_id_for_accountがない場合、口座種別から推測
                if not account_item_id_for_account:
                    if 'cash' in account.account_type.lower():
                        cash_account_item = db.query(AccountItem).filter(
                            AccountItem.organization_id == get_current_organization_id(),
                            AccountItem.account_name == '現金'
                        ).first()
                        if cash_account_item:
                            account_item_id_for_account = cash_account_item.id
                    elif 'bank' in account.account_type.lower():
                        bank_account_item = db.query(AccountItem).filter(
                            AccountItem.organization_id == get_current_organization_id(),
                            AccountItem.account_name == '普通預金'
                        ).first()
                        if bank_account_item:
                            account_item_id_for_account = bank_account_item.id
                
                if account_item_id_for_account:
                    # 金額が正の場合は入金（借方=口座、貸方=勘定科目）
                    # 金額が負の場合は出金（借方=勘定科目、貸方=口座）
                    if amount_with_tax >= 0:
                        # 入金
                        debit_account = account_item_id_for_account
                        credit_account = account_item_id
                    else:
                        # 出金
                        debit_account = account_item_id
                        credit_account = account_item_id_for_account
                    
                    general_ledger_entry = GeneralLedger(
                        organization_id=get_current_organization_id(),
                        transaction_date=transaction_date,
                        debit_account_item_id=debit_account,
                        debit_amount=abs(amount_with_tax),
                        debit_tax_category_id=tax_category_id if amount_with_tax < 0 else None,
                        credit_account_item_id=credit_account,
                        credit_amount=abs(amount_with_tax),
                        credit_tax_category_id=tax_category_id if amount_with_tax >= 0 else None,
                        summary=f"{counterparty or ''} {item_name or ''}".strip(),
                        remarks=remarks,
                        source_type='cash_book',
                        source_id=new_item.id,
                        created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    )
                    db.add(general_ledger_entry)
                    db.commit()
            
            flash('出納帳に取引を追加しました', 'success')
            return redirect(url_for('cash_books_list'))
        
        return render_template('cash_books/form.html')
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('cash_books_list'))
    finally:
        db.close()

# 出納帳編集ページ


@bp.route('/cash-books/<int:item_id>/edit', methods=['GET', 'POST'])
def cash_book_edit(item_id):
    db = SessionLocal()
    try:
        item = db.query(CashBook).filter(CashBook.id == item_id).first()
        if not item:
            flash('取引が見つかりません', 'error')
            return redirect(url_for('cash_books_list'))
        
        if request.method == 'POST':
            # フォームデータを取得
            transaction_date = request.form.get('transaction_date', '').strip()
            account_item_id = request.form.get('account_item_id', type=int)
            tax_category_id = request.form.get('tax_category_id', type=int) # 新しいフィールド
            tax_rate = request.form.get('tax_rate', '').strip()
            counterparty = request.form.get('counterparty', '').strip()
            item_name = request.form.get('item_name', '').strip()
            department = request.form.get('department', '').strip()
            memo_tag = request.form.get('memo_tag', '').strip()
            payment_account = request.form.get('payment_account', '').strip()
            remarks = request.form.get('remarks', '').strip()
            amount_with_tax = request.form.get('amount_with_tax', type=int)
            amount_without_tax = request.form.get('amount_without_tax', type=int)
            tax_amount = request.form.get('tax_amount', type=int)
            
            # バリデーション
            if not transaction_date:
                flash('取引日は必須です', 'error')
                return redirect(url_for('cash_book_edit', item_id=item_id))
            
            if not account_item_id:
                flash('勘定科目は必須です', 'error')
                return redirect(url_for('cash_book_edit', item_id=item_id))
            
            # 更新
            item.transaction_date = datetime.strptime(transaction_date, '%Y-%m-%d').date()
            item.account_item_id = account_item_id
            item.tax_category_id = tax_category_id # 新しいフィールド
            item.tax_rate = tax_rate
            item.counterparty = counterparty
            item.item_name = item_name
            item.department = department
            item.memo_tag = memo_tag
            item.payment_account = payment_account
            item.remarks = remarks
            item.amount_with_tax = amount_with_tax
            item.amount_without_tax = amount_without_tax
            item.tax_amount = tax_amount
            
            db.commit()
            
            flash('出納帳の取引を更新しました', 'success')
            return redirect(url_for('cash_books_list'))
        
        return render_template('cash_books/form.html', item=item)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('cash_books_list'))
    finally:
        db.close()

# 出納帳削除API


@bp.route('/api/cash-books/<int:item_id>/delete', methods=['POST'])
def cash_book_delete(item_id):
    db = SessionLocal()
    try:
        item = db.query(CashBook).filter(CashBook.id == item_id).first()
        if not item:
            return jsonify({'success': False, 'message': '取引が見つかりません'}), 404
        
        # 仕訳帳からも削除（source_type='batch_entry'かつsource_id=cash_book.id）
        general_ledger_entries = db.query(GeneralLedger).filter(
            GeneralLedger.source_type.in_(['batch_entry', 'batch_entry_net', 'batch_entry_tax']),
            GeneralLedger.source_id == item_id
        ).all()
        
        for entry in general_ledger_entries:
            db.delete(entry)
        
        # 出納帳を削除
        db.delete(item)
        db.commit()
        return jsonify({'success': True, 'message': '取引を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 出納帳一覧ページ


@bp.route('/cash-books', methods=['GET'])
def cash_books_list():
    db = SessionLocal()
    try:
        # 表示が有効な口座を取得（boolean カラムなので is_(True) で判定）
        accounts = db.query(Account).filter(
            Account.is_visible_in_list.is_(True)
        ).order_by(Account.id.asc()).all()
        
        # 口座ごとの取引を格納する辞書
        grouped_cash_books = {}
        
        # 検索フィルター
        search_query = request.args.get('search', '', type=str)
        
        # 口座ごとの登録数内訳を格納する辞書
        account_stats = {}
        
        for account in accounts:
            # まず、この口座に紐づく出納帳を取得
            query = db.query(CashBook).filter(
                CashBook.organization_id == account.organization_id,
                CashBook.payment_account == account.account_name,
            )
            
            # 検索キーワードがあれば、摘要や取引先などに対して部分一致検索
            if search_query:
                query = query.filter(
                    (CashBook.remarks.ilike(f'%{search_query}%')) |
                    (CashBook.counterparty.ilike(f'%{search_query}%')) |
                    (CashBook.item_name.ilike(f'%{search_query}%')) |
                    (CashBook.department.ilike(f'%{search_query}%')) |
                    (CashBook.memo_tag.ilike(f'%{search_query}%'))
                )
            
            # 日付降順でソート
            items = query.order_by(CashBook.transaction_date.desc()).all()
            
            # 口座名と取引リストを辞書に格納
            grouped_cash_books[account.account_name] = items
            
            # ===== ここから登録数内訳（連続仕訳・取引明細・振替）の集計 =====
            from sqlalchemy import func
            
            # この口座に対応する勘定科目IDを特定
            account_item_ids = []
            if account.account_item_id:
                account_item_ids.append(account.account_item_id)
            else:
                # 勘定科目が未設定の場合は口座名から推測（現金・普通預金など）
                if account.account_name == '現金':
                    account_item_ids.append(1)  # 現金
                elif account.account_name in ['三井住友銀行', '三菱ＵＦＪ銀行']:
                    account_item_ids.append(2)  # 普通預金 など、必要に応じて調整
            
            # 連続仕訳の件数（借方または貸方がこの口座の勘定科目）
            batch_count = db.query(func.count(func.distinct(GeneralLedger.source_id))).filter(
                GeneralLedger.organization_id == account.organization_id,
                GeneralLedger.source_type.in_(['batch_entry', 'batch_entry_net', 'batch_entry_tax']),
                ((GeneralLedger.debit_account_item_id.in_(account_item_ids)) |
                 (GeneralLedger.credit_account_item_id.in_(account_item_ids)))
            ).scalar() or 0 if account_item_ids else 0
            
            # 取引明細（インポート元）のIDリスト
            transaction_ids = db.query(func.distinct(GeneralLedger.source_id)).filter(
                GeneralLedger.organization_id == account.organization_id,
                GeneralLedger.source_type == 'imported_transaction',
                ((GeneralLedger.debit_account_item_id.in_(account_item_ids)) |
                 (GeneralLedger.credit_account_item_id.in_(account_item_ids)))
            ).all() if account_item_ids else []
            
            transaction_ids = [t[0] for t in transaction_ids if t[0] is not None]
            
            # 未処理取引明細の件数
            transaction_unprocessed_count = db.query(func.count(ImportedTransaction.id)).filter(
                ImportedTransaction.id.in_(transaction_ids),
                ImportedTransaction.status == 0
            ).scalar() or 0 if transaction_ids else 0
            
            # 処理済み取引明細の件数
            transaction_processed_count = db.query(func.count(ImportedTransaction.id)).filter(
                ImportedTransaction.id.in_(transaction_ids),
                ImportedTransaction.status == 1
            ).scalar() or 0 if transaction_ids else 0
            
            # 振替伝票の件数
            journal_count = db.query(func.count(func.distinct(GeneralLedger.source_id))).filter(
                GeneralLedger.organization_id == account.organization_id,
                GeneralLedger.source_type == 'journal_entry',
                ((GeneralLedger.debit_account_item_id.in_(account_item_ids)) |
                 (GeneralLedger.credit_account_item_id.in_(account_item_ids)))
            ).scalar() or 0 if account_item_ids else 0
            
            account_stats[account.account_name] = {
                'batch': batch_count,
                'transaction_unprocessed': transaction_unprocessed_count,
                'transaction_processed': transaction_processed_count,
                'journal': journal_count,
            }
        
        # ページネーションは現状未実装（全件表示）
        return render_template(
            'cash_books/list.html',
            accounts=accounts,
            grouped_cash_books=grouped_cash_books,
            account_stats=account_stats,
            search_query=search_query
        )
    finally:
        db.close()



# 勘定科目一覧ページ


@bp.route('/api/cash-books/batch', methods=['POST'])
def batch_create_cash_books():
    """複数の出納帳データを一括で作成するAPI"""
    db = SessionLocal()
    try:
        data = request.get_json()
        
        if not data or 'transactions' not in data:
            return jsonify({'success': False, 'message': 'transactions データが必要です'}), 400
        
        transactions = data['transactions']
        
        if not isinstance(transactions, list) or len(transactions) == 0:
            return jsonify({'success': False, 'message': '最低1件の取引データが必要です'}), 400
        
        created_count = 0      # 実際に仕訳（GeneralLedger）を作成できた件数
        cashbook_count = 0     # 出納帳（CashBook）を作成した件数
        errors = []            # 行ごとのエラーメッセージ
        
        organization_id = get_current_organization_id() or 1
        
        for idx, transaction in enumerate(transactions):
            try:
                # デバッグ用ログ
                app.logger.info(f"処理中の取引データ (行 {idx + 1}): {transaction}")
                
                # 必須フィールドのチェック
                if not transaction.get('transaction_date'):
                    errors.append(f'行 {idx + 1}: 取引日が必要です')
                    continue
                
                if not transaction.get('account_item_id'):
                    errors.append(f'行 {idx + 1}: 勘定科目が必要です')
                    continue
                
                if not transaction.get('account_id'):
                    errors.append(f'行 {idx + 1}: 口座が必要です')
                    continue
                
                # 入金または出金のどちらかが必須
                deposit_amount = transaction.get('deposit_amount')
                withdrawal_amount = transaction.get('withdrawal_amount')
                
                if (not deposit_amount or deposit_amount == '') and (not withdrawal_amount or withdrawal_amount == ''):
                    errors.append(f'行 {idx + 1}: 入金または出金のどちらかが必須です')
                    continue
                
                # 入金は正の値、出金は負の値として amount_with_tax に設定
                if deposit_amount and deposit_amount != '':
                    amount_with_tax = int(deposit_amount)
                else:
                    amount_with_tax = -int(withdrawal_amount)
                
                # account_item_id を整数に変換
                try:
                    account_item_id = int(transaction.get('account_item_id'))
                except (ValueError, TypeError):
                    errors.append(f'行 {idx + 1}: 勘定科目IDが不正です')
                    continue
                
                # 勘定科目の存在確認
                account_item = db.query(AccountItem).filter(
                    AccountItem.id == account_item_id
                ).first()
                
                if not account_item:
                    errors.append(f'行 {idx + 1}: 勘定科目が見つかりません')
                    continue
                
                # transaction_date を date オブジェクトに変換
                transaction_date_str = transaction.get('transaction_date')
                try:
                    transaction_date = datetime.strptime(transaction_date_str, '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f'行 {idx + 1}: 取引日の形式が不正です')
                    continue
                
                # 金額の変換
                try:
                    amount_with_tax_int = int(amount_with_tax)
                    # tax_amount は現状フロントで計算されていないため 0
                    tax_amount_int = 0
                    # 税抜金額（絶対値から税額分を引く）
                    amount_without_tax_int = abs(amount_with_tax_int) - abs(tax_amount_int)
                except (ValueError, TypeError):
                    errors.append(f'行 {idx + 1}: 金額の形式が不正です')
                    continue
                
                # tax_category_id を取得し、空文字列の場合は None に変換
                tax_category_id = transaction.get('tax_category_id')
                if tax_category_id == '':
                    tax_category_id = None
                else:
                    try:
                        tax_category_id = int(tax_category_id)
                    except (ValueError, TypeError):
                        errors.append(f'行 {idx + 1}: 税区分IDの形式が不正です')
                        continue
                
                # 追加情報（現状は名称は空で保持）
                counterparty_id = transaction.get('counterparty_id')
                item_id = transaction.get('item_id')
                department_id = transaction.get('department_id')
                project_tag_id = transaction.get('project_tag_id')
                memo_tag_id = transaction.get('memo_tag_id')
                
                counterparty = ''
                item_name = ''
                department = ''
                memo_tag = ''
                
                # 口座情報を取得
                account_id = transaction.get('account_id')
                account = None
                
                if account_id not in (None, ''):
                    try:
                        account_id_int = int(account_id)
                    except (TypeError, ValueError):
                        errors.append(f'行 {idx + 1}: 口座IDが不正です')
                        continue

                    account = db.query(Account).filter(
                        Account.id == account_id_int
                    ).first()
                else:
                    account = db.query(Account).filter(
                        Account.organization_id == organization_id
                    ).first()
                
                if not account:
                    errors.append(f'行 {idx + 1}: 口座が見つかりません')
                    continue
                
                # まず CashBook を作成
                cash_book = CashBook(
                    organization_id=organization_id,
                    transaction_date=transaction_date,
                    account_item_id=account_item_id,
                    counterparty=counterparty,
                    item_name=item_name,
                    tax_category_id=tax_category_id,
                    tax_rate='',
                    department=department,
                    memo_tag=memo_tag,
                    payment_account=account.account_name,
                    remarks=transaction.get('remarks', '').strip(),
                    amount_with_tax=amount_with_tax_int,
                    amount_without_tax=amount_without_tax_int,
                    tax_amount=tax_amount_int,
                    balance=0,
                )
                
                db.add(cash_book)
                db.flush()  # cash_book.id を取得するために flush
                cashbook_count += 1
                
                # source_id を自分自身の ID に設定
                cash_book.source_id = cash_book.id
                
                # 口座の勘定科目IDを取得（NULL の場合はエラー）
                account_item_id_for_account = None
                if account.account_item_id:
                    account_item_id_for_account = account.account_item_id
                else:
                    # 口座種別から推測して取得（従来ロジックを残しつつ、失敗したらエラー）
                    if account.account_type:
                        atype = account.account_type.lower()
                        if 'cash' in atype:
                            cash_account_item = db.query(AccountItem).filter(
                                AccountItem.organization_id == organization_id,
                                AccountItem.account_name == '現金'
                            ).first()
                            if cash_account_item:
                                account_item_id_for_account = cash_account_item.id
                        elif 'bank' in atype:
                            bank_account_item = db.query(AccountItem).filter(
                                AccountItem.organization_id == organization_id,
                                AccountItem.account_name == '普通預金'
                            ).first()
                            if bank_account_item:
                                account_item_id_for_account = bank_account_item.id
                
                if not account_item_id_for_account:
                    # ここで仕訳を作ることができないので、この行はエラーとしてスキップ
                    db.delete(cash_book)
                    cashbook_count -= 1
                    errors.append(
                        f'行 {idx + 1}: 口座に紐づく勘定科目が設定されていません。'
                        '口座マスタで勘定科目を設定してください。'
                    )
                    continue
                
                # ここから仕訳帳（GeneralLedger）登録処理
                # 既存の GeneralLedger エントリを削除（更新の場合を考慮）
                db.query(GeneralLedger).filter(
                    GeneralLedger.source_type.in_(['batch_entry', 'batch_entry_net', 'batch_entry_tax']),
                    GeneralLedger.source_id == cash_book.id
                ).delete()
                
                # 仮払消費税 / 仮受消費税 の勘定科目を取得（将来税額対応時用）
                tax_account_item = db.query(AccountItem).filter(
                    AccountItem.organization_id == organization_id,
                    AccountItem.account_name.in_(['仮払消費税', '仮受消費税'])
                ).first()
                
                remarks = transaction.get('remarks', '')
                
                # 1. 税金分の仕訳を考慮した登録（現状 tax_amount_int は 0 のはずなので通常は通らない）
                if tax_amount_int != 0 and tax_account_item:
                    tax_account_item_id = tax_account_item.id
                    tax_amount_abs = abs(tax_amount_int)
                    
                    # 1-1. 取引勘定科目と口座勘定科目の仕訳 (税抜金額)
                    amount_to_use = amount_without_tax_int
                    
                    if amount_to_use != 0:
                        if amount_with_tax_int >= 0:
                            # 入金: 借方=口座、貸方=取引勘定科目
                            debit_account_id_net = account_item_id_for_account
                            credit_account_id_net = account_item_id
                        else:
                            # 出金: 借方=取引勘定科目、貸方=口座
                            debit_account_id_net = account_item_id
                            credit_account_id_net = account_item_id_for_account
                        
                        general_ledger_entry_net = GeneralLedger(
                            organization_id=organization_id,
                            transaction_date=transaction_date,
                            debit_account_item_id=debit_account_id_net,
                            debit_amount=abs(amount_to_use),
                            credit_account_item_id=credit_account_id_net,
                            credit_amount=abs(amount_to_use),
                            summary=remarks,
                            source_type='batch_entry_net',
                            source_id=cash_book.id,
                            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        )
                        db.add(general_ledger_entry_net)
                    
                    # 1-2. 税金分の仕訳 (税額)
                    if tax_amount_int != 0:
                        if amount_with_tax_int >= 0:
                            # 入金（売上など）: 借方: 口座 / 貸方: 仮受消費税
                            debit_account_id_tax = account_item_id_for_account
                            credit_account_id_tax = tax_account_item_id
                        else:
                            # 出金（費用など）: 借方: 仮払消費税 / 貸方: 口座
                            debit_account_id_tax = tax_account_item_id
                            credit_account_id_tax = account_item_id_for_account
                        
                        general_ledger_entry_tax = GeneralLedger(
                            organization_id=organization_id,
                            transaction_date=transaction_date,
                            debit_account_item_id=debit_account_id_tax,
                            debit_amount=tax_amount_abs,
                            credit_account_item_id=credit_account_id_tax,
                            credit_amount=tax_amount_abs,
                            summary=remarks + ' (消費税)',
                            source_type='batch_entry_tax',
                            source_id=cash_book.id,
                            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        )
                        db.add(general_ledger_entry_tax)
                    
                    created_count += 1  # 税分仕訳まで作れた場合もカウント
                
                # 2. 税金勘定科目がない、または税金がない場合は、税込1本の仕訳を登録
                elif amount_with_tax_int != 0:
                    if amount_with_tax_int >= 0:
                        # 入金: 借方=口座、貸方=取引勘定科目
                        debit_account_id = account_item_id_for_account
                        credit_account_id = account_item_id
                    else:
                        # 出金: 借方=取引勘定科目、貸方=口座
                        debit_account_id = account_item_id
                        credit_account_id = account_item_id_for_account
                        
                    general_ledger_entry = GeneralLedger(
                        organization_id=organization_id,
                        transaction_date=transaction_date,
                        debit_account_item_id=debit_account_id,
                        debit_amount=abs(amount_with_tax_int),
                        credit_account_item_id=credit_account_id,
                        credit_amount=abs(amount_with_tax_int),
                        summary=remarks,
                        source_type='batch_entry',
                        source_id=cash_book.id,
                        created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    )
                    db.add(general_ledger_entry)
                    created_count += 1  # 仕訳を1本作成できたのでカウント
            
            except Exception as e:
                import traceback
                error_msg = f'行 {idx + 1}: {str(e)}'
                app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                errors.append(error_msg)
        
        # 1件も仕訳が作成できなかった場合はロールバックしてエラー
        if created_count == 0:
            db.rollback()
            return jsonify({
                'success': False,
                'created_count': 0,
                'errors': errors,
                'message': '仕訳を1件も登録できませんでした。口座マスタ等の設定を確認してください。'
            }), 200  # ステータスは 200 にしておき、フロント側は success を見るようにする
        
        # 仕訳が1件でも作成できていればコミット
        db.commit()
        
        return jsonify({
            'success': True,
            'created_count': created_count,
            'cashbook_count': cashbook_count,
            'errors': errors,
            'message': f'{created_count}件の仕訳を登録しました'
        })
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()



# 出納帳リスト取得API


@bp.route('/api/cash-books/list', methods=['GET'])
def get_cash_books_list():
    """登録済み出納帳データのリストを取得するAPI"""
    db = SessionLocal()
    try:
        account_id = request.args.get('account_id', type=int)
        limit = request.args.get('limit', default=50, type=int)
        
        if not account_id:
            return jsonify({'success': False, 'message': 'account_idが必要です'}), 400
        
        # 口座情報を取得
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return jsonify({'success': False, 'message': '口座が見つかりません'}), 404
        
        # 出納帳データを取得（最新順）
        # payment_accountが空文字列のデータも含める
        cash_books = db.query(CashBook).filter(
            (CashBook.payment_account == account.account_name) | (CashBook.payment_account == '')
        ).order_by(
            CashBook.transaction_date.desc(),
            CashBook.id.desc()
        ).limit(limit).all()
        
        # データを整形
        result_data = []
        for cb in cash_books:
            # 入金・出金を判定
            deposit_amount = cb.amount_with_tax if cb.amount_with_tax > 0 else None
            withdrawal_amount = abs(cb.amount_with_tax) if cb.amount_with_tax < 0 else None
            
            result_data.append({
                'id': cb.id,
                'transaction_date': str(cb.transaction_date),
                'account_name': cb.payment_account,
                'account_item_name': cb.account_item.account_name if cb.account_item else '',
                'tax_category': cb.tax_category.name if cb.tax_category else cb.tax_rate or '',
                'counterparty': cb.counterparty or '',
                'item_name': cb.item_name or '',
                'department': cb.department or '',
                'memo_tag': cb.memo_tag or '',
                'deposit_amount': deposit_amount,
                'withdrawal_amount': withdrawal_amount,
                'tax_amount': cb.tax_amount or 0,
                'remarks': cb.remarks or ''
            })
        
        return jsonify({'success': True, 'data': result_data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 出納帳データ取得API


@bp.route('/api/cash-books/<int:item_id>', methods=['GET'])
def get_cash_book(item_id):
    """出納帳データを取得するAPI"""
    db = SessionLocal()
    try:
        cash_book = db.query(CashBook).filter(CashBook.id == item_id).first()
        if not cash_book:
            return jsonify({'success': False, 'message': 'データが見つかりません'}), 404
        
        # 口座情報を取得（payment_accountからaccount_idを推定）
        account = None
        if cash_book.payment_account:
            account = db.query(Account).filter(Account.account_name == cash_book.payment_account).first()
        
        # 入金・出金を判定
        deposit_amount = cash_book.amount_with_tax if cash_book.amount_with_tax > 0 else None
        withdrawal_amount = abs(cash_book.amount_with_tax) if cash_book.amount_with_tax < 0 else None
        
        data = {
            'id': cash_book.id,
            'transaction_date': str(cash_book.transaction_date),
            'account_id': account.id if account else None,
            'account_item_id': cash_book.account_item_id,
            'tax_category_id': cash_book.tax_category_id,
            'tax_category': cash_book.tax_category.name if cash_book.tax_category else cash_book.tax_rate or '',
            'counterparty': cash_book.counterparty or '',
            'item_name': cash_book.item_name or '',
            'deposit_amount': deposit_amount,
            'withdrawal_amount': withdrawal_amount,
            'tax_amount': cash_book.tax_amount or 0,
            'remarks': cash_book.remarks or ''
        }
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 出納帳データ更新API


@bp.route('/api/cash-books/<int:item_id>', methods=['PUT'])
def update_cash_book(item_id):
    """出納帳データを更新するAPI"""
    db = SessionLocal()
    try:
        cash_book = db.query(CashBook).filter(CashBook.id == item_id).first()
        if not cash_book:
            return jsonify({'success': False, 'message': 'データが見つかりません'}), 404
        
        data = request.get_json()
        
        # 入金または出金のどちらかが必須
        deposit_amount = data.get('deposit_amount')
        withdrawal_amount = data.get('withdrawal_amount')
        
        if (not deposit_amount or deposit_amount == '') and (not withdrawal_amount or withdrawal_amount == ''):
            return jsonify({'success': False, 'message': '入金または出金のどちらかが必須です'}), 400
        
        # 入金は正の値、出金は負の値としてamount_with_taxに設定
        if deposit_amount and deposit_amount != '':
            amount_with_tax = int(deposit_amount)
        else:
            amount_with_tax = -int(withdrawal_amount)
        
        # 税抜金額を計算
        tax_amount = int(data.get('tax_amount', 0))
        amount_without_tax = abs(amount_with_tax) - abs(tax_amount)
        
        # 取引日の変換
        transaction_date_str = data.get('transaction_date')
        try:
            transaction_date = datetime.strptime(transaction_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'message': '取引日の形式が不正です'}), 400
        
        # tax_categoryの名前からtax_category_idを取得
        tax_category_name = data.get('tax_category', '').strip()
        tax_category_id = None
        if tax_category_name:
            tax_category_obj = db.query(TaxCategory).filter(
                TaxCategory.name == tax_category_name
            ).first()
            if tax_category_obj:
                tax_category_id = tax_category_obj.id
        
        # 口座情報を取得
        account_id = data.get('account_id')
        payment_account = ''
        if account_id:
            account = db.query(Account).filter(Account.id == account_id).first()
            if account:
                payment_account = account.account_name
        
        # データを更新
        cash_book.transaction_date = transaction_date
        cash_book.account_item_id = int(data.get('account_item_id'))
        cash_book.tax_category_id = tax_category_id
        cash_book.counterparty = data.get('counterparty', '').strip()
        cash_book.item_name = data.get('item_name', '').strip()
        cash_book.payment_account = payment_account
        cash_book.remarks = data.get('remarks', '').strip()
        cash_book.amount_with_tax = amount_with_tax
        cash_book.amount_without_tax = amount_without_tax
        cash_book.tax_amount = tax_amount
        cash_book.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        db.commit()
        
        return jsonify({'success': True, 'message': 'データを更新しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()



@bp.route('/cash-books/<int:cash_book_id>/update', methods=['POST'])
def update_cash_book_batch(cash_book_id):
    """連続仕訳登録画面からの更新API"""
    db = SessionLocal()
    try:
        cash_book = db.query(CashBook).filter(CashBook.id == cash_book_id).first()
        if not cash_book:
            return jsonify({'success': False, 'error': 'データが見つかりません'}), 404
        
        data = request.get_json()
        
        # 入力値を取得
        date_str = data.get('date')
        template_name = data.get('template')
        account_item_id = data.get('account_item_id')
        tax_category_id = data.get('tax_category_id')
        unified_tag = data.get('unified_tag')
        counterparty = data.get('counterparty')
        item_name = data.get('item_name')
        department = data.get('department')
        project_tag = data.get('project_tag')
        memo_tag = data.get('memo_tag')
        remarks = data.get('remarks', '')
        debit = float(data.get('debit', 0))
        credit = float(data.get('credit', 0))
        
        # バリデーション
        if debit > 0 and credit > 0:
            return jsonify({'success': False, 'error': '入金と出金の両方に金額を入力することはできません'}), 400
        
        if debit == 0 and credit == 0:
            return jsonify({'success': False, 'error': '入金または出金のいずれかを入力してください'}), 400
        
        # 日付の変換
        try:
            transaction_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': '日付の形式が不正です'}), 400
        
        # 勘定科目IDで検索（通常登録と同じ方法）
        if not account_item_id:
            return jsonify({'success': False, 'error': '勘定科目IDが必要です'}), 400
        
        try:
            account_item_id_int = int(account_item_id)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': '勘定科目IDが不正です'}), 400
        
        account_item = db.query(AccountItem).filter(
            AccountItem.id == account_item_id_int
        ).first()
        if not account_item:
            return jsonify({'success': False, 'error': f'勘定科目が見つかりません: ID={account_item_id}'}), 404
        
        # 税区分IDで検索（通常登録と同じ方法）
        if tax_category_id and tax_category_id != '':
            try:
                tax_category_id_int = int(tax_category_id)
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': '税区分IDが不正です'}), 400
            
            tax_category = db.query(TaxCategory).filter(TaxCategory.id == tax_category_id_int).first()
            if not tax_category:
                return jsonify({'success': False, 'error': f'税区分が見つかりません: ID={tax_category_id}'}), 404
        else:
            tax_category = None
        
        # 金額を計算（入金は正、出金は負）
        amount_with_tax = debit if debit > 0 else -credit
        
        # 更新
        cash_book.transaction_date = transaction_date
        cash_book.account_item_id = account_item.id
        cash_book.tax_category_id = tax_category.id if tax_category else None
        cash_book.counterparty = counterparty
        cash_book.item_name = item_name
        cash_book.department = department
        cash_book.project_tag = project_tag
        cash_book.memo_tag = memo_tag
        cash_book.remarks = remarks
        cash_book.amount_with_tax = amount_with_tax
        cash_book.amount_without_tax = amount_with_tax  # 簡易計算（必要に応じて税額計算を追加）
        
        db.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


# ========== 勘定科目CSV/ExcelインポートAPI ==========

