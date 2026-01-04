# -*- coding: utf-8 -*-
"""
OpenAI APIキー取得ユーティリティ
"""

import os
from .db import get_db_connection, _sql


def get_openai_api_key(store_id=None, tenant_id=None, app_name=None):
    """
    OpenAI APIキーを階層的に取得
    
    優先順位:
    1. 店舗アプリ設定 (store_id + app_name)
    2. 店舗設定 (store_id)
    3. テナントアプリ設定 (tenant_id + app_name)
    4. テナント設定 (tenant_id)
    5. システム管理者設定 (T_管理者のrole='system_admin'の最初のユーザー)
    6. 環境変数 (OPENAI_API_KEY)
    
    Args:
        store_id: 店舗ID (オプション)
        tenant_id: テナントID (オプション)
        app_name: アプリ名 (オプション)
    
    Returns:
        str: APIキー、見つからない場合はNone
    """
    api_key = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. 店舗アプリ設定のキーを確認
        if store_id and app_name:
            cur.execute(_sql(conn, '''
                SELECT openai_api_key, store_id 
                FROM "T_店舗アプリ設定" 
                WHERE store_id = %s AND app_name = %s
            '''), (store_id, app_name))
            result = cur.fetchone()
            if result and result[0]:
                conn.close()
                return result[0]
        
        # 2. 店舗設定のキーを確認
        if store_id:
            cur.execute(_sql(conn, '''
                SELECT openai_api_key, tenant_id 
                FROM "T_店舗" 
                WHERE id = %s
            '''), (store_id,))
            result = cur.fetchone()
            if result:
                if result[0]:  # 店舗にAPIキーが設定されている
                    conn.close()
                    return result[0]
                # 店舗にキーがない場合、tenant_idを取得
                if not tenant_id and result[1]:
                    tenant_id = result[1]
        
        # 3. テナントアプリ設定のキーを確認
        if tenant_id and app_name:
            cur.execute(_sql(conn, '''
                SELECT openai_api_key 
                FROM "T_テナントアプリ設定" 
                WHERE tenant_id = %s AND app_name = %s
            '''), (tenant_id, app_name))
            result = cur.fetchone()
            if result and result[0]:
                conn.close()
                return result[0]
        
        # 4. テナント設定のキーを確認
        if tenant_id:
            cur.execute(_sql(conn, '''
                SELECT openai_api_key 
                FROM "T_テナント" 
                WHERE id = %s
            '''), (tenant_id,))
            result = cur.fetchone()
            if result and result[0]:
                conn.close()
                return result[0]
        
        # 5. システム管理者設定のキーを確認
        cur.execute(_sql(conn, '''
            SELECT openai_api_key 
            FROM "T_管理者" 
            WHERE role = %s AND openai_api_key IS NOT NULL
            ORDER BY id 
            LIMIT 1
        '''), ('system_admin',))
        result = cur.fetchone()
        if result and result[0]:
            conn.close()
            return result[0]
        
        conn.close()
    except Exception as e:
        print(f"Error getting OpenAI API key from database: {e}")
    
    # 6. 環境変数を確認
    api_key = os.environ.get('OPENAI_API_KEY')
    
    return api_key


def get_openai_client(store_id=None, tenant_id=None, app_name=None):
    """
    OpenAIクライアントを取得
    
    Args:
        store_id: 店舗ID (オプション)
        tenant_id: テナントID (オプション)
        app_name: アプリ名 (オプション)
    
    Returns:
        OpenAI: OpenAIクライアント、APIキーが見つからない場合はNone
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("Error: openai package is not installed")
        return None
    
    api_key = get_openai_api_key(store_id=store_id, tenant_id=tenant_id, app_name=app_name)
    
    if not api_key:
        print("Error: OpenAI API key not found")
        return None
    
    return OpenAI(api_key=api_key, base_url='https://api.openai.com/v1')
