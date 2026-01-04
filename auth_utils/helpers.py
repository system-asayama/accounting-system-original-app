# -*- coding: utf-8 -*-
"""
認証システム用のヘルパー関数
"""
from functools import wraps
from flask import session, redirect, url_for, flash
from db import SessionLocal

# ロール定義
ROLES = {
    "SYSTEM_ADMIN": "system_admin",
    "TENANT_ADMIN": "tenant_admin",
    "ADMIN": "admin",
    "EMPLOYEE": "employee"
}

def login_required(f):
    """ログインが必要なルートに付与するデコレーター"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('ログインが必要です。', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    """特定のロールが必要なルートに付与するデコレーター"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('ログインが必要です。', 'error')
                return redirect(url_for('auth.login'))
            
            user_role = session.get('role')
            if user_role not in roles:
                flash('アクセス権限がありません。', 'error')
                return redirect(url_for('auth.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_current_user():
    """現在ログイン中のユーザー情報を取得"""
    if 'user_id' not in session:
        return None
    
    from models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == session['user_id']).first()
        return user
    finally:
        db.close()

def get_current_organization():
    """現在ログイン中のユーザーの組織情報を取得"""
    if 'organization_id' not in session:
        return None
    
    from models import Organization
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.id == session['organization_id']).first()
        return org
    finally:
        db.close()

def admin_exists():
    """管理者が存在するかチェック"""
    from models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.role.in_([
            ROLES["SYSTEM_ADMIN"],
            ROLES["TENANT_ADMIN"],
            ROLES["ADMIN"]
        ])).first()
        return user is not None
    finally:
        db.close()

def login_user(user):
    """ユーザーをセッションにログイン"""
    from models import Organization
    
    session['user_id'] = user.id
    session['login_id'] = user.login_id
    session['name'] = user.name
    session['role'] = user.role
    session['organization_id'] = user.organization_id
    session['is_owner'] = user.is_owner
    session['can_manage_admins'] = user.can_manage_admins
    
    # 組織名も取得して保存
    if user.organization_id:
        db = SessionLocal()
        try:
            org = db.query(Organization).filter(Organization.id == user.organization_id).first()
            if org:
                session['organization_name'] = org.name
        finally:
            db.close()

def logout_user():
    """ユーザーをログアウト"""
    session.clear()
