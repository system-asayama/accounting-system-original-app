"""
counterparties Blueprint
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

bp = Blueprint('counterparties', __name__, url_prefix='')

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


@bp.route('/counterparties', methods=['GET'])
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


@bp.route('/counterparties/new', methods=['GET'])
@login_required
def counterparty_new():
    """取引先新規作成ページ"""
    return render_template('counterparties/form.html', counterparty=None)


# 取引先作成API


@bp.route('/counterparties/create', methods=['POST'])
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


@bp.route('/counterparties/<int:counterparty_id>/edit', methods=['GET'])
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


@bp.route('/counterparties/<int:counterparty_id>/update', methods=['POST'])
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


@bp.route('/api/counterparties/<int:counterparty_id>/delete', methods=['POST'])
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


@bp.route('/api/counterparties/all', methods=['GET'])
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

