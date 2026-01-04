"""
project_tags Blueprint
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

bp = Blueprint('project_tags', __name__, url_prefix='')

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


@bp.route('/project-tags', methods=['GET'])
@login_required
def project_tags_list():
    """案件タグ一覧ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '').strip()
        
        query = db.query(ProjectTag).filter(ProjectTag.organization_id == organization_id)
        if search_query:
            query = query.filter(ProjectTag.tag_name.like(f'%{search_query}%'))
        
        project_tags = query.order_by(ProjectTag.id).all()
        
        return render_template('project_tags/list.html', 
                             project_tags=project_tags,
                             search_query=search_query)
    finally:
        db.close()




@bp.route('/project-tags/new', methods=['GET'])
@login_required
def project_tag_new():
    """案件タグ新規作成ページ"""
    return render_template('project_tags/form.html', project_tag=None)




@bp.route('/project-tags/create', methods=['POST'])
@login_required
def project_tag_create():
    """案件タグ作成"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        tag_name = request.form.get('tag_name', '').strip()
        description = request.form.get('description', '').strip()
        is_active = request.form.get('is_active', '1')
        
        if not tag_name:
            flash('案件タグ名を入力してください', 'error')
            return redirect(url_for('project_tag_new'))
        
        existing = db.query(ProjectTag).filter(
            ProjectTag.organization_id == organization_id,
            ProjectTag.tag_name == tag_name
        ).first()
        if existing:
            flash(f'案件タグ「{tag_name}」は既に登録されています', 'error')
            return redirect(url_for('project_tag_new'))
        
        from datetime import datetime
        project_tag = ProjectTag(
            organization_id=organization_id,
            tag_name=tag_name,
            description=description,
            is_active=int(is_active),
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        db.add(project_tag)
        db.commit()
        
        flash(f'案件タグ「{tag_name}」を作成しました', 'success')
        return redirect(url_for('project_tags_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('project_tag_new'))
    finally:
        db.close()




@bp.route('/project-tags/<int:project_tag_id>/edit', methods=['GET'])
@login_required
def project_tag_edit(project_tag_id):
    """案件タグ編集ページ"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        project_tag = db.query(ProjectTag).filter(
            ProjectTag.id == project_tag_id,
            ProjectTag.organization_id == organization_id
        ).first()
        if not project_tag:
            flash('案件タグが見つかりません', 'error')
            return redirect(url_for('project_tags_list'))
        
        return render_template('project_tags/form.html', project_tag=project_tag)
    finally:
        db.close()




@bp.route('/project-tags/<int:project_tag_id>/update', methods=['POST'])
@login_required
def project_tag_update(project_tag_id):
    """案件タグ更新"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        project_tag = db.query(ProjectTag).filter(
            ProjectTag.id == project_tag_id,
            ProjectTag.organization_id == organization_id
        ).first()
        if not project_tag:
            flash('案件タグが見つかりません', 'error')
            return redirect(url_for('project_tags_list'))
        
        tag_name = request.form.get('tag_name', '').strip()
        description = request.form.get('description', '').strip()
        is_active = request.form.get('is_active', '1')
        
        if not tag_name:
            flash('案件タグ名を入力してください', 'error')
            return redirect(url_for('project_tag_edit', project_tag_id=project_tag_id))
        
        existing = db.query(ProjectTag).filter(
            ProjectTag.organization_id == organization_id,
            ProjectTag.tag_name == tag_name,
            ProjectTag.id != project_tag_id
        ).first()
        if existing:
            flash(f'案件タグ「{tag_name}」は既に登録されています', 'error')
            return redirect(url_for('project_tag_edit', project_tag_id=project_tag_id))
        
        from datetime import datetime
        project_tag.tag_name = tag_name
        project_tag.description = description
        project_tag.is_active = int(is_active)
        project_tag.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.commit()
        
        flash(f'案件タグ「{tag_name}」を更新しました', 'success')
        return redirect(url_for('project_tags_list'))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('project_tag_edit', project_tag_id=project_tag_id))
    finally:
        db.close()




@bp.route('/api/project-tags/<int:project_tag_id>/delete', methods=['POST'])
@login_required
def project_tag_delete(project_tag_id):
    """案件タグ削除"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        project_tag = db.query(ProjectTag).filter(
            ProjectTag.id == project_tag_id,
            ProjectTag.organization_id == organization_id
        ).first()
        if not project_tag:
            return jsonify({'success': False, 'message': '案件タグが見つかりません'}), 404
        
        tag_name = project_tag.tag_name
        db.delete(project_tag)
        db.commit()
        
        return jsonify({'success': True, 'message': f'案件タグ「{tag_name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


# ========== メモタグ管理 ==========

# メモタグ一覧


@bp.route('/api/project-tags/all', methods=['GET'])
@login_required
def get_all_project_tags():
    db = SessionLocal()
    try:
        project_tags = db.query(ProjectTag).filter(
            ProjectTag.organization_id == session['organization_id'],
            ProjectTag.is_active == 1
        ).order_by(ProjectTag.tag_name.asc()).all()
        
        project_tags_list = [{'id': p.id, 'name': p.tag_name} for p in project_tags]
        return jsonify({'success': True, 'project_tags': project_tags_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# メモタグ全件取得API (Tom Select用)

