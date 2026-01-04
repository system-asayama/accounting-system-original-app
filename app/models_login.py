"""
login-system-app用のSQLAlchemyモデル
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from app.db import Base


class TKanrisha(Base):
    """T_管理者テーブル（system_admin / tenant_admin / admin）"""
    __tablename__ = 'T_管理者'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    login_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(50), default='admin')  # system_admin, tenant_admin, admin
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    active = Column(Integer, default=1)
    is_owner = Column(Integer, default=0)
    can_manage_admins = Column(Integer, default=0)
    openai_api_key = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TJugyoin(Base):
    """T_従業員テーブル（employee）"""
    __tablename__ = 'T_従業員'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    login_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(Text, nullable=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=True)
    role = Column(String(50), default='employee')
    active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TTenant(Base):
    """T_テナントテーブル"""
    __tablename__ = 'T_テナント'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    名称 = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    郵便番号 = Column(String(10), nullable=True)
    住所 = Column(String(500), nullable=True)
    電話番号 = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    openai_api_key = Column(String(255), nullable=True)
    有効 = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class TTenpo(Base):
    """T_店舗テーブル"""
    __tablename__ = 'T_店舗'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    名称 = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    郵便番号 = Column(String(10), nullable=True)
    住所 = Column(String(500), nullable=True)
    電話番号 = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    openai_api_key = Column(String(255), nullable=True)
    有効 = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class TKanrishaTenpo(Base):
    """Ｔ_管理者_店舗（多対多）"""
    __tablename__ = 'T_管理者_店舗'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey('T_管理者.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=False)
    is_owner = Column(Integer, default=0, comment='この店舗のオーナーかどうか')
    can_manage_admins = Column(Integer, default=0, comment='店舗管理者を管理する権限')
    created_at = Column(DateTime, server_default=func.now())


class TJugyoinTenpo(Base):
    """T_従業員_店舗（多対多）"""
    __tablename__ = 'T_従業員_店舗'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey('T_従業員.id'), nullable=False)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class TTenantAppSetting(Base):
    """T_テナントアプリ設定"""
    __tablename__ = 'T_テナントアプリ設定'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    app_id = Column(String(255), nullable=False)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())
    openai_api_key = Column(Text, nullable=True)


class TTenpoAppSetting(Base):
    """T_店舗アプリ設定"""
    __tablename__ = 'T_店舗アプリ設定'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey('T_店舗.id'), nullable=False)
    app_id = Column(String(255), nullable=False)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())
    openai_api_key = Column(Text, nullable=True)


class TTenantAdminTenant(Base):
    """T_テナント管理者_テナント中間テーブル"""
    __tablename__ = 'T_テナント管理者_テナント'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey('T_管理者.id'), nullable=False)
    tenant_id = Column(Integer, ForeignKey('T_テナント.id'), nullable=False)
    is_owner = Column(Integer, default=0, comment='このテナントのオーナーかどうか')
    can_manage_tenant_admins = Column(Integer, default=0, comment='テナント管理者を管理する権限')
    created_at = Column(DateTime, server_default=func.now())
    
    # ユニーク制約: 同じ管理者が同じテナントに複数回紐付けられないようにする
    __table_args__ = (
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci', 'extend_existing': True}
    )
