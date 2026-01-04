from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum, Text, Numeric, Date
from sqlalchemy.orm import relationship
import enum

# ベースクラス
class Base(declarative_base()):
    __abstract__ = True
    pass

class AccountItem(Base):
    __tablename__ = 'account_items'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    # CSVの1列目: 勘定科目
    account_name = Column(String(255), nullable=False)
    # CSVの2列目: 表示名（決算書）
    display_name = Column(String(255))
    # CSVの3列目: 小分類
    sub_category = Column(String(255))
    # CSVの4列目: 中分類
    mid_category = Column(String(255))
    # CSVの5列目: 大分類
    major_category = Column(String(255))
    # 流動性分類（流動資産、固定資産、流動負債、固定負債、純資産など）
    liquidity_category = Column(String(50))
    # 流動性配列法のためのソート順（数字が小さいほど流動性が高い）
    liquidity_rank = Column(Integer)
    # P/Lの階段式表示カテゴリ
    pl_category = Column(String(50))
    # P/Lの階段式表示順序
    pl_rank = Column(Integer)
    # B/Sの詳細分類（流動資産、固定資産、投資その他の資産、流動負債、固定負債、資本金、資本剰余金、利益剰余金）
    bs_category = Column(String(50))
    # B/Sの詳細分類の表示順序
    bs_rank = Column(Integer)
    # CSVの6列目: 収入取引相手方勘定科目
    income_counterpart = Column(String(255))
    # CSVの7列目: 支出取引相手方勘定科目
    expense_counterpart = Column(String(255))
    # CSVの8列目: 税区分
    tax_category = Column(String(255))
    # CSVの9列目: ショートカット1
    shortcut1 = Column(String(50))
    # CSVの10列目: ショートカット2
    shortcut2 = Column(String(50))
    # CSVの11列目: 入力候補 (YES/NOをBooleanに変換)
    input_candidate = Column(Boolean, default=True)
    # CSVの12列目: 補助科目優先タグ (空欄/YESをBooleanに変換)
    sub_account_priority_tag = Column(Boolean, default=False)

    def __repr__(self):
        return f"<AccountItem(account_name=\'{self.account_name}\', major_category=\'{self.major_category}\', liquidity_category=\'{self.liquidity_category}\', liquidity_rank={self.liquidity_rank}, pl_category=\'{self.pl_category}\', pl_rank={self.pl_rank})>"

# 既存のUserモデル（仮に存在すると想定して残す）
class ImportTemplate(Base):
    __tablename__ = 'import_templates'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    file_type = Column(String(10), nullable=False) # 'csv' or 'excel'
    mapping_json = Column(Text, nullable=False) # JSON string of column mappings
    skip_rows = Column(Integer, default=0) # スキップするヘッダー行数
    
    def __repr__(self):
        return f"<ImportTemplate(name='{self.name}', file_type='{self.file_type}')>"


class CashBook(Base):
    __tablename__ = 'cash_books'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    # 取引日
    transaction_date = Column(String(10), nullable=False)  # YYYY-MM-DD形式
    # 勘定科目（AccountItemのidを参照）
    account_item_id = Column(Integer, ForeignKey('account_items.id'), nullable=False)
    # 消費税区分（TaxCategoryのidを参照）
    tax_category_id = Column(Integer, ForeignKey('tax_categories.id'))
    # 消費税率
    tax_rate = Column(String(10))  # 例: "8%", "10%"
    # 取引先
    counterparty = Column(String(255))
    # 品目
    item_name = Column(String(255))
    # 部門
    department = Column(String(255))
    # メモタグ
    memo_tag = Column(String(255))
    # 支払口座
    payment_account = Column(String(255))
    # 備考
    remarks = Column(Text)
    # 税込入出金金額（実際の出入金額）
    amount_with_tax = Column(Integer, nullable=False)
    # 税抜金額
    amount_without_tax = Column(Integer)
    # 消費税額
    tax_amount = Column(Integer)
    # 残高
    balance = Column(Integer)
    # 作成日時
    created_at = Column(String(19))  # YYYY-MM-DD HH:MM:SS形式
    # 更新日時
    updated_at = Column(String(19))

    # リレーションシップ
    account_item = relationship("AccountItem", foreign_keys=[account_item_id])
    tax_category = relationship("TaxCategory", foreign_keys=[tax_category_id])

    def __repr__(self):
        return f"<CashBook(transaction_date='{self.transaction_date}', amount_with_tax={self.amount_with_tax})>"


class TaxCategory(Base):
    __tablename__ = 'tax_categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False) # 例: 課対仕入10%

    def __repr__(self):
        return f"<TaxCategory(name='{self.name}')>"


class Account(Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    # 口座名称（例：現金、普通預金、クレジットカード）
    account_name = Column(String(255), nullable=False)
    # 口座種別（例：現金、普通預金、当座預金、クレジットカード、電子決済、売掛金、買掛金）
    # 口座種別（例：cash, bank, credit_card, e_money, receivable, payable）
    account_type = Column(String(50), nullable=False)
    # 決算書表示名
    display_name = Column(String(255))
    # 銀行名
    bank_name = Column(String(255))
    # 支店名
    branch_name = Column(String(255))
    # 口座番号
    account_number = Column(String(50))
    # 口座の勘定科目ID
    account_item_id = Column(Integer, ForeignKey('account_items.id'))
    # メモ
    memo = Column(Text)
    # 出納帳一覧画面での表示フラグ（デフォルトは表示）
    is_visible_in_list = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<Account(account_name='{self.account_name}', account_type='{self.account_type}')>"


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
    created_at = Column(String(19))  # YYYY-MM-DD HH:MM:SS形式
    
    # 更新日時
    updated_at = Column(String(19))
    
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
    created_at = Column(String(19))  # YYYY-MM-DD HH:MM:SS形式
    
    def __repr__(self):
        return f"<UserOrganization(user_id={self.user_id}, organization_id={self.organization_id})>"


class Department(Base):
    __tablename__ = 'departments'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(100), nullable=False)

    def __repr__(self):
        return f"<Department(name='{self.name}')>"


class Counterparty(Base):
    __tablename__ = 'counterparties'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    # 住所、電話番号など、取引先に関する情報を追加可能

    def __repr__(self):
        return f"<Counterparty(name='{self.name}')>"


class Item(Base):
    __tablename__ = 'items'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    # 単価、説明など、品目に関する情報を追加可能

    def __repr__(self):
        return f"<Item(name='{self.name}')>"


class ProjectTag(Base):
    __tablename__ = 'project_tags'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    # 案件タグ名
    tag_name = Column(String(100), nullable=False)
    # 説明
    description = Column(Text)
    # 有効/無効
    is_active = Column(Integer, default=1)
    # 作成日時
    created_at = Column(String(50), nullable=False)
    # 更新日時
    updated_at = Column(String(50), nullable=False)

    def __repr__(self):
        return f"<ProjectTag(tag_name='{self.tag_name}')>"


class MemoTag(Base):
    __tablename__ = 'memo_tags'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(100), nullable=False)

    def __repr__(self):
        return f"<MemoTag(name='{self.name}')>"


class JournalEntry(Base):
    __tablename__ = 'journal_entries'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    # 伝票日付
    transaction_date = Column(String(10), nullable=False)  # YYYY-MM-DD形式
    # 借方勘定科目（AccountItemのidを参照）
    debit_account_item_id = Column(Integer, ForeignKey('account_items.id'), nullable=False)
    # 借方金額
    debit_amount = Column(Integer, nullable=False)
    # 借方税区分（TaxCategoryのidを参照）
    debit_tax_category_id = Column(Integer, ForeignKey('tax_categories.id'))
    # 貸方勘定科目（AccountItemのidを参照）
    credit_account_item_id = Column(Integer, ForeignKey('account_items.id'), nullable=False)
    # 貸方金額
    credit_amount = Column(Integer, nullable=False)
    # 貸方税区分（TaxCategoryのidを参照）
    credit_tax_category_id = Column(Integer, ForeignKey('tax_categories.id'))
    # 摘要
    summary = Column(Text)
    # 備考
    remarks = Column(Text)
    # 作成日時
    created_at = Column(String(19))  # YYYY-MM-DD HH:MM:SS形式
    # 更新日時
    updated_at = Column(String(19))

    # リレーションシップ
    debit_account_item = relationship("AccountItem", foreign_keys=[debit_account_item_id], backref="debit_entries")
    credit_account_item = relationship("AccountItem", foreign_keys=[credit_account_item_id], backref="credit_entries")

    def __repr__(self):
        return f"<JournalEntry(transaction_date='{self.transaction_date}', debit_amount={self.debit_amount}, credit_amount={self.credit_amount})>"


class Template(Base):
    __tablename__ = 'templates'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    # テンプレート名
    name = Column(String(255), nullable=False)
    # 勘定科目（AccountItemのidを参照）
    account_item_id = Column(Integer, ForeignKey('account_items.id'), nullable=False)
    # 消費税区分（TaxCategoryのidを参照）
    tax_category_id = Column(Integer, ForeignKey('tax_categories.id'))
    # 取引先
    counterparty = Column(String(255))
    # 品目
    item_name = Column(String(255))
    # 部門
    department = Column(String(255))
    # メモタグ
    memo_tag = Column(String(255))
    # 備考
    remarks = Column(Text)
    # 税込入出金金額（金額は保存しないが、テンプレートの種別として金額の方向を保持する）
    # 0: 支出, 1: 収入
    transaction_type = Column(Integer, nullable=False)
    # 作成日時
    created_at = Column(String(19))  # YYYY-MM-DD HH:MM:SS形式
    # 更新日時
    updated_at = Column(String(19))

    # リレーションシップ
    account_item = relationship("AccountItem", foreign_keys=[account_item_id])
    tax_category = relationship("TaxCategory", foreign_keys=[tax_category_id])

    def __repr__(self):
        return f"<Template(name='{self.name}', transaction_type={self.transaction_type})>"


class CashBookMaster(Base):
    __tablename__ = 'cash_book_masters'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    # 出納帳名
    name = Column(String(255), nullable=False)
    # 説明
    description = Column(Text)
    # 作成日時
    created_at = Column(String(19))  # YYYY-MM-DD HH:MM:SS形式
    # 更新日時
    updated_at = Column(String(19))
    # 一覧表示
    is_display = Column(Integer, default=1)

    def __repr__(self):
        return f"<CashBookMaster(name='{self.name}')>"



class FiscalPeriod(Base):
    __tablename__ = 'fiscal_periods'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    # 会計期間名（例: 2024年度、第5期など）
    name = Column(String(255), nullable=False)
    # 開始日（YYYY-MM-DD形式）
    start_date = Column(String(10), nullable=False)
    # 終了日（YYYY-MM-DD形式）
    end_date = Column(String(10), nullable=False)
    # 事業種別（individual: 個人, corporate: 法人）
    business_type = Column(String(20), nullable=False, default='corporate')
    # ステータス（open: 進行中, closed: 締め済み）
    status = Column(String(20), nullable=False, default='open')
    # 期数（任意）
    period_number = Column(Integer)
    # 備考
    notes = Column(Text)
    # 作成日時
    created_at = Column(String(19))  # YYYY-MM-DD HH:MM:SS形式
    # 更新日時
    updated_at = Column(String(19))

    def __repr__(self):
        return f"<FiscalPeriod(name='{self.name}', start_date='{self.start_date}', end_date='{self.end_date}')>"


# ========== 事業所マスター ==========
class Organization(Base):
    __tablename__ = 'organizations'

    id = Column(Integer, primary_key=True)
    # 事業所名（法人名または個人名）
    name = Column(String(255), nullable=False)
    # 事業所コード
    code = Column(String(50))
    # 事業種別（individual: 個人, corporate: 法人）
    business_type = Column(String(20), nullable=False, default='corporate')
    # 郵便番号
    postal_code = Column(String(10))
    # 住所
    address = Column(String(500))
    # 電話番号
    phone = Column(String(20))
    # FAX番号
    fax = Column(String(20))
    # メールアドレス
    email = Column(String(255))
    # 代表者名
    representative = Column(String(255))
    # 設立日/開業日（YYYY-MM-DD形式）
    established_date = Column(String(10))
    # 備考
    notes = Column(Text)
    # 作成日時
    created_at = Column(String(19))  # YYYY-MM-DD HH:MM:SS形式
    # 更新日時
    updated_at = Column(String(19))

    def __repr__(self):
        return f"<Organization(name='{self.name}', code='{self.code}', business_type='{self.business_type}')>"


# ========== 取引明細インポート ==========
class ImportedTransaction(Base):
    __tablename__ = 'imported_transactions'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    # インポート元口座名 (Account.account_nameと一致)
    account_name = Column(String(255), nullable=False)
    # 取引日
    transaction_date = Column(String(10), nullable=False) # YYYY-MM-DD
    # 摘要/内容
    description = Column(Text)
    # 入金金額
    income_amount = Column(Integer, default=0)
    # 出金金額
    expense_amount = Column(Integer, default=0)
    # 処理ステータス (0:未処理, 1:処理済み)
    status = Column(Integer, default=0)
    # 処理済みの場合の仕訳ID
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id'), nullable=True)
    # 登録された勘定科目ID
    account_item_id = Column(Integer, ForeignKey('account_items.id'), nullable=True)
    # インポート日時
    imported_at = Column(String(19))

    def __repr__(self):
        return f"<ImportedTransaction(account='{self.account_name}', date='{self.transaction_date}', status={self.status})>"

class GeneralLedger(Base):
    __tablename__ = 'general_ledger'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'))
    transaction_date = Column(String(10))
    debit_account_item_id = Column(Integer, ForeignKey('account_items.id'))
    debit_amount = Column(Integer)
    debit_tax_category_id = Column(Integer, ForeignKey('tax_categories.id'), nullable=True)
    credit_account_item_id = Column(Integer, ForeignKey('account_items.id'))
    credit_amount = Column(Integer)
    credit_tax_category_id = Column(Integer, ForeignKey('tax_categories.id'), nullable=True)
    summary = Column(String(255), nullable=True)
    remarks = Column(String(255), nullable=True)
    source_type = Column(String(50))
    source_id = Column(Integer, nullable=True)
    created_at = Column(String(19), nullable=True)
    updated_at = Column(String(19), nullable=True)
    counterparty_id = Column(Integer, ForeignKey('counterparties.id'), nullable=True)
    department_id = Column(Integer, ForeignKey('departments.id'), nullable=True)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=True)
    project_tag_id = Column(Integer, ForeignKey('project_tags.id'), nullable=True)
    memo_tag_id = Column(Integer, ForeignKey('memo_tags.id'), nullable=True)
    
    # リレーションシップ
    debit_account_item = relationship('AccountItem', foreign_keys=[debit_account_item_id])
    credit_account_item = relationship('AccountItem', foreign_keys=[credit_account_item_id])
    counterparty = relationship('Counterparty', foreign_keys=[counterparty_id])
    department = relationship('Department', foreign_keys=[department_id])
    item = relationship('Item', foreign_keys=[item_id])
    project_tag = relationship('ProjectTag', foreign_keys=[project_tag_id])
    memo_tag = relationship('MemoTag', foreign_keys=[memo_tag_id])
    
    def __repr__(self):
        return f"<GeneralLedger(date='{self.transaction_date}', debit={self.debit_amount}, credit={self.credit_amount})>"


class OpeningBalance(Base):
    """期首残高テーブル"""
    __tablename__ = 'opening_balances'

    id = Column(Integer, primary_key=True)
    # 事業所ID
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    # 会計期間ID
    fiscal_period_id = Column(Integer, ForeignKey('fiscal_periods.id'), nullable=False)
    # 勘定科目ID
    account_item_id = Column(Integer, ForeignKey('account_items.id'), nullable=False)
    # 借方金額
    debit_amount = Column(Numeric(15, 2), default=0, nullable=False)
    # 貸方金額
    credit_amount = Column(Numeric(15, 2), default=0, nullable=False)
    # 作成日時
    created_at = Column(String(19), nullable=True)
    # 更新日時
    updated_at = Column(String(19), nullable=True)

    # リレーションシップ
    organization = relationship('Organization', foreign_keys=[organization_id])
    fiscal_period = relationship('FiscalPeriod', foreign_keys=[fiscal_period_id])
    account_item = relationship('AccountItem', foreign_keys=[account_item_id])

    def __repr__(self):
        return f"<OpeningBalance(fiscal_period_id={self.fiscal_period_id}, account_item_id={self.account_item_id}, debit={self.debit_amount}, credit={self.credit_amount})>"
