"""
tax_categories Blueprint
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

bp = Blueprint('tax_categories', __name__, url_prefix='')

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


@bp.route('/api/tax-categories/all', methods=['GET'])
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




@bp.route('/tax-categories', methods=['GET'])
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


@bp.route('/tax-categories/new', methods=['GET', 'POST'])
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


@bp.route('/tax-categories/<int:tax_category_id>/edit', methods=['GET', 'POST'])
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


@bp.route('/api/tax-categories/<int:tax_category_id>/delete', methods=['POST'])
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


@bp.route('/api/tax-categories/import', methods=['POST'])
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

