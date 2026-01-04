# -*- coding: utf-8 -*-
"""
認証関連ルート
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from app.utils import get_db, _sql, login_user, admin_exists, ROLES

bp = Blueprint('auth', __name__)


@bp.route('/')
def index():
    """トップページ - ロール別リダイレクト"""
    role = session.get("role")
    if role == ROLES["SYSTEM_ADMIN"]:
        return redirect(url_for('system_admin.mypage'))
    if role == ROLES["TENANT_ADMIN"]:
        return redirect(url_for('tenant_admin.dashboard'))
    if role == ROLES["ADMIN"]:
        return redirect(url_for('admin.dashboard'))
    if role == ROLES["EMPLOYEE"]:
        return redirect(url_for('employee.mypage'))
    return redirect(url_for('auth.select_login'))


@bp.route('/select_login')
def select_login():
    """ログイン選択画面"""
    # 管理者が未作成なら、初回セットアップへ誘導
    if not admin_exists():
        return redirect(url_for('auth.first_admin_setup'))
    return render_template('login_choice.html')


@bp.route('/first_admin_setup', methods=['GET', 'POST'])
def first_admin_setup():
    """初回セットアップ（最初の sysadmin 作成）"""
    # すでに管理者がいれば、このページは出さない
    if admin_exists():
        return redirect(url_for('auth.select_login'))

    error = None
    if request.method == 'POST':
        # --- CSRF チェック ---
        form_token = request.form.get('csrf_token', '')
        if not form_token or form_token != session.get('csrf_token'):
            error = "セッションが無効です。もう一度お試しください。"
        else:
            name = (request.form.get('name') or '').strip()
            login_id = (request.form.get('login_id') or '').strip()
            email = (request.form.get('email') or '').strip()
            password = request.form.get('password') or ''
            confirm = request.form.get('confirm') or ''

            # --- 入力バリデーション ---
            if not name or not login_id or not email or not password or not confirm:
                error = "すべての項目を入力してください。"
            elif len(password) < 8:
                error = "パスワードは8文字以上にしてください。"
            elif password != confirm:
                error = "パスワード（確認）が一致しません。"

            if not error:
                # 既存重複確認 & 作成
                conn = get_db()
                try:
                    cur = conn.cursor()
                    # 同じ login_id が無いか
                    sql_chk = _sql(conn, 'SELECT 1 FROM "T_管理者" WHERE login_id=%s')
                    cur.execute(sql_chk, (login_id,))
                    exists = cur.fetchone()
                    if exists:
                        error = "このログインIDはすでに使用されています。"
                    else:
                        ph = generate_password_hash(password)
                        sql_ins = _sql(conn, '''
                            INSERT INTO "T_管理者"(login_id, name, email, password_hash, role, tenant_id, is_owner, can_manage_admins)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ''')
                        cur.execute(sql_ins, (login_id, name, email, ph, ROLES["SYSTEM_ADMIN"], None, 1, 1))
                        from app.utils.db import _is_pg
                        if not _is_pg(conn):
                            conn.commit()
                        flash("システム管理者を作成しました。ログインできます。", "success")
                        return redirect(url_for('auth.select_login'))
                finally:
                    try:
                        conn.close()
                    except:
                        pass

    return render_template('first_setup.html', error=error)


@bp.route('/system_admin_login', methods=['GET','POST'])
def system_admin_login():
    """システム管理者ログイン"""
    error = None
    if request.method == 'POST':
        login_id = request.form.get('login_id','').strip()
        password = request.form.get('password','')
        conn = get_db()
        try:
            cur = conn.cursor()
            sql = _sql(conn, 'SELECT id, name, password_hash, tenant_id, is_owner FROM "T_管理者" WHERE login_id=%s AND role=%s')
            cur.execute(sql, (login_id, ROLES["SYSTEM_ADMIN"]))
            row = cur.fetchone()
            if row and check_password_hash(row[2], password):
                user_id, name, tenant_id, is_owner = row[0], row[1], row[3], row[4]
                login_user(user_id, name, ROLES["SYSTEM_ADMIN"], tenant_id)
                session['is_owner'] = (is_owner == 1)
                return redirect(url_for('system_admin.mypage'))
            error = "ログインIDまたはパスワードが違います"
        finally:
            try: conn.close()
            except: pass
    return render_template('sysadmin_login.html', error=error)


@bp.route('/tenant_admin_login', methods=['GET','POST'])
def tenant_admin_login():
    """テナント管理者ログイン"""
    error = None
    if request.method == 'POST':
        login_id = request.form.get('login_id','').strip()
        password = request.form.get('password','')
        conn = get_db()
        try:
            cur = conn.cursor()
            sql = _sql(conn, 'SELECT id, name, password_hash, tenant_id, is_owner FROM "T_管理者" WHERE login_id=%s AND role=%s')
            cur.execute(sql, (login_id, ROLES["TENANT_ADMIN"]))
            row = cur.fetchone()
            if row and check_password_hash(row[2], password):
                user_id, name, tenant_id, is_owner = row[0], row[1], row[3], row[4]
                login_user(user_id, name, ROLES["TENANT_ADMIN"], tenant_id)
                session['is_owner'] = (is_owner == 1)
                return redirect(url_for('tenant_admin.mypage'))
            else:
                error = "ログインIDまたはパスワードが違います"
        finally:
            try: conn.close()
            except: pass
    return render_template('tenant_admin_login.html', error=error)


@bp.route('/admin_login', methods=['GET','POST'])
def admin_login():
    """管理者ログイン"""
    error = None
    if request.method == 'POST':
        login_id = request.form.get('login_id','').strip()
        password = request.form.get('password','')
        conn = get_db()
        try:
            cur = conn.cursor()
            sql = _sql(conn, 'SELECT id, name, password_hash, tenant_id, is_owner FROM "T_管理者" WHERE login_id=%s AND role=%s')
            cur.execute(sql, (login_id, ROLES["ADMIN"]))
            row = cur.fetchone()
            if row and check_password_hash(row[2], password):
                user_id, name, tenant_id, is_owner = row[0], row[1], row[3], row[4]
                if not tenant_id:
                    error = "この管理者にはテナントが紐づいていません。"
                else:
                    login_user(user_id, name, ROLES["ADMIN"], tenant_id)
                    session['store_id'] = None  # 店舗未選択
                    session['is_owner'] = (is_owner == 1)
                    return redirect(url_for('admin.mypage'))
            else:
                error = "ログインIDまたはパスワードが違います"
        finally:
            try: conn.close()
            except: pass
    return render_template('store_login.html', error=error)


@bp.route('/employee_login', methods=['GET','POST'])
def employee_login():
    """従業員ログイン"""
    error = None
    if request.method == 'POST':
        login_id = request.form.get('login_id','').strip()  # email でも login_id でもOK
        password = request.form.get('password','')
        conn = get_db()
        try:
            cur = conn.cursor()
            sql = _sql(conn, 'SELECT id, name, password_hash, tenant_id FROM "T_従業員" WHERE login_id=%s OR email=%s')
            cur.execute(sql, (login_id, login_id))
            row = cur.fetchone()
            if row:
                user_id, name, hashv, tenant_id = row[0], row[1], row[2], row[3]
                # 初回パス未設定 + 123456 を許容
                if (not hashv or hashv == '') and password == '123456':
                    login_user(user_id, name, ROLES["EMPLOYEE"], tenant_id, is_employee=True)
                    session['store_id'] = None  # 店舗未選択
                    return redirect(url_for('employee.mypage'))
                if hashv and check_password_hash(hashv, password):
                    login_user(user_id, name, ROLES["EMPLOYEE"], tenant_id, is_employee=True)
                    session['store_id'] = None  # 店舗未選択
                    return redirect(url_for('employee.mypage'))
            error = "ログインIDまたはパスワードが違います"
        finally:
            try: conn.close()
            except: pass
    return render_template('staff_login.html', error=error)


@bp.route('/staff_login', methods=['GET','POST'])
def staff_login():
    """既存互換：従業員ログイン（/staff_login）"""
    return redirect(url_for('auth.employee_login'))


@bp.route('/logout')
def logout():
    """ログアウト"""
    session.clear()
    return redirect(url_for('auth.select_login'))


# ========================================
# ルートエイリアス（元のapp.pyとの互換性）
# ========================================

@bp.route('/system_admin')
def system_admin_redirect():
    """元のapp.pyとの互換性のため /system_admin → /system_admin/ へリダイレクト"""
    return redirect(url_for('system_admin.mypage'))


@bp.route('/tenant_admin')
def tenant_admin_redirect():
    """元のapp.pyとの互換性のため /tenant_admin → /tenant_admin/ へリダイレクト"""
    return redirect(url_for('tenant_admin.dashboard'))


@bp.route('/admin')
def admin_redirect():
    """元のapp.pyとの互換性のため /admin → /admin/ へリダイレクト"""
    return redirect(url_for('admin.dashboard'))


@bp.route('/select_tenant', methods=['GET', 'POST'])
def select_tenant():
    """テナント選択画面"""
    user_id = session.get('temp_user_id')
    name = session.get('temp_name')
    role = session.get('temp_role')
    
    if not user_id or role != ROLES["TENANT_ADMIN"]:
        return redirect(url_for('auth.tenant_admin_login'))
    
    conn = get_db()
    try:
        cur = conn.cursor()
        
        if request.method == 'POST':
            tenant_id = request.form.get('tenant_id')
            if tenant_id:
                # セッションをクリアして正式にログイン
                session.pop('temp_user_id', None)
                session.pop('temp_name', None)
                session.pop('temp_role', None)
                login_user(user_id, name, role, int(tenant_id))
                return redirect(url_for('tenant_admin.dashboard'))
        
        # 所属テナント一覧を取得
        sql = _sql(conn, '''
            SELECT t.id, t.名称, t.slug
            FROM "T_テナント" t
            INNER JOIN "T_テナント管理者_テナント" tt ON t.id = tt.tenant_id
            WHERE tt.tenant_admin_id = %s AND t.有効 = 1
            ORDER BY t.名称
        ''')
        cur.execute(sql, (user_id,))
        tenants = []
        for row in cur.fetchall():
            tenants.append({
                'id': row[0],
                '名称': row[1],
                'slug': row[2]
            })
        
        return render_template('select_tenant.html', tenants=tenants)
    finally:
        try: conn.close()
        except: pass


@bp.route('/select_store', methods=['GET', 'POST'])
def select_store():
    """店舗選択画面"""
    user_id = session.get('temp_user_id')
    name = session.get('temp_name')
    tenant_id = session.get('temp_tenant_id')
    role = session.get('temp_role')
    role_param = request.args.get('role', 'admin')
    
    if not user_id or not tenant_id:
        if role_param == 'employee':
            return redirect(url_for('auth.employee_login'))
        else:
            return redirect(url_for('auth.admin_login'))
    
    conn = get_db()
    try:
        cur = conn.cursor()
        
        if request.method == 'POST':
            store_id = request.form.get('store_id')
            if store_id:
                # セッションをクリアして正式にログイン
                session.pop('temp_user_id', None)
                session.pop('temp_name', None)
                session.pop('temp_tenant_id', None)
                session.pop('temp_role', None)
                
                if role == ROLES["EMPLOYEE"]:
                    login_user(user_id, name, role, tenant_id, is_employee=True)
                    session['store_id'] = int(store_id)
                    return redirect(url_for('employee.mypage'))
                else:
                    login_user(user_id, name, role, tenant_id)
                    session['store_id'] = int(store_id)
                    return redirect(url_for('admin.dashboard'))
        
        # 所属店舗一覧を取得
        if role == ROLES["EMPLOYEE"]:
            sql = _sql(conn, '''
                SELECT s.id, s.名称, s.slug
                FROM "T_店舗" s
                INNER JOIN "T_従業員_店舗" es ON s.id = es.store_id
                WHERE es.employee_id = %s AND s.tenant_id = %s AND s.有効 = 1
                ORDER BY s.名称
            ''')
        else:
            sql = _sql(conn, '''
                SELECT s.id, s.名称, s.slug
                FROM "T_店舗" s
                INNER JOIN "T_管理者_店舗" ams ON s.id = ams.store_id
                WHERE ams.admin_id = %s AND s.tenant_id = %s AND s.有効 = 1
                ORDER BY s.名称
            ''')
        
        cur.execute(sql, (user_id, tenant_id))
        stores = []
        for row in cur.fetchall():
            stores.append({
                'id': row[0],
                '名称': row[1],
                'slug': row[2]
            })
        
        return render_template('select_store.html', stores=stores)
    finally:
        try: conn.close()
        except: pass
