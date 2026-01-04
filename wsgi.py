from flask import Flask, session, redirect, url_for, render_template, request, flash, jsonify, send_file
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from db import SessionLocal, engine
from models import Base, AccountItem, CashBook, ImportTemplate, Account, TaxCategory, JournalEntry, Department, Counterparty, Item, ProjectTag, MemoTag, CashBookMaster, FiscalPeriod, Organization, ImportedTransaction, GeneralLedger, OpeningBalance, Template, User, UserOrganization
from app.models_login import TKanrisha, TJugyoin, TTenant, TTenpo, TKanrishaTenpo, TJugyoinTenpo, TTenantAppSetting, TTenpoAppSetting, TTenantAdminTenant
import os
from datetime import datetime
import json
from import_utils import ImportProcessor
from functools import wraps
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

# ========== ヘルパー関数 ==========
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
    
    # CSRFトークン生成関数
    def get_csrf():
        import secrets
        tok = session.get("csrf_token")
        if not tok:
            tok = secrets.token_hex(16)
            session["csrf_token"] = tok
        return tok
    
    return dict(
        Account=Account,
        current_organization=current_org,
        current_fiscal_period=current_fiscal_period,
        get_csrf=get_csrf
    )

# ========== 起動時の初期データ作成 ==========
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

# ========== Blueprintの登録 ==========
# 会計システムのBlueprints
from blueprints.home import bp as home_bp
from blueprints.cash_books import bp as cash_books_bp
from blueprints.account_items import bp as account_items_bp
from blueprints.accounts import bp as accounts_bp
from blueprints.tax_categories import bp as tax_categories_bp
from blueprints.journal_entries import bp as journal_entries_bp
from blueprints.cash_book_masters import bp as cash_book_masters_bp
from blueprints.departments import bp as departments_bp
from blueprints.counterparties import bp as counterparties_bp
from blueprints.items import bp as items_bp
from blueprints.project_tags import bp as project_tags_bp
from blueprints.memo_tags import bp as memo_tags_bp
from blueprints.fiscal_periods import bp as fiscal_periods_bp
from blueprints.organizations import bp as organizations_bp
from blueprints.reports import bp as reports_bp
from blueprints.import_data import bp as import_data_bp
from blueprints.templates import bp as templates_bp

# ログインシステムのBlueprints
try:
    from blueprints.auth import bp as auth_bp
    from blueprints.system_admin import bp as system_admin_bp
    from blueprints.tenant_admin import bp as tenant_admin_bp
    from blueprints.admin import bp as admin_bp
    from blueprints.employee import bp as employee_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(system_admin_bp)
    app.register_blueprint(tenant_admin_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(employee_bp)
    print("✅ ログインシステムのBlueprintを登録しました")
except Exception as e:
    print(f"⚠️ ログインシステムのBlueprint登録エラー: {e}")

# 会計システムのBlueprintを登録
app.register_blueprint(home_bp, url_prefix='/accounting')
app.register_blueprint(cash_books_bp, url_prefix='/accounting')
app.register_blueprint(account_items_bp, url_prefix='/accounting')
app.register_blueprint(accounts_bp, url_prefix='/accounting')
app.register_blueprint(tax_categories_bp, url_prefix='/accounting')
app.register_blueprint(journal_entries_bp, url_prefix='/accounting')
app.register_blueprint(cash_book_masters_bp, url_prefix='/accounting')
app.register_blueprint(departments_bp, url_prefix='/accounting')
app.register_blueprint(counterparties_bp, url_prefix='/accounting')
app.register_blueprint(items_bp, url_prefix='/accounting')
app.register_blueprint(project_tags_bp, url_prefix='/accounting')
app.register_blueprint(memo_tags_bp, url_prefix='/accounting')
app.register_blueprint(fiscal_periods_bp, url_prefix='/accounting')
app.register_blueprint(organizations_bp, url_prefix='/accounting')
app.register_blueprint(reports_bp, url_prefix='/accounting')
app.register_blueprint(import_data_bp, url_prefix='/accounting')
app.register_blueprint(templates_bp, url_prefix='/accounting')

if __name__ == '__main__':
    app.run(debug=True)
