"""
items Blueprint
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

bp = Blueprint('items', __name__, url_prefix='')

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


@bp.route('/items', methods=['GET'])
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




@bp.route('/items/new', methods=['GET'])
@login_required
def item_new():
    """品目新規作成ページ"""
    return render_template('items/form.html', item=None)




@bp.route('/items/create', methods=['POST'])
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




@bp.route('/items/<int:item_id>/edit', methods=['GET'])
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




@bp.route('/items/<int:item_id>/update', methods=['POST'])
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




@bp.route('/api/items/<int:item_id>/delete', methods=['POST'])
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


@bp.route('/api/items/all', methods=['GET'])
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

