# -*- coding: utf-8 -*-
"""
ユーティリティモジュール
"""

from .db import get_db, get_db_connection, init_schema, _is_pg, _sql
from .security import login_user, admin_exists, get_csrf, is_owner, can_manage_system_admins, is_tenant_owner, can_manage_tenant_admins
from .decorators import require_roles, current_tenant_filter_sql, require_app_enabled, ROLES
from .api_key import get_openai_api_key, get_openai_client

__all__ = [
    'get_db',
    'get_db_connection',
    'init_schema',
    '_is_pg',
    '_sql',
    'login_user',
    'admin_exists',
    'get_csrf',
    'is_owner',
    'can_manage_system_admins',
    'is_tenant_owner',
    'can_manage_tenant_admins',
    'require_roles',
    'current_tenant_filter_sql',
    'require_app_enabled',
    'ROLES',
    'get_openai_api_key',
    'get_openai_client',
]
