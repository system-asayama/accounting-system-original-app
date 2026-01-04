from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
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
from blueprints.transactions import transactions_bp
from blueprints.auth import bp as auth_bp
from blueprints.system_admin import bp as system_admin_bp
from blueprints.tenant_admin import bp as tenant_admin_bp
from blueprints.admin import bp as admin_bp
from blueprints.employee import bp as employee_bp

# -----------------------------------------------------------------------------
# Standard library imports used throughout this application.
#
# The CSV/Excel import endpoint defined later in this file relies on the
# built‑in ``csv`` and ``io`` modules to parse uploaded files. Without these
# imports the application will raise a ``NameError`` when processing an
# import request. In such cases Flask returns its default HTML error page,
# which starts with a ``<!doctype html>`` declaration. Client‑side JavaScript
# expecting a JSON response will then attempt to parse this HTML as JSON and
# fail with a ``SyntaxError: Unexpected token '<'`` (or similar). To avoid
# this situation we explicitly import ``csv`` and ``io`` here.
import csv
import io

# データベーステーブルを作成
Base.metadata.create_all(bind=engine)

# ログインシステムのマイグレーションを実行
try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from app.migrations import run_migrations
    print("✅ ログインシステムのマイグレーションを実行中...")
    run_migrations()
    print("✅ ログインシステムのマイグレーションが完了しました")
except Exception as e:
    print(f"⚠️ ログインシステムのマイグレーションエラー: {e}")
    import traceback
    traceback.print_exc()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Blueprintを登録
app.register_blueprint(transactions_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(system_admin_bp)
app.register_blueprint(tenant_admin_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(employee_bp)

# ========== 認証デコレーター ==========
# 新しい認証システムのデコレーターをインポート
from auth_utils.helpers import login_required as auth_login_required

def login_required(f):
    """ログインが必要なルートに付与するデコレーター（新認証システム）"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # ユーザーログインをチェック
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        # 組織選択もチェック
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

# テンプレートで使用する変数や関数を提供
@app.context_processor
def inject_globals():
    """Ｊｉｎｊａ２テンプレートにグローバル変数を注入"""
    current_org = get_current_organization()
    current_fiscal_period = None
    
    # 会計期間情報を取得（最新の会計期間）
    if current_org:
        db = SessionLocal()
        try:
            current_fiscal_period = db.query(FiscalPeriod).filter(
                FiscalPeriod.organization_id == current_org.id
            ).order_by(FiscalPeriod.start_date.desc()).first()
        finally:
            db.close()
    
    return dict(
        Account=Account,
        current_organization=current_org,
        current_fiscal_period=current_fiscal_period
    )

# ========== 起動時の初期データ作成 ==========
def initialize_default_accounts():
    """起動時に口座マスターを自動作成"""
    db = SessionLocal()
    try:
        # 口座が存在しない場合だけ初期データを作成
        existing_accounts = db.query(Account).count()
        if existing_accounts > 0:
            return  # 口座が既に存在している場合、作成をスキップ
        
        # 初期口座データを定義
        default_accounts = [
            {
                'account_name': '現金',
                'account_type': 'cash',
                'display_name': '現金'
            },
            {
                'account_name': '普通預金',
                'account_type': 'bank',
                'display_name': '普通預金'
            },
            {
                'account_name': '当座預金',
                'account_type': 'bank',
                'display_name': '当座預金'
            },
            {
                'account_name': 'クレジットカード',
                'account_type': 'credit_card',
                'display_name': 'クレジットカード'
            },
            {
                'account_name': '電子決済',
                'account_type': 'e_money',
                'display_name': '電子決済'
            },
            {
                'account_name': '売掛金',
                'account_type': 'receivable',
                'display_name': '売掛金'
            },
            {
                'account_name': '買掛金',
                'account_type': 'payable',
                'display_name': '買掛金'
            }
        ]
        
        # 初期口座を作成
        for account_data in default_accounts:
            account = Account(
                account_name=account_data['account_name'],
                account_type=account_data['account_type'],
                display_name=account_data['display_name']
            )
            db.add(account)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f'口座マスター初期化エラー: {str(e)}')
    finally:
        db.close()

# 起動時に初期データを作成
# initialize_default_accounts()  # マルチテナント対応のため一時無効化

def initialize_default_tax_categories():
    """起動時に税区分マスターを自動作成"""
    db = SessionLocal()
    try:
        # 税区分が存在しない場合だけ初期データを作成
        existing_tax_categories = db.query(TaxCategory).count()
        if existing_tax_categories > 0:
            return  # 税区分が既に存在している場合、作成をスキップ
        
        # 初期税区分データを定義
        default_tax_categories = [
            '課対仕入10%',
            '課対仕入8%',
            '課対仕入5%',
            '課対売上10%',
            '課対売上8%',
            '課対売上5%',
            '非課税売上',
            '免税売上',
            '課税対象外'
        ]
        
        # 初期税区分を作成
        for tax_category_name in default_tax_categories:
            tax_category = TaxCategory(name=tax_category_name)
            db.add(tax_category)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f'税区分マスター初期化エラー: {str(e)}')
    finally:
        db.close()

# 起動時に税区分初期データを作成
initialize_default_tax_categories()

def initialize_default_account_items():
    """起動時に勘定科目マスターを自動作成"""
    db = SessionLocal()
    try:
        # 勘定科目が存在しない場合だけ初期データを作成
        existing_account_items = db.query(AccountItem).count()
        if existing_account_items > 0:
            return  # 勘定科目が既に存在している場合、作成をスキップ
        
        # 初期勘定科目データを定義（一部抵抗勘定科目）
        # major_category: 資産, 負債, 純資産, 収益, 費用
        # liquidity_category: 流動資産, 固定資産, 流動負債, 固定負債, 純資産
        default_account_items = [
            # 資産 (流動資産: 10, 固定資産: 20, 投資その他の資産: 30)
            {'account_name': '現金', 'display_name': '現金', 'major_category': '資産', 'liquidity_category': '流動資産', 'liquidity_rank': 11, 'bs_category': '流動資産', 'bs_rank': 10},
            {'account_name': '普通預金', 'display_name': '普通預金', 'major_category': '資産', 'liquidity_category': '流動資産', 'liquidity_rank': 12, 'bs_category': '流動資産', 'bs_rank': 11},
            {'account_name': '当座預金', 'display_name': '当座預金', 'major_category': '資産', 'liquidity_category': '流動資産', 'liquidity_rank': 13, 'bs_category': '流動資産', 'bs_rank': 12},
            {'account_name': '定期預金', 'display_name': '定期預金', 'major_category': '資産', 'liquidity_category': '流動資産', 'liquidity_rank': 14, 'bs_category': '流動資産', 'bs_rank': 13},
            {'account_name': '应接金', 'display_name': '应接金', 'major_category': '資産', 'liquidity_category': '流動資産', 'liquidity_rank': 15, 'bs_category': '流動資産', 'bs_rank': 14},
            {'account_name': '应收金', 'display_name': '应收金', 'major_category': '資産', 'liquidity_category': '流動資産', 'liquidity_rank': 16, 'bs_category': '流動資産', 'bs_rank': 15},
            # 負債 (流動負債: 30, 固定負債: 40)
            {'account_name': '支付い高い金', 'display_name': '支付い高い金', 'major_category': '負債', 'liquidity_category': '流動負債', 'liquidity_rank': 31, 'bs_category': '流動負債', 'bs_rank': 30},
            {'account_name': '支付い手形', 'display_name': '支付い手形', 'major_category': '負債', 'liquidity_category': '流動負債', 'liquidity_rank': 32, 'bs_category': '流動負債', 'bs_rank': 31},
            {'account_name': '支付い下い金', 'display_name': '支付い下い金', 'major_category': '負債', 'liquidity_category': '流動負債', 'liquidity_rank': 33, 'bs_category': '流動負債', 'bs_rank': 32},
            {'account_name': '未払い金', 'display_name': '未払い金', 'major_category': '負債', 'liquidity_category': '流動負債', 'liquidity_rank': 34, 'bs_category': '流動負債', 'bs_rank': 33},
            # 収益 (純資産: 50)
            {'account_name': '売上高', 'display_name': '売上高', 'major_category': '収益', 'liquidity_category': '純資産', 'liquidity_rank': 51, 'pl_category': '売上高', 'pl_rank': 10},
            {'account_name': '売上を返し', 'display_name': '売上を返し', 'major_category': '収益', 'liquidity_category': '純資産', 'liquidity_rank': 52, 'pl_category': '売上高', 'pl_rank': 11},
            {'account_name': '値引を返し', 'display_name': '値引を返し', 'major_category': '収益', 'liquidity_category': '純資産', 'liquidity_rank': 53, 'pl_category': '売上高', 'pl_rank': 12},
            # 費用 (純資産: 50)
            {'account_name': '仕入高', 'display_name': '仕入高', 'major_category': '費用', 'liquidity_category': '純資産', 'liquidity_rank': 54, 'pl_category': '売上原価', 'pl_rank': 20},
            {'account_name': '仕入を返し', 'display_name': '仕入を返し', 'major_category': '費用', 'liquidity_category': '純資産', 'liquidity_rank': 55, 'pl_category': '売上原価', 'pl_rank': 21},
            {'account_name': '給料手形', 'display_name': '給料手形', 'major_category': '費用', 'liquidity_category': '純資産', 'liquidity_rank': 56, 'pl_category': '販管費', 'pl_rank': 40},
            {'account_name': '旅費交通費', 'display_name': '旅費交通費', 'major_category': '費用', 'liquidity_category': '純資産', 'liquidity_rank': 57, 'pl_category': '販管費', 'pl_rank': 41},
            {'account_name': '会議費', 'display_name': '会議費', 'major_category': '費用', 'liquidity_category': '純資産', 'liquidity_rank': 58, 'pl_category': '販管費', 'pl_rank': 42},
            {'account_name': '通信費', 'display_name': '通信費', 'major_category': '費用', 'liquidity_category': '純資産', 'liquidity_rank': 59, 'pl_category': '販管費', 'pl_rank': 43},
            {'account_name': '広告費', 'display_name': '広告費', 'major_category': '費用', 'liquidity_category': '純資産', 'liquidity_rank': 60, 'pl_category': '販管費', 'pl_rank': 44},
        ]
        
        # 初期勘定科目を作成
        # デフォルト組織が存在するか確認
        default_org = db.query(Organization).filter(Organization.id == 1).first()
        if not default_org:
            # デフォルト組織が存在しない場合は作成
            default_org = Organization(
                id=1,
                name='デフォルト組織',
                fiscal_year_start_month=4,
                tax_accounting_method='税込経理'
            )
            db.add(default_org)
            db.commit()
            
        for item_data in default_account_items:
            # organization_idを追加（デフォルト組織ID=1）
            item_data['organization_id'] = 1
            account_item = AccountItem(**item_data)
            db.add(account_item)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f'勘定科目マスター初期化エラー: {str(e)}')
    finally:
        db.close()

# 起動時に勘定科目初期データを作成
# initialize_default_account_items()  # 自動登録機能を無効化

def initialize_default_departments():
    """起動時に部門マスターを自動作成"""
    db = SessionLocal()
    try:
        # 部門が存在しない場合だけ初期データを作成
        existing_departments = db.query(Department).count()
        if existing_departments > 0:
            return  # 部門が既に存在している場合、作成をスキップ
        
        # 初期部門データを定義
        default_departments = [
            {'name': '計画'},
            {'name': '営業'},
            {'name': '管理'},
            {'name': '研究開発'},
        ]
        
        # 初期部門を作成
        for dept_data in default_departments:
            department = Department(**dept_data)
            db.add(department)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f'部門マスター初期化エラー: {str(e)}')
    finally:
        db.close()

def initialize_default_counterparties():
    """起動時に取引先マスターを自動作成"""
    db = SessionLocal()
    try:
        # 取引先が存在しない場合だけ初期データを作成
        existing_counterparties = db.query(Counterparty).count()
        if existing_counterparties > 0:
            return  # 取引先が既に存在している場合、作成をスキップ
        
        # 初期取引先データを定義
        default_counterparties = [
            {'name': '画社 A'},
            {'name': '画社 B'},
            {'name': '画社 C'},
        ]
        
        # 初期取引先を作成
        for counterparty_data in default_counterparties:
            counterparty = Counterparty(**counterparty_data)
            db.add(counterparty)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f'取引先マスター初期化エラー: {str(e)}')
    finally:
        db.close()

def initialize_default_items():
    """起動時に品目マスターを自動作成"""
    db = SessionLocal()
    try:
        # 品目が存在しない場合だけ初期データを作成
        existing_items = db.query(Item).count()
        if existing_items > 0:
            return  # 勘定科目が既に存在している場合、作成をスキップ       
        # 初期品目データを定義
        default_items = [
            {'name': 'サービス A'},
            {'name': 'サービス B'},
            {'name': 'サービス C'},
        ]
        
        # 初期品目を作成
        for item_data in default_items:
            item = Item(**item_data)
            db.add(item)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f'品目マスター初期化エラー: {str(e)}')
    finally:
        db.close()

def initialize_default_memo_tags():
    """起動時にメモタグマスターを自動作成"""
    db = SessionLocal()
    try:
        # メモタグが存在しない場合だけ初期データを作成
        existing_memo_tags = db.query(MemoTag).count()
        if existing_memo_tags > 0:
            return  # メモタグが既に存在している場合、作成をスキップ
        
        # 初期メモタグデータを定義
        default_memo_tags = [
            {'name': '緑費'},
            {'name': '緑費不算入'},
            {'name': '緑費不算出'},
            {'name': '緑費不算入出'},
        ]
        
        # 初期メモタグを作成
        for tag_data in default_memo_tags:
            memo_tag = MemoTag(**tag_data)
            db.add(memo_tag)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f'メモタグマスター初期化エラー: {str(e)}')
    finally:
        db.close()

# 起動時に各マスター初期データを作成
# initialize_default_departments()  # マルチテナント対応のため一時無効化
# initialize_default_counterparties()  # マルチテナント対応のため一時無効化
# initialize_default_items()  # マルチテナント対応のため一時無効化
# initialize_default_memo_tags()  # マルチテナント対応のため一時無効化

# ========== マスター管理画面 ==========

@app.route('/masters')
def masters_index():
    """マスター管理画面"""
    return render_template('masters/index.html')

# ========== ホーム画面 ==========

@app.route('/')
def home():
    """ホーム画面 - ログインしていない場合はログイン画面へ"""
    # ユーザーログインチェック
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    # 組織選択チェック
    if 'organization_id' not in session:
        return redirect(url_for('auth.login'))
    
    db = SessionLocal()
    try:
        # 統計情報を取得（事業所フィルタリング適用）
        organization_id = session['organization_id']
        account_items_count = db.query(AccountItem).filter(AccountItem.organization_id == organization_id).count()
        cash_books_count = db.query(CashBook).filter(CashBook.organization_id == organization_id).count()
        
        return render_template(
            'home.html',
            account_items_count=account_items_count,
            cash_books_count=cash_books_count
        )
    finally:
        db.close()

# データベースセッション取得用
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ホームページ
@app.route('/index')
@login_required
def index():
    return redirect(url_for('home'))











# 勘定科目全件取得API (Tom Select用)
@app.route('/api/account-items/all', methods=['GET'])
@login_required
def get_all_account_items():
    db = SessionLocal()
    try:
        # 勘定科目を取得
        items = db.query(AccountItem).filter(
            AccountItem.organization_id == session['organization_id']
        ).order_by(AccountItem.major_category.asc(), AccountItem.account_name.asc()).all()
        
        account_items_list = []
        for item in items:
            account_items_list.append({
                'id': item.id,
                'account_name': item.account_name,
                'display_name': item.display_name,
                'major_category': item.major_category,
                'is_account': False  # 勘定科目であることを示す
            })
        
        # 口座を取得して追加
        accounts = db.query(Account).filter(
            Account.organization_id == session['organization_id']
        ).all()
        
        for account in accounts:
            # 口座に対応する勘定科目を取得
            account_item = db.query(AccountItem).filter(
                AccountItem.id == account.account_item_id
            ).first()
            
            if account_item:
                account_items_list.append({
                    'id': f'account_{account.id}',  # 口座IDにプレフィックスを付ける
                    'account_name': account.account_name,  # 具体的な口座名（例：三井住友銀行 普通預金）
                    'display_name': account.account_name,
                    'major_category': '口座',  # カテゴリを「口座」に設定
                    'is_account': True,  # 口座であることを示す
                    'account_item_id': account.account_item_id  # 対応する勘定科目ID
                })
            
        return jsonify({'success': True, 'account_items': account_items_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 口座データ取得API
@app.route('/api/accounts/all')
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
@app.route('/cash-books/batch', methods=['GET'])
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
@app.route('/cash-books/new', methods=['GET', 'POST'])
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
@app.route('/cash-books/<int:item_id>/edit', methods=['GET', 'POST'])
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
@app.route('/api/cash-books/<int:item_id>/delete', methods=['POST'])
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
@app.route('/cash-books', methods=['GET'])
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
@app.route('/account-items', methods=['GET'])
@login_required
def account_items_list():
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '', type=str)
        page = request.args.get('page', 1, type=int)
        category_filter = request.args.get('category', '', type=str)  # 大分類フィルタ
        mid_filter = request.args.get('mid', '', type=str)  # 中分類フィルタ
        sub_filter = request.args.get('sub', '', type=str)  # 小分類フィルタ
        per_page = 20
        
        query = db.query(AccountItem).filter(AccountItem.organization_id == session['organization_id'])
        
        # 大分類フィルタを適用
        if category_filter:
            query = query.filter(AccountItem.major_category == category_filter)
        
        # 中分類フィルタを適用
        if mid_filter:
            query = query.filter(AccountItem.mid_category == mid_filter)
        
        # 小分類フィルタを適用
        if sub_filter:
            query = query.filter(AccountItem.sub_category == sub_filter)
        
        # 検索クエリを適用
        if search_query:
            query = query.filter(
                (AccountItem.account_name.ilike(f'%{search_query}%')) |
                (AccountItem.display_name.ilike(f'%{search_query}%'))
            )
        
        total_items = query.count()
        total_pages = (total_items + per_page - 1) // per_page
        
        offset = (page - 1) * per_page
        # 流動性配列順にソート: 大分類 → 中分類 → 小分類 → bs_rank → 勘定科目名
        from sqlalchemy import case
        
        # 大分類の順序（資産→負債→純資産→损益）
        major_order = case(
            (AccountItem.major_category == '資産', 1),
            (AccountItem.major_category == '負債', 2),
            (AccountItem.major_category == '純資産', 3),
            (AccountItem.major_category == '损益', 4),
            else_=9
        )
        
        # 中分類の順序
        mid_order = case(
            # 資産
            (AccountItem.mid_category == '流動資産', 1),
            (AccountItem.mid_category == '固定資産', 2),
            (AccountItem.mid_category == '繰延資産', 3),
            # 負債
            (AccountItem.mid_category == '流動負債', 1),
            (AccountItem.mid_category == '固定負債', 2),
            # 純資産
            (AccountItem.mid_category == '資本金', 1),
            (AccountItem.mid_category == '資本剰余金', 2),
            (AccountItem.mid_category == '利益剰余金', 3),
            (AccountItem.mid_category == '自己株式', 4),
            (AccountItem.mid_category == '評価換算差額等', 5),
            (AccountItem.mid_category == '新株予約権', 6),
            # 損益
            (AccountItem.mid_category == '売上高', 1),
            (AccountItem.mid_category == '売上原価', 2),
            (AccountItem.mid_category == '販売費及び一般管理費', 3),
            (AccountItem.mid_category == '営業外収益', 4),
            (AccountItem.mid_category == '営業外費用', 5),
            (AccountItem.mid_category == '特別利益', 6),
            (AccountItem.mid_category == '特別損失', 7),
            (AccountItem.mid_category == '法人税等', 8),
            else_=9
        )
        
        # 小分類の順序
        sub_order = case(
            # 資産
            (AccountItem.sub_category == '現金及び預金', 1),
            (AccountItem.sub_category == '売上債権', 2),
            (AccountItem.sub_category == '有価証券', 3),
            (AccountItem.sub_category == '棚卸資産', 4),
            (AccountItem.sub_category == 'その他流動資産', 5),
            (AccountItem.sub_category == '有形固定資産', 10),
            (AccountItem.sub_category == '無形固定資産', 11),
            (AccountItem.sub_category == '投資その他の資産', 12),
            (AccountItem.sub_category == '繰延資産', 20),
            # 負債
            (AccountItem.sub_category == '仕入債務', 30),
            (AccountItem.sub_category == 'その他流動負債', 31),
            (AccountItem.sub_category == '固定負債', 40),
            # 損益（売上高）
            (AccountItem.sub_category == '売上高', 100),
            # 損益（売上原価）
            (AccountItem.sub_category == '売上原価', 110),
            # 損益（販管費）
            (AccountItem.sub_category == '販売費', 120),
            (AccountItem.sub_category == '一般管理費', 121),
            # 損益（営業外）
            (AccountItem.sub_category == '営業外収益', 130),
            (AccountItem.sub_category == '営業外費用', 131),
            # 損益（特別損益）
            (AccountItem.sub_category == '特別利益', 140),
            (AccountItem.sub_category == '特別損失', 141),
            # 損益（税金）
            (AccountItem.sub_category == '法人税等', 150),
            else_=999
        )
        
        items = query.order_by(
            major_order.asc(),
            mid_order.asc(),
            sub_order.asc(),
            AccountItem.bs_rank.asc().nullslast(),
            AccountItem.account_name.asc()
        ).offset(offset).limit(per_page).all()
        
        # 各カテゴリの件数を取得
        base_query = db.query(AccountItem).filter(AccountItem.organization_id == session['organization_id'])
        category_counts = {
            'all': base_query.count(),
            '損益': base_query.filter(AccountItem.major_category == '損益').count(),
            '資産': base_query.filter(AccountItem.major_category == '資産').count(),
            '負債': base_query.filter(AccountItem.major_category == '負債').count(),
            '純資産': base_query.filter(AccountItem.major_category == '純資産').count(),
        }
        
        # 選択された大分類の中分類一覧を取得
        mid_categories = []
        if category_filter:
            mid_query = base_query.filter(AccountItem.major_category == category_filter)
            mid_results = db.query(AccountItem.mid_category, func.count(AccountItem.id)).filter(
                AccountItem.organization_id == session['organization_id'],
                AccountItem.major_category == category_filter
            ).group_by(AccountItem.mid_category).all()
            
            # 中分類の順序定義
            mid_order_map = {
                '流動資産': 1, '固定資産': 2, '繰延資産': 3,
                '流動負債': 1, '固定負債': 2,
                '資本金': 1, '資本剰余金': 2, '利益剰余金': 3, '自己株式': 4, '評価換算差額等': 5, '新株予約権': 6,
                '売上高': 1, '売上原価': 2, '販売費及び一般管理費': 3, '営業外収益': 4, '営業外費用': 5, '特別利益': 6, '特別損失': 7, '法人税等': 8
            }
            mid_categories = sorted(
                [{'name': name, 'count': count} for name, count in mid_results if name],
                key=lambda x: mid_order_map.get(x['name'], 999)
            )
        
        # 選択された中分類の小分類一覧を取得
        sub_categories = []
        if mid_filter:
            sub_results = db.query(AccountItem.sub_category, func.count(AccountItem.id)).filter(
                AccountItem.organization_id == session['organization_id'],
                AccountItem.mid_category == mid_filter
            ).group_by(AccountItem.sub_category).all()
            
            # 小分類の順序定義
            sub_order_map = {
                # 資産
                '現金及び預金': 1, '売上債権': 2, '有価証券': 3, '棚卸資産': 4, 'その他流動資産': 5,
                '有形固定資産': 10, '無形固定資産': 11, '投資その他の資産': 12,
                '繰延資産': 20,
                # 負債
                '仕入債務': 30, 'その他流動負債': 31, '固定負債': 40,
                # 損益
                '売上高': 100,
                # 売上原価の詳細
                '期首商品棚卸高': 110, '当期商品仕入': 111, '他勘定振替高(商)': 112, '期末商品棚卸高': 113,
                '売上原価': 114,
                # 販管費
                '販売費': 120, '一般管理費': 121,
                # 営業外
                '営業外収益': 130, '営業外費用': 131,
                # 特別損益
                '特別利益': 140, '特別損失': 141,
                # 税金
                '法人税等': 150
            }
            sub_categories = sorted(
                [{'name': name, 'count': count} for name, count in sub_results if name],
                key=lambda x: sub_order_map.get(x['name'], 999)
            )
        
        return render_template(
            'account_items/list.html',
            items=items,
            search_query=search_query,
            page=page,
            total_pages=total_pages,
            total_items=total_items,
            category_filter=category_filter,
            mid_filter=mid_filter,
            sub_filter=sub_filter,
            category_counts=category_counts,
            mid_categories=mid_categories,
            sub_categories=sub_categories
        )
    finally:
        db.close()

# 勘定科目新規追加ページ
# 勘定科目新規追加ページ
@app.route('/account-items/new', methods=['GET', 'POST'])
@login_required
def account_item_create():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # フォームデータを取得
            account_name = request.form.get('account_name', '').strip()
            display_name = request.form.get('display_name', '').strip()
            major_category = request.form.get('major_category', '').strip()
            mid_category = request.form.get('mid_category', '').strip()
            sub_category = request.form.get('sub_category', '').strip()
            income_counterpart = request.form.get('income_counterpart', '').strip()
            expense_counterpart = request.form.get('expense_counterpart', '').strip()
            tax_category = request.form.get('tax_category', '').strip()
            
            # 表示順序関連
            bs_rank_str = request.form.get('bs_rank', '').strip()
            liquidity_rank_str = request.form.get('liquidity_rank', '').strip()
            bs_rank = int(bs_rank_str) if bs_rank_str else None
            liquidity_rank = int(liquidity_rank_str) if liquidity_rank_str else None
            
            # バリデーション
            if not account_name:
                flash('勘定科目名は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not display_name:
                flash('表示名は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not major_category:
                flash('大分類は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not mid_category:
                flash('中分類は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not sub_category:
                flash('小分類は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not income_counterpart:
                flash('収入取引相手方は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not expense_counterpart:
                flash('支出取引相手方は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not tax_category:
                flash('税区分は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            # 重複チェック
            existing = db.query(AccountItem).filter(
                AccountItem.organization_id == session['organization_id'],
                AccountItem.account_name == account_name
            ).first()
            
            if existing:
                flash('この勘定科目名は既に登録されています', 'error')
                return redirect(url_for('account_item_create'))
            
            # 新規作成
            new_item = AccountItem(
                account_name=account_name,
                display_name=display_name,
                major_category=major_category,
                mid_category=mid_category,
                sub_category=sub_category,
                income_counterpart=income_counterpart,
                expense_counterpart=expense_counterpart,
                tax_category=tax_category,
                bs_rank=bs_rank,
                liquidity_rank=liquidity_rank,
                organization_id=session['organization_id']
            )
            
            db.add(new_item)
            db.commit()
            
            flash(f'勘定科目「{account_name}」を追加しました', 'success')
            return redirect(url_for('account_items_list'))
        
        # 分類階層データを読み込む
        import json
        categories_path = os.path.join(os.path.dirname(__file__), 'account_item_categories.json')
        with open(categories_path, 'r', encoding='utf-8') as f:
            categories = json.load(f)
        
        # 選択肢データを読み込む
        options_path = os.path.join(os.path.dirname(__file__), 'account_item_options.json')
        with open(options_path, 'r', encoding='utf-8') as f:
            options = json.load(f)
        
        return render_template('account_items/form.html', categories=categories, options=options)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('account_items_list'))
    finally:
        db.close()

# 勘定科目編集ページ
@app.route('/account-items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def account_item_edit(item_id):
    db = SessionLocal()
    try:
        item = db.query(AccountItem).filter(
            AccountItem.id == item_id,
            AccountItem.organization_id == session['organization_id']
        ).first()
        if not item:
            flash('勘定科目が見つかりません', 'error')
            return redirect(url_for('account_items_list'))
        
        if request.method == 'POST':
            # フォームデータを取得
            account_name = request.form.get('account_name', '').strip()
            display_name = request.form.get('display_name', '').strip()
            major_category = request.form.get('major_category', '').strip()
            mid_category = request.form.get('mid_category', '').strip()
            sub_category = request.form.get('sub_category', '').strip()
            income_counterpart = request.form.get('income_counterpart', '').strip()
            expense_counterpart = request.form.get('expense_counterpart', '').strip()
            tax_category = request.form.get('tax_category', '').strip()
            
            # 表示順序関連
            bs_rank_str = request.form.get('bs_rank', '').strip()
            liquidity_rank_str = request.form.get('liquidity_rank', '').strip()
            bs_rank = int(bs_rank_str) if bs_rank_str else None
            liquidity_rank = int(liquidity_rank_str) if liquidity_rank_str else None
            
            # バリデーション
            if not account_name:
                flash('勘定科目名は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not display_name:
                flash('表示名は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not major_category:
                flash('大分類は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not mid_category:
                flash('中分類は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not sub_category:
                flash('小分類は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not income_counterpart:
                flash('収入取引相手方は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not expense_counterpart:
                flash('支出取引相手方は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not tax_category:
                flash('税区分は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            # 重複チェック（自分自身は除外）
            existing = db.query(AccountItem).filter(
                AccountItem.organization_id == session['organization_id'],
                AccountItem.account_name == account_name,
                AccountItem.id != item_id
            ).first()
            
            if existing:
                flash('この勘定科目名は既に登録されています', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            # 更新
            item.account_name = account_name
            item.display_name = display_name
            item.major_category = major_category
            item.mid_category = mid_category
            item.sub_category = sub_category
            item.income_counterpart = income_counterpart
            item.expense_counterpart = expense_counterpart
            item.tax_category = tax_category
            item.bs_rank = bs_rank
            item.liquidity_rank = liquidity_rank
            
            db.commit()
            
            flash(f'勘定科目「{account_name}」を更新しました', 'success')
            return redirect(url_for('account_items_list'))
        
        # 分類階層データを読み込む
        import json
        categories_path = os.path.join(os.path.dirname(__file__), 'account_item_categories.json')
        with open(categories_path, 'r', encoding='utf-8') as f:
            categories = json.load(f)
        
        # 選択肢データを読み込む
        options_path = os.path.join(os.path.dirname(__file__), 'account_item_options.json')
        with open(options_path, 'r', encoding='utf-8') as f:
            options = json.load(f)
        
        return render_template('account_items/form.html', item=item, categories=categories, options=options)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('account_items_list'))
    finally:
        db.close()

@app.route('/import', methods=['GET', 'POST'])
def import_page():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # ファイルアップロード処理
            if 'file' not in request.files:
                flash('ファイルが選択されていません', 'error')
                return redirect(url_for('import_page'))
            
            file = request.files['file']
            if file.filename == '':
                flash('ファイルが選択されていません', 'error')
                return redirect(url_for('import_page'))
            
            # ファイルタイプを判定
            file_type = request.form.get('file_type', 'csv')
            
            # ファイル内容を読み込み
            file_content = file.read()
            
            # プレビューを表示するページにリダイレクト
            return redirect(url_for(
                'import_preview',
                file_type=file_type
            ))
        
        # 保存済みテンプレートを取得
        templates = db.query(ImportTemplate).all()
        
        return render_template('import/index.html', templates=templates)
    finally:
        db.close()

# インポートプレビューページ
@app.route('/import/preview', methods=['GET', 'POST'])
def import_preview():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # マッピング情報を取得
            file_type = request.form.get('file_type')
            file_content = request.form.get('file_content')
            skip_rows = int(request.form.get('skip_rows', 0))
            template_name = request.form.get('template_name', '').strip()
            account_item_id = request.form.get('account_item_id', type=int)
            
            # マッピング情報を取得
            mapping = {}
            date_col = request.form.get('date_col')
            amount_col = request.form.get('amount_col')
            counterparty_col = request.form.get('counterparty_col')
            remarks_col = request.form.get('remarks_col')
            
            if date_col:
                mapping['date_col'] = int(date_col)
            if amount_col:
                mapping['amount_col'] = int(amount_col)
            if counterparty_col:
                mapping['counterparty_col'] = int(counterparty_col)
            if remarks_col:
                mapping['remarks_col'] = int(remarks_col)
            if account_item_id:
                mapping['account_item_id'] = account_item_id
            
            # テンプレートを保存（指定された場合）
            if template_name:
                existing_template = db.query(ImportTemplate).filter(
                    ImportTemplate.name == template_name
                ).first()
                
                if existing_template:
                    existing_template.mapping_json = json.dumps(mapping)
                    existing_template.skip_rows = skip_rows
                else:
                    new_template = ImportTemplate(
                        name=template_name,
                        file_type=file_type,
                        mapping_json=json.dumps(mapping),
                        skip_rows=skip_rows
                    )
                    db.add(new_template)
                db.commit()
            
            # インポートを実行
            processor = ImportProcessor()
            result = processor.import_data(
                file_content.encode() if isinstance(file_content, str) else file_content,
                file_type,
                mapping,
                skip_rows,
                account_item_id
            )
            
            # 結果を表示
            return render_template(
                'import/result.html',
                result=result,
                template_name=template_name
            )
        
        # GETリクエストの場合、セッションからファイル情報を取得
        # ここでは実装を粗くしています
        return redirect(url_for('import_page'))
    finally:
        db.close()

# インポートテンプレート一覧
@app.route('/import/templates', methods=['GET'])
def import_templates_list():
    db = SessionLocal()
    try:
        templates = db.query(ImportTemplate).all()
        return render_template('import/templates.html', templates=templates)
    finally:
        db.close()

# ========== 連続仕訳テンプレート機能 ==========

# テンプレート一覧ページ
@app.route('/templates', methods=['GET'])
@login_required
def templates_list():
    db = SessionLocal()
    try:
        templates = db.query(Template).filter(
            Template.organization_id == session['organization_id']
        ).all()
        
        # 勘定科目と税区分の情報を取得
        template_data = []
        for t in templates:
            account_item = db.query(AccountItem).filter(AccountItem.id == t.account_item_id).first()
            tax_category = db.query(TaxCategory).filter(TaxCategory.id == t.tax_category_id).first()
            
            template_data.append({
                'id': t.id,
                'name': t.name,
                'account_item_name': account_item.account_name if account_item else '不明',
                'tax_category_name': tax_category.name if tax_category else '不明',
                'counterparty': t.counterparty,
                'item_name': t.item_name,
                'department': t.department,
                'memo_tag': t.memo_tag,
                'remarks': t.remarks,
                'transaction_type': '収入' if t.transaction_type == 1 else '支出'
            })
            
        return render_template('templates/list.html', templates=template_data)
    finally:
        db.close()

# テンプレート新規作成・編集ページ
@app.route('/templates/new', methods=['GET', 'POST'])
@app.route('/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
def template_form(template_id=None):
    db = SessionLocal()
    try:
        template = None
        if template_id:
            template = db.query(Template).filter(
                Template.id == template_id,
                Template.organization_id == session['organization_id']
            ).first()
            if not template:
                flash('テンプレートが見つかりません', 'error')
                return redirect(url_for('templates_list'))

        if request.method == 'POST':
            # フォームデータを取得
            name = request.form.get('name', '').strip()
            account_item_id = request.form.get('account_item_id', type=int)
            tax_category_id = request.form.get('tax_category_id', type=int)
            counterparty = request.form.get('counterparty', '').strip()
            item_name = request.form.get('item_name', '').strip()
            department = request.form.get('department', '').strip()
            memo_tag = request.form.get('memo_tag', '').strip()
            remarks = request.form.get('remarks', '').strip()
            transaction_type = request.form.get('transaction_type', type=int)

            # バリデーション
            if not name or not account_item_id or transaction_type is None:
                flash('テンプレート名、勘定科目、取引種別は必須です', 'error')
                return redirect(request.url)

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if template:
                # 更新
                template.name = name
                template.account_item_id = account_item_id
                template.tax_category_id = tax_category_id
                template.counterparty = counterparty
                template.item_name = item_name
                template.department = department
                template.memo_tag = memo_tag
                template.remarks = remarks
                template.transaction_type = transaction_type
                template.updated_at = now
                flash(f'テンプレート「{name}」を更新しました', 'success')
            else:
                # 新規作成
                template = Template(
                    organization_id=session['organization_id'],
                    name=name,
                    account_item_id=account_item_id,
                    tax_category_id=tax_category_id,
                    counterparty=counterparty,
                    item_name=item_name,
                    department=department,
                    memo_tag=memo_tag,
                    remarks=remarks,
                    transaction_type=transaction_type,
                    created_at=now,
                    updated_at=now
                )
                db.add(template)
                flash(f'テンプレート「{name}」を追加しました', 'success')

            db.commit()
            return redirect(url_for('templates_list'))

        # GETリクエストの場合
        account_items = db.query(AccountItem).filter(AccountItem.organization_id == session['organization_id']).all()
        tax_categories = db.query(TaxCategory).all()
        
        return render_template(
            'templates/form.html',
            template=template,
            account_items=account_items,
            tax_categories=tax_categories
        )
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('templates_list'))
    finally:
        db.close()

# テンプレート削除API
@app.route('/api/templates/<int:template_id>/delete', methods=['POST'])
@login_required
def template_delete(template_id):
    db = SessionLocal()
    try:
        template = db.query(Template).filter(
            Template.id == template_id,
            Template.organization_id == session['organization_id']
        ).first()
        if not template:
            return jsonify({'success': False, 'message': 'テンプレートが見つかりません'}), 404
        
        name = template.name
        db.delete(template)
        db.commit()
        
        return jsonify({'success': True, 'message': f'テンプレート「{name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# テンプレート全件取得API (連続仕訳登録画面用)
@app.route('/api/templates/all', methods=['GET'])
@login_required
def get_all_templates():
    db = SessionLocal()
    try:
        templates = db.query(Template).filter(
            Template.organization_id == session['organization_id']
        ).all()
        
        templates_list = []
        for t in templates:
            account_item = db.query(AccountItem).filter(AccountItem.id == t.account_item_id).first()
            tax_category = db.query(TaxCategory).filter(TaxCategory.id == t.tax_category_id).first()
            
            templates_list.append({
                'id': t.id,
                'name': t.name,
                'account_item_id': t.account_item_id,
                'account_item_name': account_item.account_name if account_item else '',
                'tax_category_id': t.tax_category_id,
                'tax_category_name': tax_category.name if tax_category else '',
                'counterparty': t.counterparty,
                'item_name': t.item_name,
                'department': t.department,
                'memo_tag': t.memo_tag,
                'remarks': t.remarks,
                'transaction_type': t.transaction_type,
                'display_name': f"{t.name} ({'収入' if t.transaction_type == 1 else '支出'})"
            })
            
        return jsonify(templates_list)
    finally:
        db.close()

# 選択された大分類に属する勘定科目を返すAPI
@app.route('/api/account-items/by-major-category', methods=['GET'])
@login_required
def get_account_items_by_major_category():
    db = SessionLocal()
    try:
        major_category = request.args.get('major_category')
        
        if not major_category:
            return jsonify({'success': False, 'message': 'major_category is required'}), 400
        
        items = db.query(AccountItem).filter(
            AccountItem.organization_id == session['organization_id'],
            AccountItem.major_category == major_category
        ).order_by(AccountItem.account_name.asc()).all()
        
        # JSON形式に変換
        account_items_data = [
            {
                'id': item.id,
                'account_name': item.account_name,
                'display_name': item.display_name
            } for item in items
        ]
        return jsonify({'success': True, 'account_items': account_items_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

@app.route('/api/cash-books/batch', methods=['POST'])
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
@app.route('/api/cash-books/list', methods=['GET'])
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
@app.route('/api/cash-books/<int:item_id>', methods=['GET'])
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
@app.route('/api/cash-books/<int:item_id>', methods=['PUT'])
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

@app.route('/import-templates/<int:template_id>/delete', methods=['POST'])
def delete_import_template(template_id):
    db = SessionLocal()
    try:
        template = db.query(ImportTemplate).filter(ImportTemplate.id == template_id).first()
        if not template:
            return jsonify({'success': False, 'message': 'テンプレートが見つかりません'}), 404
        
        db.delete(template)
        db.commit()
        return jsonify({'success': True, 'message': 'テンプレートを削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# TaxCategoryの一覧を取得するAPI
@app.route('/api/tax-categories/all', methods=['GET'])
def get_all_tax_categories():
    db = SessionLocal()
    try:
        tax_categories = db.query(TaxCategory).all()
        
        # JSON形式に変換
        tax_categories_list = [
            {'id': tc.id, 'name': tc.name}
            for tc in tax_categories
        ]
        
        return jsonify({'success': True, 'tax_categories': tax_categories_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


@app.route('/cash-books/<int:cash_book_id>/update', methods=['POST'])
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
@app.route("/import-account-items", methods=["POST"])
def import_account_items():
    """
    勘定科目CSVをアップロードして取り込むAPI
    freee の勘定科目CSVを想定（Shift_JIS / UTF-8 どちらも対応）
    """
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "message": "ファイルが指定されていません"}), 400

        file = request.files["file"]

        if file.filename == "":
            return jsonify({"success": False, "message": "ファイル名が空です"}), 400

        # ---------- 文字コード判定（UTF-8 優先、ダメなら CP932） ----------
        raw_bytes = file.stream.read()

        try:
            # UTF-8 / UTF-8(BOM) を優先
            text_data = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                # freee CSV はだいたい CP932（Shift_JIS 系）
                text_data = raw_bytes.decode("cp932")
            except UnicodeDecodeError:
                return jsonify({
                    "success": False,
                    "message": "文字コードの判定に失敗しました。UTF-8 もしくは Shift_JIS(CP932) で保存したCSVをアップロードしてください。"
                }), 400

        # ---------- CSV をヘッダー付きで読み込む ----------
        stream = io.StringIO(text_data)
        reader = csv.DictReader(stream)

        # 列名（freee標準）
        COL_ACCOUNT_NAME = "勘定科目"
        COL_DISPLAY_NAME = "表示名（決算書）"
        COL_SUB_CATEGORY = "小分類"
        COL_MID_CATEGORY = "中分類"
        COL_MAJOR_CATEGORY = "大分類"
        COL_INCOME_CP = "収入取引相手方勘定科目"
        COL_EXPENSE_CP = "支出取引相手方勘定科目"
        COL_TAX_CATEGORY = "税区分"
        COL_SHORTCUT1 = "ショートカット1"
        COL_SHORTCUT2 = "ショートカット2"
        COL_SUB_ACCOUNT_TAG = "補助科目優先タグ"

        db = SessionLocal()
        organization_id = get_current_organization_id() or 1

        imported = 0
        skipped = 0

        for row in reader:
            # 勘定科目名が空行ならスキップ
            account_name = (row.get(COL_ACCOUNT_NAME) or "").strip()
            if not account_name:
                continue

            # すでに同じ勘定科目が存在する場合はスキップ（重複エラー回避）
            exists = (
                db.query(AccountItem)
                .filter(
                    AccountItem.organization_id == organization_id,
                    AccountItem.account_name == account_name,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            account_item = AccountItem(
                organization_id=organization_id,
                account_name=account_name,
                display_name=(row.get(COL_DISPLAY_NAME) or None),
                sub_category=(row.get(COL_SUB_CATEGORY) or None),
                mid_category=(row.get(COL_MID_CATEGORY) or None),
                major_category=(row.get(COL_MAJOR_CATEGORY) or None),
                income_counterpart=(row.get(COL_INCOME_CP) or None),
                expense_counterpart=(row.get(COL_EXPENSE_CP) or None),
                tax_category=(row.get(COL_TAX_CATEGORY) or None),   # ★ ここが本当の「税区分」
                shortcut1=(row.get(COL_SHORTCUT1) or None),
                shortcut2=(row.get(COL_SHORTCUT2) or None),
                sub_account_priority_tag=(row.get(COL_SUB_ACCOUNT_TAG) or None),
                # freee CSV には「入力候補」列が無いので、とりあえず False にしておく
                input_candidate=False,
            )

            db.add(account_item)
            imported += 1

        db.commit()

        msg = f"{imported}件の勘定科目を取り込みました。"
        if skipped:
            msg += f"（{skipped}件は既存の勘定科目名と重複のためスキップしました）"

        return jsonify({
            "success": True,
            "message": msg,
            "count": imported,
        })

    except Exception as e:
        # ここで例外メッセージをそのまま返す（必要ならログ出力を追加）
        return jsonify({
            "success": False,
            "message": f"インポートに失敗しました: {e}",
        }), 500


# ========== 口座管理 ==========
@app.route('/accounts', methods=['GET'])
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
@app.route('/accounts/new', methods=['GET', 'POST'])
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


@app.route('/accounts/<int:account_id>/edit', methods=['GET', 'POST'])
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
@app.route('/api/accounts/<int:account_id>/toggle-visibility', methods=['POST'])
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
@app.route('/api/accounts/<int:account_id>/delete', methods=['POST'])
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
@app.route('/api/accounts/import', methods=['POST'])
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
@app.route('/tax-categories', methods=['GET'])
def tax_categories_list():
    """消費税区分一覧"""
    db = SessionLocal()
    try:
        # ページネーション
        page = request.args.get('page', 1, type=int)
        per_page = 20
        offset = (page - 1) * per_page
        
        # 検索フィルター
        search_query = request.args.get('search', '', type=str)
        
        # クエリ構築
        query = db.query(TaxCategory)
        if search_query:
            query = query.filter(
                TaxCategory.name.ilike(f'%{search_query}%')
            )
        
        # 名前でソート
        query = query.order_by(TaxCategory.name.asc())
        
        # 総件数
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        
        # データ取得
        tax_categories = query.offset(offset).limit(per_page).all()
        
        return render_template(
            'tax_categories/list.html',
            tax_categories=tax_categories,
            page=page,
            total_pages=total_pages,
            total=total,
            search_query=search_query
        )
    finally:
        db.close()

# 消費税区分新規追加ページ
@app.route('/tax-categories/new', methods=['GET', 'POST'])
def tax_category_create():
    """消費税区分新規追加"""
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # フォームデータを取得
            name = request.form.get('name', '').strip()
            
            # バリデーション
            if not name:
                flash('消費税区分名は必須です', 'error')
                return redirect(url_for('tax_category_create'))
            
            # 複数存在を確認
            existing = db.query(TaxCategory).filter(
                TaxCategory.name == name
            ).first()
            
            if existing:
                flash('消費税区分「' + name + '」は既に存在します', 'error')
                return redirect(url_for('tax_category_create'))
            
            # 消費税区分を作成
            tax_category = TaxCategory(name=name)
            
            db.add(tax_category)
            db.commit()
            
            flash('消費税区分「' + name + '」を作成しました', 'success')
            return redirect(url_for('tax_categories_list'))
        
        return render_template('tax_categories/form.html')
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('tax_categories_list'))
    finally:
        db.close()

# 消費税区分編集ページ
@app.route('/tax-categories/<int:tax_category_id>/edit', methods=['GET', 'POST'])
def tax_category_edit(tax_category_id):
    """消費税区分編集"""
    db = SessionLocal()
    try:
        tax_category = db.query(TaxCategory).filter(TaxCategory.id == tax_category_id).first()
        if not tax_category:
            flash('消費税区分が見つかりません', 'error')
            return redirect(url_for('tax_categories_list'))
        
        if request.method == 'POST':
            # フォームデータを取得
            name = request.form.get('name', '').strip()
            
            # バリデーション
            if not name:
                flash('消費税区分名は必須です', 'error')
                return redirect(url_for('tax_category_edit', tax_category_id=tax_category_id))
            
            # 同じ名前の異なる消費税区分が存在しないか確認
            existing = db.query(TaxCategory).filter(
                TaxCategory.name == name,
                TaxCategory.id != tax_category_id
            ).first()
            
            if existing:
                flash('消費税区分「' + name + '」は既に存在します', 'error')
                return redirect(url_for('tax_category_edit', tax_category_id=tax_category_id))
            
            # 更新
            tax_category.name = name
            
            db.commit()
            
            flash('消費税区分「' + name + '」を更新しました', 'success')
            return redirect(url_for('tax_categories_list'))
        
        return render_template('tax_categories/form.html', tax_category=tax_category)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('tax_categories_list'))
    finally:
        db.close()

# 消費税区分削除API
@app.route('/api/tax-categories/<int:tax_category_id>/delete', methods=['POST'])
def tax_category_delete(tax_category_id):
    """消費税区分削除"""
    db = SessionLocal()
    try:
        tax_category = db.query(TaxCategory).filter(TaxCategory.id == tax_category_id).first()
        if not tax_category:
            return jsonify({'success': False, 'message': '消費税区分が見つかりません'}), 404
        
        name = tax_category.name
        db.delete(tax_category)
        db.commit()
        
        return jsonify({'success': True, 'message': '消費税区分「' + name + '」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 消費税区分CSV/ExcelインポートAPI
@app.route('/api/tax-categories/import', methods=['POST'])
def import_tax_categories():
    """消費税区分をCSV/Excelファイルからインポート"""
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
                    if len(row) < 1:
                        errors.append(f'行 {row_idx}: 列数が不足しています')
                        continue
                    
                    # 消費税区分名を取得
                    name = str(row[0]).strip() if row[0] else None
                    if not name:
                        errors.append(f'行 {row_idx}: 消費税区分名が空です')
                        continue
                    
                    # 複数存在をチェック
                    existing = db.query(TaxCategory).filter(
                        TaxCategory.name == name
                    ).first()
                    
                    if existing:
                        errors.append(f'行 {row_idx}: 消費税区分「{name}」は既に存在します')
                        continue
                    
                    # 消費税区分を作成
                    tax_category = TaxCategory(name=name)
                    
                    db.add(tax_category)
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


# ========== 振替伝票管理機能 ==========

# 振替伝票一覧ページ
@app.route('/journal-entries', methods=['GET'])
def journal_entries_list():
    db = SessionLocal()
    try:
        # 検索フィルター
        search_query = request.args.get('search', '', type=str)
        # 口座フィルター（動定科目ID）
        account_item_id = request.args.get('account_item_id', type=int)
        
        # 取引明細から登録されたjournal_entry_idを取得
        imported_journal_entry_ids = db.query(ImportedTransaction.journal_entry_id).filter(
            ImportedTransaction.journal_entry_id.isnot(None)
        ).all()
        imported_journal_entry_ids = [item[0] for item in imported_journal_entry_ids]
        
        # クエリ構築（取引明細から登録された仕訳を除外）
        query = db.query(JournalEntry).filter(
            ~JournalEntry.id.in_(imported_journal_entry_ids)
        )
        
        # 口座フィルター（借方または貸方が指定された動定科目）
        if account_item_id:
            query = query.filter(
                (JournalEntry.debit_account_item_id == account_item_id) |
                (JournalEntry.credit_account_item_id == account_item_id)
            )
        
        if search_query:
            query = query.filter(
                (JournalEntry.summary.ilike(f'%{search_query}%')) |
                (JournalEntry.remarks.ilike(f'%{search_query}%'))
            )
        
        # 取引日降順でソート
        items = query.order_by(JournalEntry.transaction_date.desc()).all()
        
        return render_template(
            'journal_entries/list.html',
            items=items,
            search_query=search_query,
            account_item_id=account_item_id
        )
    finally:
        db.close()

# 振替伝票新規追加ページ
@app.route('/journal-entries/new', methods=['GET', 'POST'])
def journal_entry_create():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # フォームデータを取得
            transaction_date = request.form.get('transaction_date', '').strip()
            debit_account_item_id_str = request.form.get('debit_account_item_id[]', '').strip()
            debit_amount = request.form.get('debit_amount[]', type=int)
            debit_tax_category_id = request.form.get('debit_tax_category_id[]', type=int)
            credit_account_item_id_str = request.form.get('credit_account_item_id[]', '').strip()
            credit_amount = request.form.get('credit_amount[]', type=int)
            credit_tax_category_id = request.form.get('credit_tax_category_id[]', type=int)
            summary = request.form.get('summary', '').strip()
            remarks = request.form.get('remarks', '').strip()
            counterparty_id = request.form.get('counterparty_id', type=int) or None
            department_id = request.form.get('department_id', type=int) or None
            item_id = request.form.get('item_id', type=int) or None
            project_tag_id = request.form.get('project_tag_id', type=int) or None
            memo_tag_id = request.form.get('memo_tag_id', type=int) or None
            
            # 借方: 口座IDの場合は勘定科目IDに変換
            if not debit_account_item_id_str:
                debit_account_item_id = None
            elif debit_account_item_id_str.startswith('account_'):
                account_id = int(debit_account_item_id_str.replace('account_', ''))
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    debit_account_item_id = account.account_item_id
                else:
                    flash('指定された口座が見つかりません', 'error')
                    return redirect(url_for('journal_entry_create'))
            else:
                debit_account_item_id = int(debit_account_item_id_str)
            
            # 貸方: 口座IDの場合は勘定科目IDに変換
            if not credit_account_item_id_str:
                credit_account_item_id = None
            elif credit_account_item_id_str.startswith('account_'):
                account_id = int(credit_account_item_id_str.replace('account_', ''))
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    credit_account_item_id = account.account_item_id
                else:
                    flash('指定された口座が見つかりません', 'error')
                    return redirect(url_for('journal_entry_create'))
            else:
                credit_account_item_id = int(credit_account_item_id_str)
            
            # バリドーション
            if not transaction_date:
                flash('取引日は必須です', 'error')
                return redirect(url_for('journal_entry_create'))
            
            if not debit_account_item_id or not credit_account_item_id:
                flash('勘定科目は必須です', 'error')
                return redirect(url_for('journal_entry_create'))
            
            if debit_amount != credit_amount:
                flash('借方金額と賯方金額が一致していません', 'error')
                return redirect(url_for('journal_entry_create'))
            
            # 新規作成
            new_entry = JournalEntry(
                organization_id=get_current_organization_id(),
                transaction_date=transaction_date,
                debit_account_item_id=debit_account_item_id,
                debit_amount=debit_amount,
                debit_tax_category_id=debit_tax_category_id,
                credit_account_item_id=credit_account_item_id,
                credit_amount=credit_amount,
                credit_tax_category_id=credit_tax_category_id,
                summary=summary,
                remarks=remarks,
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            db.add(new_entry)
            db.commit()
            
            # 仕訳帳マスタにも登録
            general_ledger_entry = GeneralLedger(
                organization_id=get_current_organization_id(),
                transaction_date=transaction_date,
                debit_account_item_id=debit_account_item_id,
                debit_amount=debit_amount,
                debit_tax_category_id=debit_tax_category_id,
                credit_account_item_id=credit_account_item_id,
                credit_amount=credit_amount,
                credit_tax_category_id=credit_tax_category_id,
                summary=summary,
                remarks=remarks,
                counterparty_id=counterparty_id,
                department_id=department_id,
                item_id=item_id,
                project_tag_id=project_tag_id,
                memo_tag_id=memo_tag_id,
                source_type='journal_entry',
                source_id=new_entry.id,
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.add(general_ledger_entry)
            db.commit()
            
            flash('振替伝票を追加しました', 'success')
            return redirect(url_for('journal_entries_list'))
        
        # GETリクエスト時のデータ取得
        today = datetime.now().strftime('%Y-%m-%d')
        
        return render_template('journal_entries/form.html', 
                             today=today)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('journal_entries_list'))
    finally:
        db.close()

# 振替伝票編集ページ
@app.route('/journal-entries/<int:entry_id>/edit', methods=['GET', 'POST'])
def journal_entry_edit(entry_id):
    db = SessionLocal()
    try:
        entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
        if not entry:
            flash('振替伝票が見つかりません', 'error')
            return redirect(url_for('journal_entries_list'))
        
        if request.method == 'POST':
            # フォームデータを取得
            transaction_date = request.form.get('transaction_date', '').strip()
            debit_account_item_id_str = request.form.get('debit_account_item_id[]', '').strip()
            debit_amount = request.form.get('debit_amount[]', type=int)
            debit_tax_category_id = request.form.get('debit_tax_category_id[]', type=int)
            credit_account_item_id_str = request.form.get('credit_account_item_id[]', '').strip()
            credit_amount = request.form.get('credit_amount[]', type=int)
            credit_tax_category_id = request.form.get('credit_tax_category_id[]', type=int)
            summary = request.form.get('summary', '').strip()
            remarks = request.form.get('remarks', '').strip()
            counterparty_id = request.form.get('counterparty_id', type=int) or None
            department_id = request.form.get('department_id', type=int) or None
            item_id = request.form.get('item_id', type=int) or None
            project_tag_id = request.form.get('project_tag_id', type=int) or None
            memo_tag_id = request.form.get('memo_tag_id', type=int) or None
            
            # 借方: 口座IDの場合は勘定科目IDに変換
            if not debit_account_item_id_str:
                debit_account_item_id = None
            elif debit_account_item_id_str.startswith('account_'):
                account_id = int(debit_account_item_id_str.replace('account_', ''))
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    debit_account_item_id = account.account_item_id
                else:
                    flash('指定された口座が見つかりません', 'error')
                    return redirect(url_for('journal_entry_create'))
            else:
                debit_account_item_id = int(debit_account_item_id_str)
            
            # 貸方: 口座IDの場合は勘定科目IDに変換
            if not credit_account_item_id_str:
                credit_account_item_id = None
            elif credit_account_item_id_str.startswith('account_'):
                account_id = int(credit_account_item_id_str.replace('account_', ''))
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    credit_account_item_id = account.account_item_id
                else:
                    flash('指定された口座が見つかりません', 'error')
                    return redirect(url_for('journal_entry_create'))
            else:
                credit_account_item_id = int(credit_account_item_id_str)
            
            # バリドーション
            if not transaction_date:
                flash('取引日は必須です', 'error')
                return redirect(url_for('journal_entry_edit', entry_id=entry_id))
            
            if debit_amount != credit_amount:
                flash('借方金額と賯方金額が一致していません', 'error')
                return redirect(url_for('journal_entry_edit', entry_id=entry_id))
            
            # 更新
            entry.transaction_date = transaction_date
            entry.debit_account_item_id = debit_account_item_id
            entry.debit_amount = debit_amount
            entry.debit_tax_category_id = debit_tax_category_id
            entry.credit_account_item_id = credit_account_item_id
            entry.credit_amount = credit_amount
            entry.credit_tax_category_id = credit_tax_category_id
            entry.summary = summary
            entry.remarks = remarks
            entry.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # GeneralLedgerも更新
            gl_entry = db.query(GeneralLedger).filter(
                GeneralLedger.source_type == 'journal_entry',
                GeneralLedger.source_id == entry_id
            ).first()
            
            if gl_entry:
                gl_entry.transaction_date = transaction_date
                gl_entry.debit_account_item_id = debit_account_item_id
                gl_entry.debit_amount = debit_amount
                gl_entry.debit_tax_category_id = debit_tax_category_id
                gl_entry.credit_account_item_id = credit_account_item_id
                gl_entry.credit_amount = credit_amount
                gl_entry.credit_tax_category_id = credit_tax_category_id
                gl_entry.summary = summary
                gl_entry.remarks = remarks
                gl_entry.counterparty_id = counterparty_id
                gl_entry.department_id = department_id
                gl_entry.item_id = item_id
                gl_entry.project_tag_id = project_tag_id
                gl_entry.memo_tag_id = memo_tag_id
                gl_entry.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            db.commit()
            
            flash('振替伝票を更新しました', 'success')
            return redirect(url_for('journal_entries_list'))
        
        # GETリクエスト時のデータ取得
        return render_template('journal_entries/form.html', 
                             entry=entry)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('journal_entries_list'))
    finally:
        db.close()

# 振替伝票削除API
@app.route('/api/journal-entries/<int:entry_id>/delete', methods=['POST'])
def journal_entry_delete(entry_id):
    db = SessionLocal()
    try:
        entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
        if not entry:
            return jsonify({'success': False, 'message': '振替伝票が見つかりません'}), 404
        
        db.delete(entry)
        db.commit()
        return jsonify({'success': True, 'message': '振替伝票を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 連続仕訳登録ページ
@app.route('/journal-entries/continuous', methods=['GET'])
def journal_entries_continuous():
    # 出納帳の連続仕訳登録ページにリダイレクト
    return redirect(url_for('batch_create_cash_books_page'))

# 取引明細登録ページ
@app.route('/journal-entries/detail', methods=['GET'])
def journal_entries_detail():
    # 取引明細インポートページにリダイレクト
    return redirect(url_for('transactions.transaction_import'))


# ========== 出納帳マスター管理 ==========
# 出納帳マスター一覧ページ
@app.route('/cash-book-masters', methods=['GET'])
def cash_book_masters_list():
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '', type=str)
        
        # 口座マスターからすべての口座を取得
        query = db.query(Account)
        if search_query:
            query = query.filter(
                Account.account_name.ilike(f'%{search_query}%')
            )
        
        accounts = query.order_by(Account.id).all()
        
        return render_template(
            'cash_book_masters/list.html',
            accounts=accounts,
            search_query=search_query
        )
    finally:
        db.close()

# 出納帳マスター新規追加ページ
@app.route('/cash-book-masters/new', methods=['GET', 'POST'])
def cash_book_master_create():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # フォームデータを取得
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            # バリデーション
            if not name:
                flash('出納帳名は必須です', 'error')
                return redirect(url_for('cash_book_master_create'))
            
            # 重複チェック
            existing = db.query(CashBookMaster).filter(
                CashBookMaster.name == name
            ).first()
            
            if existing:
                flash('この出納帳名は既に登録されています', 'error')
                return redirect(url_for('cash_book_master_create'))
            
            # 新規作成
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            new_item = CashBookMaster(
                name=name,
                description=description,
                created_at=now,
                updated_at=now
            )
            db.add(new_item)

            # Accountテーブルにも同じ名前で登録
            new_account = Account(
                account_name=name,
                account_type='現金',  # デフォルトの種別を設定
                display_name=name
            )
            db.add(new_account)

            db.commit()
            
            flash(f'出納帳「{name}」を追加しました', 'success')
            return redirect(url_for('cash_book_masters_list'))
        
        return render_template('cash_book_masters/form.html')
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('cash_book_masters_list'))
    finally:
        db.close()

# 出納帳マスター編集ページ
@app.route('/cash-book-masters/<int:item_id>/edit', methods=['GET', 'POST'])
def cash_book_master_edit(item_id):
    db = SessionLocal()
    try:
        item = db.query(CashBookMaster).filter(CashBookMaster.id == item_id).first()
        if not item:
            flash('出納帳マスターが見つかりません', 'error')
            return redirect(url_for('cash_book_masters_list'))
        
        if request.method == 'POST':
            # フォームデータを取得
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            # バリデーション
            if not name:
                flash('出納帳名は必須です', 'error')
                return redirect(url_for('cash_book_master_edit', item_id=item_id))
            
            # 重複チェック（自分自身は除外）
            existing = db.query(CashBookMaster).filter(
                CashBookMaster.name == name,
                CashBookMaster.id != item_id
            ).first()
            
            if existing:
                flash('この出納帳名は既に登録されています', 'error')
                return redirect(url_for('cash_book_master_edit', item_id=item_id))
            
            # 更新
            # 更新
            old_name = item.name
            item.name = name
            item.description = description
            item.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Accountテーブルも更新
            account = db.query(Account).filter(Account.account_name == old_name).first()
            if account:
                account.account_name = name
                account.display_name = name
            
            db.commit()
            
            flash(f'出納帳「{name}」を更新しました', 'success')
            return redirect(url_for('cash_book_masters_list'))
        
        return render_template('cash_book_masters/form.html', item=item)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('cash_book_masters_list'))
    finally:
        db.close()

# 出納帳マスター削除API@app.route('/api/cash-book-masters/<int:item_id>/delete', methods=['POST'])
def cash_book_master_delete(item_id):
    db = SessionLocal()
    try:
        item = db.query(CashBookMaster).filter(CashBookMaster.id == item_id).first()
        if not item:
            return jsonify({'success': False, 'message': '出納帳マスターが見つかりません'}), 404
        
        name = item.name
        db.delete(item)
        
        # Accountテーブルからも削除
        account = db.query(Account).filter(Account.account_name == name).first()
        if account:
            db.delete(account)
            
        db.commit()
        
        return jsonify({'success': True, 'message': f'出納帳「{name}」を削除しました'}).rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


# ========== 部門管理 ==========

# 部門一覧
@app.route('/departments', methods=['GET'])
@login_required
def departments_list():
    """部門一覧ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '').strip()
        
        query = db.query(Department).filter(Department.organization_id == organization_id)
        if search_query:
            query = query.filter(Department.name.like(f'%{search_query}%'))
        
        departments = query.order_by(Department.id).all()
        
        return render_template('departments/list.html', 
                             departments=departments,
                             search_query=search_query)
    finally:
        db.close()


# 部門新規作成ページ
@app.route('/departments/new', methods=['GET'])
@login_required
def department_new():
    """部門新規作成ページ"""
    return render_template('departments/form.html', department=None)


# 部門作成API
@app.route('/departments/create', methods=['POST'])
@login_required
def department_create():
    """部門作成"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('部門名を入力してください', 'error')
            return redirect(url_for('department_new'))
        
        # 重複チェック（同一事業所内）
        existing = db.query(Department).filter(
            Department.organization_id == organization_id,
            Department.name == name
        ).first()
        if existing:
            flash(f'部門「{name}」は既に登録されています', 'error')
            return redirect(url_for('department_new'))
        
        department = Department(
            organization_id=organization_id,
            name=name
        )
        db.add(department)
        db.commit()
        
        flash(f'部門「{name}」を作成しました', 'success')
        return redirect(url_for('departments_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('department_new'))
    finally:
        db.close()


# 部門編集ページ
@app.route('/departments/<int:department_id>/edit', methods=['GET'])
@login_required
def department_edit(department_id):
    """部門編集ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        department = db.query(Department).filter(
            Department.id == department_id,
            Department.organization_id == organization_id
        ).first()
        if not department:
            flash('部門が見つかりません', 'error')
            return redirect(url_for('departments_list'))
        
        return render_template('departments/form.html', department=department)
    finally:
        db.close()


# 部門更新API
@app.route('/departments/<int:department_id>/update', methods=['POST'])
@login_required
def department_update(department_id):
    """部門更新"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        department = db.query(Department).filter(
            Department.id == department_id,
            Department.organization_id == organization_id
        ).first()
        if not department:
            flash('部門が見つかりません', 'error')
            return redirect(url_for('departments_list'))
        
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('部門名を入力してください', 'error')
            return redirect(url_for('department_edit', department_id=department_id))
        
        # 重複チェック（同一事業所内、自分以外）
        existing = db.query(Department).filter(
            Department.organization_id == organization_id,
            Department.name == name,
            Department.id != department_id
        ).first()
        if existing:
            flash(f'部門「{name}」は既に登録されています', 'error')
            return redirect(url_for('department_edit', department_id=department_id))
        
        department.name = name
        db.commit()
        
        flash(f'部門「{name}」を更新しました', 'success')
        return redirect(url_for('departments_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('department_edit', department_id=department_id))
    finally:
        db.close()


# 部門削除API
@app.route('/api/departments/<int:department_id>/delete', methods=['POST'])
@login_required
def department_delete(department_id):
    """部門削除"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        department = db.query(Department).filter(
            Department.id == department_id,
            Department.organization_id == organization_id
        ).first()
        if not department:
            return jsonify({'success': False, 'message': '部門が見つかりません'}), 404
        
        name = department.name
        db.delete(department)
        db.commit()
        
        return jsonify({'success': True, 'message': f'部門「{name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


# ========== 取引先管理 ==========

# 取引先一覧
@app.route('/counterparties', methods=['GET'])
@login_required
def counterparties_list():
    """取引先一覧ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '').strip()
        
        query = db.query(Counterparty).filter(Counterparty.organization_id == organization_id)
        if search_query:
            query = query.filter(Counterparty.name.like(f'%{search_query}%'))
        
        counterparties = query.order_by(Counterparty.id).all()
        
        return render_template('counterparties/list.html', 
                             counterparties=counterparties,
                             search_query=search_query)
    finally:
        db.close()


# 取引先新規作成ページ
@app.route('/counterparties/new', methods=['GET'])
@login_required
def counterparty_new():
    """取引先新規作成ページ"""
    return render_template('counterparties/form.html', counterparty=None)


# 取引先作成API
@app.route('/counterparties/create', methods=['POST'])
@login_required
def counterparty_create():
    """取引先作成"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('取引先名を入力してください', 'error')
            return redirect(url_for('counterparty_new'))
        
        # 重複チェック（同一事業所内）
        existing = db.query(Counterparty).filter(
            Counterparty.organization_id == organization_id,
            Counterparty.name == name
        ).first()
        if existing:
            flash(f'取引先「{name}」は既に登録されています', 'error')
            return redirect(url_for('counterparty_new'))
        
        counterparty = Counterparty(
            organization_id=organization_id,
            name=name
        )
        db.add(counterparty)
        db.commit()
        
        flash(f'取引先「{name}」を作成しました', 'success')
        return redirect(url_for('counterparties_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('counterparty_new'))
    finally:
        db.close()


# 取引先編集ページ
@app.route('/counterparties/<int:counterparty_id>/edit', methods=['GET'])
@login_required
def counterparty_edit(counterparty_id):
    """取引先編集ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        counterparty = db.query(Counterparty).filter(
            Counterparty.id == counterparty_id,
            Counterparty.organization_id == organization_id
        ).first()
        if not counterparty:
            flash('取引先が見つかりません', 'error')
            return redirect(url_for('counterparties_list'))
        
        return render_template('counterparties/form.html', counterparty=counterparty)
    finally:
        db.close()


# 取引先更新API
@app.route('/counterparties/<int:counterparty_id>/update', methods=['POST'])
@login_required
def counterparty_update(counterparty_id):
    """取引先更新"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        counterparty = db.query(Counterparty).filter(
            Counterparty.id == counterparty_id,
            Counterparty.organization_id == organization_id
        ).first()
        if not counterparty:
            flash('取引先が見つかりません', 'error')
            return redirect(url_for('counterparties_list'))
        
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('取引先名を入力してください', 'error')
            return redirect(url_for('counterparty_edit', counterparty_id=counterparty_id))
        
        # 重複チェック（同一事業所内、自分以外）
        existing = db.query(Counterparty).filter(
            Counterparty.organization_id == organization_id,
            Counterparty.name == name,
            Counterparty.id != counterparty_id
        ).first()
        if existing:
            flash(f'取引先「{name}」は既に登録されています', 'error')
            return redirect(url_for('counterparty_edit', counterparty_id=counterparty_id))
        
        counterparty.name = name
        db.commit()
        
        flash(f'取引先「{name}」を更新しました', 'success')
        return redirect(url_for('counterparties_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('counterparty_edit', counterparty_id=counterparty_id))
    finally:
        db.close()


# 取引先削除API
@app.route('/api/counterparties/<int:counterparty_id>/delete', methods=['POST'])
@login_required
def counterparty_delete(counterparty_id):
    """取引先削除"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        counterparty = db.query(Counterparty).filter(
            Counterparty.id == counterparty_id,
            Counterparty.organization_id == organization_id
        ).first()
        if not counterparty:
            return jsonify({'success': False, 'message': '取引先が見つかりません'}), 404
        
        name = counterparty.name
        db.delete(counterparty)
        db.commit()
        
        return jsonify({'success': True, 'message': f'取引先「{name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


# ========== 品目管理 ==========

# 品目一覧
@app.route('/items', methods=['GET'])
@login_required
def items_list():
    """品目一覧ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '').strip()
        
        query = db.query(Item).filter(Item.organization_id == organization_id)
        if search_query:
            query = query.filter(Item.name.like(f'%{search_query}%'))
        
        items = query.order_by(Item.id).all()
        
        return render_template('items/list.html', 
                             items=items,
                             search_query=search_query)
    finally:
        db.close()


@app.route('/items/new', methods=['GET'])
@login_required
def item_new():
    """品目新規作成ページ"""
    return render_template('items/form.html', item=None)


@app.route('/items/create', methods=['POST'])
@login_required
def item_create():
    """品目作成"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('品目名を入力してください', 'error')
            return redirect(url_for('item_new'))
        
        existing = db.query(Item).filter(
            Item.organization_id == organization_id,
            Item.name == name
        ).first()
        if existing:
            flash(f'品目「{name}」は既に登録されています', 'error')
            return redirect(url_for('item_new'))
        
        item = Item(
            organization_id=organization_id,
            name=name
        )
        db.add(item)
        db.commit()
        
        flash(f'品目「{name}」を作成しました', 'success')
        return redirect(url_for('items_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('item_new'))
    finally:
        db.close()


@app.route('/items/<int:item_id>/edit', methods=['GET'])
@login_required
def item_edit(item_id):
    """品目編集ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        item = db.query(Item).filter(
            Item.id == item_id,
            Item.organization_id == organization_id
        ).first()
        if not item:
            flash('品目が見つかりません', 'error')
            return redirect(url_for('items_list'))
        
        return render_template('items/form.html', item=item)
    finally:
        db.close()


@app.route('/items/<int:item_id>/update', methods=['POST'])
@login_required
def item_update(item_id):
    """品目更新"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        item = db.query(Item).filter(
            Item.id == item_id,
            Item.organization_id == organization_id
        ).first()
        if not item:
            flash('品目が見つかりません', 'error')
            return redirect(url_for('items_list'))
        
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('品目名を入力してください', 'error')
            return redirect(url_for('item_edit', item_id=item_id))
        
        existing = db.query(Item).filter(
            Item.organization_id == organization_id,
            Item.name == name,
            Item.id != item_id
        ).first()
        if existing:
            flash(f'品目「{name}」は既に登録されています', 'error')
            return redirect(url_for('item_edit', item_id=item_id))
        
        item.name = name
        db.commit()
        
        flash(f'品目「{name}」を更新しました', 'success')
        return redirect(url_for('items_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('item_edit', item_id=item_id))
    finally:
        db.close()


@app.route('/api/items/<int:item_id>/delete', methods=['POST'])
@login_required
def item_delete(item_id):
    """品目削除"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        item = db.query(Item).filter(
            Item.id == item_id,
            Item.organization_id == organization_id
        ).first()
        if not item:
            return jsonify({'success': False, 'message': '品目が見つかりません'}), 404
        
        name = item.name
        db.delete(item)
        db.commit()
        
        return jsonify({'success': True, 'message': f'品目「{name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


# ========== 案件タグ管理 ==========

# 案件タグ一覧
@app.route('/project-tags', methods=['GET'])
@login_required
def project_tags_list():
    """案件タグ一覧ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '').strip()
        
        query = db.query(ProjectTag).filter(ProjectTag.organization_id == organization_id)
        if search_query:
            query = query.filter(ProjectTag.tag_name.like(f'%{search_query}%'))
        
        project_tags = query.order_by(ProjectTag.id).all()
        
        return render_template('project_tags/list.html', 
                             project_tags=project_tags,
                             search_query=search_query)
    finally:
        db.close()


@app.route('/project-tags/new', methods=['GET'])
@login_required
def project_tag_new():
    """案件タグ新規作成ページ"""
    return render_template('project_tags/form.html', project_tag=None)


@app.route('/project-tags/create', methods=['POST'])
@login_required
def project_tag_create():
    """案件タグ作成"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        tag_name = request.form.get('tag_name', '').strip()
        description = request.form.get('description', '').strip()
        is_active = request.form.get('is_active', '1')
        
        if not tag_name:
            flash('案件タグ名を入力してください', 'error')
            return redirect(url_for('project_tag_new'))
        
        existing = db.query(ProjectTag).filter(
            ProjectTag.organization_id == organization_id,
            ProjectTag.tag_name == tag_name
        ).first()
        if existing:
            flash(f'案件タグ「{tag_name}」は既に登録されています', 'error')
            return redirect(url_for('project_tag_new'))
        
        from datetime import datetime
        project_tag = ProjectTag(
            organization_id=organization_id,
            tag_name=tag_name,
            description=description,
            is_active=int(is_active),
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        db.add(project_tag)
        db.commit()
        
        flash(f'案件タグ「{tag_name}」を作成しました', 'success')
        return redirect(url_for('project_tags_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('project_tag_new'))
    finally:
        db.close()


@app.route('/project-tags/<int:project_tag_id>/edit', methods=['GET'])
@login_required
def project_tag_edit(project_tag_id):
    """案件タグ編集ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        project_tag = db.query(ProjectTag).filter(
            ProjectTag.id == project_tag_id,
            ProjectTag.organization_id == organization_id
        ).first()
        if not project_tag:
            flash('案件タグが見つかりません', 'error')
            return redirect(url_for('project_tags_list'))
        
        return render_template('project_tags/form.html', project_tag=project_tag)
    finally:
        db.close()


@app.route('/project-tags/<int:project_tag_id>/update', methods=['POST'])
@login_required
def project_tag_update(project_tag_id):
    """案件タグ更新"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        project_tag = db.query(ProjectTag).filter(
            ProjectTag.id == project_tag_id,
            ProjectTag.organization_id == organization_id
        ).first()
        if not project_tag:
            flash('案件タグが見つかりません', 'error')
            return redirect(url_for('project_tags_list'))
        
        tag_name = request.form.get('tag_name', '').strip()
        description = request.form.get('description', '').strip()
        is_active = request.form.get('is_active', '1')
        
        if not tag_name:
            flash('案件タグ名を入力してください', 'error')
            return redirect(url_for('project_tag_edit', project_tag_id=project_tag_id))
        
        existing = db.query(ProjectTag).filter(
            ProjectTag.organization_id == organization_id,
            ProjectTag.tag_name == tag_name,
            ProjectTag.id != project_tag_id
        ).first()
        if existing:
            flash(f'案件タグ「{tag_name}」は既に登録されています', 'error')
            return redirect(url_for('project_tag_edit', project_tag_id=project_tag_id))
        
        from datetime import datetime
        project_tag.tag_name = tag_name
        project_tag.description = description
        project_tag.is_active = int(is_active)
        project_tag.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.commit()
        
        flash(f'案件タグ「{tag_name}」を更新しました', 'success')
        return redirect(url_for('project_tags_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('project_tag_edit', project_tag_id=project_tag_id))
    finally:
        db.close()


@app.route('/api/project-tags/<int:project_tag_id>/delete', methods=['POST'])
@login_required
def project_tag_delete(project_tag_id):
    """案件タグ削除"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        project_tag = db.query(ProjectTag).filter(
            ProjectTag.id == project_tag_id,
            ProjectTag.organization_id == organization_id
        ).first()
        if not project_tag:
            return jsonify({'success': False, 'message': '案件タグが見つかりません'}), 404
        
        tag_name = project_tag.tag_name
        db.delete(project_tag)
        db.commit()
        
        return jsonify({'success': True, 'message': f'案件タグ「{tag_name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


# ========== メモタグ管理 ==========

# メモタグ一覧
@app.route('/memo-tags', methods=['GET'])
@login_required
def memo_tags_list():
    """メモタグ一覧ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '').strip()
        
        query = db.query(MemoTag).filter(MemoTag.organization_id == organization_id)
        if search_query:
            query = query.filter(MemoTag.name.like(f'%{search_query}%'))
        
        memo_tags = query.order_by(MemoTag.id).all()
        
        return render_template('memo_tags/list.html', 
                             memo_tags=memo_tags,
                             search_query=search_query)
    finally:
        db.close()


@app.route('/memo-tags/new', methods=['GET'])
@login_required
def memo_tag_new():
    """メモタグ新規作成ページ"""
    return render_template('memo_tags/form.html', memo_tag=None)


@app.route('/memo-tags/create', methods=['POST'])
@login_required
def memo_tag_create():
    """メモタグ作成"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('メモタグ名を入力してください', 'error')
            return redirect(url_for('memo_tag_new'))
        
        existing = db.query(MemoTag).filter(
            MemoTag.organization_id == organization_id,
            MemoTag.name == name
        ).first()
        if existing:
            flash(f'メモタグ「{name}」は既に登録されています', 'error')
            return redirect(url_for('memo_tag_new'))
        
        memo_tag = MemoTag(
            organization_id=organization_id,
            name=name
        )
        db.add(memo_tag)
        db.commit()
        
        flash(f'メモタグ「{name}」を作成しました', 'success')
        return redirect(url_for('memo_tags_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('memo_tag_new'))
    finally:
        db.close()


@app.route('/memo-tags/<int:memo_tag_id>/edit', methods=['GET'])
@login_required
def memo_tag_edit(memo_tag_id):
    """メモタグ編集ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        memo_tag = db.query(MemoTag).filter(
            MemoTag.id == memo_tag_id,
            MemoTag.organization_id == organization_id
        ).first()
        if not memo_tag:
            flash('メモタグが見つかりません', 'error')
            return redirect(url_for('memo_tags_list'))
        
        return render_template('memo_tags/form.html', memo_tag=memo_tag)
    finally:
        db.close()


@app.route('/memo-tags/<int:memo_tag_id>/update', methods=['POST'])
@login_required
def memo_tag_update(memo_tag_id):
    """メモタグ更新"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        memo_tag = db.query(MemoTag).filter(
            MemoTag.id == memo_tag_id,
            MemoTag.organization_id == organization_id
        ).first()
        if not memo_tag:
            flash('メモタグが見つかりません', 'error')
            return redirect(url_for('memo_tags_list'))
        
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('メモタグ名を入力してください', 'error')
            return redirect(url_for('memo_tag_edit', memo_tag_id=memo_tag_id))
        
        existing = db.query(MemoTag).filter(
            MemoTag.organization_id == organization_id,
            MemoTag.name == name,
            MemoTag.id != memo_tag_id
        ).first()
        if existing:
            flash(f'メモタグ「{name}」は既に登録されています', 'error')
            return redirect(url_for('memo_tag_edit', memo_tag_id=memo_tag_id))
        
        memo_tag.name = name
        db.commit()
        
        flash(f'メモタグ「{name}」を更新しました', 'success')
        return redirect(url_for('memo_tags_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('memo_tag_edit', memo_tag_id=memo_tag_id))
    finally:
        db.close()


@app.route('/api/memo-tags/<int:memo_tag_id>/delete', methods=['POST'])
@login_required
def memo_tag_delete(memo_tag_id):
    """メモタグ削除"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        memo_tag = db.query(MemoTag).filter(
            MemoTag.id == memo_tag_id,
            MemoTag.organization_id == organization_id
        ).first()
        if not memo_tag:
            return jsonify({'success': False, 'message': 'メモタグが見つかりません'}), 404
        
        name = memo_tag.name
        db.delete(memo_tag)
        db.commit()
        
        return jsonify({'success': True, 'message': f'メモタグ「{name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


# ========== 会計期間管理 ==========

# 会計期間一覧
@app.route('/fiscal-periods', methods=['GET'])
@login_required
def fiscal_periods_list():
    """会計期間一覧ページ"""
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '').strip()
        
        query = db.query(FiscalPeriod).filter(FiscalPeriod.organization_id == session['organization_id'])
        if search_query:
            query = query.filter(FiscalPeriod.name.like(f'%{search_query}%'))
        
        fiscal_periods = query.order_by(FiscalPeriod.start_date.desc()).all()
        
        return render_template('fiscal_periods/list.html', 
                             fiscal_periods=fiscal_periods,
                             search_query=search_query)
    finally:
        db.close()


@app.route('/fiscal-periods/new', methods=['GET'])
@login_required
def fiscal_period_new():
    """会計期間新規作成ページ"""
    return render_template('fiscal_periods/form.html', fiscal_period=None)


@app.route('/fiscal-periods/create', methods=['POST'])
@login_required
def fiscal_period_create():
    """会計期間作成"""
    db = SessionLocal()
    try:
        from datetime import datetime
        
        name = request.form.get('name', '').strip()
        start_date = request.form.get('start_date', '').strip()
        end_date = request.form.get('end_date', '').strip()
        business_type = request.form.get('business_type', 'corporate').strip()
        notes = request.form.get('notes', '').strip()
        
        if not name or not start_date or not end_date:
            flash('必須項目を入力してください', 'error')
            return redirect(url_for('fiscal_period_new'))
        
        # 個人の場合、1月1日～12月31日であることをチェック
        if business_type == 'individual':
            if not (start_date.endswith('-01-01') and end_date.endswith('-12-31')):
                flash('個人の会計期間は1月1日～12月31日である必要があります', 'error')
                return redirect(url_for('fiscal_period_new'))
            
            # 同じ年であることをチェック
            if start_date[:4] != end_date[:4]:
                flash('個人の会計期間は同じ年内である必要があります', 'error')
                return redirect(url_for('fiscal_period_new'))
        
        # 開始日が終了日より前であることをチェック
        if start_date >= end_date:
            flash('開始日は終了日より前である必要があります', 'error')
            return redirect(url_for('fiscal_period_new'))
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        fiscal_period = FiscalPeriod(
            name=name,
            start_date=start_date,
            end_date=end_date,
            business_type=business_type,
            status='open',
            notes=notes,
            organization_id=session['organization_id'],
            created_at=now,
            updated_at=now
        )
        db.add(fiscal_period)
        db.commit()
        
        flash(f'会計期間「{name}」を作成しました', 'success')
        return redirect(url_for('fiscal_periods_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('fiscal_period_new'))
    finally:
        db.close()


@app.route('/fiscal-periods/<int:fiscal_period_id>/edit', methods=['GET'])
@login_required
def fiscal_period_edit(fiscal_period_id):
    """会計期間編集ページ"""
    db = SessionLocal()
    try:
        fiscal_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.id == fiscal_period_id,
            FiscalPeriod.organization_id == session['organization_id']
        ).first()
        if not fiscal_period:
            flash('会計期間が見つかりません', 'error')
            return redirect(url_for('fiscal_periods_list'))
        
        return render_template('fiscal_periods/form.html', fiscal_period=fiscal_period)
    finally:
        db.close()


@app.route('/fiscal-periods/<int:fiscal_period_id>/update', methods=['POST'])
@login_required
def fiscal_period_update(fiscal_period_id):
    """会計期間更新"""
    db = SessionLocal()
    try:
        from datetime import datetime
        
        fiscal_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.id == fiscal_period_id,
            FiscalPeriod.organization_id == session['organization_id']
        ).first()
        if not fiscal_period:
            flash('会計期間が見つかりません', 'error')
            return redirect(url_for('fiscal_periods_list'))
        
        name = request.form.get('name', '').strip()
        start_date = request.form.get('start_date', '').strip()
        end_date = request.form.get('end_date', '').strip()
        business_type = request.form.get('business_type', 'corporate').strip()
        notes = request.form.get('notes', '').strip()
        
        if not name or not start_date or not end_date:
            flash('必須項目を入力してください', 'error')
            return redirect(url_for('fiscal_period_edit', fiscal_period_id=fiscal_period_id))
        
        # 個人の場合、1月1日～12月31日であることをチェック
        if business_type == 'individual':
            if not (start_date.endswith('-01-01') and end_date.endswith('-12-31')):
                flash('個人の会計期間は1月1日～12月31日である必要があります', 'error')
                return redirect(url_for('fiscal_period_edit', fiscal_period_id=fiscal_period_id))
            
            if start_date[:4] != end_date[:4]:
                flash('個人の会計期間は同じ年内である必要があります', 'error')
                return redirect(url_for('fiscal_period_edit', fiscal_period_id=fiscal_period_id))
        
        if start_date >= end_date:
            flash('開始日は終了日より前である必要があります', 'error')
            return redirect(url_for('fiscal_period_edit', fiscal_period_id=fiscal_period_id))
        
        fiscal_period.name = name
        fiscal_period.start_date = start_date
        fiscal_period.end_date = end_date
        fiscal_period.business_type = business_type
        fiscal_period.notes = notes
        fiscal_period.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.commit()
        
        flash(f'会計期間「{name}」を更新しました', 'success')
        return redirect(url_for('fiscal_periods_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('fiscal_period_edit', fiscal_period_id=fiscal_period_id))
    finally:
        db.close()


@app.route('/api/fiscal-periods/<int:fiscal_period_id>/delete', methods=['POST'])
@login_required
def fiscal_period_delete(fiscal_period_id):
    """会計期間削除"""
    db = SessionLocal()
    try:
        fiscal_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.id == fiscal_period_id,
            FiscalPeriod.organization_id == session['organization_id']
        ).first()
        if not fiscal_period:
            return jsonify({'success': False, 'message': '会計期間が見つかりません'}), 404
        
        name = fiscal_period.name
        db.delete(fiscal_period)
        db.commit()
        
        return jsonify({'success': True, 'message': f'会計期間「{name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


@app.route('/api/fiscal-periods/<int:fiscal_period_id>/close', methods=['POST'])
@login_required
def fiscal_period_close(fiscal_period_id):
    """会計期間を締める"""
    db = SessionLocal()
    try:
        from datetime import datetime
        
        fiscal_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.id == fiscal_period_id,
            FiscalPeriod.organization_id == session['organization_id']
        ).first()
        if not fiscal_period:
            return jsonify({'success': False, 'message': '会計期間が見つかりません'}), 404
        
        if fiscal_period.status == 'closed':
            return jsonify({'success': False, 'message': 'この会計期間は既に締められています'}), 400
        
        fiscal_period.status = 'closed'
        fiscal_period.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.commit()
        
        return jsonify({'success': True, 'message': f'会計期間「{fiscal_period.name}」を締めました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


# ========== 事業所マスター管理 ==========
@app.route('/organizations')
def organizations_list():
    """事業所一覧ページ（ログアウト状態でのみアクセス可能）"""
    # ログイン中の場合はホーム画面にリダイレクト
    if 'organization_id' in session:
        flash('事業所管理はログアウト状態でのみアクセスできます。', 'warning')
        return redirect(url_for('index'))
    
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '')
        
        query = db.query(Organization)
        if search_query:
            query = query.filter(Organization.name.like(f'%{search_query}%'))
        
        organizations = query.order_by(Organization.id.asc()).all()
        return render_template('organizations/list.html', organizations=organizations, search_query=search_query)
    finally:
        db.close()

@app.route('/organizations/new', methods=['GET', 'POST'])
def organization_create():
    """事業所新規作成ページ"""
    if request.method == 'POST':
        db = SessionLocal()
        try:
            name = request.form.get('name', '').strip()
            code = request.form.get('code', '').strip()
            business_type = request.form.get('business_type', 'corporate')
            postal_code = request.form.get('postal_code', '').strip()
            address = request.form.get('address', '').strip()
            phone = request.form.get('phone', '').strip()
            fax = request.form.get('fax', '').strip()
            email = request.form.get('email', '').strip()
            representative = request.form.get('representative', '').strip()
            established_date = request.form.get('established_date', '').strip()
            notes = request.form.get('notes', '').strip()
            
            if not name:
                flash('事業所名は必須です', 'danger')
                return redirect(url_for('organization_create'))
            
            # 事業所コードの重複チェック
            if code:
                existing = db.query(Organization).filter(Organization.code == code).first()
                if existing:
                    flash(f'事業所コード「{code}」は既に使用されています', 'danger')
                    return redirect(url_for('organization_create'))
            
            new_org = Organization(
                name=name,
                code=code if code else None,
                business_type=business_type,
                postal_code=postal_code if postal_code else None,
                address=address if address else None,
                phone=phone if phone else None,
                fax=fax if fax else None,
                email=email if email else None,
                representative=representative if representative else None,
                established_date=established_date if established_date else None,
                notes=notes if notes else None,
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.add(new_org)
            db.commit()
            flash(f'事業所「{name}」を作成しました', 'success')
            return redirect(url_for('organizations_list'))
        except Exception as e:
            db.rollback()
            flash(f'エラーが発生しました: {str(e)}', 'danger')
            return redirect(url_for('organization_create'))
        finally:
            db.close()
    
    return render_template('organizations/form.html', organization=None)

@app.route('/organizations/<int:organization_id>/edit', methods=['GET', 'POST'])
def organization_edit(organization_id):
    """事業所編集ページ（ログアウト状態でのみアクセス可能）"""
    # ログイン中の場合はホーム画面にリダイレクト
    if 'organization_id' in session:
        flash('事業所管理はログアウト状態でのみアクセスできます。', 'warning')
        return redirect(url_for('index'))
    
    db = SessionLocal()
    try:
        organization = db.query(Organization).filter(Organization.id == organization_id).first()
        if not organization:
            flash('事業所が見つかりません', 'danger')
            return redirect(url_for('organizations_list'))
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            code = request.form.get('code', '').strip()
            business_type = request.form.get('business_type', 'corporate')
            postal_code = request.form.get('postal_code', '').strip()
            address = request.form.get('address', '').strip()
            phone = request.form.get('phone', '').strip()
            fax = request.form.get('fax', '').strip()
            email = request.form.get('email', '').strip()
            representative = request.form.get('representative', '').strip()
            established_date = request.form.get('established_date', '').strip()
            notes = request.form.get('notes', '').strip()
            
            if not name:
                flash('事業所名は必須です', 'danger')
                return redirect(url_for('organization_edit', organization_id=organization_id))
            
            # 事業所コードの重複チェック（自分以外）
            if code:
                existing = db.query(Organization).filter(
                    Organization.code == code,
                    Organization.id != organization_id
                ).first()
                if existing:
                    flash(f'事業所コード「{code}」は既に使用されています', 'danger')
                    return redirect(url_for('organization_edit', organization_id=organization_id))
            
            organization.name = name
            organization.code = code if code else None
            organization.business_type = business_type
            organization.postal_code = postal_code if postal_code else None
            organization.address = address if address else None
            organization.phone = phone if phone else None
            organization.fax = fax if fax else None
            organization.email = email if email else None
            organization.representative = representative if representative else None
            organization.established_date = established_date if established_date else None
            organization.notes = notes if notes else None
            organization.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            db.commit()
            flash(f'事業所「{name}」を更新しました', 'success')
            return redirect(url_for('organizations_list'))
        
        return render_template('organizations/form.html', organization=organization)
    finally:
        db.close()

@app.route('/api/organizations/<int:organization_id>/delete', methods=['POST'])
def organization_delete(organization_id):
    """事業所削除API（ログアウト状態でのみアクセス可能）"""
    # ログイン中の場合はエラーを返す
    if 'organization_id' in session:
        return jsonify({'success': False, 'message': '事業所管理はログアウト状態でのみアクセスできます。'}), 403
    
    db = SessionLocal()
    try:
        organization = db.query(Organization).filter(Organization.id == organization_id).first()
        if not organization:
            return jsonify({'success': False, 'message': '事業所が見つかりません'}), 404
        
        org_name = organization.name
        db.delete(organization)
        db.commit()
        
        return jsonify({'success': True, 'message': f'事業所「{org_name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()



# ========== 期首残高設定 ==========
@app.route('/opening-balances', methods=['GET'])
@login_required
def opening_balances():
    """期首残高設定画面"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        # 会計期間一覧を取得
        fiscal_periods = db.query(FiscalPeriod).filter(
            FiscalPeriod.organization_id == organization_id
        ).order_by(FiscalPeriod.start_date.desc()).all()
        
        if not fiscal_periods:
            flash('会計期間が登録されていません。まず会計期間を登録してください。', 'warning')
            return redirect(url_for('fiscal_periods_index'))
        
        # 選択された会計期間ID（デフォルトは最新）
        selected_period_id = request.args.get('fiscal_period_id', type=int)
        if not selected_period_id:
            selected_period_id = fiscal_periods[0].id
        
        # 選択された会計期間を取得
        selected_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.id == selected_period_id,
            FiscalPeriod.organization_id == organization_id
        ).first()
        
        if not selected_period:
            flash('指定された会計期間が見つかりません。', 'danger')
            return redirect(url_for('opening_balances'))
        
        # 勘定科目一覧を取得（B/S科目のみ）
        account_items = db.query(AccountItem).filter(
            AccountItem.organization_id == organization_id,
            AccountItem.major_category.in_(['資産', '負債', '純資産'])
        ).order_by(
            AccountItem.liquidity_rank,
            AccountItem.account_name
        ).all()
        
        # 期首残高データを取得
        opening_balances = db.query(OpeningBalance).filter(
            OpeningBalance.organization_id == organization_id,
            OpeningBalance.fiscal_period_id == selected_period_id
        ).all()
        
        # 勘定科目IDをキーとした辞書を作成
        opening_balance_dict = {ob.account_item_id: ob for ob in opening_balances}
        
        # 表示用データを作成
        balance_data = []
        for account_item in account_items:
            ob = opening_balance_dict.get(account_item.id)
            balance_data.append({
                'account_item': account_item,
                'debit_amount': float(ob.debit_amount) if ob else 0,
                'credit_amount': float(ob.credit_amount) if ob else 0
            })
        
        # 借方合計・貸方合計を計算
        debit_total = sum([item['debit_amount'] for item in balance_data])
        credit_total = sum([item['credit_amount'] for item in balance_data])
        
        return render_template(
            'opening_balances/index.html',
            fiscal_periods=fiscal_periods,
            selected_period_id=selected_period_id,
            selected_period=selected_period,
            balance_data=balance_data,
            debit_total=debit_total,
            credit_total=credit_total
        )
    finally:
        db.close()


@app.route('/opening-balances/save', methods=['POST'])
@login_required
def save_opening_balances():
    """期首残高を保存"""
    organization_id = get_current_organization_id()
    fiscal_period_id = request.form.get('fiscal_period_id', type=int)
    
    if not fiscal_period_id:
        flash('会計期間が指定されていません。', 'danger')
        return redirect(url_for('opening_balances'))
    
    db = SessionLocal()
    try:
        from datetime import datetime
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 既存の期首残高を取得
        existing_balances = db.query(OpeningBalance).filter(
            OpeningBalance.organization_id == organization_id,
            OpeningBalance.fiscal_period_id == fiscal_period_id
        ).all()
        
        existing_balance_dict = {ob.account_item_id: ob for ob in existing_balances}
        
        # フォームデータを処理（勘定科目ごとに借方・貸方をまとめる）
        account_data = {}
        for key, value in request.form.items():
            if key.startswith('debit_') or key.startswith('credit_'):
                parts = key.split('_')
                if len(parts) == 2:
                    field_type = parts[0]  # 'debit' or 'credit'
                    account_item_id = int(parts[1])
                    amount = float(value) if value else 0
                    
                    if account_item_id not in account_data:
                        account_data[account_item_id] = {'debit': 0, 'credit': 0}
                    account_data[account_item_id][field_type] = amount
        
        # 勘定科目ごとに期首残高を保存
        for account_item_id, amounts in account_data.items():
            debit_amount = amounts['debit']
            credit_amount = amounts['credit']
            
            # 既存のレコードを更新または新規作成
            if account_item_id in existing_balance_dict:
                ob = existing_balance_dict[account_item_id]
                ob.debit_amount = debit_amount
                ob.credit_amount = credit_amount
                ob.updated_at = current_time
            else:
                # 新規作成
                ob = OpeningBalance(
                    organization_id=organization_id,
                    fiscal_period_id=fiscal_period_id,
                    account_item_id=account_item_id,
                    debit_amount=debit_amount,
                    credit_amount=credit_amount,
                    created_at=current_time,
                    updated_at=current_time
                )
                db.add(ob)
        
        db.commit()
        flash('期首残高を保存しました。', 'success')
        return redirect(url_for('opening_balances', fiscal_period_id=fiscal_period_id))
    except Exception as e:
        db.rollback()
        flash(f'期首残高の保存に失敗しました: {str(e)}', 'danger')
        return redirect(url_for('opening_balances', fiscal_period_id=fiscal_period_id))
    finally:
        db.close()


# ========== 試算表 ==========
@app.route('/trial-balance', methods=['GET'])
@login_required
def trial_balance():
    """試算表表示
    B/S：大分類→中分類→小分類→勘定科目
    P/L：大分類=「損益」の科目のみを対象とし、階段式に集計
    """
    from collections import OrderedDict

    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        # 会計期間一覧を取得
        fiscal_periods = (
            db.query(FiscalPeriod)
            .filter(FiscalPeriod.organization_id == organization_id)
            .order_by(FiscalPeriod.start_date.desc())
            .all()
        )

        # 選択された会計期間ID（デフォルトは最新）
        selected_period_id = request.args.get("fiscal_period_id", type=int)
        if not selected_period_id and fiscal_periods:
            selected_period_id = fiscal_periods[0].id

        # ------------------------------
        # 初期化
        # ------------------------------
        bs_data = []  # 貸借対照表用の明細（科目単位）
        pl_data = []  # 損益計算書用の明細（科目単位：大分類=損益のみ）
        bs_debit_total = 0
        bs_credit_total = 0
        pl_debit_total = 0
        pl_credit_total = 0

        # 旧ロジック互換用（集計値など）
        bs_stair_step_data = {}
        pl_stair_step_data = {}
        pl_calculations = {}

        # freee 風ツリー
        from collections import OrderedDict
        bs_tree = OrderedDict()
        pl_tree = OrderedDict()

        # --------- ★ P/Lカテゴリ判定ヘルパー（ここがポイント） ----------
        def get_pl_cat(ai):
            """
            P/L 上のカテゴリを決めるカラム
            1. pl_category が入っていればそれを優先
            2. なければ mid_category（中分類）
            3. それも無ければ sub_category（小分類）
            """
            return (ai.pl_category or ai.mid_category or ai.sub_category or "").strip()

        if selected_period_id:
            # 選択された会計期間を取得
            selected_period = (
                db.query(FiscalPeriod)
                .filter(
                    FiscalPeriod.id == selected_period_id,
                    FiscalPeriod.organization_id == organization_id,
                )
                .first()
            )

            if selected_period:
                # ------------------------------
                # 期首残高の取得
                # ------------------------------
                opening_balances_db = (
                    db.query(OpeningBalance)
                    .filter(
                        OpeningBalance.organization_id == organization_id,
                        OpeningBalance.fiscal_period_id == selected_period_id,
                    )
                    .all()
                )

                # 期首残高が登録されていない場合は、前期の仕訳から計算
                if not opening_balances_db:
                    opening_balance_entries = (
                        db.query(GeneralLedger)
                        .filter(
                            GeneralLedger.organization_id == organization_id,
                            GeneralLedger.transaction_date < selected_period.start_date,
                        )
                        .all()
                    )
                else:
                    opening_balance_entries = []

                # 当期仕訳を取得
                current_period_entries = (
                    db.query(GeneralLedger)
                    .filter(
                        GeneralLedger.organization_id == organization_id,
                        GeneralLedger.transaction_date >= selected_period.start_date,
                        GeneralLedger.transaction_date <= selected_period.end_date,
                    )
                    .all()
                )

                # ------------------------------
                # 勘定科目ごとに集計
                # ------------------------------
                account_summary = {}

                # 期首残高テーブルから期首残高を設定
                for ob in opening_balances_db:
                    account_id = ob.account_item_id
                    if account_id not in account_summary:
                        account_summary[account_id] = {
                            "account_item": ob.account_item,
                            "opening_balance": 0,
                            "current_debit": 0,
                            "current_credit": 0,
                        }

                    major_category = ob.account_item.major_category or ""
                    if major_category == "財産":
                        major_category = "負債"

                    if major_category == "資産":
                        # 資産科目: 借方がプラス
                        account_summary[account_id]["opening_balance"] += (
                            float(ob.debit_amount) - float(ob.credit_amount)
                        )
                    elif major_category in ["負債", "純資産"]:
                        # 負債・純資産科目: 貸方がプラス
                        account_summary[account_id]["opening_balance"] += (
                            float(ob.credit_amount) - float(ob.debit_amount)
                        )
                    else:
                        # その他: 借方がプラス
                        account_summary[account_id]["opening_balance"] += (
                            float(ob.debit_amount) - float(ob.credit_amount)
                        )

                # 前期の仕訳から期首残高を計算（期首残高テーブルが空の場合）
                for entry in opening_balance_entries:
                    # 借方
                    debit_account_id = entry.debit_account_item_id
                    if debit_account_id not in account_summary:
                        account_summary[debit_account_id] = {
                            "account_item": entry.debit_account_item,
                            "opening_balance": 0,
                            "current_debit": 0,
                            "current_credit": 0,
                        }
                    account_summary[debit_account_id]["opening_balance"] += entry.debit_amount

                    # 貸方
                    credit_account_id = entry.credit_account_item_id
                    if credit_account_id not in account_summary:
                        account_summary[credit_account_id] = {
                            "account_item": entry.credit_account_item,
                            "opening_balance": 0,
                            "current_debit": 0,
                            "current_credit": 0,
                        }
                    account_summary[credit_account_id]["opening_balance"] -= entry.credit_amount

                # 当期借方・貸方を集計
                for entry in current_period_entries:
                    # 借方
                    debit_account_id = entry.debit_account_item_id
                    if debit_account_id not in account_summary:
                        account_summary[debit_account_id] = {
                            "account_item": entry.debit_account_item,
                            "opening_balance": 0,
                            "current_debit": 0,
                            "current_credit": 0,
                        }
                    account_summary[debit_account_id]["current_debit"] += entry.debit_amount

                    # 貸方
                    credit_account_id = entry.credit_account_item_id
                    if credit_account_id not in account_summary:
                        account_summary[credit_account_id] = {
                            "account_item": entry.credit_account_item,
                            "opening_balance": 0,
                            "current_debit": 0,
                            "current_credit": 0,
                        }
                    account_summary[credit_account_id]["current_credit"] += entry.credit_amount

                # ------------------------------
                # 試算表データを作成 (B/S と P/L に分ける)
                #   P/L は「major_category = 損益」の科目のみ
                # ------------------------------
                for account_id, summary in account_summary.items():
                    opening = summary["opening_balance"]
                    current_debit = summary["current_debit"]
                    current_credit = summary["current_credit"]

                    account_item = summary["account_item"]
                    # account_itemがNoneの場合はスキップ
                    if account_item is None:
                        continue
                    major_category = account_item.major_category or ""

                    # major_category が '財産' の場合は '負債'
                    if major_category == "財産":
                        major_category = "負債"

                    # 残高計算（元のロジックを踏襲）
                    if major_category in ["收入", "収益"]:
                        # 収益科目: 貸方プラス、借方マイナス
                        closing = opening - current_debit + current_credit
                    elif major_category == "資産":
                        # 資産科目: 借方プラス
                        closing = opening + current_debit - current_credit
                    elif major_category in ["負債", "純資産"]:
                        # 負債・純資産科目: 貸方プラス
                        closing = opening - current_debit + current_credit
                    else:
                        # その他（費用・損益など）: 借方プラス
                        closing = opening + current_debit - current_credit

                    data_item = {
                        "account_item": account_item,
                        "opening_balance": opening,
                        "current_debit": current_debit,
                        "current_credit": current_credit,
                        "closing_balance": closing,
                    }

                    # B/S と P/L に分類
                    if major_category in ["資産", "負債", "純資産"]:
                        # 貸借対照表
                        bs_data.append(data_item)
                        bs_debit_total += current_debit
                        bs_credit_total += current_credit
                    elif major_category == "損益":
                        # 損益計算書
                        pl_data.append(data_item)
                        pl_debit_total += current_debit
                        pl_credit_total += current_credit
                    else:
                        # その他の大分類はとりあえず B/S 側に退避
                        bs_data.append(data_item)
                        bs_debit_total += current_debit
                        bs_credit_total += current_credit

                # ------------------------------
                # 並び順（B/S）
                # ------------------------------
                def bs_sort_key(item):
                    ai = item["account_item"]

                    # B/S 大分類の順番
                    bs_major_order = {
                        "資産": 1,
                        "負債": 2,
                        "純資産": 3,
                    }
                    
                    # 中分類の順番（流動性配列法）
                    bs_middle_order = {
                        # 資産
                        "流動資産": 1,
                        "固定資産": 2,
                        "繰延資産": 3,
                        # 負債
                        "流動負債": 1,
                        "固定負債": 2,
                        # 純資産
                        "資本金": 1,
                        "資本剰余金": 2,
                        "利益剰余金": 3,
                        "自己株式": 4,
                        "評価換算差額等": 5,
                        "新株予約権": 6,
                    }
                    
                    # 小分類の順番（流動性配列法：流動性が高い順）
                    bs_small_order = {
                        # 流動資産：現金化しやすい順
                        "現金及び預金": 1,
                        "売上債権": 2,
                        "有価証券": 3,
                        "棚卸資産": 4,
                        "その他流動資産": 5,
                        # 固定資産
                        "有形固定資産": 1,
                        "無形固定資産": 2,
                        "投資その他の資産": 3,
                        # 繰延資産
                        "繰延資産": 1,
                        # 流動負債
                        "仕入債務": 1,
                        "その他流動負債": 2,
                        # 固定負債
                        "固定負債": 1,
                        # 純資産
                        "資本金": 1,
                        "新株式申込証拠金": 1,
                        "資本準備金": 2,
                        "その他資本剰余金": 3,
                        "利益準備金": 1,
                        "その他利益剰余金": 2,
                        "自己株式": 1,
                        "自己株式申込証拠金": 2,
                        "他有価証券評価差額金": 1,
                        "繰延ヘッジ損益": 2,
                        "土地再評価差額金": 3,
                        "新株予約権": 1,
                        # その他
                        "諸口": 99,
                    }

                    major = ai.major_category or ""
                    middle = ai.mid_category or ""
                    small = ai.sub_category or ""

                    return (
                        bs_major_order.get(major, 99),
                        bs_middle_order.get(middle, 99),
                        bs_small_order.get(small, 99),
                        ai.bs_rank
                        if getattr(ai, "bs_rank", None) is not None
                        else (ai.liquidity_rank if getattr(ai, "liquidity_rank", None) is not None else 9999),
                        ai.account_name,
                    )

                # デバッグ: ソート前の現金及び預金科目を確認
                import sys
                for item in bs_data:
                    ai = item["account_item"]
                    if ai.sub_category == "現金及び預金":
                        print(f"[DEBUG] ソート前: {ai.account_name}, bs_rank={ai.bs_rank}", file=sys.stderr, flush=True)
                
                bs_data.sort(key=bs_sort_key)
                
                # デバッグ: ソート後の現金及び預金科目を確認
                for item in bs_data:
                    ai = item["account_item"]
                    if ai.sub_category == "現金及び預金":
                        print(f"[DEBUG] ソート後: {ai.account_name}, bs_rank={ai.bs_rank}", file=sys.stderr, flush=True)

                # ------------------------------
                # P/L 生データ側の並び
                # ------------------------------
                pl_cat_order = {
                    "売上高": 10,
                    # 売上原価の詳細（小分類の値）
                    "期首商品棚卸": 11,
                    "当期商品仕入": 12,
                    "他勘定振替高(商)": 13,
                    "期末商品棚卸": 14,
                    "売上原価": 20,
                    "売上総利益": 30,
                    "販売管理費": 40,
                    "販管費": 40,
                    "販売費及び一般管理費": 40,
                    "営業利益": 50,
                    "営業外収益": 60,
                    "営業外費用": 70,
                    "経常利益": 80,
                    "特別利益": 90,
                    "特別損失": 100,
                    "税引前当期純利益": 110,
                    "法人税等": 120,
                    "法人税等調整額": 130,
                    "当期純利益": 140,
                }

                def pl_sort_key(item):
                    ai = item["account_item"]
                    # 小分類を優先的にチェック
                    sub = (ai.sub_category or "").strip()
                    mid = (ai.mid_category or "").strip()
                    cat = get_pl_cat(ai)
                    
                    # 小分類が pl_cat_order にあればそれを使用、なければ中分類、最後にカテゴリ
                    order = pl_cat_order.get(sub, pl_cat_order.get(mid, pl_cat_order.get(cat, 999)))
                    
                    return (
                        order,
                        ai.pl_rank
                        if getattr(ai, "pl_rank", None) is not None
                        else 9999,
                        ai.account_name or "",
                    )

                pl_data.sort(key=pl_sort_key)

                # ------------------------------
                # 旧ステップ風集計（B/S・P/L 集計値）
                # ------------------------------

                # --- B/S（流動資産など）---
                bs_stair_step_data = {
                    "流動資産": [],
                    "固定資産": [],
                    "投資その他の資産": [],
                    "流動負債": [],
                    "固定負債": [],
                    "資本金": [],
                    "資本剰余金": [],
                    "利益剰余金": [],
                }
                for item in bs_data:
                    bs_category = item["account_item"].bs_category
                    if bs_category and bs_category in bs_stair_step_data:
                        bs_stair_step_data[bs_category].append(item)

                # --- P/L（階段式用）---
                pl_stair_step_data = {
                    "sales": [],
                    "cogs": [],
                    "sga": [],
                    "non_operating_income": [],
                    "non_operating_expense": [],
                    "extraordinary_income": [],
                    "extraordinary_loss": [],
                    "income_taxes": [],
                    "income_taxes_adjustments": [],
                }

                sales_total = 0
                cogs_total = 0
                sga_total = 0
                non_operating_income_total = 0
                non_operating_expense_total = 0
                extraordinary_income_total = 0
                extraordinary_loss_total = 0
                income_taxes_total = 0
                income_taxes_adjustments_total = 0

                for item in pl_data:
                    ai = item["account_item"]
                    category = get_pl_cat(ai)   # ★ ここもヘルパーで判定
                    amount = item["closing_balance"] or 0

                    if category == "売上高":
                        pl_stair_step_data["sales"].append(item)
                        sales_total += amount
                    elif category == "売上原価":
                        pl_stair_step_data["cogs"].append(item)
                        cogs_total += amount
                    elif category in ["販管費", "販売費及び一般管理費", "販売管理費"]:
                        pl_stair_step_data["sga"].append(item)
                        sga_total += amount
                    elif category == "営業外収益":
                        pl_stair_step_data["non_operating_income"].append(item)
                        non_operating_income_total += amount
                    elif category == "営業外費用":
                        pl_stair_step_data["non_operating_expense"].append(item)
                        non_operating_expense_total += amount
                    elif category == "特別利益":
                        pl_stair_step_data["extraordinary_income"].append(item)
                        extraordinary_income_total += amount
                    elif category == "特別損失":
                        pl_stair_step_data["extraordinary_loss"].append(item)
                        extraordinary_loss_total += amount
                    elif category == "法人税等":
                        pl_stair_step_data["income_taxes"].append(item)
                        income_taxes_total += amount
                    elif category == "法人税等調整額":
                        pl_stair_step_data["income_taxes_adjustments"].append(item)
                        income_taxes_adjustments_total += amount

                # 階段式の各段計算
                gross_profit = sales_total - cogs_total
                operating_income = gross_profit - sga_total
                ordinary_income = (
                    operating_income
                    + non_operating_income_total
                    - non_operating_expense_total
                )
                pre_tax_income = (
                    ordinary_income
                    + extraordinary_income_total
                    - extraordinary_loss_total
                )
                net_income = (
                    pre_tax_income
                    - income_taxes_total
                    - income_taxes_adjustments_total
                )

                pl_calculations = {
                    "sales_total": sales_total,
                    "cogs_total": cogs_total,
                    "gross_profit": gross_profit,
                    "sga_total": sga_total,
                    "operating_income": operating_income,
                    "non_operating_income_total": non_operating_income_total,
                    "non_operating_expense_total": non_operating_expense_total,
                    "ordinary_income": ordinary_income,
                    "extraordinary_income_total": extraordinary_income_total,
                    "extraordinary_loss_total": extraordinary_loss_total,
                    "pre_tax_income": pre_tax_income,
                    "income_taxes_total": income_taxes_total,
                    "income_taxes_adjustments_total": income_taxes_adjustments_total,
                    "net_income": net_income,
                }

                # =====================================================
                # B/S 用ツリー（大分類→中分類→小分類→勘定科目）
                # P/Lと同様に、取引の有無に関わらず全科目を表示
                # =====================================================
                
                # bs_data を account_id ベースでマップ化
                bs_map = {row["account_item"].id: row for row in bs_data}
                
                # 大分類が「資産」「負債」「純資産」「負債及び純資産」の全勘定科目を取得
                all_bs_accounts = (
                    db.query(AccountItem)
                    .filter(AccountItem.organization_id == organization_id)
                    .filter(AccountItem.major_category.in_(["資産", "負債", "純資産", "負債及び純資産"]))
                    .all()
                )
                
                # 全科目を含むbs_data_fullを作成
                bs_data_full = []
                for ai in all_bs_accounts:
                    row = bs_map.get(ai.id)
                    if row:
                        # 取引がある場合は実際の金額
                        bs_data_full.append(row)
                    else:
                        # 取引がない場合は0
                        major_category = ai.major_category or ""
                        if major_category == "資産":
                            opening = 0
                            closing = 0
                        elif major_category in ["負債", "純資産", "負債及び純資産"]:
                            opening = 0
                            closing = 0
                        else:
                            opening = 0
                            closing = 0
                        
                        bs_data_full.append({
                            "account_item": ai,
                            "opening_balance": opening,
                            "current_debit": 0,
                            "current_credit": 0,
                            "closing_balance": closing,
                        })
                
                # bs_data_fullを流動性配列（流動性の高い順）で並び替え
                def bs_sort_key_full(item):
                    ai = item["account_item"]
                    
                    # 大分類の順序
                    bs_major_order = {
                        "資産": 1,
                        "負債": 2,
                        "純資産": 3,
                        "負債及び純資産": 2,
                    }
                    
                    # 中分類の順序（流動性ベース）
                    mid_category_order = {
                        # 資産：流動資産 → 固定資産 → 繰延資産
                        "流動資産": 1,
                        "固定資産": 2,
                        "繰延資産": 3,
                        # 負債：流動負債 → 固定負債
                        "流動負債": 1,
                        "固定負債": 2,
                        # 純資産：資本金 → 資本剰余金 → 利益剰余金 → 自己株式 → 評価換算差額等 → 新株予約権
                        "資本金": 1,
                        "資本剰余金": 2,
                        "利益剰余金": 3,
                        "自己株式": 4,
                        "評価換算差額等": 5,
                        "新株予約権": 6,
                        # 損益：P/Lの順序
                        "売上高": 1,
                        "売上原価": 2,
                        "販売費及び一般管理費": 3,
                        "営業外収益": 4,
                        "営業外費用": 5,
                        "特別利益": 6,
                        "特別損失": 7,
                        "法人税等": 8,
                        "法人税等調整額": 9,
                    }
                    
                    # 小分類の順序（流動性配列法：流動性が高い順）
                    sub_category_order = {
                        # 流動資産：現金化しやすい順
                        "現金及び預金": 1,
                        "売上債権": 2,
                        "有価証券": 3,
                        "棚卸資産": 4,
                        "その他流動資産": 5,
                        # 固定資産
                        "有形固定資産": 1,
                        "無形固定資産": 2,
                        "投資その他の資産": 3,
                        # 繰延資産
                        "繰延資産": 1,
                        # 流動負債
                        "仕入債務": 1,
                        "その他流動負債": 2,
                        # 固定負債
                        "固定負債": 1,
                        # 純資産：資本金
                        "資本金": 1,
                        # 純資産：資本剰余金
                        "新株式申込証拠金": 1,
                        "資本準備金": 2,
                        "その他資本剰余金": 3,
                        # 純資産：利益剰余金
                        "利益準備金": 1,
                        "その他利益剰余金": 2,
                        # 純資産：自己株式
                        "自己株式": 1,
                        "自己株式申込証拠金": 2,
                        # 純資産：評価換算差額等
                        "他有価証券評価差額金": 1,
                        "繰延ヘッジ損益": 2,
                        "土地再評価差額金": 3,
                        # 純資産：新株予約権
                        "新株予約権": 1,
                        # 損益
                        "売上高": 1,
                        "期首商品棚卸": 1,
                        "当期商品仕入": 2,
                        "他勘定振替高(商)": 3,
                        "期末商品棚卸": 4,
                        "販売管理費": 1,
                        "営業外収益": 1,
                        "営業外費用": 1,
                        "特別利益": 1,
                        "特別損失": 1,
                        "法人税等": 1,
                        "法人税等調整額": 1,
                    }
                    
                    major = ai.major_category or ""
                    middle = ai.mid_category or ""
                    small = ai.sub_category or ""
                    
                    return (
                        bs_major_order.get(major, 99),
                        mid_category_order.get(middle, 99),
                        sub_category_order.get(small, 99),
                        ai.bs_rank if getattr(ai, "bs_rank", None) is not None
                        else (ai.liquidity_rank if getattr(ai, "liquidity_rank", None) is not None else 9999),
                        ai.account_name,
                    )
                
                bs_data_full.sort(key=bs_sort_key_full)
                
                def build_bs_tree(data_list, major_order=None):
                    tmp = {}
                    for row in data_list:
                        ai = row["account_item"]
                        major = (ai.major_category or "その他").strip()
                        mid = (ai.mid_category or "その他").strip()
                        sub = (ai.sub_category or "その他").strip()

                        if major not in tmp:
                            tmp[major] = OrderedDict()
                        if mid not in tmp[major]:
                            tmp[major][mid] = OrderedDict()
                        if sub not in tmp[major][mid]:
                            tmp[major][mid][sub] = []
                        tmp[major][mid][sub].append(row)

                    # 大分類の並び順を固定（定義にないものは後ろ）
                    if major_order:
                        ordered = OrderedDict()
                        for m in major_order:
                            if m in tmp:
                                ordered[m] = tmp[m]
                        for m in tmp.keys():
                            if m not in ordered:
                                ordered[m] = tmp[m]
                        return ordered
                    else:
                        return OrderedDict(tmp)

                bs_tree = build_bs_tree(bs_data_full, major_order=["資産", "負債", "純資産"])
                
                # 小分類計と中分類計を計算
                bs_subtotals = {}
                for major, mid_dict in bs_tree.items():
                    mid_totals = {}
                    for mid, sub_dict in mid_dict.items():
                        sub_totals = {}
                        for sub, rows in sub_dict.items():
                            # 小分類計
                            opening_total = sum(row.get('opening_balance', 0) or 0 for row in rows)
                            debit_total = sum(row.get('current_debit', 0) or 0 for row in rows)
                            credit_total = sum(row.get('current_credit', 0) or 0 for row in rows)
                            closing_total = sum(row.get('closing_balance', 0) or 0 for row in rows)
                            
                            sub_key = f"{major}_{mid}_{sub}"
                            bs_subtotals[sub_key] = {
                                'opening': opening_total,
                                'debit': debit_total,
                                'credit': credit_total,
                                'closing': closing_total
                            }
                            
                            # 中分類計に加算
                            if mid not in mid_totals:
                                mid_totals[mid] = {'opening': 0, 'debit': 0, 'credit': 0, 'closing': 0}
                            mid_totals[mid]['opening'] += opening_total
                            mid_totals[mid]['debit'] += debit_total
                            mid_totals[mid]['credit'] += credit_total
                            mid_totals[mid]['closing'] += closing_total
                        
                        # 中分類計を保存
                        mid_key = f"{major}_{mid}"
                        bs_subtotals[mid_key] = mid_totals[mid]

                # =====================================================
                # P/L 用ツリー（小分類 → 勘定科目）
                # =====================================================

                # pl_data を account_id ベースでマップ化（当期数字）
                pl_map = {row["account_item"].id: row for row in pl_data}

                # 大分類=損益 の全勘定科目を取得
                all_pl_accounts = (
                    db.query(AccountItem)
                    .filter(AccountItem.organization_id == organization_id)
                    .filter(AccountItem.major_category == "損益")
                    .all()
                )

                pl_tree = OrderedDict()
                sub_priority = {}

                for ai in all_pl_accounts:
                    sub = (ai.sub_category or "その他").strip()
                    if sub not in pl_tree:
                        pl_tree[sub] = {
                            "total_debit": 0,
                            "total_credit": 0,
                            "total_closing": 0,
                            "accounts": OrderedDict(),
                        }

                    row = pl_map.get(ai.id)
                    if row:
                        cd = row["current_debit"]
                        cc = row["current_credit"]
                        cb = row["closing_balance"]
                    else:
                        cd = 0
                        cc = 0
                        cb = 0

                    pl_tree[sub]["accounts"][ai.id] = {
                        "account_item": ai,
                        "current_debit": cd,
                        "current_credit": cc,
                        "closing_balance": cb,
                    }
                    pl_tree[sub]["total_debit"] += cd
                    pl_tree[sub]["total_credit"] += cc
                    pl_tree[sub]["total_closing"] += cb

                    # 並び替え用のカテゴリ優先順位（小分類優先）
                    sub_cat = (ai.sub_category or "").strip()
                    mid_cat = (ai.mid_category or "").strip()
                    cat = get_pl_cat(ai)
                    # 小分類 → 中分類 → カテゴリの順で優先的にチェック
                    cat_ord = pl_cat_order.get(sub_cat, pl_cat_order.get(mid_cat, pl_cat_order.get(cat, 999)))
                    if sub not in sub_priority or cat_ord < sub_priority[sub]:
                        sub_priority[sub] = cat_ord

                # 小分類の並び順を「カテゴリ優先順位 → 小分類名」で並べ替え
                ordered_pl_tree = OrderedDict()
                for sub_name in sorted(
                    pl_tree.keys(),
                    key=lambda s: (sub_priority.get(s, 999), s),
                ):
                    ordered_pl_tree[sub_name] = pl_tree[sub_name]
                pl_tree = ordered_pl_tree
                
                # 中分類でグループ化
                pl_mid_tree = OrderedDict()
                for sub_name, info in pl_tree.items():
                    # 小分類の最初の勘定科目から中分類を取得
                    mid_cat = "その他"
                    for acc in info["accounts"].values():
                        ai = acc["account_item"]
                        mid_cat = (ai.mid_category or "その他").strip()
                        break
                    
                    if mid_cat not in pl_mid_tree:
                        pl_mid_tree[mid_cat] = OrderedDict()
                    pl_mid_tree[mid_cat][sub_name] = info
                
                # 集計行を計算
                pl_subtotals = {}
                
                # 売上高計
                sales_total = sum(info['total_closing'] for name, info in pl_tree.items() if name == '売上高')
                pl_subtotals['売上高計'] = sales_total
                
                # 売上原価計
                cogs_total = sum(info['total_closing'] for name, info in pl_tree.items() 
                               if name in ['期首商品棚卸', '当期商品仕入', '他勘定振替高(商)', '期末商品棚卸', '売上原価'])
                pl_subtotals['売上原価計'] = cogs_total
                
                # 売上総利益 = 売上高計 - 売上原価計
                gross_profit = sales_total - cogs_total
                pl_subtotals['売上総利益'] = gross_profit
                
                # 販売管理費計
                sg_total = sum(info['total_closing'] for name, info in pl_tree.items() 
                              if name in ['販売費', '一般管理費', '販売管理費', '販管費', '販売費及び一般管理費'])
                pl_subtotals['販売管理費計'] = sg_total
                
                # 営業利益 = 売上総利益 - 販売管理費計
                operating_profit = gross_profit - sg_total
                pl_subtotals['営業利益'] = operating_profit
                
                # 営業外収益計
                non_op_income = sum(info['total_closing'] for name, info in pl_tree.items() if name == '営業外収益')
                pl_subtotals['営業外収益計'] = non_op_income
                # 営業外費用計
                non_op_expense = sum(info['total_closing'] for name, info in pl_tree.items() if name == '営業外費用')
                pl_subtotals['営業外費用計'] = non_op_expense
                
                # 経常利益 = 営業利益 + 営業外収益 - 営業外費用
                ordinary_profit = operating_profit + non_op_income - non_op_expense
                pl_subtotals['経常利益'] = ordinary_profit
                
                # 特別利益計
                special_income = sum(info['total_closing'] for name, info in pl_tree.items() if name == '特別利益')
                pl_subtotals['特別利益計'] = special_income
                # 特別損失計
                special_loss = sum(info['total_closing'] for name, info in pl_tree.items() if name == '特別損失')
                pl_subtotals['特別損失計'] = special_loss
                
                # 税引前当期純利益 = 経常利益 + 特別利益 - 特別損失
                pretax_profit = ordinary_profit + special_income - special_loss
                pl_subtotals['税引前当期純利益'] = pretax_profit
                
                # 法人税等計
                tax_total = sum(info['total_closing'] for name, info in pl_tree.items() 
                               if name in ['法人税等', '法人税等調整額'])
                pl_subtotals['法人税等計'] = tax_total
                
                # 当期純利益 = 税引前当期純利益 - 法人税等
                net_profit = pretax_profit - tax_total
                pl_subtotals['当期純利益'] = net_profit

        return render_template(
            "trial_balance/index.html",
            fiscal_periods=fiscal_periods,
            selected_period_id=selected_period_id,
            # 明細データ
            bs_data=bs_data_full,
            pl_data=pl_data,
            # freee風ツリー
            bs_tree=bs_tree,
            pl_tree=pl_tree,
            pl_mid_tree=pl_mid_tree,
            pl_subtotals=pl_subtotals,
            bs_subtotals=bs_subtotals,
            # 旧ロジックの集計値
            bs_stair_step_data=bs_stair_step_data,
            pl_stair_step_data=pl_stair_step_data,
            pl_calculations=pl_calculations,
            bs_debit_total=bs_debit_total,
            bs_credit_total=bs_credit_total,
            pl_debit_total=pl_debit_total,
            pl_credit_total=pl_credit_total,
        )
    finally:
        db.close()


# ========== 仕訳帳 ==========
@app.route('/general-ledger')
@login_required
def general_ledger():
    """仕訳帳一覧表示"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        # 会計期間一覧を取得
        fiscal_periods = (
            db.query(FiscalPeriod)
            .filter(FiscalPeriod.organization_id == organization_id)
            .order_by(FiscalPeriod.start_date.desc())
            .all()
        )

        # 選択された会計期間ID（デフォルトは最新）
        selected_period_id = request.args.get('fiscal_period_id', type=int)

        general_ledger_entries = []
        selected_period = None

        # 会計期間が登録されているか確認し、デフォルトを選択
        if fiscal_periods:
            if not selected_period_id:
                selected_period_id = fiscal_periods[0].id

            # 選択された会計期間を取得
            selected_period = (
                db.query(FiscalPeriod)
                .filter(
                    FiscalPeriod.id == selected_period_id,
                    FiscalPeriod.organization_id == organization_id,
                )
                .first()
            )

        # クエリの基本形
        query = db.query(GeneralLedger).filter(
            GeneralLedger.organization_id == organization_id
        )

        if selected_period:
            # 会計期間内の仕訳帳データを取得
            query = query.filter(
                GeneralLedger.transaction_date >= selected_period.start_date,
                GeneralLedger.transaction_date <= selected_period.end_date,
            )

        # 仕訳帳データを取得
        general_ledger_entries = query.order_by(
            GeneralLedger.transaction_date, GeneralLedger.id
        ).all()

        # 口座の場合は口座名を上書き
        for entry in general_ledger_entries:
            # 借方が口座の場合、口座名を取得
            if entry.debit_account_item_id:
                account = (
                    db.query(Account)
                    .filter(
                        Account.account_item_id == entry.debit_account_item_id,
                        Account.organization_id == organization_id,
                    )
                    .first()
                )
                if account and entry.debit_account_item:
                    entry.debit_account_item.account_name = account.account_name

            # 貸方が口座の場合、口座名を取得
            if entry.credit_account_item_id:
                account = (
                    db.query(Account)
                    .filter(
                        Account.account_item_id == entry.credit_account_item_id,
                        Account.organization_id == organization_id,
                    )
                    .first()
                )
                if account and entry.credit_account_item:
                    entry.credit_account_item.account_name = account.account_name

        return render_template(
            "general_ledger/index.html",
            fiscal_periods=fiscal_periods,
            selected_period_id=selected_period_id,
            selected_period=selected_period,
            general_ledger_entries=general_ledger_entries,
        )
    except Exception as e:
        flash(f"エラーが発生しました: {str(e)}", "error")
        return redirect(url_for("home"))
    finally:
        db.close()


# 孤立した仕訳データを削除するAPI
@app.route('/api/general-ledger/orphaned/<int:cash_book_id>', methods=['DELETE'])
@login_required
def delete_orphaned_journal_entry(cash_book_id):
    """出納帳データが存在しない仕訳データを削除するAPI"""
    db = SessionLocal()
    try:
        organization_id = get_current_organization_id()
        
        # source_type='batch_entry'かつsource_id=cash_book_idの仕訳データを検索
        general_ledger_entries = db.query(GeneralLedger).filter(
            GeneralLedger.source_type.in_(['batch_entry', 'batch_entry_net', 'batch_entry_tax']),
            GeneralLedger.source_id == cash_book_id,
            GeneralLedger.organization_id == organization_id
        ).all()
        
        if not general_ledger_entries:
            return jsonify({'success': False, 'message': '仕訳データが見つかりません'}), 404
        
        # 仕訳データを削除
        for entry in general_ledger_entries:
            db.delete(entry)
        
        db.commit()
        return jsonify({'success': True, 'message': f'{len(general_ledger_entries)}件の仕訳データを削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

@app.route('/organization/create', methods=['GET', 'POST'])
def organization_create_page():
    """事業所追加ページと追加処理（開発用）"""
    if request.method == 'GET':
        return render_template('organization_create.html')
    
    # POSTリクエストの場合
    db = SessionLocal()
    try:
        # フォームデータを取得
        org = Organization(
            name=request.form.get('name'),
            code=request.form.get('code'),
            business_type=request.form.get('business_type'),
            representative=request.form.get('representative'),
            established_date=request.form.get('established_date') or None,
            postal_code=request.form.get('postal_code'),
            address=request.form.get('address'),
            phone=request.form.get('phone'),
            fax=request.form.get('fax'),
            email=request.form.get('email'),
            notes=request.form.get('notes'),
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        
        db.add(org)
        db.commit()
        db.refresh(org)
        
        flash(f'事業所「{org.name}」を追加しました', 'success')
        return redirect(url_for('login'))
    except Exception as e:
        db.rollback()
        import traceback
        error_msg = traceback.format_exc()
        print(f'Error creating organization: {error_msg}')
        flash(f'事業所の追加に失敗しました: {str(e)}', 'danger')
        return redirect(url_for('organization_create_page'))
    finally:
        db.close()

# 総勘定元帳
@app.route('/ledger', methods=['GET'])
@login_required
def ledger():
    org_id = get_current_organization_id()
    db = SessionLocal()
    try:
        # 会計期間を取得
        fiscal_periods = (
            db.query(FiscalPeriod)
            .filter_by(organization_id=org_id)
            .order_by(FiscalPeriod.start_date.desc())
            .all()
        )

        # 勘定科目を取得
        account_items = (
            db.query(AccountItem)
            .filter_by(organization_id=org_id)
            .order_by(AccountItem.account_name)
            .all()
        )

        # 選択された会計期間と勘定科目
        selected_fiscal_period_id = request.args.get('fiscal_period_id', type=int)
        selected_account_item_id = request.args.get('account_item_id', type=int)

        transactions = []
        monthly_totals = []
        opening_balance = 0
        selected_fiscal_period = None
        selected_account_item = None

        if selected_fiscal_period_id and selected_account_item_id:
            selected_fiscal_period = (
                db.query(FiscalPeriod)
                .filter_by(id=selected_fiscal_period_id, organization_id=org_id)
                .first()
            )
            selected_account_item = (
                db.query(AccountItem)
                .filter_by(id=selected_account_item_id, organization_id=org_id)
                .first()
            )

            if selected_fiscal_period and selected_account_item:
                # 期首残高を計算（会計期間開始日より前の仕訳）
                opening_entries = (
                    db.query(GeneralLedger)
                    .filter(
                        GeneralLedger.organization_id == org_id,
                        GeneralLedger.transaction_date < selected_fiscal_period.start_date,
                        or_(
                            GeneralLedger.debit_account_item_id
                            == selected_account_item_id,
                            GeneralLedger.credit_account_item_id
                            == selected_account_item_id,
                        ),
                    )
                    .all()
                )

                for entry in opening_entries:
                    if entry.debit_account_item_id == selected_account_item_id:
                        opening_balance += entry.debit_amount
                    if entry.credit_account_item_id == selected_account_item_id:
                        opening_balance -= entry.credit_amount

                # 勘定科目の種類に応じて期首残高の符号を調整
                if selected_account_item.major_category in ['收入']:
                    opening_balance = -opening_balance

                # 当期の仕訳を取得
                current_entries = (
                    db.query(GeneralLedger)
                    .filter(
                        GeneralLedger.organization_id == org_id,
                        GeneralLedger.transaction_date
                        >= selected_fiscal_period.start_date,
                        GeneralLedger.transaction_date
                        <= selected_fiscal_period.end_date,
                        or_(
                            GeneralLedger.debit_account_item_id
                            == selected_account_item_id,
                            GeneralLedger.credit_account_item_id
                            == selected_account_item_id,
                        ),
                    )
                    .order_by(GeneralLedger.transaction_date)
                    .all()
                )

                # 取引データを作成
                running_balance = opening_balance
                current_month = None
                month_debit_total = 0
                month_credit_total = 0

                for entry in current_entries:
                    # transaction_date は文字列想定なので先頭7桁(YYYY-MM) を取得
                    entry_month = entry.transaction_date[:7]
                    if current_month and current_month != entry_month:
                        monthly_totals.append(
                            {
                                "month": current_month,
                                "debit_total": month_debit_total,
                                "credit_total": month_credit_total,
                            }
                        )
                        month_debit_total = 0
                        month_credit_total = 0
                    current_month = entry_month

                    # 相手勘定科目と金額を決定
                    if entry.debit_account_item_id == selected_account_item_id:
                        counterpart_account = entry.credit_account_item.account_name
                        debit_amount = entry.debit_amount
                        credit_amount = 0
                        if selected_account_item.major_category in ['收入']:
                            running_balance -= debit_amount
                        else:
                            running_balance += debit_amount
                        month_debit_total += debit_amount
                    else:
                        counterpart_account = entry.debit_account_item.account_name
                        debit_amount = 0
                        credit_amount = entry.credit_amount
                        if selected_account_item.major_category in ['收入']:
                            running_balance += credit_amount
                        else:
                            running_balance -= credit_amount
                        month_credit_total += credit_amount

                    transactions.append(
                        {
                            "date": entry.transaction_date,
                            "counterpart_account": counterpart_account,
                            "summary": entry.summary or "",
                            "debit": debit_amount,
                            "credit": credit_amount,
                            "balance": running_balance,
                        }
                    )

                # 最後の月の合計を追加
                if current_month:
                    monthly_totals.append(
                        {
                            "month": current_month,
                            "debit_total": month_debit_total,
                            "credit_total": month_credit_total,
                        }
                    )

        return render_template(
            "ledger/index.html",
            fiscal_periods=fiscal_periods,
            account_items=account_items,
            selected_fiscal_period=selected_fiscal_period,
            selected_account_item=selected_account_item,
            opening_balance=opening_balance,
            transactions=transactions,
            monthly_totals=monthly_totals,
            current_organization=get_current_organization(),
        )
    finally:
        db.close()



# ========== タグマスターAPI =========

# 取引先全件取得API (Tom Select用)
@app.route('/api/counterparties/all', methods=['GET'])
@login_required
def get_all_counterparties():
    db = SessionLocal()
    try:
        counterparties = db.query(Counterparty).filter(
            Counterparty.organization_id == session['organization_id']
        ).order_by(Counterparty.name.asc()).all()
        
        counterparties_list = [{'id': c.id, 'name': c.name} for c in counterparties]
        return jsonify({'success': True, 'counterparties': counterparties_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 部門全件取得API (Tom Select用)
@app.route('/api/departments/all', methods=['GET'])
@login_required
def get_all_departments():
    db = SessionLocal()
    try:
        departments = db.query(Department).filter(
            Department.organization_id == session['organization_id']
        ).order_by(Department.name.asc()).all()
        
        departments_list = [{'id': d.id, 'name': d.name} for d in departments]
        return jsonify({'success': True, 'departments': departments_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 品目全件取得API (Tom Select用)
@app.route('/api/items/all', methods=['GET'])
@login_required
def get_all_items():
    db = SessionLocal()
    try:
        items = db.query(Item).filter(
            Item.organization_id == session['organization_id']
        ).order_by(Item.name.asc()).all()
        
        items_list = [{'id': i.id, 'name': i.name} for i in items]
        return jsonify({'success': True, 'items': items_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 案件タグ全件取得API (Tom Select用)
@app.route('/api/project-tags/all', methods=['GET'])
@login_required
def get_all_project_tags():
    db = SessionLocal()
    try:
        project_tags = db.query(ProjectTag).filter(
            ProjectTag.organization_id == session['organization_id'],
            ProjectTag.is_active == 1
        ).order_by(ProjectTag.tag_name.asc()).all()
        
        project_tags_list = [{'id': p.id, 'name': p.tag_name} for p in project_tags]
        return jsonify({'success': True, 'project_tags': project_tags_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# メモタグ全件取得API (Tom Select用)
@app.route('/api/memo-tags/all', methods=['GET'])
@login_required
def get_all_memo_tags():
    db = SessionLocal()
    try:
        memo_tags = db.query(MemoTag).filter(
            MemoTag.organization_id == session['organization_id']
        ).order_by(MemoTag.name.asc()).all()
        
        memo_tags_list = [{'id': m.id, 'name': m.name} for m in memo_tags]
        return jsonify({'success': True, 'memo_tags': memo_tags_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# ========== 事業所設定画面 ==========
@app.route('/organization_settings', methods=['GET', 'POST'])
@login_required
def organization_settings():
    """事業所設定画面"""
    db = SessionLocal()
    try:
        org_id = session.get('organization_id')
        organization = db.query(Organization).filter(Organization.id == org_id).first()
        
        if not organization:
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            # フォームデータの処理
            tab = request.form.get('tab', 'basic-info')
            
            if tab == 'basic-info':
                # 基本情報の更新
                organization.name = request.form.get('name', organization.name)
                organization.code = request.form.get('code', organization.code)
                organization.business_type = request.form.get('business_type', organization.business_type)
                organization.postal_code = request.form.get('postal_code', organization.postal_code)
                organization.address = request.form.get('address', organization.address)
                organization.phone = request.form.get('phone', organization.phone)
                organization.fax = request.form.get('fax', organization.fax)
                organization.email = request.form.get('email', organization.email)
                organization.representative = request.form.get('representative', organization.representative)
                organization.established_date = request.form.get('established_date', organization.established_date)
                organization.notes = request.form.get('notes', organization.notes)
                organization.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                db.commit()
                return render_template('organization_settings.html', 
                                     organization=organization,
                                     active_menu='settings',
                                     active_submenu='organization_settings',
                                     success_message='基本情報を保存しました。')
            
            elif tab == 'accounting-period':
                # 会計期間の更新（FiscalPeriodテーブルに保存）
                start_date = request.form.get('start_date')
                end_date = request.form.get('end_date')
                period_number_str = request.form.get('period_number', '').strip()
                period_number = int(period_number_str) if period_number_str else None
                
                # 既存の会計期間を取得
                fiscal_period = db.query(FiscalPeriod).filter(
                    FiscalPeriod.organization_id == org_id
                ).first()
                
                if not fiscal_period:
                    fiscal_period = FiscalPeriod(
                        organization_id=org_id,
                        start_date=start_date,
                        end_date=end_date,
                        period_number=period_number
                    )
                    db.add(fiscal_period)
                else:
                    fiscal_period.start_date = start_date
                    fiscal_period.end_date = end_date
                    fiscal_period.period_number = period_number
                
                db.commit()
                return render_template('organization_settings.html', 
                                     organization=organization,
                                     active_menu='settings',
                                     active_submenu='organization_settings',
                                     success_message='会計期間を保存しました。')
            
            else:
                # その他の設定（将来の拡張用）
                db.commit()
                return render_template('organization_settings.html', 
                                     organization=organization,
                                     active_menu='settings',
                                     active_submenu='organization_settings',
                                     success_message='設定を保存しました。')
        
        # GET リクエスト：設定画面を表示
        fiscal_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.organization_id == org_id
        ).first()
        
        fiscal_year_start = fiscal_period.start_date if fiscal_period else ''
        fiscal_year_end = fiscal_period.end_date if fiscal_period else ''
        period_number = fiscal_period.period_number if fiscal_period else ''
        
        # 貸借対照表科目を流動性配列で取得
        bs_accounts_query = db.query(AccountItem).filter(
            AccountItem.organization_id == org_id,
            AccountItem.major_category.in_(['資産', '負債', '純資産'])
        ).order_by(AccountItem.bs_rank.nullslast(), AccountItem.account_name).all()
        
        # カテゴリ別に整理（sub_categoryでグループ化）
        from collections import OrderedDict
        bs_accounts_by_category = OrderedDict()
        
        # カテゴリの順序を定義（sub_categoryベース）
        category_order = [
            # 流動資産
            '現金及び預金',
            '売上債権',
            '有価証券',
            '棚卸資産',
            'その他流動資産',
            # 固定資産
            '有形固定資産',
            '無形固定資産',
            '投資その他の資産',
            # 繰延資産
            '繰延資産',
            # 流動負債
            '仕入債務',
            'その他流動負債',
            # 固定負債
            '固定負債',
            # 純資産
            '資本金',
            '新株式申込証拠金',
            '資本準備金',
            'その他資本剰余金',
            '利益準備金',
            'その他利益剰余金',
            '自己株式',
            '自己株式申込証拠金',
            '新株予約権',
            '他有価証券評価差額金',
            '繰延ヘッジ損益',
            '土地再評価差額金',
            '請口'
        ]
        
        for item in bs_accounts_query:
            sub_cat = item.sub_category or 'その他'
            if sub_cat not in bs_accounts_by_category:
                bs_accounts_by_category[sub_cat] = []
            bs_accounts_by_category[sub_cat].append({
                'id': item.id,
                'account_name': item.account_name,
                'display_name': item.display_name
            })
        
        # カテゴリを定義された順序に並べ替え
        sorted_bs_accounts = OrderedDict()
        for cat in category_order:
            if cat in bs_accounts_by_category:
                sorted_bs_accounts[cat] = bs_accounts_by_category[cat]
        # 定義にないカテゴリを追加
        for cat, items in bs_accounts_by_category.items():
            if cat not in sorted_bs_accounts:
                sorted_bs_accounts[cat] = items
        
        # 期首残高を取得
        opening_balances = []
        opening_balance_dict = {}
        if fiscal_period:
            opening_balances = db.query(OpeningBalance).filter(
                OpeningBalance.organization_id == org_id,
                OpeningBalance.fiscal_period_id == fiscal_period.id
            ).all()
            # account_item_idをキーとした辞書を作成
            opening_balance_dict = {ob.account_item_id: ob for ob in opening_balances}
        
        return render_template('organization_settings.html',
                             organization=organization,
                             start_date=fiscal_year_start,
                             end_date=fiscal_year_end,
                             period_number=period_number,
                             bs_accounts_by_category=sorted_bs_accounts,
                             opening_balance_dict=opening_balance_dict,
                             active_menu='settings',
                             active_submenu='organization_settings')
    
    except Exception as e:
        db.rollback()
        # エラー発生時もorganizationを渡すように修正
        organization = organization if 'organization' in locals() else None
        return render_template('organization_settings.html',
                             organization=organization,
                             active_menu='settings',
                             active_submenu='organization_settings',
                             error_message=f'エラーが発生しました: {str(e)}')
    finally:
        db.close()


# ========== 期首残高保存API ==========
@app.route('/organization_settings/opening_balances', methods=['POST'])
@login_required
def save_organization_opening_balances():
    """事業所設定画面から期首残高を保存"""
    db = SessionLocal()
    try:
        org_id = session.get('organization_id')
        data = request.get_json()
        opening_balances_data = data.get('opening_balances', [])
        
        # 会計期間を取得
        fiscal_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.organization_id == org_id
        ).first()
        
        if not fiscal_period:
            return jsonify({'success': False, 'error': '会計期間が設定されていません。'})
        
        # 既存の期首残高を削除
        db.query(OpeningBalance).filter(
            OpeningBalance.organization_id == org_id,
            OpeningBalance.fiscal_period_id == fiscal_period.id
        ).delete()
        
        # 新しい期首残高を追加
        for ob_data in opening_balances_data:
            opening_balance = OpeningBalance(
                organization_id=org_id,
                fiscal_period_id=fiscal_period.id,
                account_item_id=ob_data['account_item_id'],
                debit_amount=ob_data['debit_amount'],
                credit_amount=ob_data['credit_amount'],
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.add(opening_balance)
        
        db.commit()
        return jsonify({'success': True})
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()


# ========== アプリケーション起動 ===========
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
