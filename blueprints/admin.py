# -*- coding: utf-8 -*-
"""
管理者ダッシュボード（SQLAlchemy版）
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import SessionLocal
from app.models_login import TKanrisha, TJugyoin, TTenant, TTenpo, TKanrishaTenpo, TJugyoinTenpo, TTenpoAppSetting, TTenantAdminTenant
from sqlalchemy import func, and_, or_
from app.utils.decorators import ROLES
from app.utils.decorators import require_roles

bp = Blueprint('admin', __name__, url_prefix='/admin')

# 利用可能なアプリの定義
AVAILABLE_APPS = [
    # 現在利用可能なアプリはありません
]


@bp.route('/')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def dashboard():
    """管理者ダッシュボード"""
    # 店舗で有効なアプリを取得
    store_id = session.get('store_id')
    tenant_id = session.get('tenant_id')
    enabled_apps = []
    
    tenant = None
    store = None
    
    if store_id:
        db = SessionLocal()
        
        try:
            # テナント情報を取得
            tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
            
            # 店舗情報を取得
            store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
            
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
        finally:
            db.close()
    
    return render_template('admin_dashboard.html', tenant_id=tenant_id, apps=enabled_apps, tenant=tenant, store=store)


@bp.route('/available_apps')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def available_apps():
    """利用可能アプリ一覧"""
    store_id = session.get('store_id')
    tenant_id = session.get('tenant_id')
    enabled_apps = []
    
    tenant = None
    store = None
    
    if store_id:
        db = SessionLocal()
        
        try:
            # テナント情報を取得
            tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
            
            # 店舗情報を取得
            store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
            
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
        finally:
            db.close()
    
    # マイページURLを取得
    user_role = session.get('role')
    if user_role == ROLES["SYSTEM_ADMIN"]:
        mypage_url = url_for('system_admin.mypage')
    elif user_role == ROLES["TENANT_ADMIN"]:
        mypage_url = url_for('tenant_admin.mypage')
    else:
        mypage_url = url_for('admin.mypage')
    
    return render_template('admin_available_apps.html', tenant_id=tenant_id, apps=enabled_apps, mypage_url=mypage_url, tenant=tenant, store=store)


@bp.route('/mypage', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def mypage():
    """管理者マイページ"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # ユーザー情報を取得
        user_obj = db.query(TKanrisha).filter(
            TKanrisha.id == user_id,
            TKanrisha.role == ROLES["ADMIN"]
        ).first()
        
        if not user_obj:
            flash('ユーザー情報が見つかりません', 'error')
            return redirect(url_for('admin.dashboard'))
        
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
        
        # 所属店舗リストを取得（管理者が管理する店舗、オーナー情報も取得）
        store_rels = db.query(TTenpo, TKanrishaTenpo).join(
            TKanrishaTenpo, TKanrishaTenpo.store_id == TTenpo.id
        ).filter(
            TKanrishaTenpo.admin_id == user_id
        ).order_by(TTenpo.名称).all()
        
        stores = []
        store_list = []
        for store, rel in store_rels:
            store_name = store.名称
            if rel.is_owner:
                store_name += '（オーナー）'
            stores.append(store_name)
            store_list.append({'id': store.id, 'name': store.名称, 'tenant_id': store.tenant_id})
        
        # テナントリストを取得（管理者が所属する店舗のテナント）
        tenant_ids = list(set([s['tenant_id'] for s in store_list]))
        tenant_objs = db.query(TTenant).filter(TTenant.id.in_(tenant_ids)).order_by(TTenant.名称).all()
        tenant_list = [{'id': t.id, 'name': t.名称} for t in tenant_objs]
        
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
                    return render_template('admin_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list, tenant_list=tenant_list)
                
                # ログインID重複チェック（自分以外）
                existing = db.query(TKanrisha).filter(
                    TKanrisha.login_id == login_id,
                    TKanrisha.id != user_id
                ).first()
                if existing:
                    flash('このログインIDは既に使用されています', 'error')
                    return render_template('admin_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list, tenant_list=tenant_list)
                
                # プロフィール更新
                user_obj.login_id = login_id
                user_obj.name = name
                user_obj.email = email
                if hasattr(user_obj, 'updated_at'):
                    user_obj.updated_at = func.now()
                db.commit()
                
                flash('プロフィール情報を更新しました', 'success')
                return redirect(url_for('admin.mypage'))
            
            elif action == 'change_password':
                # パスワード変更
                current_password = request.form.get('current_password', '').strip()
                new_password = request.form.get('new_password', '').strip()
                new_password_confirm = request.form.get('new_password_confirm', '').strip()
            
                # パスワード一致チェック
                if new_password != new_password_confirm:
                    flash('パスワードが一致しません', 'error')
                    return render_template('admin_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list, tenant_list=tenant_list)
                
                # 現在のパスワードを確認
                if not check_password_hash(user_obj.password_hash, current_password):
                    flash('現在のパスワードが正しくありません', 'error')
                    return render_template('admin_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list, tenant_list=tenant_list)
                
                # パスワードを更新
                user_obj.password_hash = generate_password_hash(new_password)
                if hasattr(user_obj, 'updated_at'):
                    user_obj.updated_at = func.now()
                db.commit()
                
                flash('パスワードを変更しました', 'success')
                return redirect(url_for('admin.mypage'))
        
        return render_template('admin_mypage.html', user=user, tenant_name=tenant_name, stores=stores, store_list=store_list, tenant_list=tenant_list)
    finally:
        db.close()


@bp.route('/store_info')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_info():
    """店舗情報表示"""
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    user_id = session.get('user_id')
    db = SessionLocal()
    
    try:
        # セッションにstore_idがない場合はダッシュボードにリダイレクト
        if not store_id:
            flash('店舗が選択されていません', 'error')
            return redirect(url_for('admin.dashboard'))
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        # 選択された店舗の情報を取得
        store_obj = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        
        if not store_obj:
            flash('店舗情報が見つかりません', 'error')
            return redirect(url_for('admin.dashboard'))
        
        store = {
            'id': store_obj.id,
            '名称': store_obj.名称,
            'slug': store_obj.slug,
            '郵便番号': store_obj.郵便番号 if hasattr(store_obj, '郵便番号') else None,
            '住所': store_obj.住所 if hasattr(store_obj, '住所') else None,
            '電話番号': store_obj.電話番号 if hasattr(store_obj, '電話番号') else None,
            'email': store_obj.email if hasattr(store_obj, 'email') else None,
            'openai_api_key': store_obj.openai_api_key if hasattr(store_obj, 'openai_api_key') else None,
            '有効': store_obj.有効 if hasattr(store_obj, '有効') else 1,
            'created_at': store_obj.created_at,
            'updated_at': store_obj.updated_at if hasattr(store_obj, 'updated_at') else None
        }
        
        return render_template('admin_store_info.html', store=store, tenant=tenant, store_obj=store_obj)
    finally:
        db.close()


@bp.route('/store/<int:store_id>')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_detail(store_id):
    """店舗詳細"""
    tenant_id = session.get('tenant_id')
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        store_obj = db.query(TTenpo).filter(
            and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
        ).first()
        
        if not store_obj:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('admin.store_info'))
        
        store = {
            'id': store_obj.id,
            '名称': store_obj.名称,
            'slug': store_obj.slug,
            '郵便番号': store_obj.郵便番号 if hasattr(store_obj, '郵便番号') else None,
            '住所': store_obj.住所 if hasattr(store_obj, '住所') else None,
            '電話番号': store_obj.電話番号 if hasattr(store_obj, '電話番号') else None,
            'email': store_obj.email if hasattr(store_obj, 'email') else None,
            'openai_api_key': store_obj.openai_api_key if hasattr(store_obj, 'openai_api_key') else None,
            '有効': store_obj.有効,
            'created_at': store_obj.created_at,
            'updated_at': store_obj.updated_at if hasattr(store_obj, 'updated_at') else None
        }
        
        return render_template('admin_store_detail.html', store=store, tenant=tenant, store_obj=store_obj)
    finally:
        db.close()


@bp.route('/admins')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admins():
    """店舗管理者一覧"""
    store_id = session.get('store_id')
    tenant_id = session.get('tenant_id')
    user_id = session.get('user_id')
    
    if not store_id:
        flash('店舗を選択してください。マイページの「店舗選択」から店舗を選んでダッシュボードへ進んでください。', 'warning')
        return redirect(url_for('admin.mypage'))
    
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        # 店舗情報を取得
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        
        # 現在のユーザーのロールを確認
        user_role = session.get('role')
        is_system_admin = (user_role == ROLES["SYSTEM_ADMIN"])
        is_tenant_admin = (user_role == ROLES["TENANT_ADMIN"])
        
        # 現在のユーザーがオーナーかどうかを中間テーブルから確認
        current_admin_rel = db.query(TKanrishaTenpo).filter(
            and_(TKanrishaTenpo.admin_id == user_id, TKanrishaTenpo.store_id == store_id)
        ).first()
        is_owner = current_admin_rel.is_owner if current_admin_rel else False
        can_manage_admins = current_admin_rel.can_manage_admins if current_admin_rel else False
        
        # システム管理者またはテナント管理者は全ての店舗管理者を管理可能
        if is_system_admin or is_tenant_admin:
            can_manage_admins = True
        
        # 店舗に紐づく管理者を取得
        admin_relations = db.query(TKanrishaTenpo).filter(
            TKanrishaTenpo.store_id == store_id
        ).all()
        
        admins_data = []
        for rel in admin_relations:
            admin = db.query(TKanrisha).filter(TKanrisha.id == rel.admin_id).first()
            if admin:
                # この管理者が所属する店舗を取得
                store_rels = db.query(TTenpo, TKanrishaTenpo).join(
                    TKanrishaTenpo, TTenpo.id == TKanrishaTenpo.store_id
                ).filter(
                    TKanrishaTenpo.admin_id == admin.id
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
                    'stores': stores_with_owner,
                    'can_manage_admins': rel.can_manage_admins,
                    'created_at': admin.created_at.strftime('%Y-%m-%d %H:%M:%S') if admin.created_at else '-',
                    'updated_at': admin.updated_at.strftime('%Y-%m-%d %H:%M:%S') if admin.updated_at else None
                })
        
        return render_template('admin_admins.html', 
                             admins=admins_data, 
                             current_user_id=user_id,
                             is_owner=is_owner,
                             can_manage_admins=can_manage_admins,
                             tenant=tenant,
                             store=store)
    finally:
        db.close()


@bp.route('/employees')
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employees():
    """従業員一覧"""
    store_id = session.get('store_id')
    tenant_id = session.get('tenant_id')
    
    if not store_id:
        flash('店舗を選択してください。マイページの「店舗選択」から店舗を選んでダッシュボードへ進んでください。', 'warning')
        return redirect(url_for('admin.mypage'))
    
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        # 店舗情報を取得
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        
        # 店舗に紐づく従業員を取得
        employee_relations = db.query(TJugyoinTenpo).filter(
            TJugyoinTenpo.store_id == store_id
        ).all()
        
        employees_data = []
        for rel in employee_relations:
            employee = db.query(TJugyoin).filter(TJugyoin.id == rel.employee_id).first()
            if employee:
                # 所属店舗を取得
                employee_stores = db.query(TTenpo).join(
                    TJugyoinTenpo, TTenpo.id == TJugyoinTenpo.store_id
                ).filter(
                    TJugyoinTenpo.employee_id == employee.id
                ).all()
                
                stores_list = [{'id': s.id, 'name': s.名称} for s in employee_stores]
                
                employees_data.append({
                    'id': employee.id,
                    'login_id': employee.login_id,
                    'name': employee.name,
                    'email': employee.email,
                    'active': employee.active,
                    'created_at': employee.created_at.strftime('%Y-%m-%d %H:%M:%S') if employee.created_at else '-',
                    'updated_at': employee.updated_at.strftime('%Y-%m-%d %H:%M:%S') if employee.updated_at else None,
                    'stores': stores_list
                })
        
        return render_template('admin_employees.html', employees=employees_data, tenant=tenant, store=store)
    finally:
        db.close()


@bp.route('/employees/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_new():
    """従業員新規作成"""
    store_id = session.get('store_id')
    tenant_id = session.get('tenant_id')
    admin_id = session.get('user_id')
    
    if not store_id:
        flash('店舗を選択してください。マイページの「店舗選択」から店舗を選んでダッシュボードへ進んでください。', 'warning')
        return redirect(url_for('admin.mypage'))
    
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        # 店舗情報を取得
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        
        # ユーザーのロールを確認
        user_role = session.get('role')
        
        # テナント管理者またはシステム管理者の場合は、テナントに属するすべての店舗を取得
        if user_role in ['system_admin', 'tenant_admin']:
            stores_list = db.query(TTenpo).filter(
                TTenpo.tenant_id == tenant_id
            ).order_by(TTenpo.id).all()
        else:
            # 店舗管理者の場合は、管理する店舗一覧を取得
            stores_list = db.query(TTenpo).join(
                TKanrishaTenpo, TTenpo.id == TKanrishaTenpo.store_id
            ).filter(
                TKanrishaTenpo.admin_id == admin_id
            ).order_by(TTenpo.id).all()
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')
            store_ids = request.form.getlist('store_ids')
            
            # 作成元の店舗IDを必ず含める
            if str(store_id) not in store_ids:
                store_ids.append(str(store_id))
            
            # バリデーション
            if not login_id or not name or not email:
                flash('ログインID、氏名、メールアドレスは必須です', 'error')
                return render_template('admin_employee_new.html', stores=stores_list, from_store_id=store_id, back_url=url_for('admin.employees'), tenant=tenant, store=store)
            
            if not store_ids:
                flash('少なくとも1つの店舗を選択してください', 'error')
                return render_template('admin_employee_new.html', stores=stores_list, from_store_id=store_id, back_url=url_for('admin.employees'), tenant=tenant, store=store)
            
            if password and password != password_confirm:
                flash('パスワードが一致しません', 'error')
                return render_template('admin_employee_new.html', stores=stores_list, from_store_id=store_id, back_url=url_for('admin.employees'), tenant=tenant, store=store)
            
            if password and len(password) < 8:
                flash('パスワードは8文字以上にしてください', 'error')
                return render_template('admin_employee_new.html', stores=stores_list, from_store_id=store_id, back_url=url_for('admin.employees'), tenant=tenant, store=store)
            
            # ログインID重複チェック
            existing = db.query(TJugyoin).filter(TJugyoin.login_id == login_id).first()
            if existing:
                flash(f'ログインID "{login_id}" は既に使用されています', 'error')
                return render_template('admin_employee_new.html', stores=stores_list, from_store_id=store_id, back_url=url_for('admin.employees'), tenant=tenant, store=store)
            
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
            db.flush()  # IDを取得するため
            
            # 選択された店舗との関連を作成
            for store_id_str in store_ids:
                store_id_int = int(store_id_str)
                new_relation = TJugyoinTenpo(
                    employee_id=new_employee.id,
                    store_id=store_id_int
                )
                db.add(new_relation)
            db.commit()
            
            flash(f'従業員 "{name}" を作成しました', 'success')
            return redirect(url_for('admin.employees'))
        
        return render_template('admin_employee_new.html', stores=stores_list, from_store_id=store_id, back_url=url_for('admin.employees'), tenant=tenant, store=store)
    finally:
        db.close()


@bp.route('/employees/<int:employee_id>/toggle', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_toggle(employee_id):
    """従業員の有効/無効切り替え"""
    db = SessionLocal()
    
    try:
        employee = db.query(TJugyoin).filter(TJugyoin.id == employee_id).first()
        
        if employee:
            employee.active = 0 if employee.active == 1 else 1
            db.commit()
            flash('ステータスを更新しました', 'success')
        
        return redirect(url_for('admin.employees'))
    finally:
        db.close()


@bp.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_edit(employee_id):
    """従業員編集"""
    db = SessionLocal()
    
    try:
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            role = request.form.get('role', 'employee').strip()
            password = request.form.get('password', '').strip()
            active = 1 if request.form.get('active') == '1' else 0
            
            if not login_id or not name or not email:
                flash('ログインID、氏名、メールアドレスは必須です', 'error')
            else:
                # ログインIDの重複チェック
                existing = db.query(TJugyoin).filter(
                    and_(TJugyoin.login_id == login_id, TJugyoin.id != employee_id)
                ).first()
                if existing:
                    flash('このログインIDは既に使用されています', 'error')
                else:
                    employee = db.query(TJugyoin).filter(TJugyoin.id == employee_id).first()
                    
                    if employee:
                        # 役割変更の処理
                        old_role = employee.role
                        new_role = role
                        tenant_id = session.get('tenant_id')
                        store_ids = request.form.getlist('store_ids')
                        
                        if old_role != new_role:
                            # 従業員から店舗管理者に変更
                            if old_role == ROLES["EMPLOYEE"] and new_role == ROLES["ADMIN"]:
                                # 従業員テーブルから削除
                                db.query(TJugyoinTenpo).filter(TJugyoinTenpo.employee_id == employee_id).delete()
                                # 店舗管理者テーブルに移動（TKanrishaに移動）
                                new_admin = TKanrisha(
                                    login_id=employee.login_id,
                                    name=name,
                                    email=email,
                                    password_hash=employee.password_hash if not password else generate_password_hash(password),
                                    role=ROLES["ADMIN"],
                                    tenant_id=tenant_id,
                                    active=active
                                )
                                db.add(new_admin)
                                db.flush()
                                # 店舗管理者として店舗に追加
                                if store_ids:
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
                                db.commit()
                                flash(f'"{name}"を店舗管理者に変更しました', 'success')
                                return redirect(url_for('admin.employees'))
                            
                            # 従業員からテナント管理者に変更
                            elif old_role == ROLES["EMPLOYEE"] and new_role == ROLES["TENANT_ADMIN"]:
                                # 従業員テーブルから削除
                                db.query(TJugyoinTenpo).filter(TJugyoinTenpo.employee_id == employee_id).delete()
                                # テナント管理者テーブルに移動（TKanrishaに移動）
                                new_admin = TKanrisha(
                                    login_id=employee.login_id,
                                    name=name,
                                    email=email,
                                    password_hash=employee.password_hash if not password else generate_password_hash(password),
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
                                db.commit()
                                flash(f'"{name}"をテナント管理者に変更しました', 'success')
                                return redirect(url_for('admin.employees'))
                            else:
                                flash('役割変更は従業員からのみ対応しています', 'error')
                        else:
                            # 役割変更がない場合は通常の更新
                            employee.login_id = login_id
                            employee.name = name
                            employee.email = email
                            employee.active = active
                            if password:
                                employee.password_hash = generate_password_hash(password)
                            
                            # 店舗所属の更新
                            if store_ids:
                                # 既存の店舗所属を削除
                                db.query(TJugyoinTenpo).filter(
                                    TJugyoinTenpo.employee_id == employee_id
                                ).delete()
                                
                                # 新しい店舗所属を追加
                                for store_id in store_ids:
                                    rel = TJugyoinTenpo(
                                        employee_id=employee_id,
                                        store_id=int(store_id)
                                    )
                                    db.add(rel)
                            
                            db.commit()
                            flash('従業員を更新しました', 'success')
                            return redirect(url_for('admin.employees'))
        
        # GETリクエスト時は現在の情報を表示
        employee = db.query(TJugyoin).filter(TJugyoin.id == employee_id).first()
        
        if not employee:
            flash('従業員が見つかりません', 'error')
            return redirect(url_for('admin.employees'))
        
        # テナントIDを取得
        tenant_id = session.get('tenant_id')
        
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        # 現在の店舗情報を取得
        store_id = session.get('store_id')
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
        
        # テナントの全店舗を取得
        stores = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).all()
        store_list = [{'id': s.id, '名称': s.名称} for s in stores]
        
        # 従業員が所属している店舗IDを取得
        assigned_stores = db.query(TJugyoinTenpo).filter(
            TJugyoinTenpo.employee_id == employee_id
        ).all()
        assigned_store_ids = [rel.store_id for rel in assigned_stores]
        
        employee_data = {
            'id': employee.id,
            'login_id': employee.login_id,
            'name': employee.name,
            'email': employee.email,
            'active': employee.active,
            'role': employee.role
        }
        
        return render_template('admin_employee_edit.html', 
                             employee=employee_data,
                             stores=store_list,
                             assigned_store_ids=assigned_store_ids,
                             tenant=tenant,
                             store=store)
    finally:
        db.close()


@bp.route('/employees/<int:employee_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_delete(employee_id):
    """従業員削除"""
    db = SessionLocal()
    
    try:
        employee = db.query(TJugyoin).filter(TJugyoin.id == employee_id).first()
        
        if employee:
            # 店舗との紐付けも削除
            db.query(TJugyoinTenpo).filter(TJugyoinTenpo.employee_id == employee_id).delete()
            db.delete(employee)
            db.commit()
            flash('従業員を削除しました', 'success')
        
        return redirect(url_for('admin.employees'))
    finally:
        db.close()

@bp.route('/employees/invite', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_invite():
    """既存の従業員を招待"""
    tenant_id = session.get('tenant_id')
    
    if not tenant_id:
        flash('テナントIDが取得できません', 'error')
        return redirect(url_for('admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        tenant_name = tenant.名称 if tenant else 'テストテナント'
        
        # 店舗情報を取得
        store_id = session.get('store_id')
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first() if store_id else None
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            
            # バリデーション
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
                return render_template('admin_employee_invite.html', tenant_name=tenant_name, tenant=tenant, store=store)
            
            # ログインIDと氏名が一致する従業員を検索
            existing_employee = db.query(TJugyoin).filter(
                and_(
                    TJugyoin.login_id == login_id,
                    TJugyoin.name == name,
                    TJugyoin.tenant_id == tenant_id
                )
            ).first()
            
            if not existing_employee:
                flash(f'ログインID「{login_id}」と氏名「{name}」が一致する従業員が見つかりません', 'error')
                return render_template('admin_employee_invite.html', tenant_name=tenant_name, tenant=tenant, store=store)
            
            flash(f'従業員「{name}」は既にこのテナントに所属しています', 'info')
            return redirect(url_for('admin.employees'))
        
        return render_template('admin_employee_invite.html', tenant_name=tenant_name, tenant=tenant, store=store)
    finally:
        db.close()



@bp.route('/store/<int:store_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_edit(store_id):
    """店舗編集"""
    tenant_id = session.get('tenant_id')
    session_store_id = session.get('store_id')
    db = SessionLocal()
    
    try:
        # テナント情報を取得
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        
        # セッションのstore_idと一致するか確認
        if store_id != session_store_id:
            flash('この店舗を編集する権限がありません', 'error')
            return redirect(url_for('admin.store_info'))
        
        store_obj = db.query(TTenpo).filter(
            and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
        ).first()
        
        if not store_obj:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('admin.store_info'))
        
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
                flash('名称とSlugは必須です', 'error')
                return render_template('admin_store_edit.html', store=store_obj, tenant=tenant)
            
            # Slug重複チェック（自分以外）
            existing = db.query(TTenpo).filter(
                and_(
                    TTenpo.slug == slug,
                    TTenpo.tenant_id == tenant_id,
                    TTenpo.id != store_id
                )
            ).first()
            
            if existing:
                flash(f'Slug "{slug}" は既に使用されています', 'error')
                return render_template('admin_store_edit.html', store=store_obj, tenant=tenant)
            
            # 更新
            store_obj.名称 = name
            store_obj.slug = slug
            store_obj.郵便番号 = postal_code if postal_code else None
            store_obj.住所 = address if address else None
            store_obj.電話番号 = phone if phone else None
            store_obj.email = email if email else None
            store_obj.openai_api_key = openai_api_key if openai_api_key else None
            store_obj.有効 = active
            db.commit()
            
            flash('店舗情報を更新しました', 'success')
            return redirect(url_for('admin.store_info'))
        
        return render_template('admin_store_edit.html', store=store_obj, tenant=tenant)
    finally:
        db.close()


@bp.route('/store/<int:store_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def store_delete(store_id):
    """店舗削除"""
    tenant_id = session.get('tenant_id')
    session_store_id = session.get('store_id')
    user_id = session.get('user_id')
    db = SessionLocal()
    
    try:
        # パスワード検証
        password = request.form.get('password')
        if not password:
            flash('パスワードを入力してください', 'error')
            return redirect(url_for('admin.store_info'))
        
        # ユーザーを取得してパスワードを検証
        user = db.query(TKanrisha).filter(TKanrisha.id == user_id).first()
        if not user or not check_password_hash(user.password, password):
            flash('パスワードが正しくありません', 'error')
            return redirect(url_for('admin.store_info'))
        
        # セッションのstore_idと一致するか確認
        if store_id != session_store_id:
            flash('この店舗を削除する権限がありません', 'error')
            return redirect(url_for('admin.store_info'))
        
        store_obj = db.query(TTenpo).filter(
            and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
        ).first()
        
        if not store_obj:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('admin.store_info'))
        
        # 関連データの削除（必要に応じて）
        # 店舗管理者の関連を削除
        db.query(TKanrishaTenpo).filter(TKanrishaTenpo.store_id == store_id).delete()
        
        # 従業員の関連を削除
        db.query(TJugyoinTenpo).filter(TJugyoinTenpo.store_id == store_id).delete()
        
        # アプリ設定を削除
        db.query(TTenpoAppSetting).filter(TTenpoAppSetting.store_id == store_id).delete()
        
        # 店舗を削除
        db.delete(store_obj)
        db.commit()
        
        # セッションから店舗IDを削除
        session.pop('store_id', None)
        
        flash('店舗を削除しました', 'success')
        
        # ユーザーの役割に応じてリダイレクト
        user_role = session.get('role')
        if user_role == ROLES["SYSTEM_ADMIN"]:
            return redirect(url_for('system_admin.mypage'))
        elif user_role == ROLES["TENANT_ADMIN"]:
            return redirect(url_for('tenant_admin.mypage'))
        else:
            return redirect(url_for('auth.logout'))
    finally:
        db.close()


@bp.route('/mypage/select_store', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def select_store_from_mypage():
    """マイページから店舗を選択してダッシュボードへ進む"""
    store_id = request.form.get('store_id')
    
    if not store_id:
        flash('店舗を選択してください', 'error')
        return redirect(url_for('admin.mypage'))
    
    session['store_id'] = int(store_id)
    flash('店舗を選択しました', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_edit(admin_id):
    """店舗管理者編集"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    
    db = SessionLocal()
    
    try:
        # 権限チェック（システム管理者とテナント管理者は無条件で許可）
        role = session.get('role')
        store_id = session.get('store_id')
        if role not in ['system_admin', 'tenant_admin']:
            # 店舗管理者の場合は中間テーブルから権限をチェック
            current_admin_rel = db.query(TKanrishaTenpo).filter(
                and_(TKanrishaTenpo.admin_id == user_id, TKanrishaTenpo.store_id == store_id)
            ).first()
            if not current_admin_rel or (current_admin_rel.is_owner != 1 and current_admin_rel.can_manage_admins != 1):
                flash('管理者を編集する権限がありません', 'error')
                return redirect(url_for('admin.dashboard'))
        
        # 店舗一覧を取得
        stores = db.query(TTenpo).filter(
            and_(TTenpo.tenant_id == tenant_id, TTenpo.有効 == 1)
        ).order_by(TTenpo.名称).all()
        
        # 各店舗について、編集対象の管理者がオーナーかどうかを取得
        stores_data = []
        for store in stores:
            # この店舗で編集対象の管理者がオーナーかどうかを確認
            rel = db.query(TKanrishaTenpo).filter(
                and_(
                    TKanrishaTenpo.admin_id == admin_id,
                    TKanrishaTenpo.store_id == store.id
                )
            ).first()
            is_owner = rel.is_owner == 1 if rel else False
            stores_data.append({
                'id': store.id,
                '名称': store.名称,
                'is_owner': is_owner
            })
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            password_confirm = request.form.get('password_confirm', '').strip()
            store_ids = request.form.getlist('store_ids')
            active = int(request.form.get('active', 1))
            can_manage_admins = 1 if request.form.get('can_manage_admins') == '1' else 0
            
            # 編集対象の管理者を取得
            admin = db.query(TKanrisha).filter(
                and_(
                    TKanrisha.id == admin_id,
                    TKanrisha.tenant_id == tenant_id,
                    TKanrisha.role == ROLES["ADMIN"]
                )
            ).first()
            
            if not admin:
                flash('管理者が見つかりません', 'error')
                return redirect(url_for('admin.admins'))
            
            is_owner = admin.is_owner
            
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
            elif password and password != password_confirm:
                flash('パスワードが一致しません', 'error')
            elif not store_ids:
                flash('少なくとも1つの店舗を選択してください', 'error')
            elif is_owner == 1 and active == 0:
                flash('オーナーを無効にすることはできません。先にオーナー権限を移譲してください。', 'error')
            else:
                # 重複チェック（自分以外）
                existing = db.query(TKanrisha).filter(
                    and_(TKanrisha.login_id == login_id, TKanrisha.id != admin_id)
                ).first()
                
                if existing:
                    flash(f'ログインID "{login_id}" は既に使用されています', 'error')
                else:
                    # 管理者情報を更新
                    admin.login_id = login_id
                    admin.name = name
                    admin.email = email
                    admin.active = active
                    
                    if password:
                        admin.password_hash = generate_password_hash(password)
                    
                    # 所属店舗を更新
                    # 既存の所属店舗を削除
                    db.query(TKanrishaTenpo).filter(TKanrishaTenpo.admin_id == admin_id).delete()
                    
                    # 新しい所属店舗を追加
                    for store_id in store_ids:
                        new_relation = TKanrishaTenpo(
                            admin_id=admin_id,
                            store_id=int(store_id),
                            can_manage_admins=can_manage_admins
                        )
                        db.add(new_relation)
                    
                    db.commit()
                    flash('管理者情報を更新しました', 'success')
                    return redirect(url_for('admin.admins'))
        
        # GETリクエスト：管理者情報を取得
        admin = db.query(TKanrisha).filter(
            and_(
                TKanrisha.id == admin_id,
                TKanrisha.tenant_id == tenant_id,
                TKanrisha.role == ROLES["ADMIN"]
            )
        ).first()
        
        if not admin:
            flash('管理者が見つかりません', 'error')
            return redirect(url_for('admin.admins'))
        
        # 現在の所属店舗を取得
        admin_store_relations = db.query(TKanrishaTenpo).filter(
            TKanrishaTenpo.admin_id == admin_id
        ).all()
        
        # 中間テーブルからis_ownerを取得（いずれかの店舗でオーナーであればTrue）
        is_owner = any(rel.is_owner == 1 for rel in admin_store_relations)
        
        admin_data = {
            'id': admin.id,
            'login_id': admin.login_id,
            'name': admin.name,
            'email': admin.email,
            'is_owner': 1 if is_owner else 0,
            'active': admin.active if admin.active is not None else 1
        }
        admin_store_ids = [rel.store_id for rel in admin_store_relations]
        
        # can_manage_adminsを取得（いずれかの店舗で権限があればTrue）
        can_manage_admins = any(rel.can_manage_admins == 1 for rel in admin_store_relations)
        
        return render_template('admin_admin_edit.html', 
                             admin=admin_data, 
                             stores=stores_data, 
                             admin_store_ids=admin_store_ids, 
                             can_manage_admins=can_manage_admins,
                             back_url=url_for('admin.admins'))
    finally:
        db.close()


@bp.route('/admins/<int:admin_id>/delete', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_delete(admin_id):
    """店舗管理者削除"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    
    db = SessionLocal()
    
    try:
        # 権限チェック（システム管理者とテナント管理者は無条件で許可）
        role = session.get('role')
        store_id = session.get('store_id')
        if role not in ['system_admin', 'tenant_admin']:
            # 店舗管理者の場合は中間テーブルから権限をチェック
            current_admin_rel = db.query(TKanrishaTenpo).filter(
                and_(TKanrishaTenpo.admin_id == user_id, TKanrishaTenpo.store_id == store_id)
            ).first()
            if not current_admin_rel or (current_admin_rel.is_owner != 1 and current_admin_rel.can_manage_admins != 1):
                flash('管理者を削除する権限がありません', 'error')
                return redirect(url_for('admin.dashboard'))
        
        # 削除対象の管理者を取得
        admin = db.query(TKanrisha).filter(
            and_(
                TKanrisha.id == admin_id,
                TKanrisha.tenant_id == tenant_id,
                TKanrisha.role == ROLES["ADMIN"]
            )
        ).first()
        
        if not admin:
            flash('管理者が見つかりません', 'error')
            return redirect(url_for('admin.admins'))
        
        # オーナーは削除できない
        if admin.is_owner == 1:
            flash('オーナーは削除できません', 'error')
        else:
            # 所属店舗の関連を削除
            db.query(TKanrishaTenpo).filter(TKanrishaTenpo.admin_id == admin_id).delete()
            
            # 管理者を削除
            db.delete(admin)
            db.commit()
            flash('管理者を削除しました', 'success')
        
        return redirect(url_for('admin.admins'))
    finally:
        db.close()


@bp.route('/admins/<int:admin_id>/transfer_owner', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_transfer_owner(admin_id):
    """オーナー権限移譲"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    
    db = SessionLocal()
    
    try:
        # 権限チェック（システム管理者とテナント管理者は無条件で許可）
        role = session.get('role')
        store_id = session.get('store_id')
        if role not in ['system_admin', 'tenant_admin']:
            # 店舗管理者の場合は中間テーブルから権限をチェック
            current_admin_rel = db.query(TKanrishaTenpo).filter(
                and_(TKanrishaTenpo.admin_id == user_id, TKanrishaTenpo.store_id == store_id)
            ).first()
            if not current_admin_rel or current_admin_rel.is_owner != 1:
                flash('オーナー権限を移譲する権限がありません', 'error')
                return redirect(url_for('admin.admins'))
        
        # 自分自身への移譲を防止
        if admin_id == user_id:
            flash('自分自身にオーナー権限を移譲することはできません', 'error')
            return redirect(url_for('admin.admins'))
        
        # 移譲先の管理者が同じテナントか確認
        target_admin = db.query(TKanrisha).filter(
            and_(
                TKanrisha.id == admin_id,
                TKanrisha.tenant_id == tenant_id,
                TKanrisha.role == ROLES["ADMIN"]
            )
        ).first()
        
        if not target_admin:
            flash('管理者が見つかりません', 'error')
        else:
            # 現在の店舗のオーナー権限を解除（中間テーブル）
            current_owner_rel = db.query(TKanrishaTenpo).filter(
                and_(
                    TKanrishaTenpo.store_id == store_id,
                    TKanrishaTenpo.is_owner == 1
                )
            ).first()
            
            if current_owner_rel:
                current_owner_rel.is_owner = 0
            
            # 新しいオーナーに権限を付与（中間テーブル）
            target_admin_rel = db.query(TKanrishaTenpo).filter(
                and_(
                    TKanrishaTenpo.admin_id == admin_id,
                    TKanrishaTenpo.store_id == store_id
                )
            ).first()
            
            if target_admin_rel:
                target_admin_rel.is_owner = 1
                db.commit()
                flash(f'{target_admin.name} にオーナー権限を移譲しました', 'success')
            else:
                flash('管理者がこの店舗に所属していません', 'error')
        
        return redirect(url_for('admin.admins'))
    finally:
        db.close()


@bp.route('/admins/<int:admin_id>/toggle_active', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_toggle_active(admin_id):
    """店舗管理者の有効/無効を切り替え"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    
    db = SessionLocal()
    
    try:
        # 権限チェック
        role = session.get('role')
        if role not in [ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"]]:
            # 店舗管理者の場合は中間テーブルから権限をチェック
            current_admin_rel = db.query(TKanrishaTenpo).filter(
                and_(TKanrishaTenpo.admin_id == user_id, TKanrishaTenpo.store_id == store_id)
            ).first()
            if not current_admin_rel or (current_admin_rel.is_owner != 1 and current_admin_rel.can_manage_admins != 1):
                flash('管理者のステータスを変更する権限がありません', 'error')
                return redirect(url_for('admin.admins'))
        
        # 対象の管理者を取得
        admin = db.query(TKanrisha).filter(TKanrisha.id == admin_id).first()
        if not admin:
            flash('管理者が見つかりません', 'error')
            return redirect(url_for('admin.admins'))
        
        # ステータスを切り替え
        admin.active = not admin.active
        db.commit()
        
        status_text = "有効化" if admin.active else "無効化"
        flash(f'{admin.name} を{status_text}しました', 'success')
        
        return redirect(url_for('admin.admins'))
    finally:
        db.close()


@bp.route('/admins/<int:admin_id>/toggle_permission', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_toggle_permission(admin_id):
    """店舗管理者の管理権限を切り替え"""
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    
    db = SessionLocal()
    
    try:
        # 権限チェック
        role = session.get('role')
        if role not in [ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"]]:
            # 店舗管理者の場合は中間テーブルから権限をチェック
            current_admin_rel = db.query(TKanrishaTenpo).filter(
                and_(TKanrishaTenpo.admin_id == user_id, TKanrishaTenpo.store_id == store_id)
            ).first()
            if not current_admin_rel or current_admin_rel.is_owner != 1:
                flash('管理権限を変更する権限がありません', 'error')
                return redirect(url_for('admin.admins'))
        
        # 対象の管理者と店舗の関係を取得
        admin_rel = db.query(TKanrishaTenpo).filter(
            and_(TKanrishaTenpo.admin_id == admin_id, TKanrishaTenpo.store_id == store_id)
        ).first()
        
        if not admin_rel:
            flash('管理者が見つかりません', 'error')
            return redirect(url_for('admin.admins'))
        
        # 管理権限を切り替え
        admin_rel.can_manage_admins = not admin_rel.can_manage_admins
        db.commit()
        
        admin = db.query(TKanrisha).filter(TKanrisha.id == admin_id).first()
        permission_text = "付与" if admin_rel.can_manage_admins else "前奪"
        flash(f'{admin.name} の管理権限を{permission_text}しました', 'success')
        
        return redirect(url_for('admin.admins'))
    finally:
        db.close()


@bp.route('/admins/new', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_new():
    """店舗管理者新規作成（選択された店舗に追加）"""
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    user_id = session.get('user_id')
    
    if not store_id:
        flash('店舗を選択してください', 'error')
        return redirect(url_for('admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        # 権限チェック
        role = session.get('role')
        if role not in [ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"]]:
            # 店舗管理者の場合は中間テーブルから権限をチェック
            current_admin_rel = db.query(TKanrishaTenpo).filter(
                and_(TKanrishaTenpo.admin_id == user_id, TKanrishaTenpo.store_id == store_id)
            ).first()
            if not current_admin_rel or (current_admin_rel.is_owner != 1 and current_admin_rel.can_manage_admins != 1):
                flash('管理者を作成する権限がありません', 'error')
                return redirect(url_for('admin.admins'))
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')
            store_ids = request.form.getlist('store_ids')
            
            # 店舗管理者の場合は作成元の店舗のみを許可
            if role not in [ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"]]:
                # 作成元以外の店舗が選択されているかチェック
                for sid in store_ids:
                    if int(sid) != store_id:
                        flash('作成元の店舗のみを選択できます', 'error')
                        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                        stores_list = [store]
                        return render_template('admin_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('admin.admins'))
                # 作成元の店舗のみを設定
                store_ids = [str(store_id)]
            else:
                # システム管理者またはテナント管理者の場合は作成元の店舗IDを必ず含める
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
                # 店舗リストのフィルタリング
                if role == ROLES["SYSTEM_ADMIN"] or role == ROLES["TENANT_ADMIN"]:
                    stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
                else:
                    stores_list = [store]
                return render_template('admin_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('admin.admins'))
            
            if not store_ids:
                flash('少なくとも1つの店舗を選択してください', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                # 店舗リストのフィルタリング
                if role == ROLES["SYSTEM_ADMIN"] or role == ROLES["TENANT_ADMIN"]:
                    stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
                else:
                    stores_list = [store]
                return render_template('admin_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('admin.admins'))
            
            if password != password_confirm:
                flash('パスワードが一致しません', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                # 店舗リストのフィルタリング
                if role == ROLES["SYSTEM_ADMIN"] or role == ROLES["TENANT_ADMIN"]:
                    stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
                else:
                    stores_list = [store]
                return render_template('admin_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('admin.admins'))
            
            if len(password) < 8:
                flash('パスワードは8文字以上にしてください', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                # 店舗リストのフィルタリング
                if role == ROLES["SYSTEM_ADMIN"] or role == ROLES["TENANT_ADMIN"]:
                    stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
                else:
                    stores_list = [store]
                return render_template('admin_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('admin.admins'))
            
            # ログインID重複チェック
            existing = db.query(TKanrisha).filter(TKanrisha.login_id == login_id).first()
            if existing:
                flash(f'ログインID "{login_id}" は既に使用されています', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                # 店舗リストのフィルタリング
                if role == ROLES["SYSTEM_ADMIN"] or role == ROLES["TENANT_ADMIN"]:
                    stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
                else:
                    stores_list = [store]
                return render_template('admin_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('admin.admins'))
            
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
            return redirect(url_for('admin.admins'))
        
        # GET: フォーム表示
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        
        # 店舗リストのフィルタリング
        if role == ROLES["SYSTEM_ADMIN"]:
            # システム管理者は全ての店舗を表示
            stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
        elif role == ROLES["TENANT_ADMIN"]:
            # テナント管理者は全ての店舗を表示
            stores_list = db.query(TTenpo).filter(TTenpo.tenant_id == tenant_id).order_by(TTenpo.id).all()
        else:
            # 店舗管理者は作成元の店舗のみを表示
            stores_list = [store]
        
        return render_template('admin_admin_new.html', tenant=tenant, store=store, stores=stores_list, from_store_id=store_id, back_url=url_for('admin.admins'))
    finally:
        db.close()


@bp.route('/admins/invite', methods=['GET', 'POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def admin_invite():
    """店舗管理者を追加（同一テナント内の既存管理者を招待）"""
    tenant_id = session.get('tenant_id')
    store_id = session.get('store_id')
    user_id = session.get('user_id')
    
    if not tenant_id:
        flash('テナントが選択されていません', 'error')
        return redirect(url_for('admin.dashboard'))
    
    if not store_id:
        flash('店舗が選択されていません', 'error')
        return redirect(url_for('admin.dashboard'))
    
    db = SessionLocal()
    
    try:
        # 権限チェック
        role = session.get('role')
        if role not in [ROLES["SYSTEM_ADMIN"], ROLES["TENANT_ADMIN"]]:
            # 店舗管理者の場合は中間テーブルから権限をチェック
            current_admin_rel = db.query(TKanrishaTenpo).filter(
                and_(TKanrishaTenpo.admin_id == user_id, TKanrishaTenpo.store_id == store_id)
            ).first()
            if not current_admin_rel or (current_admin_rel.is_owner != 1 and current_admin_rel.can_manage_admins != 1):
                flash('管理者を招待する権限がありません', 'error')
                return redirect(url_for('admin.admins'))
        
        if request.method == 'POST':
            login_id = request.form.get('login_id', '').strip()
            name = request.form.get('name', '').strip()
            
            # バリデーション
            if not login_id or not name:
                flash('ログインIDと氏名は必須です', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
                return render_template('admin_admin_invite.html', tenant=tenant, store=store)
            
            # 店舗がこのテナントに属しているか確認
            store = db.query(TTenpo).filter(
                and_(TTenpo.id == store_id, TTenpo.tenant_id == tenant_id)
            ).first()
            
            if not store:
                flash('店舗が見つかりません', 'error')
                tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
                return render_template('admin_admin_invite.html', tenant=tenant, store=None)
            
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
                return render_template('admin_admin_invite.html', tenant=tenant, store=store)
            
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
                return render_template('admin_admin_invite.html', tenant=tenant, store=store)
            
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
            return redirect(url_for('admin.admins'))
        
        tenant = db.query(TTenant).filter(TTenant.id == tenant_id).first()
        store = db.query(TTenpo).filter(TTenpo.id == store_id).first()
        return render_template('admin_admin_invite.html', tenant=tenant, store=store)
    finally:
        db.close()


@bp.route('/employees/<int:employee_id>/toggle_active', methods=['POST'])
@require_roles(ROLES["ADMIN"], ROLES["TENANT_ADMIN"], ROLES["SYSTEM_ADMIN"])
def employee_toggle_active(employee_id):
    """従業員の有効/無効を切り替え"""
    db = SessionLocal()
    
    try:
        employee = db.query(TJugyoin).filter(TJugyoin.id == employee_id).first()
        
        if not employee:
            flash('従業員が見つかりません', 'error')
            return redirect(url_for('admin.employees'))
        
        # ステータスを切り替え
        employee.active = not employee.active
        db.commit()
        
        status_text = "有効化" if employee.active else "無効化"
        flash(f'{employee.name} を{status_text}しました', 'success')
        
        return redirect(url_for('admin.employees'))
    finally:
        db.close()
