"""
import_data Blueprint
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

bp = Blueprint('import_data', __name__, url_prefix='')

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


@bp.route('/import', methods=['GET', 'POST'])
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


@bp.route('/import/preview', methods=['GET', 'POST'])
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


@bp.route('/import/templates', methods=['GET'])
def import_templates_list():
    db = SessionLocal()
    try:
        templates = db.query(ImportTemplate).all()
        return render_template('import/templates.html', templates=templates)
    finally:
        db.close()

# ========== 連続仕訳テンプレート機能 ==========

# テンプレート一覧ページ


@bp.route('/import-templates/<int:template_id>/delete', methods=['POST'])
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

