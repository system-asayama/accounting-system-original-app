"""
accounts Blueprint
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

bp = Blueprint('accounts', __name__, url_prefix='')

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


@bp.route('/api/accounts/all')
def get_all_accounts():
    db = SessionLocal()
    try:
        organization_id = get_current_organization_id()
        accounts = db.query(Account).filter(
            Account.organization_id == organization_id
        ).order_by(Account.account_name.asc()).all()
        
        accounts_list = []
        for account in accounts:
            accounts_list.append({
                'id': account.id,
                'account_name': account.account_name,
                'account_number': account.account_number,
                'account_type': account.account_type,
                'display_name': f"{account.account_name}{' (' + account.account_number + ')' if account.account_number else ''}"
            })
            
        return jsonify({'success': True, 'accounts': accounts_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

## ========== 出納帳管理機能 ===========

# 連続仕訳登録ページ


@bp.route('/accounts', methods=['GET'])
@login_required
def accounts_list():
    """口座一覧"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        # ページネーション
        page = request.args.get('page', 1, type=int)
        per_page = 20
        offset = (page - 1) * per_page
        
        # 検索フィルター
        search_query = request.args.get('search', '', type=str)
        
        # クエリ構築（事業所フィルタリング）
        query = db.query(Account).filter(Account.organization_id == organization_id)
        if search_query:
            query = query.filter(
                (Account.account_name.ilike(f'%{search_query}%')) |
                (Account.account_type.ilike(f'%{search_query}%')) |
                (Account.bank_name.ilike(f'%{search_query}%'))
            )
        
        # 口座名でソート
        query = query.order_by(Account.account_name.asc())
        
        # 総件数
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        
        # データ取得
        accounts = query.offset(offset).limit(per_page).all()
        
        return render_template(
            'accounts/list.html',
            accounts=accounts,
            page=page,
            total_pages=total_pages,
            total=total,
            search_query=search_query
        )
    finally:
        db.close()

# 口座新規追加ページ


@bp.route('/accounts/new', methods=['GET', 'POST'])
@login_required
def account_create():
    """口座新規追加"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # フォームデータを取得
            account_name = request.form.get('account_name', '').strip()
            account_type = request.form.get('account_type', '').strip()
            display_name = request.form.get('display_name', '').strip()
            bank_name = request.form.get('bank_name', '').strip()
            branch_name = request.form.get('branch_name', '').strip()
            account_number = request.form.get('account_number', '').strip()
            memo = request.form.get('memo', '').strip()
            
            # 勘定科目詳細情報を取得
            major_category = request.form.get('major_category', '').strip()
            mid_category = request.form.get('mid_category', '').strip()
            sub_category = request.form.get('sub_category', '').strip()
            income_counterpart = request.form.get('income_counterpart', '').strip()
            expense_counterpart = request.form.get('expense_counterpart', '').strip()
            tax_category = request.form.get('tax_category', '').strip()

            # ===== バリデーション =====
            if not account_name:
                flash('口座名は必須です', 'error')
                return redirect(url_for('account_create'))

            if not account_type:
                flash('口座種別は必須です', 'error')
                return redirect(url_for('account_create'))
            
            # 勘定科目詳細情報のバリデーション
            if not major_category:
                flash('大分類は必須です', 'error')
                return redirect(url_for('account_create'))
            
            if not mid_category:
                flash('中分類は必須です', 'error')
                return redirect(url_for('account_create'))
            
            if not sub_category:
                flash('小分類は必須です', 'error')
                return redirect(url_for('account_create'))
            
            if not income_counterpart:
                flash('収入取引相手方は必須です', 'error')
                return redirect(url_for('account_create'))
            
            if not expense_counterpart:
                flash('支出取引相手方は必須です', 'error')
                return redirect(url_for('account_create'))
            
            if not tax_category:
                flash('税区分は必須です', 'error')
                return redirect(url_for('account_create'))

            # 同一事業所内で同名口座の重複チェック
            existing = db.query(Account).filter(
                Account.organization_id == organization_id,
                Account.account_name == account_name
            ).first()
            if existing:
                flash(f'口座「{account_name}」は既に存在します', 'error')
                return redirect(url_for('account_create'))

            # ===== ここからが今回のポイント =====
            # 口座名＝勘定科目名となるように、同名の勘定科目を取得 or 作成
            display_name_for_item = display_name if display_name else account_name

            account_item = db.query(AccountItem).filter(
                AccountItem.organization_id == organization_id,
                AccountItem.account_name == account_name
            ).first()

            if not account_item:
                # 同名の勘定科目がなければ自動作成
                account_item = AccountItem(
                    organization_id=organization_id,
                    account_name=account_name,
                    display_name=display_name_for_item,
                    major_category=major_category,
                    mid_category=mid_category,
                    sub_category=sub_category,
                    income_counterpart=income_counterpart,
                    expense_counterpart=expense_counterpart,
                    tax_category=tax_category,
                    input_candidate=True       # 入力候補に出す
                )
                db.add(account_item)
                db.flush()  # account_item.id を取得するため

            # ===== 口座を作成（勘定科目IDを紐づける） =====
            account = Account(
                organization_id=organization_id,
                account_name=account_name,
                account_type=account_type,
                display_name=display_name if display_name else None,
                bank_name=bank_name if bank_name else None,
                branch_name=branch_name if branch_name else None,
                account_number=account_number if account_number else None,
                memo=memo if memo else None,
                account_item_id=account_item.id  # ← ここが重要
            )

            db.add(account)
            db.commit()

            flash(f'口座「{account_name}」を作成しました', 'success')
            return redirect(url_for('accounts_list'))

        # GET のとき
        # 分類階層データと選択肢データを読み込む
        import json
        categories_path = os.path.join(os.path.dirname(__file__), 'account_item_categories.json')
        with open(categories_path, 'r', encoding='utf-8') as f:
            categories = json.load(f)
        
        options_path = os.path.join(os.path.dirname(__file__), 'account_item_options.json')
        with open(options_path, 'r', encoding='utf-8') as f:
            options = json.load(f)
        
        return render_template('accounts/form.html', categories=categories, options=options)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('accounts_list'))
    finally:
        db.close()




@bp.route('/accounts/<int:account_id>/edit', methods=['GET', 'POST'])
@login_required
def account_edit(account_id):
    """口座編集"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        # 対象口座の取得
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.organization_id == organization_id
        ).first()
        if not account:
            flash('口座が見つかりません', 'error')
            return redirect(url_for('accounts_list'))

        if request.method == 'POST':
            # フォームデータを取得
            account_name = request.form.get('account_name', '').strip()
            account_type = request.form.get('account_type', '').strip()
            display_name = request.form.get('display_name', '').strip()
            bank_name = request.form.get('bank_name', '').strip()
            branch_name = request.form.get('branch_name', '').strip()
            account_number = request.form.get('account_number', '').strip()
            memo = request.form.get('memo', '').strip()
            
            # 勘定科目詳細情報を取得
            major_category = request.form.get('major_category', '').strip()
            mid_category = request.form.get('mid_category', '').strip()
            sub_category = request.form.get('sub_category', '').strip()
            income_counterpart = request.form.get('income_counterpart', '').strip()
            expense_counterpart = request.form.get('expense_counterpart', '').strip()
            tax_category = request.form.get('tax_category', '').strip()

            # ===== バリデーション =====
            if not account_name:
                flash('口座名は必須です', 'error')
                return redirect(url_for('account_edit', account_id=account_id))

            if not account_type:
                flash('口座種別は必須です', 'error')
                return redirect(url_for('account_edit', account_id=account_id))

            # 同じ名前の別口座が存在しないかチェック
            existing = db.query(Account).filter(
                Account.organization_id == organization_id,
                Account.account_name == account_name,
                Account.id != account_id
            ).first()
            if existing:
                flash(f'口座「{account_name}」は既に存在します', 'error')
                return redirect(url_for('account_edit', account_id=account_id))

            # ===== 勘定科目との連動部分 =====
            display_name_for_item = display_name if display_name else account_name

            # まず現在紐づいている勘定科目を取得
            account_item = None
            if account.account_item_id:
                account_item = db.query(AccountItem).filter(
                    AccountItem.id == account.account_item_id,
                    AccountItem.organization_id == organization_id
                ).first()

            if account_item:
                # 既存の勘定科目を口座名に合わせてリネーム
                account_item.account_name = account_name
                account_item.display_name = display_name_for_item
                # 勘定科目詳細情報を更新
                if major_category:
                    account_item.major_category = major_category
                if mid_category:
                    account_item.mid_category = mid_category
                if sub_category:
                    account_item.sub_category = sub_category
                if income_counterpart:
                    account_item.income_counterpart = income_counterpart
                if expense_counterpart:
                    account_item.expense_counterpart = expense_counterpart
                if tax_category:
                    account_item.tax_category = tax_category
            else:
                # ひも付いていない場合 or 勘定科目が見つからない場合は、新規 or 既存を探す
                account_item = db.query(AccountItem).filter(
                    AccountItem.organization_id == organization_id,
                    AccountItem.account_name == account_name
                ).first()

                if not account_item:
                    # なければ新規作成
                    account_item = AccountItem(
                        organization_id=organization_id,
                        account_name=account_name,
                        display_name=display_name_for_item,
                        major_category=major_category if major_category else '資産',
                        mid_category=mid_category if mid_category else None,
                        sub_category=sub_category if sub_category else None,
                        income_counterpart=income_counterpart if income_counterpart else None,
                        expense_counterpart=expense_counterpart if expense_counterpart else None,
                        tax_category=tax_category if tax_category else None,
                        input_candidate=True
                    )
                    db.add(account_item)
                    db.flush()
                else:
                    # 既存の勘定科目を更新
                    if major_category:
                        account_item.major_category = major_category
                    if mid_category:
                        account_item.mid_category = mid_category
                    if sub_category:
                        account_item.sub_category = sub_category
                    if income_counterpart:
                        account_item.income_counterpart = income_counterpart
                    if expense_counterpart:
                        account_item.expense_counterpart = expense_counterpart
                    if tax_category:
                        account_item.tax_category = tax_category

                # 口座に勘定科目IDをセット
                account.account_item_id = account_item.id

            # ===== 口座情報本体の更新 =====
            account.account_name = account_name
            account.account_type = account_type
            account.display_name = display_name if display_name else None
            account.bank_name = bank_name if bank_name else None
            account.branch_name = branch_name if branch_name else None
            account.account_number = account_number if account_number else None
            account.memo = memo if memo else None

            db.commit()

            flash(f'口座「{account_name}」を更新しました', 'success')
            return redirect(url_for('accounts_list'))

        # GET のとき
        # 分類階層データと選択肢データを読み込む
        import json
        categories_path = os.path.join(os.path.dirname(__file__), 'account_item_categories.json')
        with open(categories_path, 'r', encoding='utf-8') as f:
            categories = json.load(f)
        
        options_path = os.path.join(os.path.dirname(__file__), 'account_item_options.json')
        with open(options_path, 'r', encoding='utf-8') as f:
            options = json.load(f)
        
        # 口座に紐づく勘定科目情報を取得
        account_item = None
        if account.account_item_id:
            account_item = db.query(AccountItem).filter(
                AccountItem.id == account.account_item_id,
                AccountItem.organization_id == organization_id
            ).first()
        
        return render_template('accounts/form.html', account=account, account_item=account_item, categories=categories, options=options)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('accounts_list'))
    finally:
        db.close()


# 口座表示切替API


@bp.route('/api/accounts/<int:account_id>/toggle-visibility', methods=['POST'])
@login_required
def account_toggle_visibility(account_id):
    """口座の出納帳一覧表示フラグを切替"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.organization_id == organization_id
        ).first()
        if not account:
            return jsonify({'success': False, 'message': '口座が見つかりません'}), 404
        
        data = request.get_json()
        is_visible = data.get('is_visible', True)
        
        account.is_visible_in_list = is_visible
        db.commit()
        
        return jsonify({
            'success': True, 
            'message': f'口座「{account.account_name}」の表示設定を更新しました',
            'is_visible': is_visible
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 口座削除API


@bp.route('/api/accounts/<int:account_id>/delete', methods=['POST'])
@login_required
def account_delete(account_id):
    """口座削除"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.organization_id == organization_id
        ).first()
        if not account:
            return jsonify({'success': False, 'message': '口座が見つかりません'}), 404
        
        account_name = account.account_name
        db.delete(account)
        db.commit()
        
        return jsonify({'success': True, 'message': '口座「' + account_name + '」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 口座CSV/ExcelインポートAPI


@bp.route('/api/accounts/import', methods=['POST'])
@login_required
def import_accounts():
    """口座をCSV/Excelファイルからインポート"""
    organization_id = get_current_organization_id()
    try:
        # ファイルを取得
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'ファイルが選択されていません'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'ファイルが選択されていません'}), 400
        
        # ファイル種別を判定
        filename = file.filename.lower()
        if filename.endswith('.csv'):
            file_type = 'csv'
        elif filename.endswith(('.xlsx', '.xls')):
            file_type = 'excel'
        else:
            return jsonify({'success': False, 'message': 'CSVまたはExcelファイルを選択してください'}), 400
        
        # ファイル内容を読み込み
        file_content = file.read()
        
        # インポート処理を実行
        processor = ImportProcessor()
        db = SessionLocal()
        
        try:
            # ファイルを読み込み
            if file_type == 'csv':
                rows = processor.read_csv_file(file_content)
            else:
                rows = processor.read_excel_file(file_content)
            
            if rows is None or len(rows) == 0:
                return jsonify({
                    'success': False,
                    'message': 'ファイルが空です'
                }), 400
            
            # 最初の行をヘッダーとして使用
            headers = rows[0] if len(rows) > 0 else []
            data_rows = rows[1:] if len(rows) > 1 else []
            
            imported_count = 0
            errors = []
            
            # 各行を処理
            for row_idx, row in enumerate(data_rows, start=2):
                try:
                    # 最低限必須列数を確認
                    if len(row) < 2:
                        errors.append(f'行 {row_idx}: 列数が不足しています')
                        continue
                    
                    # 口座名を取得
                    account_name = str(row[0]).strip() if row[0] else None
                    if not account_name:
                        errors.append(f'行 {row_idx}: 口座名が空です')
                        continue
                    
                    # 複数存在をチェック（同一事業所内）
                    existing = db.query(Account).filter(
                        Account.organization_id == organization_id,
                        Account.account_name == account_name
                    ).first()
                    
                    if existing:
                        errors.append(f'行 {row_idx}: 口座「{account_name}」は既に存在します')
                        continue
                    
                    # 口座種別を取得
                    account_type = str(row[1]).strip() if len(row) > 1 and row[1] else None
                    if not account_type:
                        errors.append(f'行 {row_idx}: 口座種別が空です')
                        continue
                    
                    # その他の属性を取得
                    display_name = str(row[2]).strip() if len(row) > 2 and row[2] else None
                    bank_name = str(row[3]).strip() if len(row) > 3 and row[3] else None
                    branch_name = str(row[4]).strip() if len(row) > 4 and row[4] else None
                    account_number = str(row[5]).strip() if len(row) > 5 and row[5] else None
                    memo = str(row[6]).strip() if len(row) > 6 and row[6] else None
                    
                    # 口座を作成
                    account = Account(
                        organization_id=organization_id,
                        account_name=account_name,
                        account_type=account_type,
                        display_name=display_name,
                        bank_name=bank_name,
                        branch_name=branch_name,
                        account_number=account_number,
                        memo=memo
                    )
                    
                    db.add(account)
                    imported_count += 1
                
                except Exception as e:
                    errors.append(f'行 {row_idx}: {str(e)}')
                    continue
            
            # コミット
            db.commit()
            
            return jsonify({
                'success': True,
                'imported_count': imported_count,
                'errors': errors,
                'message': f'{imported_count}件をインポートしました'
            })
        
        except Exception as e:
            db.rollback()
            return jsonify({
                'success': False,
                'message': f'インポート処理中にエラーが発生しました: {str(e)}'
            }), 500
        finally:
            db.close()
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500


# ========== 消費税区分管理 ==========

