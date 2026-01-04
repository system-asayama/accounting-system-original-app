"""
home Blueprint
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

bp = Blueprint('home', __name__, url_prefix='')

# ヘルパー関数
def login_required(f):
    """ログインが必要なルートに付与するデコレーター"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print(f"DEBUG home.login_required: session = {dict(session)}")
        # ログインシステムの認証チェック
        if 'user_id' not in session:
            print("DEBUG home.login_required: user_id not in session, redirecting to auth.select_login")
            return redirect(url_for('auth.select_login'))
        
        # テナントIDからorganization_idを自動設定
        if 'organization_id' not in session:
            print("DEBUG home.login_required: organization_id not in session")
            tenant_id = session.get('tenant_id')
            print(f"DEBUG home.login_required: tenant_id = {tenant_id}")
            if tenant_id:
                # テナントIDからOrganizationを取得または作成
                db = SessionLocal()
                try:
                    from app.models_login import TTenant
                    tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                    if tenant:
                        # テナントに対応するOrganizationを検索
                        org = db.query(Organization).filter(Organization.name == tenant.名称).first()
                        if not org:
                            # Organizationが存在しない場合は作成
                            org = Organization(name=tenant.名称)
                            db.add(org)
                            db.commit()
                            db.refresh(org)
                        session['organization_id'] = org.id
                        print(f"DEBUG home.login_required: set organization_id = {org.id}")
                finally:
                    db.close()
            else:
                # テナントIDがない場合はログイン画面へ
                print("DEBUG home.login_required: tenant_id is None, redirecting to auth.select_login")
                return redirect(url_for('auth.select_login'))
        
        print(f"DEBUG home.login_required: calling function {f.__name__}")
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


@bp.route('/masters')
def masters_index():
    """マスター管理画面"""
    return render_template('masters/index.html')

# ========== ホーム画面 ==========



@bp.route('/')
def home():
    """ホーム画面 - ログインしていない場合はログイン画面へ"""
    import sys
    print("="*80, flush=True)
    print(f"DEBUG home(): Called at {datetime.now()}", flush=True)
    print(f"DEBUG home(): session keys = {list(session.keys())}", flush=True)
    print(f"DEBUG home(): session = {dict(session)}", flush=True)
    sys.stdout.flush()
    
    # ログインシステムの認証チェック
    if 'user_id' not in session:
        print("DEBUG home(): user_id not in session, redirecting to auth.select_login", flush=True)
        sys.stdout.flush()
        return redirect(url_for('auth.select_login'))
    
    print("DEBUG home(): user_id found in session", flush=True)
    
    # テナントIDからorganization_idを自動設定
    if 'organization_id' not in session:
        print("DEBUG home(): organization_id not in session", flush=True)
        tenant_id = session.get('tenant_id')
        print(f"DEBUG home(): tenant_id = {tenant_id}", flush=True)
        if tenant_id:
            print(f"DEBUG home(): Fetching tenant with id={tenant_id}", flush=True)
            # テナントIDからOrganizationを取得または作成
            db = SessionLocal()
            try:
                from app.models_login import TTenant
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                if tenant:
                    # テナントに対応するOrganizationを検索
                    org = db.query(Organization).filter(Organization.name == tenant.名称).first()
                    if not org:
                        # Organizationが存在しない場合は作成
                        org = Organization(name=tenant.名称)
                        db.add(org)
                        db.commit()
                        db.refresh(org)
                    session['organization_id'] = org.id
                    print(f"DEBUG home(): Set organization_id = {org.id}", flush=True)
            finally:
                db.close()
        else:
            # テナントIDがない場合はログイン画面へ
            print("DEBUG home(): tenant_id is None, redirecting to auth.select_login", flush=True)
            return redirect(url_for('auth.select_login'))
    
    print("DEBUG home(): All checks passed, rendering template", flush=True)
    print(f"DEBUG home(): Final organization_id = {session.get('organization_id')}", flush=True)
    
    db = SessionLocal()
    try:
        # 統計情報を取得（事業所フィルタリング適用）
        organization_id = session['organization_id']
        print(f"DEBUG home(): Fetching stats for organization_id = {organization_id}", flush=True)
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


@bp.route('/index')
@login_required
def index():
    return redirect(url_for('home'))











# 勘定科目全件取得API (Tom Select用)

