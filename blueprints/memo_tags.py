"""
memo_tags Blueprint
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

bp = Blueprint('memo_tags', __name__, url_prefix='')

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


@bp.route('/memo-tags', methods=['GET'])
@login_required
def memo_tags_list():
    """メモタグ一覧ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '').strip()
        
        query = db.query(MemoTag).filter(MemoTag.organization_id == organization_id)
        if search_query:
            query = query.filter(MemoTag.name.like(f'%{search_query}%'))
        
        memo_tags = query.order_by(MemoTag.id).all()
        
        return render_template('memo_tags/list.html', 
                             memo_tags=memo_tags,
                             search_query=search_query)
    finally:
        db.close()




@bp.route('/memo-tags/new', methods=['GET'])
@login_required
def memo_tag_new():
    """メモタグ新規作成ページ"""
    return render_template('memo_tags/form.html', memo_tag=None)




@bp.route('/memo-tags/create', methods=['POST'])
@login_required
def memo_tag_create():
    """メモタグ作成"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('メモタグ名を入力してください', 'error')
            return redirect(url_for('memo_tag_new'))
        
        existing = db.query(MemoTag).filter(
            MemoTag.organization_id == organization_id,
            MemoTag.name == name
        ).first()
        if existing:
            flash(f'メモタグ「{name}」は既に登録されています', 'error')
            return redirect(url_for('memo_tag_new'))
        
        memo_tag = MemoTag(
            organization_id=organization_id,
            name=name
        )
        db.add(memo_tag)
        db.commit()
        
        flash(f'メモタグ「{name}」を作成しました', 'success')
        return redirect(url_for('memo_tags_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('memo_tag_new'))
    finally:
        db.close()




@bp.route('/memo-tags/<int:memo_tag_id>/edit', methods=['GET'])
@login_required
def memo_tag_edit(memo_tag_id):
    """メモタグ編集ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        memo_tag = db.query(MemoTag).filter(
            MemoTag.id == memo_tag_id,
            MemoTag.organization_id == organization_id
        ).first()
        if not memo_tag:
            flash('メモタグが見つかりません', 'error')
            return redirect(url_for('memo_tags_list'))
        
        return render_template('memo_tags/form.html', memo_tag=memo_tag)
    finally:
        db.close()




@bp.route('/memo-tags/<int:memo_tag_id>/update', methods=['POST'])
@login_required
def memo_tag_update(memo_tag_id):
    """メモタグ更新"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        memo_tag = db.query(MemoTag).filter(
            MemoTag.id == memo_tag_id,
            MemoTag.organization_id == organization_id
        ).first()
        if not memo_tag:
            flash('メモタグが見つかりません', 'error')
            return redirect(url_for('memo_tags_list'))
        
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('メモタグ名を入力してください', 'error')
            return redirect(url_for('memo_tag_edit', memo_tag_id=memo_tag_id))
        
        existing = db.query(MemoTag).filter(
            MemoTag.organization_id == organization_id,
            MemoTag.name == name,
            MemoTag.id != memo_tag_id
        ).first()
        if existing:
            flash(f'メモタグ「{name}」は既に登録されています', 'error')
            return redirect(url_for('memo_tag_edit', memo_tag_id=memo_tag_id))
        
        memo_tag.name = name
        db.commit()
        
        flash(f'メモタグ「{name}」を更新しました', 'success')
        return redirect(url_for('memo_tags_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('memo_tag_edit', memo_tag_id=memo_tag_id))
    finally:
        db.close()




@bp.route('/api/memo-tags/<int:memo_tag_id>/delete', methods=['POST'])
@login_required
def memo_tag_delete(memo_tag_id):
    """メモタグ削除"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        memo_tag = db.query(MemoTag).filter(
            MemoTag.id == memo_tag_id,
            MemoTag.organization_id == organization_id
        ).first()
        if not memo_tag:
            return jsonify({'success': False, 'message': 'メモタグが見つかりません'}), 404
        
        name = memo_tag.name
        db.delete(memo_tag)
        db.commit()
        
        return jsonify({'success': True, 'message': f'メモタグ「{name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


# ========== 会計期間管理 ==========

# 会計期間一覧


@bp.route('/api/memo-tags/all', methods=['GET'])
@login_required
def get_all_memo_tags():
    db = SessionLocal()
    try:
        memo_tags = db.query(MemoTag).filter(
            MemoTag.organization_id == session['organization_id']
        ).order_by(MemoTag.name.asc()).all()
        
        memo_tags_list = [{'id': m.id, 'name': m.name} for m in memo_tags]
        return jsonify({'success': True, 'memo_tags': memo_tags_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# ========== 事業所設定画面 ==========

