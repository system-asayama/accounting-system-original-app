# -*- coding: utf-8 -*-
"""
UserOrganizationモデルをmodels.pyに追加するためのスクリプト
"""

# models.pyの適切な位置に以下のコードを追加してください

code_to_add = '''
class UserOrganization(Base):
    """
    ユーザーと組織の多対多関係テーブル
    （tenant_adminが複数の組織を管理する場合に使用）
    """
    __tablename__ = 'user_organizations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    created_at = Column(String(19))  # YYYY-MM-DD HH:MM:SS形式
    
    def __repr__(self):
        return f"<UserOrganization(user_id={self.user_id}, organization_id={self.organization_id})>"
'''

print(code_to_add)
