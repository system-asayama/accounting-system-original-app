# -*- coding: utf-8 -*-
"""
デコレータ
"""

from functools import wraps
from flask import session, redirect, url_for, flash


# ===========================
# 役割定義
# ===========================
ROLES = {
    "SYSTEM_ADMIN": "system_admin",     # 全テナント横断の最高権限
    "TENANT_ADMIN": "tenant_admin",     # テナント単位の管理者
    "ADMIN":        "admin",            # 店舗/拠点などの管理者
    "EMPLOYEE":     "employee",         # 従業員
}


def require_roles(*allowed_roles):
    """指定されたロールのみアクセス可能にするデコレータ"""
    def _decorator(view):
        @wraps(view)
        def _wrapped(*args, **kwargs):
            role = session.get("role")
            if not role or role not in allowed_roles:
                flash("権限がありません。", "warning")
                return redirect(url_for("auth.select_login"))
            return view(*args, **kwargs)
        return _wrapped
    return _decorator


def current_tenant_filter_sql(col_expr: str):
    """
    system_admin 以外は tenant_id で絞る WHERE句 と パラメタを返す。
    col_expr 例: '"T_従業員"."tenant_id"'
    戻り値: (where_sql, params_tuple)
    """
    role = session.get("role")
    tenant_id = session.get("tenant_id")
    if role == ROLES["SYSTEM_ADMIN"]:
        return "1=1", ()
    return f"{col_expr} = %s", (tenant_id,)


def require_app_enabled(app_name):
    """
    指定されたアプリが有効な場合のみアクセス可能にするデコレータ
    
    使用例:
        @bp.route('/apps/survey/')
        @require_app_enabled('survey-app')
        def survey_home():
            return render_template('survey/home.html')
    
    Args:
        app_name: アプリの識別子（AVAILABLE_APPSのname）
    """
    def _decorator(view):
        @wraps(view)
        def _wrapped(*args, **kwargs):
            from app.utils.db import get_db_connection, _sql
            
            # セッションから店舗IDまたはテナントIDを取得
            store_id = session.get('store_id')
            tenant_id = session.get('tenant_id')
            
            if not store_id and not tenant_id:
                flash('店舗またはテナントが選択されていません', 'error')
                return redirect(url_for('auth.select_login'))
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            # アプリが有効かどうかをチェック
            enabled = False
            
            if store_id:
                # 店舗単位のアプリ設定をチェック
                cur.execute(_sql(conn, '''
                    SELECT enabled FROM "T_店舗アプリ設定"
                    WHERE store_id = %s AND app_name = %s
                '''), (store_id, app_name))
                row = cur.fetchone()
                enabled = row[0] if row else True  # デフォルトは有効
            elif tenant_id:
                # テナント単位のアプリ設定をチェック
                cur.execute(_sql(conn, '''
                    SELECT enabled FROM "T_テナントアプリ設定"
                    WHERE tenant_id = %s AND app_name = %s
                '''), (tenant_id, app_name))
                row = cur.fetchone()
                enabled = row[0] if row else True  # デフォルトは有効
            
            conn.close()
            
            if not enabled:
                flash('このアプリは現在利用できません', 'error')
                return redirect(url_for('admin.dashboard'))
            
            return view(*args, **kwargs)
        return _wrapped
    return _decorator
