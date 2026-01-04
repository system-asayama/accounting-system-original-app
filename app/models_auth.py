# -*- coding: utf-8 -*-
"""
認証システム用のモデル定義
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base

class User(Base):
    """
    ユーザーテーブル（管理者・従業員の統合）
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    login_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    # ロール: system_admin, tenant_admin, admin, employee
    role = Column(String(50), nullable=False, default='admin')
    
    # 所属組織（テナント）ID
    organization_id = Column(Integer, ForeignKey('organizations.id'))
    
    # アカウント有効フラグ
    active = Column(Boolean, default=True)
    
    # オーナー権限（組織の所有者）
    is_owner = Column(Boolean, default=False)
    
    # 管理者管理権限（他の管理者を管理できる）
    can_manage_admins = Column(Boolean, default=False)
    
    # OpenAI APIキー（オプション）
    openai_api_key = Column(Text)
    
    # 作成日時
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 更新日時
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<User(login_id='{self.login_id}', name='{self.name}', role='{self.role}')>"


class UserOrganization(Base):
    """
    ユーザーと組織の多対多関係テーブル
    （tenant_adminが複数の組織を管理する場合に使用）
    """
    __tablename__ = 'user_organizations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<UserOrganization(user_id={self.user_id}, organization_id={self.organization_id})>"
