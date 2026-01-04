"""
fiscal_periods Blueprint
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

bp = Blueprint('fiscal_periods', __name__, url_prefix='')

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


@bp.route('/fiscal-periods', methods=['GET'])
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




@bp.route('/fiscal-periods/new', methods=['GET'])
@login_required
def fiscal_period_new():
    """会計期間新規作成ページ"""
    return render_template('fiscal_periods/form.html', fiscal_period=None)




@bp.route('/fiscal-periods/create', methods=['POST'])
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




@bp.route('/fiscal-periods/<int:fiscal_period_id>/edit', methods=['GET'])
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




@bp.route('/fiscal-periods/<int:fiscal_period_id>/update', methods=['POST'])
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




@bp.route('/api/fiscal-periods/<int:fiscal_period_id>/delete', methods=['POST'])
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




@bp.route('/api/fiscal-periods/<int:fiscal_period_id>/close', methods=['POST'])
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

