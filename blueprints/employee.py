# -*- coding: utf-8 -*-
"""
従業員マイページ（SQLAlchemy版）
"""

from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import SessionLocal
from app.models_login import TJugyoin, TTenant, TTenpo, TJugyoinTenpo
from sqlalchemy import func, and_, or_
from app.utils.decorators import ROLES
from app.utils.decorators import require_roles

bp = Blueprint('employee', __name__, url_prefix='/employee')


@bp.route('/dashboard')
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"])
def dashboard():
    """従業員ダッシュボード"""
    return render_template('employee_dashboard.html')


@bp.route('/mypage', methods=['GET', 'POST'])
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"])
def mypage():
    """従業員マイページ"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # ユーザー情報を取得
        employee = db.query(TJugyoin).filter(TJugyoin.id == user_id).first()
        
        if not employee:
            flash('ユーザー情報が見つかりません', 'error')
            return redirect(url_for('employee.dashboard'))
        
        user = {
            'id': employee.id,
            'login_id': employee.login_id,
            'name': employee.name,
            'email': employee.email,
            'created_at': employee.created_at,
            'updated_at': employee.updated_at
        }
        
        # テナント名を取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        tenant_name = tenant_obj.名称 if tenant_obj else '不明'
        
        # 所属店舗を取得
        store_relations = db.query(TJugyoinTenpo).filter(
            TJugyoinTenpo.employee_id == user_id
        ).all()
        
        stores = []
        store_list = []
        for rel in store_relations:
            store = db.query(TTenpo).filter(TTenpo.id == rel.store_id).first()
            if store:
                stores.append(store.名称)
                store_list.append({'id': store.id, 'name': store.名称})
        
        # POSTリクエスト（プロフィール編集またはパスワード変更）
        if request.method == 'POST':
            action = request.form.get('action', '')
            
            if action == 'update_profile':
                # プロフィール編集
                login_id = request.form.get('login_id', '').strip()
                name = request.form.get('name', '').strip()
                email = request.form.get('email', '').strip()
                
                if not login_id or not name:
                    flash('ログインIDと氏名は必須です', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                # ログインID重複チェック（自分以外）
                existing = db.query(TJugyoin).filter(
                    and_(TJugyoin.login_id == login_id, TJugyoin.id != user_id)
                ).first()
                if existing:
                    flash('このログインIDは既に使用されています', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                # プロフィール更新
                employee.login_id = login_id
                employee.name = name
                employee.email = email
                db.commit()
                
                flash('プロフィールを更新しました', 'success')
                return redirect(url_for('employee.mypage'))
            
            elif action == 'change_password':
                # パスワード変更
                current_password = request.form.get('current_password', '')
                new_password = request.form.get('new_password', '')
                confirm_password = request.form.get('confirm_password', '')
                
                if not current_password or not new_password or not confirm_password:
                    flash('全ての項目を入力してください', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                # 現在のパスワードを確認
                if not employee.password_hash or not check_password_hash(employee.password_hash, current_password):
                    flash('現在のパスワードが正しくありません', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                # 新しいパスワードの確認
                if new_password != confirm_password:
                    flash('新しいパスワードが一致しません', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                if len(new_password) < 8:
                    flash('パスワードは8文字以上にしてください', 'error')
                    return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
                
                # パスワード更新
                employee.password_hash = generate_password_hash(new_password)
                db.commit()
                
                flash('パスワードを変更しました', 'success')
                return redirect(url_for('employee.mypage'))
            
            elif action == 'select_store':
                # 店舗選択
                store_id = request.form.get('store_id', type=int)
                if store_id:
                    # 選択した店舗が自分の所属店舗かチェック
                    relation = db.query(TJugyoinTenpo).filter(
                        and_(
                            TJugyoinTenpo.employee_id == user_id,
                            TJugyoinTenpo.store_id == store_id
                        )
                    ).first()
                    
                    if relation:
                        session['store_id'] = store_id
                        flash('店舗を選択しました', 'success')
                    else:
                        flash('指定された店舗にアクセスする権限がありません', 'error')
                
                return redirect(url_for('employee.mypage'))
        
        return render_template('employee_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list)
    finally:
        db.close()


@bp.route('/profile')
@require_roles(ROLES["EMPLOYEE"], ROLES["SYSTEM_ADMIN"])
def profile():
    """従業員プロフィール表示"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # ユーザー情報を取得
        employee = db.query(TJugyoin).filter(TJugyoin.id == user_id).first()
        
        if not employee:
            flash('ユーザー情報が見つかりません', 'error')
            return redirect(url_for('employee.dashboard'))
        
        user = {
            'id': employee.id,
            'login_id': employee.login_id,
            'name': employee.name,
            'email': employee.email,
            'created_at': employee.created_at,
            'updated_at': employee.updated_at
        }
        
        # テナント名を取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        tenant_name = tenant_obj.名称 if tenant_obj else '不明'
        
        # 所属店舗を取得
        store_relations = db.query(TJugyoinTenpo).filter(
            TJugyoinTenpo.employee_id == user_id
        ).all()
        
        stores = []
        for rel in store_relations:
            store = db.query(TTenpo).filter(TTenpo.id == rel.store_id).first()
            if store:
                stores.append(store.名称)
        
        return render_template('employee_profile.html', user=user, tenant_name=tenant_name, stores=stores)
    finally:
        db.close()
