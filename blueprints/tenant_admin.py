# -*- coding: utf-8 -*-
"""
テナント管理者ダッシュボード（SQLAlchemy版）
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import SessionLocal
from app.models_login import TKanrisha, TJugyoin, TTenant, TTenpo, TKanrishaTenpo, TJugyoinTenpo, TTenantAppSetting, TTenpoAppSetting, TTenantAdminTenant
from sqlalchemy import func, and_, or_
from app.utils.decorators import ROLES
from app.utils.decorators import require_roles

bp = Blueprint('tenant_admin', __name__, url_prefix='/tenant_admin')


def is_tenant_owner():
    """現在のユーザーがテナントオーナーかどうかを判定"""
    user_id = session.get('user_id')
    if not user_id:
        return False
    db = SessionLocal()
    try:
        user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        return user and user.is_owner == 1
    finally:
        db.close()


def can_manage_tenant_admins():
    """現在のユーザーがテナント管理者管理権限を持つかどうかを判定"""
    user_id = session.get('user_id')
    if not user_id:
        return False
    db = SessionLocal()
    try:
        user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        return user and (user.is_owner == 1 or user.can_manage_admins == 1)
    finally:
        db.close()


@bp.route('/')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def dashboard():
    """テナント管理者ダッシュボード"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        tenant_name = tenant.名称 if tenant else None
        
        # AVAILABLE_APPSからテナントレベルのアプリをフィルタリング
        # AVAILABLE_APPSは同じファイル内で定義されているため、インポート不要
        tenant_apps = [app for app in AVAILABLE_APPS if app.get('scope') == 'tenant']
        
        return render_template('tenant_admin_dashboard.html', 
                             tenant_id=tenant_id,
                             tenant_name=tenant_name,
                             tenant_apps=tenant_apps)
    finally:
        db.close()


@bp.route('/mypage', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def mypage():
    """テナント管理者マイページ"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # ユーザー情報を取得
        user_obj = db.query(TKanrisha).filter(
            TKanrisha.id == user_id,
            TKanrisha.role == ROLES["TENANT_ADMIN"]
        ).first()
        
        if not user_obj:
            flash('ユーザー情報が見つかりません', 'error')
            return redirect(url_for('tenant_admin.dashboard'))
        
        user = {
            'id': user_obj.id,
            'login_id': user_obj.login_id,
            'name': user_obj.name,
            'email': user_obj.email or '',
            'can_manage_admins': user_obj.can_manage_admins or False,
            'created_at': user_obj.created_at,
            'updated_at': user_obj.updated_at if hasattr(user_obj, 'updated_at') else None
        }
        
        # テナント名を取得
        tenant_name = '未選択'
        if tenant_id:
            tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
            tenant_name = tenant_obj.名称 if tenant_obj else '不明'
        
        # テナントリストを取得（テナント管理者が管理するテナント）
        tenant_objs = db.query(TTenant).join(
            TKanrisha, TKanrisha.tenant_id == TTenant.id
        ).filter(
            TKanrisha.id == user_id,
            TKanrisha.role == ROLES["TENANT_ADMIN"]
        ).distinct().order_by(TTenant.名称).all()
        tenant_list = [{'id': t.id, 'name': t.名称} for t in tenant_objs]
        
        # 店舗リストを取得（テナント管理者が管理するテナントの店舗）
        store_list = []
        if tenant_list:
            tenant_ids = [t['id'] for t in tenant_list]
            store_objs = db.query(TTenpo).filter(
                TTenpo.tenant_id.in_(tenant_ids)
            ).order_by(TTenpo.名称).all()
            store_list = [{'id': s.id, 'name': s.名称, 'tenant_id': s.tenant_id} for s in store_objs]
        
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
                    return render_template('tenant_mypage.html', user=user, tenant_name=tenant_name, tenant_list=tenant_list, store_list=store_list)
                
                # ログインID重複チェック（自分以外）
                existing = db.query(TKanrisha).filter(
                    TKanrisha.login_id == login_id,
                    TKanrisha.id != user_id
                ).first()
                if existing:
                    flash('このログインIDは既に使用されています', 'error')
                    return render_template('tenant_mypage.html', user=user, tenant_name=tenant_name, tenant_list=tenant_list, store_list=store_list)
                
                # プロフィール更新
                user_obj.login_id = login_id
                user_obj.name = name
                user_obj.email = email
                if hasattr(user_obj, 'updated_at'):
                    user_obj.updated_at = func.now()
                db.commit()
                
                flash('プロフィール情報を更新しました', 'success')
                return redirect(url_for('tenant_admin.mypage'))
            
            elif action == 'change_password':
                # パスワード変更
                current_password = request.form.get('current_password', '').strip()
                new_password = request.form.get('new_password', '').strip()
                new_password_confirm = request.form.get('new_password_confirm', '').strip()
            
                # パスワード一致チェック
                if new_password != new_password_confirm:
                    flash('パスワードが一致しません', 'error')
                    return render_template('tenant_mypage.html', user=user, tenant_name=tenant_name, tenant_list=tenant_list, store_list=store_list)
                
                # 現在のパスワードを確認
                if not check_password_hash(user_obj.password_hash, current_password):
                    flash('現在のパスワードが正しくありません', 'error')
                    return render_template('tenant_mypage.html', user=user, tenant_name=tenant_name, tenant_list=tenant_list, store_list=store_list)
                
                # パスワードを更新
                user_obj.password_hash = generate_password_hash(new_password)
                if hasattr(user_obj, 'updated_at'):
                    user_obj.updated_at = func.now()
                db.commit()
                
                flash('パスワードを変更しました', 'success')
                return redirect(url_for('tenant_admin.mypage'))
        
        return render_template('tenant_mypage.html', user=user, tenant_name=tenant_name, tenant_list=tenant_list, store_list=store_list)
    finally:
        db.close()


# ========================================
# テナント情報管理
# ========================================

@bp.route('/tenant_info')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_info():
    """テナント情報表示（簡略版）"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントIDが取得できません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        if not tenant_obj:
            flash('テナント情報が見つかりません', 'error')
            return redirect(url_for('tenant_admin.dashboard'))
        
        tenant = {
            'id': tenant_obj.id,
            'name': tenant_obj.名称,
            'slug': tenant_obj.slug,
            'active': tenant_obj.有効,
            'created_at': tenant_obj.created_at,
            'updated_at': tenant_obj.updated_at if hasattr(tenant_obj, 'updated_at') else None
        }
        return render_template('tenant_info.html', tenant=tenant)
    finally:
        db.close()


@bp.route('/tenant_detail')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_detail():
    """テナント詳細情報表示"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントIDが取得できません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        if not tenant_obj:
            flash('テナント情報が見つかりません', 'error')
            return redirect(url_for('tenant_admin.dashboard'))
        
        tenant = {
            'id': tenant_obj.id,
            'name': tenant_obj.名称,
            'slug': tenant_obj.slug,
            'postal_code': tenant_obj.郵便番号 or '',
            'address': tenant_obj.住所 or '',
            'phone': tenant_obj.電話番号 or '',
            'email': tenant_obj.email or '',
            'openai_api_key': tenant_obj.openai_api_key or '',
            'active': tenant_obj.有効,
            'created_at': tenant_obj.created_at,
            'updated_at': tenant_obj.updated_at if hasattr(tenant_obj, 'updated_at') else None
        }
        return render_template('tenant_detail.html', tenant=tenant)
    finally:
        db.close()


@bp.route('/tenant_delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])  # テナント削除はシステム管理者のみ
def tenant_delete():
    """テナント削除"""
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('テナントIDが取得できません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        # パスワード検証
        password = request.form.get('password')
        if not password:
            flash('パスワードを入力してください', 'error')
            return redirect(url_for('tenant_admin.tenant_info'))
        
        # 現在のユーザーを取得
        user_id = session.get('user_id')
        current_user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        
        if not current_user or not check_password_hash(current_user.password_hash, password):
            flash('パスワードが正しくありません', 'error')
            return redirect(url_for('tenant_admin.tenant_info'))
        
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        if not tenant_obj:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('tenant_admin.tenant_info'))
        
        # テナントを無効化（物理削除ではなく論理削除）
        tenant_obj.有効 = 0
        db.commit()
        
        flash(f'テナント「{tenant_obj.名称}」を削除しました', 'success')
        
        # セッションをクリアしてログイン画面にリダイレクト
        session.clear()
        return redirect(url_for('auth.login'))
    except Exception as e:
        db.rollback()
        flash(f'削除中にエラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('tenant_admin.tenant_info'))
    finally:
        db.close()


@bp.route('/me/edit', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def me_edit():
    """自テナント情報編集"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            slug = request.form.get('slug', '').strip()
            postal_code = request.form.get('postal_code', '').strip()
            address = request.form.get('address', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip()
            openai_api_key = request.form.get('openai_api_key', '').strip()
            active = int(request.form.get('active', '1'))
            
            if not name or not slug:
                flash('名称とslugは必須です', 'error')
            else:
                # slug重複チェック（自分以外）
                existing = db.query(TTenant).filter(
                    and_(TTenant.slug == slug, TTenant.id != tenant_id)
                ).first()
                if existing:
                    flash(f'slug "{slug}" は既に使用されています', 'error')
                else:
                    tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                    if tenant_obj:
                        tenant_obj.名称 = name
                        tenant_obj.slug = slug
                        tenant_obj.郵便番号 = postal_code if postal_code else None
                        tenant_obj.住所 = address if address else None
                        tenant_obj.電話番号 = phone if phone else None
                        tenant_obj.email = email if email else None
                        tenant_obj.openai_api_key = openai_api_key if openai_api_key else None
                        tenant_obj.有効 = active
                        db.commit()
                        flash('テナント情報を更新しました', 'success')
                        return redirect(url_for('tenant_admin.tenant_info'))
        
        # テナント情報取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        if not tenant_obj:
            flash('テナント情報が見つかりません', 'error')
            return redirect(url_for('tenant_admin.dashboard'))
        
        tenant = {
            'id': tenant_obj.id,
            'name': tenant_obj.名称,
            'slug': tenant_obj.slug,
            'postal_code': tenant_obj.郵便番号 or '',
            'address': tenant_obj.住所 or '',
            'phone': tenant_obj.電話番号 or '',
            'email': tenant_obj.email or '',
            'openai_api_key': tenant_obj.openai_api_key or '',
            'active': tenant_obj.有効,
            'created_at': tenant_obj.created_at
        }
        return render_template('tenant_me_edit.html', tenant=tenant)
    finally:
        db.close()


@bp.route('/portal')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def portal():
    """テナントポータル"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        tenant = None
        if tenant_obj:
            tenant = {'id': tenant_obj.id, '名称': tenant_obj.名称, 'slug': tenant_obj.slug}
        
        # 管理者数を取得
        admin_count = db.query(func.count(TKanrisha.id)).filter(
            and_(TKanrisha.tenant_id == tenant_id, TKanrisha.role == ROLES["ADMIN"])
        ).scalar()
        
        # 従業員数を取得
        employee_count = db.query(func.count(TJugyoin.id)).filter(
            TJugyoin.tenant_id == tenant_id
        ).scalar()
        
        return render_template('tenant_portal.html', 
                             tenant=tenant,
                             admin_count=admin_count,
                             employee_count=employee_count,
                             stores=[])
    finally:
        db.close()


# ========================================
# 店舗管理
# ========================================

@bp.route('/stores')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def stores():
    """店舗一覧"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        stores_list_obj = db.query(TTenpo).filter(
            TTenpo.tenant_id == tenant_id
        ).order_by(TTenpo.id).all()
        
        stores_list = []
        for s in stores_list_obj:
            stores_list.append({
                'id': s.id,
                '名称': s.名称,
                'slug': s.slug,
                'active': s.有効,
                'created_at': s.created_at,
                'updated_at': s.updated_at
            })
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        return render_template('tenant_stores.html', stores=stores_list, tenant=tenant)
    finally:
        db.close()


@bp.route('/stores/new', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_new():
    """店舗新規作成"""
    tenant_id = session.get('tenant_id')
    
    # テナント情報を取得
    db_tenant = SessionLocal()
    try:
        tenant = db_tenant.query(TTenant).filter(TTenant.id == tenant_id).first()
    finally:
        db_tenant.close()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        postal_code = request.form.get('postal_code', '').strip()
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        openai_api_key = request.form.get('openai_api_key', '').strip()
        
        if not name or not slug:
            flash('名称とslugは必須です', 'error')
            return render_template('tenant_store_new.html', tenant=tenant)
        
        db = SessionLocal()
        
        try:
            # slug重複チェック（同一テナント内）
            existing = db.query(TTenpo).filter(
                and_(TTenpo.tenant_id == tenant_id, TTenpo.slug == slug)
            ).first()
            if existing:
                flash(f'slug "{slug}" は既に使用されています', 'error')
                return render_template('tenant_store_new.html', tenant=tenant)
            
            # 店舗作成
            new_store = TTenpo(
                tenant_id=tenant_id,
                名称=name,
                slug=slug,
                郵便番号=postal_code or None,
                住所=address or None,
                電話番号=phone or None,
                email=email or None,
                openai_api_key=openai_api_key or None,
                有効=1
            )
            db.add(new_store)
            db.commit()
            
            flash(f'店舗 "{name}" を作成しました', 'success')
            return redirect(url_for('tenant_admin.stores'))
        finally:
            db.close()
    
    return render_template('tenant_store_new.html', tenant=tenant)


@bp.route('/stores/<int:store_id>')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_detail(store_id):
    """店舗詳細"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        store_obj = db.query(TTenpo).filter(
            and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
        ).first()
        
        if not store_obj:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('tenant_admin.stores'))
        
        store = {
            'id': store_obj.id,
            '名称': store_obj.名称,
            'slug': store_obj.slug,
            '郵便番号': store_obj.郵便番号,
            '住所': store_obj.住所,
            '電話番号': store_obj.電話番号,
            'email': store_obj.email,
            'openai_api_key': store_obj.openai_api_key,
            'active': store_obj.有効,
            '有効': store_obj.有効,
            'created_at': store_obj.created_at,
            'updated_at': store_obj.updated_at
        }
        
        # 店舗管理者数を取得
        admin_count = db.query(func.count(TKanrishaTenpo.id)).filter(
            TKanrishaTenpo.store_id == store_id
        ).scalar()
        
        # 店舗従業員数を取得
        employee_count = db.query(func.count(TJugyoinTenpo.id)).filter(
            TJugyoinTenpo.store_id == store_id
        ).scalar()
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        return render_template('tenant_store_detail.html',
                             store=store,
                             admin_count=admin_count,
                             employee_count=employee_count,
                             tenant=tenant)
    finally:
        db.close()


@bp.route('/stores/<int:store_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_edit(store_id):
    """店舗編集"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            slug = request.form.get('slug', '').strip()
            postal_code = request.form.get('postal_code', '').strip()
            address = request.form.get('address', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip()
            openai_api_key = request.form.get('openai_api_key', '').strip()
            active = int(request.form.get('active', 1))
            
            if not name or not slug:
                flash('名称とslugは必須です', 'error')
            else:
                # slug重複チェック（自分以外）
                existing = db.query(TTenpo).filter(
                    and_(
                        TTenpo.tenant_id == tenant_id,
                        TTenpo.slug == slug,
                        TTenpo.id != store_id
                    )
                ).first()
                if existing:
                    flash(f'slug "{slug}" は既に使用されています', 'error')
                else:
                    store_obj = db.query(TTenpo).filter(
                        and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
                    ).first()
                    if store_obj:
                        store_obj.名称 = name
                        store_obj.slug = slug
                        store_obj.郵便番号 = postal_code or None
                        store_obj.住所 = address or None
                        store_obj.電話番号 = phone or None
                        store_obj.email = email or None
                        store_obj.openai_api_key = openai_api_key or None
                        store_obj.有効 = active
                        db.commit()
                        flash('店舗情報を更新しました', 'success')
                        return redirect(url_for('tenant_admin.stores'))
        
        # 店舗情報取得
        store_obj = db.query(TTenpo).filter(
            and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
        ).first()
        
        if not store_obj:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('tenant_admin.stores'))
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        store = {
            'id': store_obj.id,
            '名称': store_obj.名称,
            'slug': store_obj.slug,
            '郵便番号': store_obj.郵便番号,
            '住所': store_obj.住所,
            '電話番号': store_obj.電話番号,
            'email': store_obj.email,
            'openai_api_key': store_obj.openai_api_key,
            '有効': store_obj.有効,
            'active': store_obj.有効
        }
        
        return render_template('tenant_store_edit.html', tenant=tenant, store=store)
    finally:
        db.close()



@bp.route('/stores/<int:store_id>/delete', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_delete(store_id):
    """店舗削除（カスケード削除）"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # パスワード検証
        password = request.form.get('password')
        if not password:
            flash('パスワードを入力してください', 'error')
            return redirect(url_for('tenant_admin.store_detail', store_id=store_id))
        
        # 現在のユーザーを取得
        user_id = session.get('user_id')
        current_user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        
        if not current_user or not check_password_hash(current_user.password_hash, password):
            flash('パスワードが正しくありません', 'error')
            return redirect(url_for('tenant_admin.store_detail', store_id=store_id))
        
        # 店舗を取得
        store_obj = db.query(TTenpo).filter(
            and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
        ).first()
        
        if not store_obj:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('tenant_admin.stores'))
        
        # トランザクション開始
        try:
            # 1. 店舗に紐づく中間テーブルを削除
            db.query(TKanrishaTenpo).filter(TKanrishaTenpo.store_id == store_id).delete(synchronize_session=False)
            db.query(TJugyoinTenpo).filter(TJugyoinTenpo.store_id == store_id).delete(synchronize_session=False)
            
            # 2. 店舗アプリ設定を削除
            db.query(TTenpoAppSetting).filter(TTenpoAppSetting.store_id == store_id).delete(synchronize_session=False)
            
            # 3. 店舗を削除
            db.delete(store_obj)
            
            # コミット
            db.commit()
            flash('店舗と関連データを削除しました', 'success')
        except Exception as e:
            db.rollback()
            flash(f'店舗削除中にエラーが発生しました: {str(e)}', 'error')
        
        return redirect(url_for('tenant_admin.stores'))
    finally:
        db.close()


# ========================================
# 管理者管理
# ========================================

@bp.route('/tenant_admins')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admins():
    """テナント管理者一覧"""
    tenant_id = session.get('tenant_id')
    print(f"DEBUG: tenant_id = {tenant_id}")
    db = SessionLocal()
    
    try:
        # 中間テーブルを使用してテナント管理者を取得
        relations = db.query(TTenantAdminTenant).filter(
            TTenantAdminTenant.tenant_id == tenant_id
        ).all()
        print(f"DEBUG: relations count = {len(relations)}")
        for rel in relations:
            print(f"DEBUG: relation - admin_id={rel.admin_id}, tenant_id={rel.tenant_id}, is_owner={rel.is_owner}")
        
        admins_data = []
        for rel in relations:
            admin = db.query(TKanrisha).filter(
                and_(
                    TKanrisha.id == rel.admin_id,
                    TKanrisha.role == ROLES["TENANT_ADMIN"]
                )
            ).first()
            
            if admin:
                # 所属テナント情報を取得
                tenant_relations = db.query(TTenantAdminTenant).filter(
                    TTenantAdminTenant.admin_id == admin.id
                ).all()
                
                tenants = []
                for tenant_rel in tenant_relations:
                    tenant_info = db.query(TTenant).filter(TTenant.id == tenant_rel.tenant_id).first()
                    if tenant_info:
                        tenants.append({
                            'id': tenant_info.id,
                            'name': tenant_info.名称,
                            'is_owner': tenant_rel.is_owner
                        })
                
                admins_data.append({
                    'id': admin.id,
                    'login_id': admin.login_id,
                    'name': admin.name,
                    'email': admin.email,
                    'active': admin.active,
                    'can_manage_admins': rel.can_manage_tenant_admins,
                    'is_owner': rel.is_owner,
                    'tenants': tenants,
                    'created_at': admin.created_at,
                    'updated_at': admin.updated_at
                })
        
        # IDでソート
        admins_data.sort(key=lambda x: x['id'])
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        # 現在のユーザーの権限を取得
        admin_id = session.get('user_id')
        current_user = db.query(TKanrisha).filter(TKanrisha.id == admin_id).first()
        is_system_admin = current_user and current_user.role == ROLES["SYSTEM_ADMIN"]
        
        # システム管理者は全権限を持つ
        if is_system_admin:
            is_owner = True
            can_manage_tenant_admins = True
        else:
            current_admin_relation = db.query(TTenantAdminTenant).filter(
                and_(
                    TTenantAdminTenant.admin_id == admin_id,
                    TTenantAdminTenant.tenant_id == tenant_id
                )
            ).first()
            
            is_owner = current_admin_relation.is_owner == 1 if current_admin_relation else False
            can_manage_tenant_admins = current_admin_relation.can_manage_tenant_admins == 1 if current_admin_relation else False
        
        return render_template('tenant_tenant_admins.html', 
                             tenant_admins=admins_data, 
                             tenant=tenant,
                             is_owner=is_owner,
                             can_manage_tenant_admins=can_manage_tenant_admins)
    finally:
        db.close()


@bp.route('/tenant_admins/new', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admin_new():
    """テナント管理者新規作成"""
    tenant_id = session.get('tenant_id')
    admin_id = session.get('user_id')
    
    if not tenant_id:
        flash('テナントIDが取得できません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        # 現在のユーザーのロールを確認
        current_user = db.query(TKanrisha).filter(TKanrisha.id == admin_id).first()
        is_system_admin = current_user and current_user.role == ROLES["SYSTEM_ADMIN"]
        
        # システム管理者以外は権限チェック
        if not is_system_admin:
            # 権限チェック: オーナーまたは管理権限がある場合のみ
            admin_tenant_relation = db.query(TTenantAdminTenant).filter(
                and_(
                    TTenantAdminTenant.admin_id == admin_id,
                    TTenantAdminTenant.tenant_id == tenant_id
                )
            ).first()
            
            if not admin_tenant_relation:
                flash('このテナントへのアクセス権限がありません', 'error')
                return redirect(url_for('tenant_admin.tenant_admins'))
            
            is_owner = admin_tenant_relation.is_owner == 1
            can_manage = admin_tenant_relation.can_manage_tenant_admins == 1
            
            if not (is_owner or can_manage):
                flash('テナント管理者を作成する権限がありません', 'error')
                return redirect(url_for('tenant_admin.tenant_admins'))
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')
            
            # システム管理者の場合は複数テナント選択可能
            if is_system_admin:
                tenant_ids = request.form.getlist('tenant_ids')
                # 選択されていない場合は作成元テナントを追加
                if not tenant_ids:
                    tenant_ids = [str(tenant_id)]
            else:
                # テナント管理者は作成元テナントのみ
                tenant_ids = [str(tenant_id)]
            
            # バリデーション
            if not login_id or not name or not password:
                flash('ログインID、氏名、パスワードは必須です', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                tenants = db.query(TTenant).order_by(TTenant.id).all() if is_system_admin else None
                return render_template('tenant_tenant_admin_new.html', from_tenant_id=tenant_id, tenant=tenant, tenants=tenants, is_system_admin=is_system_admin)
            
            if password != password_confirm:
                flash('パスワードが一致しません', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                tenants = db.query(TTenant).order_by(TTenant.id).all() if is_system_admin else None
                return render_template('tenant_tenant_admin_new.html', from_tenant_id=tenant_id, tenant=tenant, tenants=tenants, is_system_admin=is_system_admin)
            
            if len(password) < 8:
                flash('パスワードは8文字以上にしてください', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                tenants = db.query(TTenant).order_by(TTenant.id).all() if is_system_admin else None
                return render_template('tenant_tenant_admin_new.html', from_tenant_id=tenant_id, tenant=tenant, tenants=tenants, is_system_admin=is_system_admin)
            
            # ログインID重複チェック
            existing = db.query(TKanrisha).filter(TKanrisha.login_id == login_id).first()
            if existing:
                flash(f'ログインID "{login_id}" は既に使用されています', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                tenants = db.query(TTenant).order_by(TTenant.id).all() if is_system_admin else None
                return render_template('tenant_tenant_admin_new.html', from_tenant_id=tenant_id, tenant=tenant, tenants=tenants, is_system_admin=is_system_admin)
            
            # 管理者作成
            hashed_password = generate_password_hash(password)
            new_admin = TKanrisha(
                login_id=login_id,
                name=name,
                email=email,
                password_hash=hashed_password,
                role=ROLES["TENANT_ADMIN"],
                tenant_id=tenant_id,
                active=1,
                is_owner=0,  # is_ownerはTTenantAdminTenantで管理
                can_manage_admins=0  # 店舗管理者用のフィールド
            )
            db.add(new_admin)
            db.flush()  # IDを取得するため
            
            # 選択されたテナントとの関連を作成
            for tid_str in tenant_ids:
                tid = int(tid_str)
                # 各テナントの最初の管理者かチェック
                existing_count = db.query(TTenantAdminTenant).filter(
                    TTenantAdminTenant.tenant_id == tid
                ).count()
                is_first_for_tenant = (existing_count == 0)
                
                new_relation = TTenantAdminTenant(
                    admin_id=new_admin.id,
                    tenant_id=tid,
                    is_owner=1 if is_first_for_tenant else 0,
                    can_manage_tenant_admins=0  # デフォルトは権限なし
                )
                db.add(new_relation)
            db.commit()
            
            flash(f'管理者 "{name}" を作成しました', 'success')
            return redirect(url_for('tenant_admin.tenant_admins'))
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        # システム管理者の場合は全テナントを取得
        tenants = db.query(TTenant).order_by(TTenant.id).all() if is_system_admin else None
        return render_template('tenant_tenant_admin_new.html', from_tenant_id=tenant_id, tenant=tenant, tenants=tenants, is_system_admin=is_system_admin)
    finally:
        db.close()


@bp.route('/tenant_admins/invite', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admin_invite():
    """既存のテナント管理者を招待"""
    tenant_id = session.get('tenant_id')
    admin_id = session.get('user_id')
    
    if not tenant_id:
        flash('テナントIDが取得できません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        # 現在のユーザーのロールを確認
        current_user = db.query(TKanrisha).filter(TKanrisha.id == admin_id).first()
        is_system_admin = current_user and current_user.role == ROLES["SYSTEM_ADMIN"]
        
        # システム管理者以外は権限チェック
        if not is_system_admin:
            # 権限チェック: オーナーまたは管理権限がある場合のみ
            admin_tenant_relation = db.query(TTenantAdminTenant).filter(
                and_(
                    TTenantAdminTenant.admin_id == admin_id,
                    TTenantAdminTenant.tenant_id == tenant_id
                )
            ).first()
            
            if not admin_tenant_relation:
                flash('このテナントへのアクセス権限がありません', 'error')
                return redirect(url_for('tenant_admin.tenant_admins'))
            
            is_owner = admin_tenant_relation.is_owner == 1
            can_manage = admin_tenant_relation.can_manage_tenant_admins == 1
            
            if not (is_owner or can_manage):
                flash('テナント管理者を招待する権限がありません', 'error')
                return redirect(url_for('tenant_admin.tenant_admins'))
        
        # テナント名を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        tenant_name = tenant.名称 if tenant else 'テストテナント'
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            
            # バリデーション
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
                return render_template('tenant_tenant_admin_invite.html', tenant_name=tenant_name, tenant=tenant)
            
            # ログインIDと氏名が一致するテナント管理者を検索
            existing_admin = db.query(TKanrisha).filter(
                and_(
                    TKanrisha.login_id == login_id,
                    TKanrisha.name == name,
                    TKanrisha.role == ROLES["TENANT_ADMIN"]
                )
            ).first()
            
            if not existing_admin:
                flash(f'ログインID「{login_id}」と氏名「{name}」が一致するテナント管理者が見つかりません', 'error')
                return render_template('tenant_tenant_admin_invite.html', tenant_name=tenant_name, tenant=tenant)
            
            # 既にこのテナントに所属しているかチェック
            already_in_tenant = db.query(TTenantAdminTenant).filter(
                and_(
                    TTenantAdminTenant.admin_id == existing_admin.id,
                    TTenantAdminTenant.tenant_id == tenant_id
                )
            ).first()
            
            if already_in_tenant:
                flash(f'「{name}」は既にこのテナントに所属しています', 'error')
                return render_template('tenant_tenant_admin_invite.html', tenant_name=tenant_name, tenant=tenant)
            
            # テナントに管理者を追加
            new_relation = TTenantAdminTenant(
                admin_id=existing_admin.id,
                tenant_id=tenant_id,
                is_owner=0,
                can_manage_tenant_admins=0
            )
            db.add(new_relation)
            db.commit()
            
            flash(f'テナント管理者「{name}」をこのテナントに招待しました', 'success')
            return redirect(url_for('tenant_admin.tenant_admins'))
        
        return render_template('tenant_tenant_admin_invite.html', tenant_name=tenant_name, tenant=tenant)
    finally:
        db.close()


@bp.route('/tenant_admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admin_edit(admin_id):
    """テナント管理者編集"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["TENANT_ADMIN"])
        ).first()
        
        if not admin:
            flash('テナント管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.tenant_admins'))
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            role = request.form.get('role', 'tenant_admin').strip()
            password = request.form.get('password', '').strip()
            # チェックボックスの値を取得（チェックされている場合のみ'1'が送信される）
            active = 1 if request.form.get('active') == '1' else 0
            can_manage_admins = 1 if request.form.get('can_manage_admins') == '1' else 0
            
            # オーナーかどうかを確認
            is_owner = db.query(TTenantAdminTenant).filter(
                and_(TTenantAdminTenant.admin_id == admin_id, TTenantAdminTenant.is_owner == 1)
            ).first() is not None
            
            # オーナーの場合は役割変更を禁止
            if is_owner and role != ROLES["TENANT_ADMIN"]:
                flash('オーナーは役割を変更できません', 'error')
                return redirect(url_for('tenant_admin.tenant_admin_edit', admin_id=admin_id))
            
            # 役割変更の処理
            old_role = admin.role
            new_role = role
            
            # 管理者情報を更新
            admin.login_id = login_id
            admin.name = name
            admin.email = email
            admin.role = new_role
            # オーナーでない場合のみactiveを更新
            if not is_owner:
                admin.active = active
            else:
                # オーナーは常に有効
                admin.active = 1
            
            # TTenantAdminTenantテーブルのcan_manage_tenant_adminsを更新
            if tenant_id:
                tenant_admin_relation = db.query(TTenantAdminTenant).filter(
                    and_(
                        TTenantAdminTenant.admin_id == admin_id,
                        TTenantAdminTenant.tenant_id == tenant_id
                    )
                ).first()
                
                if tenant_admin_relation:
                    if not is_owner:
                        tenant_admin_relation.can_manage_tenant_admins = can_manage_admins
                    else:
                        # オーナーは常に管理権限あり
                        tenant_admin_relation.can_manage_tenant_admins = 1
            
            if password:
                admin.password_hash = generate_password_hash(password)
            
            # 役割変更時の処理
            if old_role != new_role:
                # テナント管理者から店舗管理者に変更
                if old_role == ROLES["TENANT_ADMIN"] and new_role == ROLES["ADMIN"]:
                    # テナント管理者テーブルから削除
                    db.query(TTenantAdminTenant).filter(TTenantAdminTenant.admin_id == admin_id).delete()
                    # 店舗管理者としてテナントの全店舗に追加
                    stores = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).all()
                    for store in stores:
                        new_relation = TKanrishaTenpo(
                            admin_id=admin_id,
                            store_id=store.id,
                            is_owner=0,
                            can_manage_admins=0
                        )
                        db.add(new_relation)
                    flash(f'"{name}"を店舗管理者に変更しました', 'success')
                
                # テナント管理者から従業員に変更
                elif old_role == ROLES["TENANT_ADMIN"] and new_role == ROLES["EMPLOYEE"]:
                    # テナント管理者テーブルから削除
                    db.query(TTenantAdminTenant).filter(TTenantAdminTenant.admin_id == admin_id).delete()
                    # 従業員テーブルに移動（TJugyoinに移動）
                    new_employee = TJugyoin(
                        login_id=admin.login_id,
                        name=admin.name,
                        email=admin.email,
                        password_hash=admin.password_hash,
                        role=ROLES["EMPLOYEE"],
                        tenant_id=tenant_id,
                        active=active
                    )
                    db.add(new_employee)
                    db.flush()
                    # 従業員としてテナントの全店舗に追加
                    stores = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).all()
                    for store in stores:
                        new_relation = TJugyoinTenpo(
                            employee_id=new_employee.id,
                            store_id=store.id
                        )
                        db.add(new_relation)
                    # 元の管理者レコードを削除
                    db.delete(admin)
                    flash(f'"{name}"を従業員に変更しました', 'success')
                else:
                    flash('役割変更はテナント管理者からのみ対応しています', 'error')
            else:
                flash('テナント管理者を更新しました', 'success')
            
            db.commit()
            return redirect(url_for('tenant_admin.tenant_admins'))
        
        # システム管理者の場合はテナント一覧を取得
        tenants = []
        admin_tenant_ids = []
        owner_tenant_ids = {}
        if session.get('role') == 'system_admin':
            tenants = db.query(TTenant).order_by(TTenant.id).all()
            # 中間テーブルから管理しているテナントIDを取得
            relations = db.query(TTenantAdminTenant).filter(
                TTenantAdminTenant.admin_id == admin.id
            ).all()
            admin_tenant_ids = [r.tenant_id for r in relations] if relations else ([admin.tenant_id] if admin.tenant_id else [])
            # オーナー情報を辞書で保持
            for r in relations:
                owner_tenant_ids[r.tenant_id] = (r.is_owner == 1)
        
        # 現在のテナントでのオーナー状態を確認
        is_owner_in_current_tenant = False
        if tenant_id:
            relation = db.query(TTenantAdminTenant).filter(
                and_(
                    TTenantAdminTenant.admin_id == admin.id,
                    TTenantAdminTenant.tenant_id == tenant_id
                )
            ).first()
            if relation:
                is_owner_in_current_tenant = (relation.is_owner == 1)
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        return render_template('tenant_tenant_admin_edit.html', admin=admin, tenants=tenants, admin_tenant_ids=admin_tenant_ids, owner_tenant_ids=owner_tenant_ids, is_owner_in_current_tenant=is_owner_in_current_tenant, tenant=tenant)
    
    finally:
        db.close()


@bp.route('/tenant_admins/<int:admin_id>/delete', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admin_delete(admin_id):
    """テナント管理者削除"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["TENANT_ADMIN"])
        ).first()
        
        if not admin:
            flash('テナント管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.tenant_admins'))
        
        db.delete(admin)
        db.commit()
        flash('テナント管理者を削除しました', 'success')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    finally:
        db.close()


@bp.route('/tenant_admins/<int:admin_id>/toggle_active', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admin_toggle_active(admin_id):
    """テナント管理者の有効/無効切り替え"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["TENANT_ADMIN"])
        ).first()
        
        if admin:
            admin.active = 1 if admin.active == 0 else 0
            db.commit()
            flash(f'テナント管理者を{"有効" if admin.active == 1 else "無効"}にしました', 'success')
        
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    finally:
        db.close()


@bp.route('/tenant_admins/<int:admin_id>/toggle_manage_permission', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admin_toggle_manage_permission(admin_id):
    """テナント管理者の管理権限切り替え"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["TENANT_ADMIN"])
        ).first()
        
        if not admin:
            flash('テナント管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.tenant_admins'))
        
        # TTenantAdminTenantテーブルの関連レコードを取得
        tenant_admin_relation = db.query(TTenantAdminTenant).filter(
            and_(
                TTenantAdminTenant.admin_id == admin_id,
                TTenantAdminTenant.tenant_id == tenant_id
            )
        ).first()
        
        if tenant_admin_relation:
            # オーナーの場合は権限を変更できない
            if tenant_admin_relation.is_owner == 1:
                flash('オーナーの管理権限は変更できません', 'error')
                return redirect(url_for('tenant_admin.tenant_admins'))
            
            # can_manage_tenant_adminsを切り替え
            new_value = 1 if tenant_admin_relation.can_manage_tenant_admins == 0 else 0
            tenant_admin_relation.can_manage_tenant_admins = new_value
            db.commit()
            flash(f'管理権限を{"付与" if new_value == 1 else "剥奪"}しました', 'success')
        else:
            flash('テナント管理者の関連情報が見つかりません', 'error')
        
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    finally:
        db.close()


@bp.route('/tenant_admins/<int:admin_id>/transfer_owner', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_admin_transfer_owner(admin_id):
    """テナント管理者のオーナー権限移譲"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # 移譲先の管理者を取得
        new_owner = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["TENANT_ADMIN"])
        ).first()
        
        if not new_owner:
            flash('テナント管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.tenant_admins'))
        
        # 現在のオーナーを取得
        current_owner_rel = db.query(TTenantAdminTenant).filter(
            and_(
                TTenantAdminTenant.tenant_id == tenant_id,
                TTenantAdminTenant.is_owner == 1
            )
        ).first()
        
        if current_owner_rel:
            # 現在のオーナーを一般管理者に
            current_owner_rel.is_owner = 0
            
            # T_管理者テーブルのis_ownerも更新
            current_owner = db.query(TKanrisha).filter(TKanrisha.id == current_owner_rel.admin_id).first()
            if current_owner:
                current_owner.is_owner = 0
        
        # 新しいオーナーを設定
        new_owner_rel = db.query(TTenantAdminTenant).filter(
            and_(
                TTenantAdminTenant.admin_id == admin_id,
                TTenantAdminTenant.tenant_id == tenant_id
            )
        ).first()
        
        if new_owner_rel:
            new_owner_rel.is_owner = 1
        
        # T_管理者テーブルのis_ownerも更新
        new_owner.is_owner = 1
        # オーナーは常に有効にする
        new_owner.active = 1
        
        db.commit()
        flash(f'{new_owner.name}さんにオーナー権限を移譲しました', 'success')
        return redirect(url_for('tenant_admin.tenant_admins'))
    
    except Exception as e:
        db.rollback()
        flash(f'オーナー権限の移譲に失敗しました: {str(e)}', 'error')
        return redirect(url_for('tenant_admin.tenant_admins'))
    finally:
        db.close()


# ========================================
# 店舗管理者管理
# ========================================

@bp.route('/store_admins')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_admins():
    """店舗管理者一覧（選択された店舗の管理者）"""
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')  # 選択された店舗ID
    db = SessionLocal()
    
    try:
        # 店舗が選択されていない場合はエラー
        if not store_id:
            flash('店舗を選択してください', 'error')
            return redirect(url_for('tenant_admin.dashboard'))
        
        # 中間テーブルを使用して店舗管理者を取得
        admin_relations = db.query(TKanrishaTenpo, TKanrisha).join(
            TKanrisha, TKanrishaTenpo.admin_id == TKanrisha.id
        ).filter(
            and_(
                TKanrishaTenpo.store_id == store_id,
                TKanrisha.role == ROLES["ADMIN"]
            )
        ).order_by(TKanrishaTenpo.is_owner.desc(), TKanrisha.id).all()
        
        admins_data = []
        current_user_id = session.get('user_id')
        
        for rel, admin in admin_relations:
            # 管理者が所属する全店舗を取得（オーナー情報も含む）
            store_rels = db.query(TTenpo, TKanrishaTenpo).join(
                TKanrishaTenpo, TTenpo.id == TKanrishaTenpo.store_id
            ).filter(
                and_(
                    TKanrishaTenpo.admin_id == admin.id,
                    TTenpo.tenant_id == tenant_id
                )
            ).order_by(TTenpo.名称).all()
            
            # 所属店舗の名称とオーナー情報を取得
            stores_with_owner = []
            for store, store_rel in store_rels:
                stores_with_owner.append({
                    'name': store.名称,
                    'is_owner': store_rel.is_owner == 1
                })
            
            admins_data.append({
                'id': admin.id,
                'login_id': admin.login_id,
                'name': admin.name,
                'email': admin.email,
                'active': admin.active,
                'is_owner': rel.is_owner,
                'can_manage_admins': rel.can_manage_admins,
                'created_at': admin.created_at,
                'updated_at': admin.updated_at,
                'stores': stores_with_owner
            })
        
        # 店舗情報を取得
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        return render_template('tenant_store_admins.html', 
                             admins=admins_data, 
                             store=store,
                             tenant=tenant,
                             current_user_id=current_user_id)
    finally:
        db.close()


@bp.route('/store_admins/new', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_admin_new():
    """店舗管理者新規作成（選択された店舗に追加）"""
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    
    if not store_id:
        flash('店舗を選択してください', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    if request.method == 'POST':
        db = SessionLocal()
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        store_ids = request.form.getlist('store_ids')
        
        # 作成元の店舗IDを必ず含める
        if str(store_id) not in store_ids:
            store_ids.append(str(store_id))
        
        # 既存の店舗管理者が存在するかチェック（作成元の店舗）
        existing_admin_count = db.query(TKanrishaTenpo).filter(
            TKanrishaTenpo.store_id == store_id
        ).count()
        
        # 最初の管理者の場合は自動的にオーナーにする
        is_first_admin = (existing_admin_count == 0)
        
        # バリデーション
        if not login_id or not name or not password:
            flash('ログインID、氏名、パスワードは必須です', 'error')
            tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
            store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
            stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
            return render_template('tenant_store_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('tenant_admin.store_admins'))
        
        if not store_ids:
            flash('少なくとも1つの店舗を選択してください', 'error')
            tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
            store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
            stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
            return render_template('tenant_store_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('tenant_admin.store_admins'))
        
        if password != password_confirm:
            flash('パスワードが一致しません', 'error')
            tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
            store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
            stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
            return render_template('tenant_store_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('tenant_admin.store_admins'))
        
        if len(password) < 8:
            flash('パスワードは8文字以上にしてください', 'error')
            tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
            store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
            stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
            return render_template('tenant_store_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('tenant_admin.store_admins'))
        
        try:
            # ログインID重複チェック
            existing = db.query(TKanrisha).filter(TKanrisha.login_id == login_id).first()
            if existing:
                flash(f'ログインID "{login_id}" は既に使用されています', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
                return render_template('tenant_store_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('tenant_admin.store_admins'))
            

            # 管理者作成
            hashed_password = generate_password_hash(password)
            new_admin = TKanrisha(
                login_id=login_id,
                name=name,
                email=email,
                password_hash=hashed_password,
                role=ROLES["ADMIN"],
                tenant_id=tenant_id,
                active=1
            )
            db.add(new_admin)
            db.flush()  # IDを取得するため
            
            # 選択された店舗との関連を作成
            for sid in store_ids:
                sid_int = int(sid)
                # 作成元の店舗かつ最初の管理者の場合はオーナーにする
                is_owner_for_this_store = (sid_int == store_id and is_first_admin)
                can_manage_for_this_store = (sid_int == store_id and is_first_admin)
                admin_store_rel = TKanrishaTenpo(
                    admin_id=new_admin.id,
                    store_id=sid_int,
                    is_owner=1 if is_owner_for_this_store else 0,
                    can_manage_admins=1 if can_manage_for_this_store else 0
                )
                db.add(admin_store_rel)
            db.commit()
            
            flash(f'店舗管理者 "{name}" を作成しました', 'success')
            return redirect(url_for('tenant_admin.store_admins'))
        except Exception as e:
            db.rollback()
            flash(f'エラー: {str(e)}', 'error')
        finally:
            tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
            store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
            stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
            db.close()
            return render_template('tenant_store_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('tenant_admin.store_admins'))
    
    # GETリクエスト
    db = SessionLocal()
    try:
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        stores = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
        return render_template('tenant_store_admin_new.html', tenant=tenant, store=store, stores=stores, from_store_id=store_id, back_url=url_for('tenant_admin.store_admins'))
    finally:
        db.close()


# ========================================
# 従業員管理
# ========================================

@bp.route('/store_admins/invite', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_admin_invite():
    """店舗管理者を追加（同一テナント内の既存管理者を招待）"""
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    if not store_id:
        flash('店舗が選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            
            # バリデーション
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                return render_template('tenant_store_admin_invite.html', tenant=tenant, store=store)
            
            # 店舗がこのテナントに属しているか確認
            store = db.query(TTenpo).filter(
                and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
            ).first()
            
            if not store:
                flash('店舗が見つかりません', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_store_admin_invite.html', tenant=tenant, store=None)
            
            # ログインIDと氏名が完全一致する店舗管理者を検索（同一テナント内）
            admin = db.query(TKanrisha).filter(
                and_(
                    TKanrisha.login_id == login_id,
                    TKanrisha.name == name,
                    TKanrisha.role == ROLES["ADMIN"],
                    TKanrisha.tenant_id == tenant_id
                )
            ).first()
            
            if not admin:
                flash(f'ログインID"{login_id}"と氏名"{name}"が一致する同一テナント内の店舗管理者が見つかりません', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_store_admin_invite.html', tenant=tenant, store=store)
            
            # 既にこの店舗に所属しているか確認
            existing_relation = db.query(TKanrishaTenpo).filter(
                and_(
                    TKanrishaTenpo.admin_id == admin.id,
                    TKanrishaTenpo.store_id == store_id
                )
            ).first()
            
            if existing_relation:
                flash(f'"{admin.name}"は既にこの店舗に所属しています', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_store_admin_invite.html', tenant=tenant, store=store)
            
            # 中間テーブルに追加
            new_relation = TKanrishaTenpo(
                admin_id=admin.id,
                store_id=store_id,
                is_owner=0,  # 追加された管理者はオーナーではない
                can_manage_admins=0  # 管理権限はなし
            )
            db.add(new_relation)
            db.commit()
            
            flash(f'店舗管理者 "{admin.name}" を店舗"{store.名称}"に追加しました', 'success')
            return redirect(url_for('tenant_admin.store_admins'))
        
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        return render_template('tenant_store_admin_invite.html', tenant=tenant, store=store)
    finally:
        db.close()


@bp.route('/employees')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employees():
    """従業員一覧"""
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')  # 選択された店舗ID
    db = SessionLocal()
    
    try:
        # 店舗が選択されている場合はその店舗に所属する従業員のみを表示
        if store_id:
            employee_list = db.query(TJugyoin).join(
                TJugyoinTenpo, TJugyoin.id == TJugyoinTenpo.employee_id
            ).filter(
                and_(
                    TJugyoin.tenant_id == tenant_id,
                    TJugyoinTenpo.store_id == store_id
                )
            ).order_by(TJugyoin.id).all()
        else:
            # 店舗が選択されていない場合は全従業員を表示
            employee_list = db.query(TJugyoin).filter(
                TJugyoin.tenant_id == tenant_id
            ).order_by(TJugyoin.id).all()
        
        employees_data = []
        for e in employee_list:
            # 所属店舗を取得
            store_relations = db.query(TJugyoinTenpo).filter(
                TJugyoinTenpo.employee_id == e.id
            ).all()
            
            stores_list = []
            for rel in store_relations:
                store = db.query(TTenpo).filter(TTenpo.id == rel.store_id).first()
                if store:
                    stores_list.append({'name': store.名称})
            
            employees_data.append({
                'id': e.id,
                'login_id': e.login_id,
                'name': e.name,
                'email': e.email,
                'active': e.active,
                'created_at': e.created_at,
                'updated_at': e.updated_at,
                'stores': stores_list
            })
        
        # 店舗情報を取得
        store = None
        if store_id:
            store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        return render_template('tenant_employees.html', 
                             employees=employees_data,
                             store=store,
                             tenant=tenant)
    finally:
        db.close()


@bp.route('/employees/invite', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_invite():
    """従業員を追加（同一テナント内の既存従業員を招待）"""
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    if not store_id:
        flash('店舗が選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            
            # バリデーション
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
                # 店舗情報を取得
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_invite.html', store=store, tenant=tenant)
            
            # 店舗がこのテナントに属しているか確認
            store = db.query(TTenpo).filter(
                and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
            ).first()
            
            if not store:
                flash('店舗が見つかりません', 'error')
                # 店舗情報を取得
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_invite.html', store=store, tenant=tenant)
            
            # ログインIDと氏名が完全一致する従業員を検索（同一テナント内）
            employee = db.query(TJugyoin).filter(
                and_(
                    TJugyoin.login_id == login_id,
                    TJugyoin.name == name,
                    TJugyoin.role == ROLES["EMPLOYEE"],
                    TJugyoin.tenant_id == tenant_id
                )
            ).first()
            
            if not employee:
                flash(f'ログインID"{login_id}"と氏名"{name}"が一致する同一テナント内の従業員が見つかりません', 'error')
                # 店舗情報を取得
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_invite.html', store=store, tenant=tenant)
            
            # 既にこの店舗に所属しているか確認
            existing_relation = db.query(TJugyoinTenpo).filter(
                and_(
                    TJugyoinTenpo.employee_id == employee.id,
                    TJugyoinTenpo.store_id == store_id
                )
            ).first()
            
            if existing_relation:
                flash(f'"{employee.name}"は既にこの店舗に所属しています', 'error')
                # 店舗情報を取得
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_invite.html', store=store, tenant=tenant)
            
            # 中間テーブルに追加
            new_relation = TJugyoinTenpo(
                employee_id=employee.id,
                store_id=store_id
            )
            db.add(new_relation)
            db.commit()
            
            flash(f'従業員 "{employee.name}" を店舗"{store.名称}"に追加しました', 'success')
            return redirect(url_for('tenant_admin.employees'))
        
        # 店舗情報を取得
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        return render_template('tenant_employee_invite.html',
                             store=store,
                             tenant=tenant)
    finally:
        db.close()


@bp.route('/employees/new', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_new():
    """従業員新規作成"""
    tenant_id = session.get('tenant_id')
    from_store_id = request.args.get('from_store', type=int)  # 作成元の店舗ID
    if not from_store_id:
        from_store_id = session.get('store_id')  # セッションから取得
    db = SessionLocal()
    
    try:
        # 店舗一覧を取得
        stores = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).all()
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')
            store_ids = request.form.getlist('store_ids')
            
            # バリデーション
            if not login_id or not name or not email:
                flash('ログインID、氏名、メールアドレスは必須です', 'error')
                # 店舗情報を取得
                store = None
                if from_store_id:
                    store = db.query(TTenpo).filter(TTenpo.id == from_store_id).first()
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_new.html', stores=stores, from_store_id=from_store_id, store=store, tenant=tenant)
            
            if not store_ids:
                flash('勤務する店舗を少なくとも1つ選択してください', 'error')
                # 店舗情報を取得
                store = None
                if from_store_id:
                    store = db.query(TTenpo).filter(TTenpo.id == from_store_id).first()
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_new.html', stores=stores, from_store_id=from_store_id, store=store, tenant=tenant)
            
            if password and password != password_confirm:
                flash('パスワードが一致しません', 'error')
                # 店舗情報を取得
                store = None
                if from_store_id:
                    store = db.query(TTenpo).filter(TTenpo.id == from_store_id).first()
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_new.html', stores=stores, from_store_id=from_store_id, store=store, tenant=tenant)
            
            if password and len(password) < 8:
                flash('パスワードは8文字以上にしてください', 'error')
                # 店舗情報を取得
                store = None
                if from_store_id:
                    store = db.query(TTenpo).filter(TTenpo.id == from_store_id).first()
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_new.html', stores=stores, from_store_id=from_store_id, store=store, tenant=tenant)
            
            # ログインID重複チェック
            existing = db.query(TJugyoin).filter(TJugyoin.login_id == login_id).first()
            if existing:
                flash(f'ログインID "{login_id}" は既に使用されています', 'error')
                # 店舗情報を取得
                store = None
                if from_store_id:
                    store = db.query(TTenpo).filter(TTenpo.id == from_store_id).first()
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_new.html', stores=stores, from_store_id=from_store_id, store=store, tenant=tenant)
            
            # 従業員作成
            hashed_password = generate_password_hash(password) if password else None
            new_employee = TJugyoin(
                login_id=login_id,
                name=name,
                email=email,
                password_hash=hashed_password,
                role=ROLES["EMPLOYEE"],
                tenant_id=tenant_id,
                active=1
            )
            db.add(new_employee)
            db.flush()  # IDを取得するためにflush
            
            # 中間テーブルに店舗を登録
            for store_id in store_ids:
                relation = TJugyoinTenpo(
                    employee_id=new_employee.id,
                    store_id=int(store_id)
                )
                db.add(relation)
            
            db.commit()
            flash(f'従業員 "{name}" を作成しました', 'success')
            return redirect(url_for('tenant_admin.employees'))
        
        # 店舗情報を取得
        store = None
        if from_store_id:
            store = db.query(TTenpo).filter(TTenpo.id == from_store_id).first()
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        return render_template('tenant_employee_new.html', 
                             stores=stores, 
                             from_store_id=from_store_id,
                             store=store,
                             tenant=tenant)
    finally:
        db.close()


# ========================================
# アプリ管理
# ========================================

# 利用可能なアプリ一覧（現在は空）
# 将来的にアプリを追加する場合は、以下の形式で追加してください：
# {'name': 'app-name', 'display_name': 'アプリ表示名', 'scope': 'store'/'tenant'}
AVAILABLE_APPS = []


@bp.route('/app_management', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def app_management():
    """店舗別アプリ設定（テナント管理者用）"""
    user_id = session.get('user_id')
    user_role = session.get('role')
    db = SessionLocal()
    
    try:
        # セッションからtenant_idを取得
        session_tenant_id = session.get('tenant_id')
        
        # テナント管理者が管理できるテナント一覧を取得
        if user_role == ROLES["SYSTEM_ADMIN"]:
            # システム管理者は全テナントにアクセス可能
            tenants_list = db.query(TTenant).filter(TTenant.有効 == 1).order_by(TTenant.id).all()
            tenants = [{'id': t.id, 'name': t.名称} for t in tenants_list]
        else:
            # テナント管理者は自分が管理するテナントのみ
            tenant_relations = db.query(TTenantAdminTenant).filter(
                TTenantAdminTenant.admin_id == user_id
            ).all()
            
            tenants = []
            for rel in tenant_relations:
                tenant = db.query(TTenant).filter(
                    and_(TTenant.id == rel.tenant_id, TTenant.有効 == 1)
                ).first()
                if tenant:
                    tenants.append({'id': tenant.id, 'name': tenant.名称})
        
        # セッションにtenant_idが設定されている場合は、それを使用
        selected_tenant_id = session_tenant_id
        selected_store_id = None
        stores = []
        store_apps = []
        
        # セッションにtenant_idがある場合は、自動的に店舗一覧を取得
        if selected_tenant_id and request.method == 'GET':
            stores_list = db.query(TTenpo).filter(
                and_(TTenpo.tenant_id == selected_tenant_id, TTenpo.有効 == 1)
            ).order_by(TTenpo.id).all()
            stores = [{'id': s.id, 'name': s.名称} for s in stores_list]
        
        if request.method == 'POST':
            action = request.form.get('action', '')
            
            if action == 'select_tenant':
                # テナント選択
                selected_tenant_id = request.form.get('tenant_id', type=int)
                
                # 権限チェック
                if user_role != ROLES["SYSTEM_ADMIN"]:
                    has_permission = db.query(TTenantAdminTenant).filter(
                        and_(
                            TTenantAdminTenant.admin_id == user_id,
                            TTenantAdminTenant.tenant_id == selected_tenant_id
                        )
                    ).first()
                    
                    if not has_permission:
                        flash('このテナントを管理する権限がありません', 'error')
                        return redirect(url_for('tenant_admin.app_management'))
                
                if selected_tenant_id:
                    # 店舗一覧を取得
                    stores_list = db.query(TTenpo).filter(
                        and_(TTenpo.tenant_id == selected_tenant_id, TTenpo.有効 == 1)
                    ).order_by(TTenpo.id).all()
                    stores = [{'id': s.id, 'name': s.名称} for s in stores_list]
            
            elif action == 'select_store':
                # 店舗選択
                selected_tenant_id = request.form.get('tenant_id', type=int)
                selected_store_id = request.form.get('store_id', type=int)
                
                # 権限チェック
                if user_role != ROLES["SYSTEM_ADMIN"]:
                    has_permission = db.query(TTenantAdminTenant).filter(
                        and_(
                            TTenantAdminTenant.admin_id == user_id,
                            TTenantAdminTenant.tenant_id == selected_tenant_id
                        )
                    ).first()
                    
                    if not has_permission:
                        flash('このテナントを管理する権限がありません', 'error')
                        return redirect(url_for('tenant_admin.app_management'))
                
                if selected_tenant_id:
                    stores_list = db.query(TTenpo).filter(
                        and_(TTenpo.tenant_id == selected_tenant_id, TTenpo.有効 == 1)
                    ).order_by(TTenpo.id).all()
                    stores = [{'id': s.id, 'name': s.名称} for s in stores_list]
                
                if selected_store_id:
                    # 店舗がテナントに属しているか確認
                    store = db.query(TTenpo).filter(TTenpo.id == selected_store_id).first()
                    if not store or store.tenant_id != selected_tenant_id:
                        flash('この店舗を管理する権限がありません', 'error')
                        return redirect(url_for('tenant_admin.app_management'))
                    
                    # 店舗単位のアプリ一覧を取得
                    store_apps_data = {}
                    for app in AVAILABLE_APPS:
                        if app['scope'] == 'store':
                            app_setting = db.query(TTenpoAppSetting).filter(
                                and_(
                                    TTenpoAppSetting.store_id == selected_store_id,
                                    TTenpoAppSetting.app_name == app['name']
                                )
                            ).first()
                            enabled = app_setting.enabled if app_setting else 1  # デフォルトは有効
                            store_apps_data[app['name']] = enabled
                    
                    store_apps = [
                        {
                            'name': app['name'],
                            'display_name': app['display_name'],
                            'enabled': store_apps_data.get(app['name'], 1)
                        }
                        for app in AVAILABLE_APPS if app['scope'] == 'store'
                    ]
            
            elif action == 'update_apps':
                # アプリ設定更新
                selected_tenant_id = request.form.get('tenant_id', type=int)
                selected_store_id = request.form.get('store_id', type=int)
                
                # 権限チェック
                if user_role != ROLES["SYSTEM_ADMIN"]:
                    has_permission = db.query(TTenantAdminTenant).filter(
                        and_(
                            TTenantAdminTenant.admin_id == user_id,
                            TTenantAdminTenant.tenant_id == selected_tenant_id
                        )
                    ).first()
                    
                    if not has_permission:
                        flash('このテナントを管理する権限がありません', 'error')
                        return redirect(url_for('tenant_admin.app_management'))
                
                if selected_tenant_id:
                    stores_list = db.query(TTenpo).filter(
                        and_(TTenpo.tenant_id == selected_tenant_id, TTenpo.有効 == 1)
                    ).order_by(TTenpo.id).all()
                    stores = [{'id': s.id, 'name': s.名称} for s in stores_list]
                
                if selected_store_id:
                    # 店舗がテナントに属しているか確認
                    store = db.query(TTenpo).filter(TTenpo.id == selected_store_id).first()
                    if not store or store.tenant_id != selected_tenant_id:
                        flash('この店舗を管理する権限がありません', 'error')
                        return redirect(url_for('tenant_admin.app_management'))
                    
                    for app in AVAILABLE_APPS:
                        if app['scope'] == 'store':
                            enabled = 1 if request.form.get(f'app_{app["name"]}') == 'on' else 0
                            
                            # UPSERT処理
                            app_setting = db.query(TTenpoAppSetting).filter(
                                and_(
                                    TTenpoAppSetting.store_id == selected_store_id,
                                    TTenpoAppSetting.app_name == app['name']
                                )
                            ).first()
                            
                            if app_setting:
                                # 更新
                                app_setting.enabled = enabled
                            else:
                                # 挿入
                                new_setting = TTenpoAppSetting(
                                    store_id=selected_store_id,
                                    app_name=app['name'],
                                    enabled=enabled
                                )
                                db.add(new_setting)
                    
                    db.commit()
                    flash('店舗のアプリ設定を更新しました', 'success')
                    
                    # 更新後のデータを再取得
                    store_apps_data = {}
                    for app in AVAILABLE_APPS:
                        if app['scope'] == 'store':
                            app_setting = db.query(TTenpoAppSetting).filter(
                                and_(
                                    TTenpoAppSetting.store_id == selected_store_id,
                                    TTenpoAppSetting.app_name == app['name']
                                )
                            ).first()
                            enabled = app_setting.enabled if app_setting else 1
                            store_apps_data[app['name']] = enabled
                    
                    store_apps = [
                        {
                            'name': app['name'],
                            'display_name': app['display_name'],
                            'enabled': store_apps_data.get(app['name'], 1)
                        }
                        for app in AVAILABLE_APPS if app['scope'] == 'store'
                    ]
        
        # セッションにtenant_idがあるかどうかをテンプレートに渡す
        session_has_tenant = session_tenant_id is not None
        
        # 選択されているテナント名を取得
        selected_tenant_name = None
        if selected_tenant_id:
            for tenant in tenants:
                if tenant['id'] == selected_tenant_id:
                    selected_tenant_name = tenant['name']
                    break
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == session_tenant_id).first() if session_tenant_id else None
        
        return render_template('tenant_admin_app_management.html',
                             tenant=tenant,
                             tenants=tenants,
                             stores=stores,
                             selected_tenant_id=selected_tenant_id,
                             selected_store_id=selected_store_id,
                             store_apps=store_apps,
                             session_has_tenant=session_has_tenant,
                             selected_tenant_name=selected_tenant_name)
    finally:
        db.close()


@bp.route('/tenant_apps')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def tenant_apps():
    """テナントアプリ一覧"""
    tenant_id = session.get('tenant_id')
    
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('tenant_admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        if not tenant:
            flash('テナント情報が見つかりません', 'error')
            return redirect(url_for('tenant_admin.dashboard'))
        
        tenant_data = {
            'id': tenant.id,
            '名称': tenant.名称,
            'slug': tenant.slug,
            'created_at': tenant.created_at
        }
        
        # テナントレベルで有効なアプリを取得
        enabled_apps = []
        
        for app in AVAILABLE_APPS:
            if app['scope'] == 'tenant':
                app_setting = db.query(TTenantAppSetting).filter(
                    and_(
                        TTenantAppSetting.tenant_id == tenant_id,
                        TTenantAppSetting.app_id == app['id']
                    )
                ).first()
                enabled = app_setting.enabled if app_setting else 1
                
                if enabled:
                    enabled_apps.append(app)
        
        apps = enabled_apps
        
        # 店舗情報を取得（現在選択中の店舗）
        store_id = session.get('store_id')
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
        
        return render_template('tenant_admin_tenant_apps.html', tenant=tenant, store=store, apps=apps)
    finally:
        db.close()


@bp.route('/store_admins/<int:admin_id>/transfer_owner', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_admin_transfer_owner(admin_id):
    """店舗管理者のオーナー権限移譲"""
    store_id = session.get('store_id')
    db = SessionLocal()
    
    try:
        # 移譲先の管理者を取得
        new_owner = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["ADMIN"])
        ).first()
        
        if not new_owner:
            flash('店舗管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.store_admins'))
        
        # 現在のオーナーを取得
        current_owner_rel = db.query(TKanrishaTenpo).filter(
            and_(
                TKanrishaTenpo.store_id == store_id,
                TKanrishaTenpo.is_owner == 1
            )
        ).first()
        
        if current_owner_rel:
            # 現在のオーナーを一般管理者に
            current_owner_rel.is_owner = 0
        
        # 新しいオーナーを設定
        new_owner_rel = db.query(TKanrishaTenpo).filter(
            and_(
                TKanrishaTenpo.admin_id == admin_id,
                TKanrishaTenpo.store_id == store_id
            )
        ).first()
        
        if new_owner_rel:
            new_owner_rel.is_owner = 1
        
        # オーナーは常に有効にする
        new_owner.active = 1
        
        db.commit()
        flash(f'{new_owner.name}さんにオーナー権限を移譲しました', 'success')
        return redirect(url_for('tenant_admin.store_admins'))
    
    except Exception as e:
        db.rollback()
        flash(f'オーナー権限の移譲に失敗しました: {str(e)}', 'error')
        return redirect(url_for('tenant_admin.store_admins'))
    finally:
        db.close()


@bp.route('/store_admins/<int:admin_id>/toggle_permission', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_admin_toggle_permission(admin_id):
    """店舗管理者の管理権限付与/剝奪"""
    store_id = session.get('store_id')
    db = SessionLocal()
    
    try:
        # 中間テーブルのレコードを取得
        admin_rel = db.query(TKanrishaTenpo).filter(
            and_(
                TKanrishaTenpo.admin_id == admin_id,
                TKanrishaTenpo.store_id == store_id
            )
        ).first()
        
        if not admin_rel:
            flash('店舗管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.store_admins'))
        
        # 権限を切り替え
        admin_rel.can_manage_admins = 1 if admin_rel.can_manage_admins == 0 else 0
        db.commit()
        
        status = '付与' if admin_rel.can_manage_admins == 1 else '剝奪'
        flash(f'管理権限を{status}しました', 'success')
        return redirect(url_for('tenant_admin.store_admins'))
    
    except Exception as e:
        db.rollback()
        flash(f'エラー: {str(e)}', 'error')
        return redirect(url_for('tenant_admin.store_admins'))
    finally:
        db.close()


@bp.route('/store_admins/<int:admin_id>/toggle_active', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_admin_toggle_active(admin_id):
    """店舗管理者の有効/無効切り替え"""
    store_id = session.get('store_id')
    db = SessionLocal()
    
    try:
        # 管理者を取得
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["ADMIN"])
        ).first()
        
        if not admin:
            flash('店舗管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.store_admins'))
        
        # 中間テーブルでオーナーか確認
        admin_rel = db.query(TKanrishaTenpo).filter(
            and_(
                TKanrishaTenpo.admin_id == admin_id,
                TKanrishaTenpo.store_id == store_id
            )
        ).first()
        
        if not admin_rel:
            flash('店舗管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.store_admins'))
        
        # オーナーは無効化できない
        if admin_rel.is_owner == 1:
            flash('オーナーは常に有効です', 'error')
        else:
            admin.active = 1 if admin.active == 0 else 0
            db.commit()
            status = '有効' if admin.active == 1 else '無効'
            flash(f'店舗管理者を{status}にしました', 'success')
        
        return redirect(url_for('tenant_admin.store_admins'))
    
    except Exception as e:
        db.rollback()
        flash(f'エラー: {str(e)}', 'error')
        return redirect(url_for('tenant_admin.store_admins'))
    finally:
        db.close()


@bp.route('/store_admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_admin_edit(admin_id):
    """店舗管理者編集"""
    tenant_id = session.get('tenant_id')
    
    if not can_manage_tenant_admins():
        flash('店舗管理者を編集する権限がありません', 'error')
        return redirect(url_for('tenant_admin.store_admins'))
    
    db = SessionLocal()
    
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.tenant_id == tenant_id, TKanrisha.role == ROLES["ADMIN"])
        ).first()
        
        if not admin:
            flash('管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.store_admins'))
        
        # テナントの全店舗を取得
        stores = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
        
        # 管理者が所属している店舗IDのリストを取得
        admin_store_ids = [rel.store_id for rel in db.query(TKanrishaTenpo).filter(
            TKanrishaTenpo.admin_id == admin_id
        ).all()]
        
        # オーナー店舗のマップを作成（store_id -> is_owner）
        store_owner_map = {}
        for rel in db.query(TKanrishaTenpo).filter(TKanrishaTenpo.admin_id == admin_id).all():
            if rel.is_owner == 1:
                store_owner_map[rel.store_id] = 1
        
        if request.method == 'POST':
            try:
                login_id = request.form.get('login_id', '').strip()
                name = request.form.get('name', '').strip()
                email = request.form.get('email', '').strip()
                role = request.form.get('role', 'admin').strip()
                password = request.form.get('password', '').strip()
                active = 1 if request.form.get('active') else 0
                can_manage_admins = 1 if request.form.get('can_manage_admins') else 0
                store_ids = request.form.getlist('store_ids')
                
                # バリデーション
                if not login_id or not name:
                    flash('ログインIDと氏名は必須です', 'error')
                    tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                    store_id = session.get('store_id')
                    store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
                    return render_template('tenant_admin_edit.html', 
                                         tenant=tenant,
                                         store=store,
                                         admin=admin,
                                         stores=stores,
                                         admin_store_ids=admin_store_ids,
                                         store_owner_map=store_owner_map)
                
                if not store_ids:
                    flash('少なくとも1つの店舗を選択してください', 'error')
                    tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                    store_id = session.get('store_id')
                    store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
                    return render_template('tenant_admin_edit.html', 
                                         tenant=tenant,
                                         store=store,
                                         admin=admin,
                                         stores=stores,
                                         admin_store_ids=admin_store_ids,
                                         store_owner_map=store_owner_map)
                
                # ログインIDの重複チェック
                existing = db.query(TKanrisha).filter(
                    and_(TKanrisha.login_id == login_id, TKanrisha.id != admin_id)
                ).first()
                if existing:
                    flash('このログインIDは既に使用されています', 'error')
                    tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                    store_id = session.get('store_id')
                    store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
                    return render_template('tenant_admin_edit.html', 
                                         tenant=tenant,
                                         store=store,
                                         admin=admin,
                                         stores=stores,
                                         admin_store_ids=admin_store_ids,
                                         store_owner_map=store_owner_map)
                
                # オーナーかどうかを確認
                is_owner = db.query(TKanrishaTenpo).filter(
                    and_(TKanrishaTenpo.admin_id == admin_id, TKanrishaTenpo.is_owner == 1)
                ).first() is not None
                
                # オーナーの場合は役割変更を禁止
                if is_owner and role != ROLES["ADMIN"]:
                    flash('オーナーは役割を変更できません', 'error')
                    tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                    store_id = session.get('store_id')
                    store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
                    return render_template('tenant_admin_edit.html', 
                                         tenant=tenant,
                                         store=store,
                                         admin=admin,
                                         stores=stores,
                                         admin_store_ids=admin_store_ids,
                                         store_owner_map=store_owner_map)
                
                # 役割変更の処理
                old_role = admin.role
                new_role = role
                
                # 管理者情報を更新
                admin.login_id = login_id
                admin.name = name
                admin.email = email
                admin.role = new_role
                admin.active = active
                admin.can_manage_admins = can_manage_admins
                
                if password:
                    admin.password_hash = generate_password_hash(password)
                
                # 役割変更時の処理
                if old_role != new_role:
                    # 店舗管理者からテナント管理者に変更
                    if old_role == ROLES["ADMIN"] and new_role == ROLES["TENANT_ADMIN"]:
                        # 店舗管理者テーブルから削除
                        db.query(TKanrishaTenpo).filter(TKanrishaTenpo.admin_id == admin_id).delete()
                        # テナント管理者としてテナントに追加
                        new_relation = TTenantAdminTenant(
                            admin_id=admin_id,
                            tenant_id=tenant_id,
                            is_owner=0,
                            can_manage_admins=0
                        )
                        db.add(new_relation)
                        flash(f'"{name}"をテナント管理者に変更しました', 'success')
                    
                    # 店舗管理者から従業員に変更
                    elif old_role == ROLES["ADMIN"] and new_role == ROLES["EMPLOYEE"]:
                        # 店舗管理者テーブルから削除
                        db.query(TKanrishaTenpo).filter(TKanrishaTenpo.admin_id == admin_id).delete()
                        # 従業員テーブルに移動（TJugyoinに移動）
                        new_employee = TJugyoin(
                            login_id=admin.login_id,
                            name=admin.name,
                            email=admin.email,
                            password_hash=admin.password_hash,
                            role=ROLES["EMPLOYEE"],
                            tenant_id=tenant_id,
                            active=active
                        )
                        db.add(new_employee)
                        db.flush()
                        # 従業員として店舗に追加
                        for store_id in store_ids:
                            new_relation = TJugyoinTenpo(
                                employee_id=new_employee.id,
                                store_id=int(store_id)
                            )
                            db.add(new_relation)
                        # 元の管理者レコードを削除
                        db.delete(admin)
                        flash(f'"{name}"を従業員に変更しました', 'success')
                    else:
                        flash('役割変更は店舗管理者からのみ対応しています', 'error')
                else:
                    # 役割変更がない場合は店舗所属を更新
                    # 既存の店舗所属情報を取得して保存
                    existing_relations = {}
                    for rel in db.query(TKanrishaTenpo).filter(TKanrishaTenpo.admin_id == admin_id).all():
                        existing_relations[rel.store_id] = {
                            'is_owner': rel.is_owner,
                            'can_manage_admins': rel.can_manage_admins
                        }
                    
                    # 既存の店舗所属を削除
                    db.query(TKanrishaTenpo).filter(TKanrishaTenpo.admin_id == admin_id).delete()
                    
                    # 新しい店舗所属を追加
                    for store_id in store_ids:
                        store_id_int = int(store_id)
                        
                        if store_id_int in existing_relations:
                            # 既存の関係を復元（オーナー権限は保持、管理権限はオーナーなら常に1）
                            is_owner_for_store = existing_relations[store_id_int]['is_owner']
                            can_manage_for_store = 1 if is_owner_for_store == 1 else can_manage_admins
                            new_relation = TKanrishaTenpo(
                                admin_id=admin_id,
                                store_id=store_id_int,
                                is_owner=is_owner_for_store,
                                can_manage_admins=can_manage_for_store
                            )
                        else:
                            # 新しい関係を作成
                            new_relation = TKanrishaTenpo(
                                admin_id=admin_id,
                                store_id=store_id_int,
                                is_owner=0,
                                can_manage_admins=can_manage_admins
                            )
                        db.add(new_relation)
                    
                    flash(f'店舗管理者 "{admin.name}" を更新しました', 'success')
                
                db.commit()
                return redirect(url_for('tenant_admin.store_admins'))
            except Exception as e:
                db.rollback()
                flash(f'更新中にエラーが発生しました: {str(e)}', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                store_id = session.get('store_id')
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
                return render_template('tenant_admin_edit.html', 
                                     tenant=tenant,
                                     store=store,
                                     admin=admin,
                                     stores=stores,
                                     admin_store_ids=admin_store_ids,
                                     store_owner_map=store_owner_map)
        
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        store_id = session.get('store_id')
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
        return render_template('tenant_admin_edit.html', 
                             tenant=tenant,
                             store=store,
                             admin=admin,
                             stores=stores,
                             admin_store_ids=admin_store_ids,
                             store_owner_map=store_owner_map)
    finally:
        db.close()


@bp.route('/store_admins/<int:admin_id>/delete', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_admin_delete(admin_id):
    """店舗管理者削除"""
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')  # 店舗フィルタリング用
    
    db = SessionLocal()
    
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.tenant_id == tenant_id, TKanrisha.role == ROLES["STORE_ADMIN"])
        ).first()
        
        if not admin:
            flash('店舗管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.store_admins'))
        
        # 中間テーブルからオーナーチェック
        owner_relation = db.query(TKanrishaTenpo).filter(
            and_(TKanrishaTenpo.admin_id == admin_id, TKanrishaTenpo.is_owner == 1)
        ).first()
        
        if owner_relation:
            flash('オーナーは削除できません', 'error')
        else:
            # 中間テーブルのレコードを削除
            db.query(TKanrishaTenpo).filter(TKanrishaTenpo.admin_id == admin_id).delete(synchronize_session=False)
            
            # 店舗管理者を削除
            db.delete(admin)
            db.commit()
            flash('店舗管理者を削除しました', 'success')
        
        return redirect(url_for('tenant_admin.store_admins'))
    except Exception as e:
        db.rollback()
        flash(f'削除中にエラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('tenant_admin.store_admins'))
    finally:
        db.close()


@bp.route('/store_admins/<int:admin_id>/toggle_manage_permission', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_admin_toggle_manage_permission(admin_id):
    """テナント管理者管理権限の付与・剥奪"""
    tenant_id = session.get('tenant_id')
    
    if not can_manage_tenant_admins():
        flash('テナント管理者を管理する権限がありません', 'error')
        return redirect(url_for('tenant_admin.admins'))
    
    # 自分自身の権限は変更できない
    if admin_id == session.get('user_id'):
        flash('自分自身の権限は変更できません', 'error')
        return redirect(url_for('tenant_admin.admins'))
    
    db = SessionLocal()
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.tenant_id == tenant_id, TKanrisha.role == ROLES["ADMIN"])
        ).first()
        
        if not admin:
            flash('管理者が見つかりません', 'error')
            return redirect(url_for('tenant_admin.store_admins'))
        
        # オーナーの権限は変更できない
        if admin.is_owner == 1:
            flash('オーナーの権限は変更できません', 'error')
            return redirect(url_for('tenant_admin.admins'))
        
        # 権限を切り替え
        admin.can_manage_admins = 1 if admin.can_manage_admins == 0 else 0
        db.commit()
        
        status = '付与' if admin.can_manage_admins == 1 else '剥奪'
        flash(f'{admin.name} のテナント管理者管理権限を{status}しました', 'success')
        return redirect(url_for('tenant_admin.admins'))
    finally:
        db.close()

@bp.route('/stores/<int:store_id>/select_for_admins')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def select_store_for_admins(store_id):
    """店舗を選択して店舗管理者一覧にリダイレクト"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # 店舗が存在するか確認
        store = db.query(TTenpo).filter(
            and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
        ).first()
        
        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('tenant_admin.stores'))
        
        # セッションに店舗IDを設定
        session['store_id'] = store_id
        return redirect(url_for('tenant_admin.store_admins'))
    finally:
        db.close()

@bp.route('/stores/<int:store_id>/select_for_employees')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def select_store_for_employees(store_id):
    """店舗を選択して従業員一覧にリダイレクト"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # 店舗が存在するか確認
        store = db.query(TTenpo).filter(
            and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
        ).first()
        
        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('tenant_admin.stores'))
        
        # セッションに店舗IDを設定
        session['store_id'] = store_id
        return redirect(url_for('tenant_admin.employees'))
    finally:
        db.close()

@bp.route('/employees/<int:employee_id>/toggle_active', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_toggle_active(employee_id):
    """従業員の有効/無効を切り替える"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        employee = db.query(TJugyoin).filter(
            and_(TJugyoin.id == employee_id, TJugyoin.tenant_id == tenant_id)
        ).first()
        
        if not employee:
            flash('従業員が見つかりません', 'error')
            return redirect(url_for('tenant_admin.employees'))
        
        employee.active = 0 if employee.active else 1
        db.commit()
        
        status = "有効" if employee.active else "無効"
        flash(f'従業員 "{employee.name}" のステータスを "{status}" に切り替えました', 'success')
        return redirect(url_for('tenant_admin.employees'))
    finally:
        db.close()


@bp.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_edit(employee_id):
    """従業員編集"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        employee = db.query(TJugyoin).filter(
            and_(TJugyoin.id == employee_id, TJugyoin.tenant_id == tenant_id)
        ).first()
        
        if not employee:
            flash('従業員が見つかりません', 'error')
            return redirect(url_for('tenant_admin.employees'))
        
        # テナントの全店舗を取得
        stores = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
        
        # 従業員が所属している店舗IDのリストを取得
        employee_store_ids = [rel.store_id for rel in db.query(TJugyoinTenpo).filter(
            TJugyoinTenpo.employee_id == employee_id
        ).all()]
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            role = request.form.get('role', 'employee').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')
            active = 1 if request.form.get('active') == '1' else 0
            store_ids = request.form.getlist('store_ids')
            
            # バリデーション
            if not name or not email:
                flash('氏名、メールアドレスは必須です', 'error')
                # 店舗情報を取得
                store_id = session.get('store_id')
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_edit.html', 
                                     employee=employee,
                                     stores=stores,
                                     employee_store_ids=employee_store_ids,
                                     store=store,
                                     tenant=tenant)
            
            if password and password != password_confirm:
                flash('パスワードが一致しません', 'error')
                # 店舗情報を取得
                store_id = session.get('store_id')
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_edit.html', 
                                     employee=employee,
                                     stores=stores,
                                     employee_store_ids=employee_store_ids,
                                     store=store,
                                     tenant=tenant)
            
            if password and len(password) < 8:
                flash('パスワードは8文字以上にしてください', 'error')
                # 店舗情報を取得
                store_id = session.get('store_id')
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
                # テナント情報を取得
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('tenant_employee_edit.html', 
                                     employee=employee,
                                     stores=stores,
                                     employee_store_ids=employee_store_ids,
                                     store=store,
                                     tenant=tenant)
            
            # 役割変更の処理
            old_role = employee.role
            new_role = role
            
            # 更新
            employee.name = name
            employee.email = email
            employee.role = new_role
            employee.active = active
            if password:
                employee.password_hash = generate_password_hash(password)
            
            # 役割変更時の処理
            if old_role != new_role:
                # 従業員から店舗管理者に変更
                if old_role == ROLES["EMPLOYEE"] and new_role == ROLES["ADMIN"]:
                    # 従業員テーブルから削除
                    db.query(TJugyoinTenpo).filter(TJugyoinTenpo.employee_id == employee_id).delete()
                    # 店舗管理者テーブルに移動（TKanrishaに移動）
                    # 新しいTKanrishaレコードを作成
                    new_admin = TKanrisha(
                        login_id=employee.login_id,
                        name=employee.name,
                        email=employee.email,
                        password_hash=employee.password_hash,
                        role=ROLES["ADMIN"],
                        tenant_id=tenant_id,
                        active=active
                    )
                    db.add(new_admin)
                    db.flush()
                    # 店舗管理者として店舗に追加
                    for store_id in store_ids:
                        new_relation = TKanrishaTenpo(
                            admin_id=new_admin.id,
                            store_id=int(store_id),
                            is_owner=0,
                            can_manage_admins=0
                        )
                        db.add(new_relation)
                    # 元の従業員レコードを削除
                    db.delete(employee)
                    flash(f'"{name}"を店舗管理者に変更しました', 'success')
                
                # 従業員からテナント管理者に変更
                elif old_role == ROLES["EMPLOYEE"] and new_role == ROLES["TENANT_ADMIN"]:
                    # 従業員テーブルから削除
                    db.query(TJugyoinTenpo).filter(TJugyoinTenpo.employee_id == employee_id).delete()
                    # テナント管理者テーブルに移動（TKanrishaに移動）
                    new_admin = TKanrisha(
                        login_id=employee.login_id,
                        name=employee.name,
                        email=employee.email,
                        password_hash=employee.password_hash,
                        role=ROLES["TENANT_ADMIN"],
                        tenant_id=tenant_id,
                        active=active
                    )
                    db.add(new_admin)
                    db.flush()
                    # テナント管理者としてテナントに追加
                    new_relation = TTenantAdminTenant(
                        admin_id=new_admin.id,
                        tenant_id=tenant_id,
                        is_owner=0,
                        can_manage_admins=0
                    )
                    db.add(new_relation)
                    # 元の従業員レコードを削除
                    db.delete(employee)
                    flash(f'"{name}"をテナント管理者に変更しました', 'success')
                else:
                    flash('役割変更は従業員からのみ対応しています', 'error')
            else:
                # 役割変更がない場合は店舗所属を更新
                # 既存の店舗所属を削除
                db.query(TJugyoinTenpo).filter(TJugyoinTenpo.employee_id == employee_id).delete()
                
                # 新しい店舗所属を追加
                for store_id in store_ids:
                    new_relation = TJugyoinTenpo(
                        employee_id=employee_id,
                        store_id=int(store_id)
                    )
                    db.add(new_relation)
                
                flash(f'従業員 "{employee.name}" を更新しました', 'success')
            
            db.commit()
            return redirect(url_for('tenant_admin.employees'))
        
        # 店舗情報を取得（現在選択中の店舗）
        store_id = session.get('store_id')
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        return render_template('tenant_employee_edit.html', 
                             employee=employee,
                             stores=stores,
                             employee_store_ids=employee_store_ids,
                             store=store,
                             tenant=tenant)
    finally:
        db.close()
@bp.route('/employees/<int:employee_id>/delete', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_delete(employee_id):
    """従業員削除"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        employee = db.query(TJugyoin).filter(
            and_(TJugyoin.id == employee_id, TJugyoin.tenant_id == tenant_id)
        ).first()
        
        if not employee:
            flash('従業員が見つかりません', 'error')
            return redirect(url_for('tenant_admin.employees'))
        
        db.delete(employee)
        db.commit()
        
        flash(f'従業員 "{employee.name}" を削除しました', 'success')
        return redirect(url_for('tenant_admin.employees'))
    finally:
        db.close()


@bp.route('/mypage/select_tenant', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def select_tenant_from_mypage():
    """マイページからテナントを選択してダッシュボードへ進む"""
    tenant_id = request.form.get('tenant_id')
    
    if not tenant_id:
        flash('テナントを選択してください', 'error')
        return redirect(url_for('tenant_admin.mypage'))
    
    session['tenant_id'] = int(tenant_id)
    flash('テナントを選択しました', 'success')
    return redirect(url_for('tenant_admin.dashboard'))


@bp.route('/mypage/select_store', methods=['POST'])
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def select_store_from_mypage():
    """マイページから店舗を選択して店舗ダッシュボードへ進む"""
    store_id = request.form.get('store_id')
    
    if not store_id:
        flash('店舗を選択してください', 'error')
        return redirect(url_for('tenant_admin.mypage'))
    
    session['store_id'] = int(store_id)
    flash('店舗を選択しました', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/stores/<int:store_id>/apps')
@require_roles(ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_apps(store_id):
    """店舗レベルのアプリ一覧"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # 店舗情報を取得
        store = db.query(TTenpo).filter(
            and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
        ).first()
        
        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('tenant_admin.stores'))
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        # 店舗レベルで有効なアプリを取得
        enabled_apps = []
        
        for app in AVAILABLE_APPS:
            if app['scope'] == 'store':
                app_setting = db.query(TTenpoAppSetting).filter(
                    and_(
                        TTenpoAppSetting.store_id == store_id,
                        TTenpoAppSetting.app_name == app['name']
                    )
                ).first()
                enabled = app_setting.enabled if app_setting else 1
                
                if enabled:
                    enabled_apps.append(app)
        
        apps = enabled_apps
        
        return render_template('tenant_store_apps.html', tenant=tenant, store=store, apps=apps)
    finally:
        db.close()

# 利用可能なアプリケーション定義
AVAILABLE_APPS = [
    {
        'id': 'accounting',
        'name': '会計システム',
        'description': '会計・経理管理システム',
        'url': '/accounting/',
        'scope': 'tenant'
    }
]
