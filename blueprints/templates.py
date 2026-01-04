"""
templates Blueprint
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

bp = Blueprint('templates', __name__, url_prefix='')

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


@bp.route('/templates', methods=['GET'])
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


@bp.route('/templates/new', methods=['GET', 'POST'])
@login_required
def template_new():
    return template_form_handler(None)

@bp.route('/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
def template_edit(template_id):
    return template_form_handler(template_id)

def template_form_handler(template_id=None):
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


@bp.route('/templates/<int:template_id>/edit', methods=['GET', 'POST'])
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


@bp.route('/api/templates/<int:template_id>/delete', methods=['POST'])
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


@bp.route('/api/templates/all', methods=['GET'])
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

