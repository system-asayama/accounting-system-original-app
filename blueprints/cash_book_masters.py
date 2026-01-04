"""
cash_book_masters Blueprint
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

bp = Blueprint('cash_book_masters', __name__, url_prefix='')

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


@bp.route('/cash-book-masters', methods=['GET'])
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


@bp.route('/cash-book-masters/new', methods=['GET', 'POST'])
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


@bp.route('/cash-book-masters/<int:item_id>/edit', methods=['GET', 'POST'])
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

# 出納帳マスター削除API@bp.route('/api/cash-book-masters/<int:item_id>/delete', methods=['POST'])


# 出納帳マスター削除API@bp.route('/api/cash-book-masters/<int:item_id>/delete', methods=['POST'])
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

