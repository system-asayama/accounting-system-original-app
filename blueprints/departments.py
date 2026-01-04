"""
departments Blueprint
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

bp = Blueprint('departments', __name__, url_prefix='')

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


@bp.route('/departments', methods=['GET'])
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


@bp.route('/departments/new', methods=['GET'])
@login_required
def department_new():
    """部門新規作成ページ"""
    return render_template('departments/form.html', department=None)


# 部門作成API


@bp.route('/departments/create', methods=['POST'])
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


@bp.route('/departments/<int:department_id>/edit', methods=['GET'])
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


@bp.route('/departments/<int:department_id>/update', methods=['POST'])
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


@bp.route('/api/departments/<int:department_id>/delete', methods=['POST'])
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


@bp.route('/api/departments/all', methods=['GET'])
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

