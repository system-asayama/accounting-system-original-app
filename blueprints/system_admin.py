# -*- coding: utf-8 -*-
"""
システム管理者ダッシュボード（SQLAlchemy版）
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import SessionLocal
from app.models_login import TKanrisha, TJugyoin, TTenant, TTenpo, TKanrishaTenpo, TJugyoinTenpo, TTenantAppSetting, TTenpoAppSetting, TTenantAdminTenant
from sqlalchemy import func, and_, or_
from app.utils.decorators import ROLES
from app.utils.decorators import require_roles
from blueprints.tenant_admin import AVAILABLE_APPS
import os
import markdown

bp = Blueprint('system_admin', __name__, url_prefix='/system_admin')


def is_owner():
    """現在のユーザーがオーナーかどうかを判定"""
    user_id = session.get('user_id')
    if not user_id:
        return False
    db = SessionLocal()
    try:
        user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        return user and user.is_owner == 1
    finally:
        db.close()


def can_manage_system_admins():
    """現在のユーザーがシステム管理者管理権限を持つかどうかを判定"""
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
@require_roles(ROLES["SYSTEM_ADMIN"])
def dashboard():
    """システム管理者ダッシュボード"""
    return render_template('system_admin_dashboard.html')


@bp.route('/mypage', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def mypage():
    """システム管理者マイページ"""
    user_id = session.get('user_id')
    db = SessionLocal()
    
    try:
        # ユーザー情報を取得
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == user_id, TKanrisha.role == ROLES["SYSTEM_ADMIN"])
        ).first()
        
        if not admin:
            flash('ユーザー情報が見つかりません', 'error')
            return redirect(url_for('system_admin.dashboard'))
        
        user = {
            'id': admin.id,
            'login_id': admin.login_id,
            'name': admin.name,
            'email': admin.email,
            'is_owner': admin.is_owner,
            'can_manage_admins': admin.can_manage_admins,
            'openai_api_key': admin.openai_api_key if hasattr(admin, 'openai_api_key') else None,
            'role': ROLES["SYSTEM_ADMIN"],
            'created_at': admin.created_at,
            'updated_at': admin.updated_at
        }
        
        # POSTリクエスト（プロフィール編集またはパスワード変更）
        if request.method == 'POST':
            action = request.form.get('action', '')
            
            if action == 'update_profile':
                # プロフィール編集
                login_id = request.form.get('login_id', '').strip()
                name = request.form.get('name', '').strip()
                email = request.form.get('email', '').strip()
                openai_api_key = request.form.get('openai_api_key', '').strip()
                
                if not login_id or not name:
                    flash('ログインIDと氏名は必須です', 'error')
                    # テナント・店舗リストを取得
                    tenant_list = [{'id': t.id, 'name': t.名称} for t in db.query(TTenant).filter(TTenant.有効 == 1).order_by(TTenant.id).all()]
                    store_list = []
                    for s in db.query(TTenpo).filter(TTenpo.有効 == 1).order_by(TTenpo.tenant_id, TTenpo.id).all():
                        tenant = db.query(TTenant).filter(TTenant.id == s.tenant_id).first()
                        store_list.append({
                            'id': s.id,
                            'name': s.名称,
                            'tenant_id': s.tenant_id,
                            'tenant_name': tenant.名称 if tenant else ''
                        })
                    return render_template('sys_mypage.html', user=user, tenant_list=tenant_list, store_list=store_list)
                
                # ログインID重複チェック（自分以外）
                existing = db.query(TKanrisha).filter(
                    and_(TKanrisha.login_id == login_id, TKanrisha.id != user_id)
                ).first()
                
                if existing:
                    flash('このログインIDは既に使用されています', 'error')
                    # テナント・店舗リストを取得
                    tenant_list = [{'id': t.id, 'name': t.名称} for t in db.query(TTenant).filter(TTenant.有効 == 1).order_by(TTenant.id).all()]
                    store_list = []
                    for s in db.query(TTenpo).filter(TTenpo.有効 == 1).order_by(TTenpo.tenant_id, TTenpo.id).all():
                        tenant = db.query(TTenant).filter(TTenant.id == s.tenant_id).first()
                        store_list.append({
                            'id': s.id,
                            'name': s.名称,
                            'tenant_id': s.tenant_id,
                            'tenant_name': tenant.名称 if tenant else ''
                        })
                    return render_template('sys_mypage.html', user=user, tenant_list=tenant_list, store_list=store_list)
                
                # プロフィール更新
                admin.login_id = login_id
                admin.name = name
                admin.email = email
                if hasattr(admin, 'openai_api_key'):
                    admin.openai_api_key = openai_api_key
                db.commit()
                
                flash('プロフィール情報を更新しました', 'success')
                return redirect(url_for('system_admin.mypage'))
            
            elif action == 'change_password':
                # パスワード変更
                current_password = request.form.get('current_password', '').strip()
                new_password = request.form.get('new_password', '').strip()
                new_password_confirm = request.form.get('new_password_confirm', '').strip()
                
                if new_password != new_password_confirm:
                    flash('パスワードが一致しません', 'error')
                    # テナント・店舗リストを取得
                    tenant_list = [{'id': t.id, 'name': t.名称} for t in db.query(TTenant).filter(TTenant.有効 == 1).order_by(TTenant.id).all()]
                    store_list = []
                    for s in db.query(TTenpo).filter(TTenpo.有効 == 1).order_by(TTenpo.tenant_id, TTenpo.id).all():
                        tenant = db.query(TTenant).filter(TTenant.id == s.tenant_id).first()
                        store_list.append({
                            'id': s.id,
                            'name': s.名称,
                            'tenant_id': s.tenant_id,
                            'tenant_name': tenant.名称 if tenant else ''
                        })
                    return render_template('sys_mypage.html', user=user, tenant_list=tenant_list, store_list=store_list)
                
                # 現在のパスワードを確認
                if not check_password_hash(admin.password_hash, current_password):
                    flash('現在のパスワードが正しくありません', 'error')
                    # テナント・店舗リストを取得
                    tenant_list = [{'id': t.id, 'name': t.名称} for t in db.query(TTenant).filter(TTenant.有効 == 1).order_by(TTenant.id).all()]
                    store_list = []
                    for s in db.query(TTenpo).filter(TTenpo.有効 == 1).order_by(TTenpo.tenant_id, TTenpo.id).all():
                        tenant = db.query(TTenant).filter(TTenant.id == s.tenant_id).first()
                        store_list.append({
                            'id': s.id,
                            'name': s.名称,
                            'tenant_id': s.tenant_id,
                            'tenant_name': tenant.名称 if tenant else ''
                        })
                    return render_template('sys_mypage.html', user=user, tenant_list=tenant_list, store_list=store_list)
                
                # パスワード更新
                admin.password_hash = generate_password_hash(new_password)
                db.commit()
                
                flash('パスワードを変更しました', 'success')
                return redirect(url_for('system_admin.mypage'))
        
        # GETリクエスト - テナント・店舗リストを取得
        tenant_list = [{'id': t.id, 'name': t.名称} for t in db.query(TTenant).filter(TTenant.有効 == 1).order_by(TTenant.id).all()]
        store_list = []
        for s in db.query(TTenpo).filter(TTenpo.有効 == 1).order_by(TTenpo.tenant_id, TTenpo.id).all():
            tenant = db.query(TTenant).filter(TTenant.id == s.tenant_id).first()
            store_list.append({
                'id': s.id,
                'name': s.名称,
                'tenant_id': s.tenant_id,
                'tenant_name': tenant.名称 if tenant else ''
            })
        return render_template('sys_mypage.html', user=user, tenant_list=tenant_list, store_list=store_list)
    
    finally:
        db.close()


@bp.route('/settings', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def settings():
    """システム設定"""
    user_id = session.get('user_id')
    db = SessionLocal()
    
    try:
        if request.method == 'POST':
            openai_api_key = request.form.get('openai_api_key', '').strip()
            
            # OpenAI APIキーを更新
            user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
            if user:
                user.openai_api_key = openai_api_key
                db.commit()
                flash('システム設定を更新しました', 'success')
        
        # 現在の設定を取得
        user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        
        settings_data = {
            'openai_api_key': user.openai_api_key if user and user.openai_api_key else ''
        }
        
        return render_template('sys_settings.html', settings=settings_data)
    finally:
        db.close()


@bp.route('/docs')
@require_roles(ROLES["SYSTEM_ADMIN"])
def docs():
    """ドキュメント一覧"""
    docs_list = [
        {
            'title': '移植ガイド',
            'description': 'login-system-appを基盤として新しいビジネスアプリケーションを開発するための詳細な手順書',
            'filename': 'MIGRATION_GUIDE.md',
            'url': 'system_admin.doc_view'
        },
        {
            'title': 'AVAILABLE_APPSの定義方法',
            'description': '新しいビジネスアプリケーションを追加する際のAVAILABLE_APPSの定義方法',
            'filename': 'AVAILABLE_APPS_GUIDE.md',
            'url': 'system_admin.doc_view'
        }
    ]
    return render_template('sys_docs.html', docs=docs_list)


@bp.route('/docs/<filename>')
@require_roles(ROLES["SYSTEM_ADMIN"])
def doc_view(filename):
    """ドキュメント閲覧"""
    # セキュリティ: ファイル名のバリデーション
    allowed_files = ['MIGRATION_GUIDE.md', 'AVAILABLE_APPS_GUIDE.md', 'README.md']
    if filename not in allowed_files:
        flash('指定されたドキュメントは存在しません', 'error')
        return redirect(url_for('system_admin.docs'))
    
    # ドキュメントファイルのパスを取得
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    doc_path = os.path.join(base_dir, 'docs', filename)
    
    # ファイルが存在しない場合
    if not os.path.exists(doc_path):
        flash('ドキュメントファイルが見つかりません', 'error')
        return redirect(url_for('system_admin.docs'))
    
    # Markdownファイルを読み込んでHTMLに変換
    with open(doc_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code', 'codehilite'])
    
    # タイトルを取得（最初の#行）
    title = filename.replace('.md', '')
    for line in md_content.split('\n'):
        if line.startswith('# '):
            title = line.replace('# ', '').strip()
            break
    
    return render_template('sys_doc_view.html', title=title, content=html_content, filename=filename)


@bp.route('/docs/<filename>/download')
@require_roles(ROLES["SYSTEM_ADMIN"])
def doc_download(filename):
    """ドキュメントダウンロード"""
    # セキュリティ: ファイル名のバリデーション
    allowed_files = ['MIGRATION_GUIDE.md', 'AVAILABLE_APPS_GUIDE.md', 'README.md']
    if filename not in allowed_files:
        flash('指定されたドキュメントは存在しません', 'error')
        return redirect(url_for('system_admin.docs'))
    
    # ドキュメントファイルのパスを取得
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    doc_path = os.path.join(base_dir, 'docs', filename)
    
    # ファイルが存在しない場合
    if not os.path.exists(doc_path):
        flash('ドキュメントファイルが見つかりません', 'error')
        return redirect(url_for('system_admin.docs'))
    
    return send_file(doc_path, as_attachment=True, download_name=filename)


# ========================================
# テナント管理
# ========================================

@bp.route('/tenants')
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenants():
    """テナント一覧"""
    db = SessionLocal()
    
    try:
        tenant_list = db.query(TTenant).order_by(TTenant.id).all()
        tenants = []
        for t in tenant_list:
            tenants.append({
                'id': t.id,
                '名称': t.名称,
                'slug': t.slug,
                '有効': t.有効
            })
        return render_template('sys_tenants.html', tenants=tenants)
    finally:
        db.close()


@bp.route('/tenants/<int:tid>')
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_detail(tid):
    """テナント詳細"""
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tid).first()
        
        if not tenant_obj:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        tenant = {
            'id': tenant_obj.id,
            'name': tenant_obj.名称,
            'slug': tenant_obj.slug,
            'postal_code': tenant_obj.郵便番号,
            'address': tenant_obj.住所,
            'phone': tenant_obj.電話番号,
            'email': tenant_obj.email,
            'openai_api_key': tenant_obj.openai_api_key,
            'active': tenant_obj.有効,
            'created_at': tenant_obj.created_at,
            'updated_at': tenant_obj.updated_at
        }
        
        # テナント管理者数を取得
        admin_count = db.query(func.count(TKanrisha.id)).filter(
            and_(TKanrisha.tenant_id == tid, TKanrisha.role == ROLES["TENANT_ADMIN"])
        ).scalar()
        
        return render_template('sys_tenant_detail.html', 
                             tenant=tenant,
                             admin_count=admin_count)
    finally:
        db.close()


@bp.route('/tenants/new', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_new():
    """テナント新規作成"""
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
            return render_template('sys_tenant_new.html', name=name, slug=slug)
        
        db = SessionLocal()
        
        try:
            # slug重複チェック
            existing = db.query(TTenant).filter(TTenant.slug == slug).first()
            if existing:
                flash(f'slug "{slug}" は既に使用されています', 'error')
                return render_template('sys_tenant_new.html', name=name, slug=slug)
            
            # テナント作成
            new_tenant = TTenant(
                名称=name,
                slug=slug,
                郵便番号=postal_code or None,
                住所=address or None,
                電話番号=phone or None,
                email=email or None,
                openai_api_key=openai_api_key or None,
                有効=1
            )
            db.add(new_tenant)
            db.commit()
            
            flash(f'テナント "{name}" を作成しました', 'success')
            return redirect(url_for('system_admin.tenants'))
        finally:
            db.close()
    
    return render_template('sys_tenant_new.html')


@bp.route('/tenants/<int:tid>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_edit(tid):
    """テナント編集"""
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
                existing = db.query(TTenant).filter(
                    and_(TTenant.slug == slug, TTenant.id != tid)
                ).first()
                if existing:
                    flash(f'slug "{slug}" は既に使用されています', 'error')
                else:
                    tenant_obj = db.query(TTenant).filter(TTenant.id == tid).first()
                    if tenant_obj:
                        tenant_obj.名称 = name
                        tenant_obj.slug = slug
                        tenant_obj.郵便番号 = postal_code or None
                        tenant_obj.住所 = address or None
                        tenant_obj.電話番号 = phone or None
                        tenant_obj.email = email or None
                        tenant_obj.openai_api_key = openai_api_key or None
                        tenant_obj.有効 = active
                        db.commit()
                        flash('テナント情報を更新しました', 'success')
                        return redirect(url_for('system_admin.tenants'))
        
        # テナント情報取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tid).first()
        
        if not tenant_obj:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        tenant = {
            'id': tenant_obj.id,
            '名称': tenant_obj.名称,
            'slug': tenant_obj.slug,
            '郵便番号': tenant_obj.郵便番号,
            '住所': tenant_obj.住所,
            '電話番号': tenant_obj.電話番号,
            'email': tenant_obj.email,
            'openai_api_key': tenant_obj.openai_api_key,
            '有効': tenant_obj.有効
        }
        
        return render_template('sys_tenant_edit.html', tenant=tenant)
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_delete(tid):
    """テナント削除（カスケード削除）"""
    db = SessionLocal()
    
    try:
        # パスワード検証
        password = request.form.get('password')
        if not password:
            flash('パスワードを入力してください', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        # 現在のユーザーを取得
        user_id = session.get('user_id')
        current_user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        
        if not current_user or not check_password_hash(current_user.password_hash, password):
            flash('パスワードが正しくありません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        # テナントを取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tid).first()
        
        if not tenant_obj:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        # トランザクション開始
        try:
            # 1. テナントに紐づく店舗を取得
            stores = db.query(TTenpo).filter(TTenpo.tenant_id == tid).all()
            store_ids = [store.id for store in stores]
            
            # 2. 店舗に紐づく中間テーブルを削除
            if store_ids:
                db.query(TKanrishaTenpo).filter(TKanrishaTenpo.store_id.in_(store_ids)).delete(synchronize_session=False)
                db.query(TJugyoinTenpo).filter(TJugyoinTenpo.store_id.in_(store_ids)).delete(synchronize_session=False)
                db.query(TTenpoAppSetting).filter(TTenpoAppSetting.store_id.in_(store_ids)).delete(synchronize_session=False)
            
            # 3. 店舗を削除
            db.query(TTenpo).filter(TTenpo.tenant_id == tid).delete(synchronize_session=False)
            
            # 4. テナント管理者の中間テーブルを削除
            db.query(TTenantAdminTenant).filter(TTenantAdminTenant.tenant_id == tid).delete(synchronize_session=False)
            
            # 5. テナントに紐づく管理者を削除（テナント管理者のみ）
            db.query(TKanrisha).filter(
                and_(TKanrisha.tenant_id == tid, TKanrisha.role == ROLES["TENANT_ADMIN"])
            ).delete(synchronize_session=False)
            
            # 6. テナントに紐づく従業員を削除
            db.query(TJugyoin).filter(TJugyoin.tenant_id == tid).delete(synchronize_session=False)
            
            # 7. テナントアプリ設定を削除
            db.query(TTenantAppSetting).filter(TTenantAppSetting.tenant_id == tid).delete(synchronize_session=False)
            
            # 8. テナントを削除
            db.delete(tenant_obj)
            
            # コミット
            db.commit()
            flash('テナントと関連データを削除しました', 'success')
        except Exception as e:
            db.rollback()
            flash(f'テナント削除中にエラーが発生しました: {str(e)}', 'error')
        
        return redirect(url_for('system_admin.tenants'))
    finally:
        db.close()


# ========================================
# テナント管理者管理
# ========================================

@bp.route('/tenants/<int:tid>/admins')
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admins(tid):
    """テナント管理者一覧"""
    db = SessionLocal()
    
    try:
        # テナント情報取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tid).first()
        
        if not tenant_obj:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        tenant = {
            'id': tenant_obj.id,
            '名称': tenant_obj.名称,
            'slug': tenant_obj.slug
        }
        
        # テナント管理者一覧取得（中間テーブルから）
        relations = db.query(TTenantAdminTenant).filter(
            TTenantAdminTenant.tenant_id == tid
        ).all()
        
        admins = []
        for rel in relations:
            a = db.query(TKanrisha).filter(
                and_(TKanrisha.id == rel.admin_id, TKanrisha.role == ROLES["TENANT_ADMIN"])
            ).first()
            if a:
                # 所属テナント情報を取得
                tenant_relations = db.query(TTenantAdminTenant).filter(
                    TTenantAdminTenant.admin_id == a.id
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
                
                admins.append({
                    'id': a.id,
                    'login_id': a.login_id,
                    'name': a.name,
                    'email': a.email,
                    'active': a.active,
                    'is_owner': rel.is_owner,  # 中間テーブルのis_ownerを使用
                    'can_manage_admins': a.can_manage_admins,
                    'tenants': tenants,
                    'created_at': a.created_at,
                    'updated_at': a.updated_at
                })
        
        return render_template('sys_tenant_admins.html', tenant=tenant, admins=admins)
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/admins/new', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_new(tid):
    """テナント管理者新規作成"""
    db = SessionLocal()
    
    try:
        # テナント情報取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tid).first()
        
        if not tenant_obj:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        tenant = {
            'id': tenant_obj.id,
            '名称': tenant_obj.名称,
            'slug': tenant_obj.slug
        }
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')
            # 新規作成時は常に有効
            active = 1
            tenant_ids = request.form.getlist('tenant_ids')
            
            # 作成元のテナントIDを必ず含める
            if str(tid) not in tenant_ids:
                tenant_ids.append(str(tid))
            
            # バリデーション
            if not login_id or not name or not password:
                flash('ログインID、氏名、パスワードは必須です', 'error')
                tenants_list = db.query(TTenant).order_by(TTenant.id).all()
                return render_template('sys_tenant_admin_new.html', tenant=tenant_obj, tenants=tenants_list, from_tenant_id=tid)
            
            if not tenant_ids:
                flash('少なくとも1つのテナントを選択してください', 'error')
                tenants_list = db.query(TTenant).order_by(TTenant.id).all()
                return render_template('sys_tenant_admin_new.html', tenant=tenant_obj, tenants=tenants_list, from_tenant_id=tid)
            
            if password != password_confirm:
                flash('パスワードが一致しません', 'error')
                tenants_list = db.query(TTenant).order_by(TTenant.id).all()
                return render_template('sys_tenant_admin_new.html', tenant=tenant_obj, tenants=tenants_list, from_tenant_id=tid)
            
            if len(password) < 8:
                flash('パスワードは8文字以上にしてください', 'error')
                tenants_list = db.query(TTenant).order_by(TTenant.id).all()
                return render_template('sys_tenant_admin_new.html', tenant=tenant_obj, tenants=tenants_list, from_tenant_id=tid)
            
            # ログインID重複チェック
            existing = db.query(TKanrisha).filter(TKanrisha.login_id == login_id).first()
            if existing:
                flash(f'ログインID "{login_id}" は既に使用されています', 'error')
                tenants_list = db.query(TTenant).order_by(TTenant.id).all()
                return render_template('sys_tenant_admin_new.html', tenant=tenant_obj, tenants=tenants_list, from_tenant_id=tid)
            
            # このテナントに既存の管理者が存在するかチェック
            existing_admin_count = db.query(TKanrisha).filter(
                and_(
                    TKanrisha.role == ROLES["TENANT_ADMIN"],
                    TKanrisha.tenant_id == tid
                )
            ).count()
            
            # 最初の管理者の場合は自動的にオーナーにする
            is_first_admin = (existing_admin_count == 0)
            
            # テナント管理者作成
            hashed_password = generate_password_hash(password)
            new_admin = TKanrisha(
                login_id=login_id,
                name=name,
                email=email,
                password_hash=hashed_password,
                role=ROLES["TENANT_ADMIN"],
                tenant_id=tid,
                active=active,
                is_owner=1 if is_first_admin else 0,
                can_manage_admins=1
            )
            db.add(new_admin)
            db.flush()  # IDを取得するため
            
            # 選択されたテナントとの関連を作成
            for tenant_id_str in tenant_ids:
                tenant_id_int = int(tenant_id_str)
                # 作成元のテナントかつ最初の管理者の場合はオーナーにする
                is_owner_for_this_tenant = (tenant_id_int == tid and is_first_admin)
                new_relation = TTenantAdminTenant(
                    admin_id=new_admin.id,
                    tenant_id=tenant_id_int,
                    is_owner=1 if is_owner_for_this_tenant else 0
                )
                db.add(new_relation)
            db.commit()
            
            flash(f'テナント管理者 "{name}" を作成しました', 'success')
            return redirect(url_for('system_admin.tenant_admins', tid=tid))
        
        tenants = db.query(TTenant).order_by(TTenant.id).all()
        return render_template('sys_tenant_admin_new.html', tenant=tenant_obj, tenants=tenants, from_tenant_id=tid)
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/admins/<int:admin_id>/toggle', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_toggle(tid, admin_id):
    """テナント管理者の有効/無効切り替え"""
    db = SessionLocal()
    
    try:
        # 複数テナント対応: tenant_idの条件を削除
        admin = db.query(TKanrisha).filter(
            and_(
                TKanrisha.id == admin_id,
                TKanrisha.role == ROLES["TENANT_ADMIN"]
            )
        ).first()
        
        # 中間テーブルでこのテナントに所属しているか確認
        if admin:
            relation_exists = db.query(TTenantAdminTenant).filter(
                and_(
                    TTenantAdminTenant.admin_id == admin_id,
                    TTenantAdminTenant.tenant_id == tid
                )
            ).first()
            if not relation_exists:
                admin = None
        
        if admin:
            # can_manage_adminsを切り替え（権限剥奪）
            admin.can_manage_admins = 0 if admin.can_manage_admins == 1 else 1
            db.commit()
            status = '付与' if admin.can_manage_admins == 1 else '剥奪'
            flash(f'管理権限を{status}しました', 'success')
        else:
            flash('テナント管理者が見つかりません', 'error')
        
        return redirect(url_for('system_admin.tenant_admins', tid=tid))
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/admins/<int:admin_id>/toggle_active', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_toggle_active(tid, admin_id):
    """テナント管理者の有効/無効切り替え"""
    db = SessionLocal()
    
    try:
        # 複数テナント対応: tenant_idの条件を削除
        admin = db.query(TKanrisha).filter(
            and_(
                TKanrisha.id == admin_id,
                TKanrisha.role == ROLES["TENANT_ADMIN"]
            )
        ).first()
        
        # 中間テーブルでこのテナントに所属しているか確認
        if admin:
            relation_exists = db.query(TTenantAdminTenant).filter(
                and_(
                    TTenantAdminTenant.admin_id == admin_id,
                    TTenantAdminTenant.tenant_id == tid
                )
            ).first()
            if not relation_exists:
                admin = None
        
        if admin:
            # activeを切り替え
            admin.active = 1 if admin.active == 0 else 0
            db.commit()
            flash(f'テナント管理者を{"有効" if admin.active == 1 else "無効"}にしました', 'success')
        else:
            flash('テナント管理者が見つかりません', 'error')
        
        return redirect(url_for('system_admin.tenant_admins', tid=tid))
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_edit(tid, admin_id):
    """テナント管理者編集"""
    db = SessionLocal()
    
    try:
        # テナント情報取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tid).first()
        
        if not tenant_obj:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        tenant = {
            'id': tenant_obj.id,
            '名称': tenant_obj.名称,
            'slug': tenant_obj.slug
        }
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            role = request.form.get('role', 'tenant_admin').strip()
            password = request.form.get('password', '').strip()
            active = 1 if request.form.get('active') == '1' else 0
            can_manage = 1 if request.form.get('can_manage_admins') == '1' else 0
            
            # オーナーかどうかを確認
            is_owner = db.query(TTenantAdminTenant).filter(
                and_(TTenantAdminTenant.admin_id == admin_id, TTenantAdminTenant.tenant_id == tid, TTenantAdminTenant.is_owner == 1)
            ).first() is not None
            
            # オーナーの場合は役割変更を禁止
            if is_owner and role != ROLES["TENANT_ADMIN"]:
                flash('オーナーは役割を変更できません', 'error')
                return redirect(url_for('system_admin.tenant_admin_edit', tid=tid, admin_id=admin_id))
            
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
            else:
                # ログインIDの重複チェック
                existing = db.query(TKanrisha).filter(
                    and_(TKanrisha.login_id == login_id, TKanrisha.id != admin_id)
                ).first()
                if existing:
                    flash('このログインIDは既に使用されています', 'error')
                else:
                    # 複数テナント対応: tenant_idの条件を削除
                    admin = db.query(TKanrisha).filter(
                        and_(
                            TKanrisha.id == admin_id,
                            TKanrisha.role == ROLES["TENANT_ADMIN"]
                        )
                    ).first()
                    
                    # 中間テーブルでこのテナントに所属しているか確認
                    if admin:
                        relation_exists = db.query(TTenantAdminTenant).filter(
                            and_(
                                TTenantAdminTenant.admin_id == admin_id,
                                TTenantAdminTenant.tenant_id == tid
                            )
                        ).first()
                        if not relation_exists:
                            admin = None
                    
                    if admin:
                        # 役割変更の処理
                        if role == ROLES["ADMIN"]:
                            # テナント管理者 → 店舗管理者
                            admin.role = ROLES["ADMIN"]
                            # テナント管理者中間テーブルから削除
                            db.query(TTenantAdminTenant).filter(TTenantAdminTenant.admin_id == admin.id).delete()
                            # テナントの全店舗に所属
                            stores = db.query(TTenpo).filter(TTenpo.tenant_id == tid).all()
                            for store in stores:
                                relation = TKanrishaTenpo(kanrisha_id=admin.id, tenpo_id=store.id, is_owner=0, can_manage_admins=0)
                                db.add(relation)
                        elif role == ROLES["EMPLOYEE"]:
                            # テナント管理者 → 従業員
                            # テナント管理者中間テーブルから削除
                            db.query(TTenantAdminTenant).filter(TTenantAdminTenant.admin_id == admin.id).delete()
                            # 管理者テーブルから削除
                            db.delete(admin)
                            # 従業員テーブルに追加
                            employee = TJugyoin(
                                login_id=login_id,
                                name=name,
                                email=email,
                                password_hash=admin.password_hash if not password else generate_password_hash(password),
                                role=ROLES["EMPLOYEE"],
                                tenant_id=tid,
                                active=active
                            )
                            db.add(employee)
                            db.flush()
                            # テナントの全店舗に所属
                            stores = db.query(TTenpo).filter(TTenpo.tenant_id == tid).all()
                            for store in stores:
                                relation = TJugyoinTenpo(jugyoin_id=employee.id, tenpo_id=store.id)
                                db.add(relation)
                            db.commit()
                            flash('テナント管理者を従業員に変更しました', 'success')
                            return redirect(url_for('system_admin.tenant_admins', tid=tid))
                        else:
                            # 役割変更なし
                            admin.login_id = login_id
                            admin.name = name
                            admin.email = email
                            admin.active = active
                            admin.can_manage_admins = can_manage
                            if password:
                                admin.password_hash = generate_password_hash(password)
                        
                        # テナント選択を保存
                        tenant_ids = request.form.getlist('tenant_ids')
                        if tenant_ids:
                            # 既存の中間テーブルデータを削除
                            db.query(TTenantAdminTenant).filter(
                                TTenantAdminTenant.admin_id == admin.id
                            ).delete()
                            
                            # 新しい中間テーブルデータを追加
                            for tenant_id_str in tenant_ids:
                                tenant_id_int = int(tenant_id_str)
                                # 既存のis_ownerを取得（変更しない）
                                existing_relation = db.query(TTenantAdminTenant).filter(
                                    and_(
                                        TTenantAdminTenant.admin_id == admin.id,
                                        TTenantAdminTenant.tenant_id == tenant_id_int
                                    )
                                ).first()
                                owner_flag = existing_relation.is_owner if existing_relation else 0
                                relation = TTenantAdminTenant(
                                    admin_id=admin.id,
                                    tenant_id=tenant_id_int,
                                    is_owner=owner_flag
                                )
                                db.add(relation)
                        
                        db.commit()
                        flash('テナント管理者を更新しました', 'success')
                        return redirect(url_for('system_admin.tenant_admins', tid=tid))
        
        # GETリクエスト時は現在の情報を表示
        # 複数テナント対応: tenant_idの条件を削除
        admin = db.query(TKanrisha).filter(
            and_(
                TKanrisha.id == admin_id,
                TKanrisha.role == ROLES["TENANT_ADMIN"]
            )
        ).first()
        
        # 中間テーブルでこのテナントに所属しているか確認
        if admin:
            relation_exists = db.query(TTenantAdminTenant).filter(
                and_(
                    TTenantAdminTenant.admin_id == admin_id,
                    TTenantAdminTenant.tenant_id == tid
                )
            ).first()
            if not relation_exists:
                admin = None
        
        if not admin:
            flash('テナント管理者が見つかりません', 'error')
            return redirect(url_for('system_admin.tenant_admins', tid=tid))
        
        admin_data = {
            'id': admin.id,
            'login_id': admin.login_id,
            'name': admin.name,
            'email': admin.email,
            'active': admin.active,
            'is_owner': admin.is_owner,
            'can_manage_admins': admin.can_manage_admins
        }
        
        # テナント一覧を取得
        tenants = db.query(TTenant).order_by(TTenant.id).all()
        
        # 中間テーブルから管理しているテナントIDとオーナー情報を取得
        relations = db.query(TTenantAdminTenant).filter(
            TTenantAdminTenant.admin_id == admin.id
        ).all()
        admin_tenant_ids = [r.tenant_id for r in relations] if relations else ([admin.tenant_id] if admin.tenant_id else [])
        # テナントIDごとのis_ownerフラグを辞書で保持
        tenant_owner_map = {r.tenant_id: r.is_owner for r in relations} if relations else {}
        
        return render_template('sys_tenant_admin_edit.html', tenant=tenant, admin=admin_data, tenants=tenants, admin_tenant_ids=admin_tenant_ids, tenant_owner_map=tenant_owner_map)
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/admins/<int:admin_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_delete(tid, admin_id):
    """テナント管理者削除"""
    db = SessionLocal()
    
    try:
        # 複数テナント対応: tenant_idの条件を削除
        admin = db.query(TKanrisha).filter(
            and_(
                TKanrisha.id == admin_id,
                TKanrisha.role == ROLES["TENANT_ADMIN"]
            )
        ).first()
        
        # 中間テーブルでこのテナントに所属しているか確認
        if admin:
            relation = db.query(TTenantAdminTenant).filter(
                and_(
                    TTenantAdminTenant.admin_id == admin_id,
                    TTenantAdminTenant.tenant_id == tid
                )
            ).first()
            
            if relation:
                # オーナーの場合は削除できない
                if relation.is_owner == 1:
                    flash('オーナーは削除できません。オーナー権限を他の管理者に移譲してから削除してください。', 'error')
                else:
                    # 他のテナントにも所属しているか確認
                    other_relations = db.query(TTenantAdminTenant).filter(
                        and_(
                            TTenantAdminTenant.admin_id == admin_id,
                            TTenantAdminTenant.tenant_id != tid
                        )
                    ).count()
                    
                    if other_relations > 0:
                        # 他のテナントにも所属している場合は中間テーブルのみ削除
                        db.delete(relation)
                        db.commit()
                        flash('このテナントから管理者を削除しました', 'success')
                    else:
                        # このテナントのみの場合は管理者も削除
                        db.delete(relation)
                        db.delete(admin)
                        db.commit()
                        flash('テナント管理者を削除しました', 'success')
            else:
                flash('テナント管理者が見つかりません', 'error')
        else:
            flash('テナント管理者が見つかりません', 'error')
        
        return redirect(url_for('system_admin.tenant_admins', tid=tid))
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/admins/<int:admin_id>/transfer_owner', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_transfer_owner(tid, admin_id):
    """テナント管理者のオーナー移譲"""
    db = SessionLocal()
    
    try:
        # 移譲先の管理者を取得
        new_owner = db.query(TKanrisha).filter(
            and_(
                TKanrisha.id == admin_id,
                TKanrisha.role == ROLES["TENANT_ADMIN"]
            )
        ).first()
        
        if not new_owner:
            flash('テナント管理者が見つかりません', 'error')
            return redirect(url_for('system_admin.tenant_admins', tid=tid))
        
        # 中間テーブルでこのテナントに所属しているか確認
        new_owner_relation = db.query(TTenantAdminTenant).filter(
            and_(
                TTenantAdminTenant.admin_id == admin_id,
                TTenantAdminTenant.tenant_id == tid
            )
        ).first()
        
        if not new_owner_relation:
            flash('この管理者はこのテナントに所属していません', 'error')
            return redirect(url_for('system_admin.tenant_admins', tid=tid))
        
        # 現在のオーナーを取得
        current_owner_relation = db.query(TTenantAdminTenant).filter(
            and_(
                TTenantAdminTenant.tenant_id == tid,
                TTenantAdminTenant.is_owner == 1
            )
        ).first()
        
        # 現在のオーナーのis_ownerを0に設定
        if current_owner_relation:
            current_owner_relation.is_owner = 0
        
        # 新しいオーナーのis_ownerを1に設定
        new_owner_relation.is_owner = 1
        
        # T_管理者テーブルのis_ownerも更新（新しいオーナーのみ）
        new_owner.is_owner = 1
        if current_owner_relation:
            current_owner = db.query(TKanrisha).filter(
                TKanrisha.id == current_owner_relation.admin_id
            ).first()
            if current_owner:
                # 他のテナントでもオーナーか確認
                other_owner = db.query(TTenantAdminTenant).filter(
                    and_(
                        TTenantAdminTenant.admin_id == current_owner.id,
                        TTenantAdminTenant.is_owner == 1
                    )
                ).first()
                if not other_owner:
                    current_owner.is_owner = 0
        
        db.commit()
        flash(f'{new_owner.name}さんにオーナー権限を移譲しました', 'success')
        
        return redirect(url_for('system_admin.tenant_admins', tid=tid))
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('system_admin.tenant_admins', tid=tid))
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/admins/invite', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_admin_invite(tid):
    """既存のテナント管理者を招待"""
    db = SessionLocal()
    
    try:
        # テナント情報取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tid).first()
        
        if not tenant_obj:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        tenant = {
            'id': tenant_obj.id,
            '名称': tenant_obj.名称,
            'slug': tenant_obj.slug
        }
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            
            # バリデーション
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
                return render_template('sys_tenant_admin_invite.html', tenant=tenant)
            
            # ログインIDと氏名が完全一致するテナント管理者を検索
            admin = db.query(TKanrisha).filter(
                and_(
                    TKanrisha.login_id == login_id,
                    TKanrisha.name == name,
                    TKanrisha.role == ROLES["TENANT_ADMIN"]
                )
            ).first()
            
            if not admin:
                flash(f'ログインID"{login_id}"と氏名"{name}"が一致するテナント管理者が見つかりません', 'error')
                return render_template('sys_tenant_admin_invite.html', tenant=tenant)
            
            # 既にこのテナントに所属しているか確認
            existing_relation = db.query(TTenantAdminTenant).filter(
                and_(
                    TTenantAdminTenant.admin_id == admin.id,
                    TTenantAdminTenant.tenant_id == tid
                )
            ).first()
            
            if existing_relation:
                flash(f'"{admin.name}"は既にこのテナントに所属しています', 'error')
                return render_template('sys_tenant_admin_invite.html', tenant=tenant)
            
            # 中間テーブルに追加
            new_relation = TTenantAdminTenant(
                admin_id=admin.id,
                tenant_id=tid,
                is_owner=0  # 招待された管理者はオーナーではない
            )
            db.add(new_relation)
            db.commit()
            
            flash(f'テナント管理者 "{admin.name}" をこのテナントに招待しました', 'success')
            return redirect(url_for('system_admin.tenant_admins', tid=tid))
        
        return render_template('sys_tenant_admin_invite.html', tenant=tenant)
    finally:
        db.close()


# ========================================
# システム管理者管理
# ========================================

@bp.route('/system_admins')
@require_roles(ROLES["SYSTEM_ADMIN"])
def system_admins():
    """システム管理者一覧"""
    db = SessionLocal()
    
    try:
        admin_list = db.query(TKanrisha).filter(
            TKanrisha.role == ROLES["SYSTEM_ADMIN"]
        ).order_by(
            TKanrisha.is_owner.desc(),
            TKanrisha.can_manage_admins.desc(),
            TKanrisha.id
        ).all()
        
        admins = []
        for a in admin_list:
            admins.append({
                'id': a.id,
                'login_id': a.login_id,
                'name': a.name,
                'active': a.active,
                'created_at': a.created_at,
                'updated_at': a.updated_at,
                'is_owner': a.is_owner,
                'can_manage_admins': a.can_manage_admins
            })
        
        return render_template('sys_system_admins.html', 
                             admins=admins,
                             is_owner=is_owner,
                             can_manage_system_admins=can_manage_system_admins)
    finally:
        db.close()


@bp.route('/system_admins/new', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def system_admin_new():
    """システム管理者新規作成（システム管理者管理権限が必要）"""
    # システム管理者管理権限チェック
    if not can_manage_system_admins():
        flash('システム管理者を作成する権限がありません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        
        # バリデーション
        if not login_id or not name or not password:
            flash('全ての項目を入力してください', 'error')
            return render_template('sys_system_admin_new.html')
        
        if password != password_confirm:
            flash('パスワードが一致しません', 'error')
            return render_template('sys_system_admin_new.html')
        
        if len(password) < 8:
            flash('パスワードは8文字以上にしてください', 'error')
            return render_template('sys_system_admin_new.html')
        
        db = SessionLocal()
        
        try:
            # ログインID重複チェック
            existing = db.query(TKanrisha).filter(TKanrisha.login_id == login_id).first()
            if existing:
                flash(f'ログインID "{login_id}" は既に使用されています', 'error')
                return render_template('sys_system_admin_new.html')
            
            # 既存のシステム管理者が存在するかチェック
            existing_admin_count = db.query(TKanrisha).filter(
                TKanrisha.role == ROLES["SYSTEM_ADMIN"]
            ).count()
            
            # 最初の管理者の場合は自動的にオーナーにする
            is_first_admin = (existing_admin_count == 0)
            
            # システム管理者作成
            hashed_password = generate_password_hash(password)
            new_admin = TKanrisha(
                login_id=login_id,
                name=name,
                email=email,
                password_hash=hashed_password,
                role=ROLES["SYSTEM_ADMIN"],
                tenant_id=None,
                active=1,
                is_owner=1 if is_first_admin else 0,
                can_manage_admins=1 if is_first_admin else 0
            )
            db.add(new_admin)
            db.commit()
            
            flash(f'システム管理者 "{name}" を作成しました', 'success')
            return redirect(url_for('system_admin.system_admins'))
        finally:
            db.close()
    
    return render_template('sys_system_admin_new.html')


@bp.route('/system_admins/<int:admin_id>/toggle', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def system_admin_toggle(admin_id):
    """システム管理者の有効/無効切り替え"""
    if not can_manage_system_admins():
        flash('システム管理者を管理する権限がありません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    db = SessionLocal()
    
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["SYSTEM_ADMIN"])
        ).first()
        
        if admin:
            # オーナーは無効化できない
            if admin.is_owner == 1:
                flash('オーナーは無効化できません', 'error')
            else:
                admin.active = 0 if admin.active == 1 else 1
                db.commit()
                flash('ステータスを更新しました', 'success')
        
        return redirect(url_for('system_admin.system_admins'))
    finally:
        db.close()


@bp.route('/system_admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def system_admin_edit(admin_id):
    """システム管理者編集"""
    if not can_manage_system_admins():
        flash('システム管理者を編集する権限がありません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    db = SessionLocal()
    
    try:
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            active = 1 if request.form.get('active') == '1' else 0
            can_manage = 1 if request.form.get('can_manage_admins') == '1' else 0
            
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
            else:
                # ログインIDの重複チェック
                existing = db.query(TKanrisha).filter(
                    and_(TKanrisha.login_id == login_id, TKanrisha.id != admin_id)
                ).first()
                if existing:
                    flash('このログインIDは既に使用されています', 'error')
                else:
                    admin = db.query(TKanrisha).filter(
                        and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["SYSTEM_ADMIN"])
                    ).first()
                    
                    if admin:
                        admin.login_id = login_id
                        admin.name = name
                        admin.email = email
                        admin.active = active
                        # オーナーでない場合のみ管理権限を変更可能
                        if admin.is_owner != 1:
                            admin.can_manage_admins = can_manage
                        if password:
                            admin.password_hash = generate_password_hash(password)
                        db.commit()
                        flash('システム管理者を更新しました', 'success')
                        return redirect(url_for('system_admin.system_admins'))
        
        # GETリクエスト時は現在の情報を表示
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["SYSTEM_ADMIN"])
        ).first()
        
        if not admin:
            flash('システム管理者が見つかりません', 'error')
            return redirect(url_for('system_admin.system_admins'))
        
        admin_data = {
            'id': admin.id,
            'login_id': admin.login_id,
            'name': admin.name,
            'email': admin.email,
            'active': admin.active,
            'is_owner': admin.is_owner,
            'can_manage_admins': admin.can_manage_admins
        }
        
        return render_template('sys_system_admin_edit.html', admin=admin_data)
    finally:
        db.close()


@bp.route('/system_admins/<int:admin_id>/delete', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def system_admin_delete(admin_id):
    """システム管理者削除"""
    if not can_manage_system_admins():
        flash('システム管理者を削除する権限がありません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    db = SessionLocal()
    
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["SYSTEM_ADMIN"])
        ).first()
        
        if admin:
            # オーナーは削除できない
            if admin.is_owner == 1:
                flash('オーナーは削除できません', 'error')
            else:
                db.delete(admin)
                db.commit()
                flash('システム管理者を削除しました', 'success')
        
        return redirect(url_for('system_admin.system_admins'))
    finally:
        db.close()


@bp.route('/system_admins/<int:admin_id>/toggle_manage_permission', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def toggle_manage_permission(admin_id):
    """システム管理者管理権限の付与・剥奪（オーナーのみ）"""
    if not can_manage_system_admins():
        flash('システム管理者を管理する権限がありません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    # 自分自身の権限は変更できない
    if admin_id == session.get('user_id'):
        flash('自分自身の権限は変更できません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    db = SessionLocal()
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["SYSTEM_ADMIN"])
        ).first()
        
        if not admin:
            flash('システム管理者が見つかりません', 'error')
            return redirect(url_for('system_admin.system_admins'))
        
        # オーナーの権限は変更できない
        if admin.is_owner == 1:
            flash('オーナーの権限は変更できません', 'error')
            return redirect(url_for('system_admin.system_admins'))
        
        # 権限を切り替え
        admin.can_manage_admins = 1 if admin.can_manage_admins == 0 else 0
        db.commit()
        
        status = '付与' if admin.can_manage_admins == 1 else '剥奪'
        flash(f'{admin.name} のシステム管理者管理権限を{status}しました', 'success')
        return redirect(url_for('system_admin.system_admins'))
    finally:
        db.close()


@bp.route('/system_admins/<int:admin_id>/toggle_active', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def toggle_active(admin_id):
    """システム管理者の有効/無効切り替え"""
    if not can_manage_system_admins():
        flash('システム管理者を管理する権限がありません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    # 自分自身は無効化できない
    if admin_id == session.get('user_id'):
        flash('自分自身を無効化することはできません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    db = SessionLocal()
    try:
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["SYSTEM_ADMIN"])
        ).first()
        
        if not admin:
            flash('システム管理者が見つかりません', 'error')
            return redirect(url_for('system_admin.system_admins'))
        
        # オーナーは無効化できない
        if admin.is_owner == 1:
            flash('オーナーは無効化できません', 'error')
            return redirect(url_for('system_admin.system_admins'))
        
        # 有効/無効を切り替え
        admin.active = 1 if admin.active == 0 else 0
        db.commit()
        
        status = '有効化' if admin.active == 1 else '無効化'
        flash(f'{admin.name} を{status}しました', 'success')
        return redirect(url_for('system_admin.system_admins'))
    finally:
        db.close()


@bp.route('/system_admins/<int:admin_id>/transfer_ownership', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def transfer_ownership(admin_id):
    """オーナー権限を他のシステム管理者に移譲"""
    # オーナーのみ実行可能
    if session.get('is_owner') != 1:
        flash('オーナーのみがオーナー権限を移譲できます', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    # 自分自身には移譲できない
    if admin_id == session.get('user_id'):
        flash('自分自身にオーナー権限を移譲することはできません', 'error')
        return redirect(url_for('system_admin.system_admins'))
    
    db = SessionLocal()
    try:
        # 移譲先がシステム管理者であることを確認
        admin = db.query(TKanrisha).filter(
            and_(TKanrisha.id == admin_id, TKanrisha.role == ROLES["SYSTEM_ADMIN"])
        ).first()
        
        if not admin:
            flash('移譲先のシステム管理者が見つかりません', 'error')
            return redirect(url_for('system_admin.system_admins'))
        
        new_owner_name = admin.name
        
        # 全てのis_ownerを0にしてから、指定したユーザーを1にする
        db.query(TKanrisha).filter(TKanrisha.role == ROLES["SYSTEM_ADMIN"]).update({TKanrisha.is_owner: 0})
        admin.is_owner = 1
        db.commit()
        
        # セッションのオーナーフラグを更新
        session['is_owner'] = 0
        
        flash(f'オーナー権限を「{new_owner_name}」に移譲しました', 'success')
        return redirect(url_for('system_admin.system_admins'))
    finally:
        db.close()


@bp.route('/app_management', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def app_management():
    """アプリ管理ページ"""
    db = SessionLocal()
    
    try:
        if request.method == 'POST':
            tenant_id = request.form.get('tenant_id')
            app_id = request.form.get('app_id')
            action = request.form.get('action')  # 'enable' or 'disable'
            
            if not tenant_id or not app_id:
                flash('テナントとアプリを選択してください', 'error')
                return redirect(url_for('system_admin.app_management'))
            
            # アプリ設定を更新
            app_setting = db.query(TTenantAppSetting).filter(
                and_(
                    TTenantAppSetting.tenant_id == tenant_id,
                    TTenantAppSetting.app_name == app_id
                )
            ).first()
            
            if action == 'enable':
                if not app_setting:
                    # 新規作成
                    app_setting = TTenantAppSetting(
                        tenant_id=tenant_id,
                        app_id=app_id,
                        enabled=1
                    )
                    db.add(app_setting)
                else:
                    app_setting.enabled = 1
                db.commit()
                flash(f'アプリを有効化しました', 'success')
            elif action == 'disable':
                if app_setting:
                    app_setting.enabled = 0
                    db.commit()
                    flash(f'アプリを無効化しました', 'success')
            
            return redirect(url_for('system_admin.app_management'))
        
        # GETリクエスト
        # 全テナントを取得
        tenants = db.query(TTenant).filter(TTenant.有効 == 1).all()
        
        # 利用可能アプリ一覧を取得
        available_apps = AVAILABLE_APPS
        
        # 各テナントのアプリ設定を取得
        tenant_app_settings = {}
        for tenant in tenants:
            settings = db.query(TTenantAppSetting).filter(
                TTenantAppSetting.tenant_id == tenant.id
            ).all()
            tenant_app_settings[tenant.id] = {s.app_id: s.enabled for s in settings}
        
        return render_template('system_admin_app_management.html',
                             tenants=tenants,
                             available_apps=available_apps,
                             tenant_app_settings=tenant_app_settings)
    finally:
        db.close()


@bp.route('/select_tenant_from_mypage', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def select_tenant_from_mypage():
    """マイページからテナントを選択してテナント管理者ダッシュボードへ"""
    tenant_id = request.form.get('tenant_id')
    
    if not tenant_id:
        flash('テナントを選択してください', 'error')
        return redirect(url_for('system_admin.mypage'))
    
    # テナントが存在するか確認
    db = SessionLocal()
    try:
        tenant = db.query(TTenant).filter(
            and_(TTenant.id == tenant_id, TTenant.有効 == 1)
        ).first()
        
        if not tenant:
            flash('選択したテナントが見つかりません', 'error')
            return redirect(url_for('system_admin.mypage'))
        
        # セッションにテナント情報を保存
        session['tenant_id'] = tenant.id
        session['store_id'] = None  # 店舗選択をクリア
        
        flash(f'テナント「{tenant.名称}」を選択しました', 'success')
        
        # テナント管理者ダッシュボードへリダイレクト
        return redirect('/tenant_admin/')
    finally:
        db.close()


@bp.route('/select_store_from_mypage', methods=['POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def select_store_from_mypage():
    """マイページから店舗を選択して店舗管理者ダッシュボードへ"""
    store_id = request.form.get('store_id')
    
    if not store_id:
        flash('店舗を選択してください', 'error')
        return redirect(url_for('system_admin.mypage'))
    
    # 店舗が存在するか確認
    db = SessionLocal()
    try:
        store = db.query(TTenpo).filter(
            and_(TTenpo.id == store_id, TTenpo.有効 == 1)
        ).first()
        
        if not store:
            flash('選択した店舗が見つかりません', 'error')
            return redirect(url_for('system_admin.mypage'))
        
        # テナント名も取得
        tenant = db.query(TTenant).filter(TTenant.id == store.tenant_id).first()
        
        # セッションに店舗情報とテナント情報を保存
        session['store_id'] = store.id
        session['tenant_id'] = store.tenant_id
        
        if tenant:
            flash(f'店舗「{store.名称}」（テナント: {tenant.名称}）を選択しました', 'success')
        else:
            flash(f'店舗「{store.名称}」を選択しました', 'success')
        
        # 店舗管理者ダッシュボードへリダイレクト
        return redirect('/admin/')
    finally:
        db.close()


# ========================================
# テナントアプリ管理
# ========================================

@bp.route('/tenants/<int:tid>/apps')
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_apps(tid):
    """テナントの利用可能アプリ一覧"""
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tid).first()
        
        if not tenant:
            flash('テナント情報が見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
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
                        TTenantAppSetting.tenant_id == tid,
                        TTenantAppSetting.app_name == app['id']
                    )
                ).first()
                enabled = app_setting.enabled if app_setting else 1
                
                if enabled:
                    enabled_apps.append(app)
        
        apps = enabled_apps
        
        return render_template('sys_tenant_apps.html', tenant=tenant_data, apps=apps)
    finally:
        db.close()


# ========================================
# 店舗管理（システム管理者用）
# ========================================

@bp.route('/tenants/<int:tid>/stores')
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_stores(tid):
    """テナントの店舗一覧"""
    db = SessionLocal()
    
    try:
        # システム管理者がテナント管理者の機能を使用するためにセッションにtenant_idを設定
        session['tenant_id'] = tid
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tid).first()
        if not tenant:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        # 店舗一覧を取得
        stores = db.query(TTenpo).filter(TTenpo.tenant_id == tid).order_by(TTenpo.id).all()
        
        store_list = []
        for s in stores:
            store_list.append({
                'id': s.id,
                'name': s.名称,
                'slug': s.slug,
                'postal_code': s.郵便番号,
                'address': s.住所,
                'phone': s.電話番号,
                'email': s.email,
                'active': s.有効,
                'created_at': s.created_at,
                'updated_at': s.updated_at
            })
        
        tenant_data = {
            'id': tenant.id,
            '名称': tenant.名称,
            'slug': tenant.slug
        }
        
        return render_template('sys_tenant_stores.html', 
                             tenant=tenant_data,
                             stores=store_list)
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/stores/<int:sid>/admin_invite', methods=['GET', 'POST'])
@require_roles(ROLES["SYSTEM_ADMIN"])
def store_admin_invite(tid, sid):
    """店舗管理者を追加"""
    db = SessionLocal()
    
    try:
        # テナント情報取得
        tenant_obj = db.query(TTenant).filter(TTenant.id == tid).first()
        
        if not tenant_obj:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        tenant = {
            'id': tenant_obj.id,
            '名称': tenant_obj.名称,
            'slug': tenant_obj.slug
        }
        
        # 店舗情報取得
        store_obj = db.query(TTenpo).filter(
            and_(TTenpo.id == sid, TTenpo.tenant_id == tid)
        ).first()
        
        if not store_obj:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('system_admin.tenant_stores', tid=tid))
        
        store = {
            'id': store_obj.id,
            '名称': store_obj.名称,
            'slug': store_obj.slug
        }
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            
            # バリデーション
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
                return render_template('sys_store_admin_invite.html', tenant=tenant, store=store)
            
            # ログインIDと氏名が完全一致する店舗管理者を検索（同一テナント内）
            admin = db.query(TKanrisha).filter(
                and_(
                    TKanrisha.login_id == login_id,
                    TKanrisha.name == name,
                    TKanrisha.role == ROLES["ADMIN"],
                    TKanrisha.tenant_id == tid
                )
            ).first()
            
            if not admin:
                flash(f'ログインID"{login_id}"と氏名"{name}"が一致する同一テナント内の店舗管理者が見つかりません', 'error')
                return render_template('sys_store_admin_invite.html', tenant=tenant, store=store)
            
            # 既にこの店舗に所属しているか確認
            existing_relation = db.query(TKanrishaTenpo).filter(
                and_(
                    TKanrishaTenpo.admin_id == admin.id,
                    TKanrishaTenpo.store_id == sid
                )
            ).first()
            
            if existing_relation:
                flash(f'"{admin.name}"は既にこの店舗に所属しています', 'error')
                return render_template('sys_store_admin_invite.html', tenant=tenant, store=store)
            
            # 中間テーブルに追加
            new_relation = TKanrishaTenpo(
                admin_id=admin.id,
                store_id=sid,
                is_owner=0,  # 追加された管理者はオーナーではない
                can_manage_admins=0  # 管理権限はなし
            )
            db.add(new_relation)
            db.commit()
            
            flash(f'店舗管理者 "{admin.name}" を店舗"{store["名称"]}"に追加しました', 'success')
            return redirect(url_for('system_admin.tenant_store_detail', tid=tid, sid=sid))
        
        return render_template('sys_store_admin_invite.html', tenant=tenant, store=store)
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/stores/<int:sid>')
@require_roles(ROLES["SYSTEM_ADMIN"])
def tenant_store_detail(tid, sid):
    """テナントの店舗詳細"""
    db = SessionLocal()
    
    try:
        # システム管理者がテナント管理者の機能を使用するためにセッションにtenant_idを設定
        session['tenant_id'] = tid
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tid).first()
        if not tenant:
            flash('テナントが見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        # 店舗情報を取得
        store = db.query(TTenpo).filter(
            and_(TTenpo.id == sid, TTenpo.tenant_id == tid)
        ).first()
        
        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('system_admin.tenant_stores', tid=tid))
        
        store_data = {
            'id': store.id,
            'name': store.名称,
            'slug': store.slug,
            'postal_code': store.郵便番号,
            'address': store.住所,
            'phone': store.電話番号,
            'email': store.email,
            'openai_api_key': store.openai_api_key,
            'active': store.有効,
            'created_at': store.created_at,
            'updated_at': store.updated_at
        }
        
        tenant_data = {
            'id': tenant.id,
            '名称': tenant.名称,
            'slug': tenant.slug
        }
        
        return render_template('sys_tenant_store_detail.html', 
                             tenant=tenant_data,
                             store=store_data)
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/stores/<int:sid>/select_for_admins')
@require_roles(ROLES["SYSTEM_ADMIN"])
def sys_select_store_for_admins(tid, sid):
    """店舗を選択して店舗管理者一覧にリダイレクト（システム管理者用）"""
    db = SessionLocal()
    
    try:
        # 店舗が存在するか確認
        store = db.query(TTenpo).filter(
            and_(TTenpo.id == sid, TTenpo.tenant_id == tid)
        ).first()
        
        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('system_admin.tenant_stores', tid=tid))
        
        # セッションに店舗IDとテナントIDを設定
        session['store_id'] = sid
        session['tenant_id'] = tid
        
        # 店舗管理者一覧にリダイレクト
        return redirect(url_for('tenant_admin.store_admins'))
    finally:
        db.close()


@bp.route('/restore_owner_temp/<int:admin_id>')
def restore_owner_temp(admin_id):
    """一時的なオーナー権限復元エンドポイント（デバッグ用）"""
    from sqlalchemy import text
    db = SessionLocal()
    
    try:
        # 全てのシステム管理者のis_ownerを0に設定
        db.execute(text('UPDATE "T_管理者" SET is_owner = 0 WHERE role = \'system_admin\''))
        
        # 指定されたIDのシステム管理者にオーナー権限と管理権限を付与
        db.execute(text(f'UPDATE "T_管理者" SET is_owner = 1, can_manage_admins = 1 WHERE id = {admin_id}'))
        
        db.commit()
        
        flash(f'ID:{admin_id}にオーナー権限を復元しました', 'success')
        return redirect(url_for('system_admin.system_admins'))
    except Exception as e:
        db.rollback()
        flash(f'エラー: {str(e)}', 'error')
        return redirect(url_for('system_admin.system_admins'))
    finally:
        db.close()


@bp.route('/tenants/<int:tid>/stores/<int:sid>/apps')
@require_roles(ROLES["SYSTEM_ADMIN"])
def store_apps(tid, sid):
    """店舗の利用可能アプリ一覧"""
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tid).first()
        
        if not tenant:
            flash('テナント情報が見つかりません', 'error')
            return redirect(url_for('system_admin.tenants'))
        
        tenant_data = {
            'id': tenant.id,
            '名称': tenant.名称,
            'slug': tenant.slug,
            'created_at': tenant.created_at
        }
        
        # 店舗情報を取得
        store = db.query(TTenpo).filter(
            and_(TTenpo.id == sid, TTenpo.tenant_id == tid)
        ).first()
        
        if not store:
            flash('店舗情報が見つかりません', 'error')
            return redirect(url_for('system_admin.tenant_stores', tid=tid))
        
        store_data = {
            'id': store.id,
            '名称': store.名称,
            'slug': store.slug
        }
        
        # 店舗レベルで有効なアプリを取得
        enabled_apps = []
        
        for app in AVAILABLE_APPS:
            if app['scope'] == 'store':
                app_setting = db.query(TTenpoAppSetting).filter(
                    and_(
                        TTenpoAppSetting.store_id == sid,
                        TTenpoAppSetting.app_name == app['id']
                    )
                ).first()
                enabled = app_setting.enabled if app_setting else 1
                
                if enabled:
                    enabled_apps.append(app)
        
        apps = enabled_apps
        
        return render_template('sys_store_apps.html', tenant=tenant_data, store=store_data, apps=apps, tid=tid, sid=sid)
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
