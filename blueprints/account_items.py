"""
account_items Blueprint
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from db import SessionLocal, engine
from models import Base, AccountItem, CashBook, ImportTemplate, Account, TaxCategory, JournalEntry, Department, Counterparty, Item, ProjectTag, MemoTag, CashBookMaster, FiscalPeriod, Organization, ImportedTransaction, GeneralLedger, OpeningBalance, Template, User, UserOrganization
from app.models_login import TKanrisha, TJugyoin, TTenant, TTenpo, TTenantAdminTenant, TKanrishaTenpo, TJugyoinTenpo, TTenantAppSetting, TTenpoAppSetting
import os
from datetime import datetime
import json
from import_utils import ImportProcessor
from functools import wraps
import csv
import io

bp = Blueprint('account_items', __name__, url_prefix='')

# ヘルパー関数
def login_required(f):
    """ログインが必要なルートに付与するデコレーター"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if 'organization_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_organization():
    """現在ログイン中の事業所情報を取得"""
    if 'organization_id' not in session:
        return None
    db = SessionLocal()
    org = db.query(Organization).filter(Organization.id == session['organization_id']).first()
    db.close()
    return org

def get_current_organization_id():
    """現在ログイン中の事業所IDを取得"""
    return session.get('organization_id')


@bp.route('/api/account-items/all', methods=['GET'])
@login_required
def get_all_account_items():
    db = SessionLocal()
    try:
        # 勘定科目を取得
        items = db.query(AccountItem).filter(
            AccountItem.organization_id == session['organization_id']
        ).order_by(AccountItem.major_category.asc(), AccountItem.account_name.asc()).all()
        
        account_items_list = []
        for item in items:
            account_items_list.append({
                'id': item.id,
                'account_name': item.account_name,
                'display_name': item.display_name,
                'major_category': item.major_category,
                'is_account': False  # 勘定科目であることを示す
            })
        
        # 口座を取得して追加
        accounts = db.query(Account).filter(
            Account.organization_id == session['organization_id']
        ).all()
        
        for account in accounts:
            # 口座に対応する勘定科目を取得
            account_item = db.query(AccountItem).filter(
                AccountItem.id == account.account_item_id
            ).first()
            
            if account_item:
                account_items_list.append({
                    'id': f'account_{account.id}',  # 口座IDにプレフィックスを付ける
                    'account_name': account.account_name,  # 具体的な口座名（例：三井住友銀行 普通預金）
                    'display_name': account.account_name,
                    'major_category': '口座',  # カテゴリを「口座」に設定
                    'is_account': True,  # 口座であることを示す
                    'account_item_id': account.account_item_id  # 対応する勘定科目ID
                })
            
        return jsonify({'success': True, 'account_items': account_items_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 口座データ取得API


@bp.route('/account-items', methods=['GET'])
@login_required
def account_items_list():
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '', type=str)
        page = request.args.get('page', 1, type=int)
        category_filter = request.args.get('category', '', type=str)  # 大分類フィルタ
        mid_filter = request.args.get('mid', '', type=str)  # 中分類フィルタ
        sub_filter = request.args.get('sub', '', type=str)  # 小分類フィルタ
        per_page = 20
        
        query = db.query(AccountItem).filter(AccountItem.organization_id == session['organization_id'])
        
        # 大分類フィルタを適用
        if category_filter:
            query = query.filter(AccountItem.major_category == category_filter)
        
        # 中分類フィルタを適用
        if mid_filter:
            query = query.filter(AccountItem.mid_category == mid_filter)
        
        # 小分類フィルタを適用
        if sub_filter:
            query = query.filter(AccountItem.sub_category == sub_filter)
        
        # 検索クエリを適用
        if search_query:
            query = query.filter(
                (AccountItem.account_name.ilike(f'%{search_query}%')) |
                (AccountItem.display_name.ilike(f'%{search_query}%'))
            )
        
        total_items = query.count()
        total_pages = (total_items + per_page - 1) // per_page
        
        offset = (page - 1) * per_page
        # 流動性配列順にソート: 大分類 → 中分類 → 小分類 → bs_rank → 勘定科目名
        from sqlalchemy import case
        
        # 大分類の順序（資産→負債→純資産→损益）
        major_order = case(
            (AccountItem.major_category == '資産', 1),
            (AccountItem.major_category == '負債', 2),
            (AccountItem.major_category == '純資産', 3),
            (AccountItem.major_category == '损益', 4),
            else_=9
        )
        
        # 中分類の順序
        mid_order = case(
            # 資産
            (AccountItem.mid_category == '流動資産', 1),
            (AccountItem.mid_category == '固定資産', 2),
            (AccountItem.mid_category == '繰延資産', 3),
            # 負債
            (AccountItem.mid_category == '流動負債', 1),
            (AccountItem.mid_category == '固定負債', 2),
            # 純資産
            (AccountItem.mid_category == '資本金', 1),
            (AccountItem.mid_category == '資本剰余金', 2),
            (AccountItem.mid_category == '利益剰余金', 3),
            (AccountItem.mid_category == '自己株式', 4),
            (AccountItem.mid_category == '評価換算差額等', 5),
            (AccountItem.mid_category == '新株予約権', 6),
            # 損益
            (AccountItem.mid_category == '売上高', 1),
            (AccountItem.mid_category == '売上原価', 2),
            (AccountItem.mid_category == '販売費及び一般管理費', 3),
            (AccountItem.mid_category == '営業外収益', 4),
            (AccountItem.mid_category == '営業外費用', 5),
            (AccountItem.mid_category == '特別利益', 6),
            (AccountItem.mid_category == '特別損失', 7),
            (AccountItem.mid_category == '法人税等', 8),
            else_=9
        )
        
        # 小分類の順序
        sub_order = case(
            # 資産
            (AccountItem.sub_category == '現金及び預金', 1),
            (AccountItem.sub_category == '売上債権', 2),
            (AccountItem.sub_category == '有価証券', 3),
            (AccountItem.sub_category == '棚卸資産', 4),
            (AccountItem.sub_category == 'その他流動資産', 5),
            (AccountItem.sub_category == '有形固定資産', 10),
            (AccountItem.sub_category == '無形固定資産', 11),
            (AccountItem.sub_category == '投資その他の資産', 12),
            (AccountItem.sub_category == '繰延資産', 20),
            # 負債
            (AccountItem.sub_category == '仕入債務', 30),
            (AccountItem.sub_category == 'その他流動負債', 31),
            (AccountItem.sub_category == '固定負債', 40),
            # 損益（売上高）
            (AccountItem.sub_category == '売上高', 100),
            # 損益（売上原価）
            (AccountItem.sub_category == '売上原価', 110),
            # 損益（販管費）
            (AccountItem.sub_category == '販売費', 120),
            (AccountItem.sub_category == '一般管理費', 121),
            # 損益（営業外）
            (AccountItem.sub_category == '営業外収益', 130),
            (AccountItem.sub_category == '営業外費用', 131),
            # 損益（特別損益）
            (AccountItem.sub_category == '特別利益', 140),
            (AccountItem.sub_category == '特別損失', 141),
            # 損益（税金）
            (AccountItem.sub_category == '法人税等', 150),
            else_=999
        )
        
        items = query.order_by(
            major_order.asc(),
            mid_order.asc(),
            sub_order.asc(),
            AccountItem.bs_rank.asc().nullslast(),
            AccountItem.account_name.asc()
        ).offset(offset).limit(per_page).all()
        
        # 各カテゴリの件数を取得
        base_query = db.query(AccountItem).filter(AccountItem.organization_id == session['organization_id'])
        category_counts = {
            'all': base_query.count(),
            '損益': base_query.filter(AccountItem.major_category == '損益').count(),
            '資産': base_query.filter(AccountItem.major_category == '資産').count(),
            '負債': base_query.filter(AccountItem.major_category == '負債').count(),
            '純資産': base_query.filter(AccountItem.major_category == '純資産').count(),
        }
        
        # 選択された大分類の中分類一覧を取得
        mid_categories = []
        if category_filter:
            mid_query = base_query.filter(AccountItem.major_category == category_filter)
            mid_results = db.query(AccountItem.mid_category, func.count(AccountItem.id)).filter(
                AccountItem.organization_id == session['organization_id'],
                AccountItem.major_category == category_filter
            ).group_by(AccountItem.mid_category).all()
            
            # 中分類の順序定義
            mid_order_map = {
                '流動資産': 1, '固定資産': 2, '繰延資産': 3,
                '流動負債': 1, '固定負債': 2,
                '資本金': 1, '資本剰余金': 2, '利益剰余金': 3, '自己株式': 4, '評価換算差額等': 5, '新株予約権': 6,
                '売上高': 1, '売上原価': 2, '販売費及び一般管理費': 3, '営業外収益': 4, '営業外費用': 5, '特別利益': 6, '特別損失': 7, '法人税等': 8
            }
            mid_categories = sorted(
                [{'name': name, 'count': count} for name, count in mid_results if name],
                key=lambda x: mid_order_map.get(x['name'], 999)
            )
        
        # 選択された中分類の小分類一覧を取得
        sub_categories = []
        if mid_filter:
            sub_results = db.query(AccountItem.sub_category, func.count(AccountItem.id)).filter(
                AccountItem.organization_id == session['organization_id'],
                AccountItem.mid_category == mid_filter
            ).group_by(AccountItem.sub_category).all()
            
            # 小分類の順序定義
            sub_order_map = {
                # 資産
                '現金及び預金': 1, '売上債権': 2, '有価証券': 3, '棚卸資産': 4, 'その他流動資産': 5,
                '有形固定資産': 10, '無形固定資産': 11, '投資その他の資産': 12,
                '繰延資産': 20,
                # 負債
                '仕入債務': 30, 'その他流動負債': 31, '固定負債': 40,
                # 損益
                '売上高': 100,
                # 売上原価の詳細
                '期首商品棚卸高': 110, '当期商品仕入': 111, '他勘定振替高(商)': 112, '期末商品棚卸高': 113,
                '売上原価': 114,
                # 販管費
                '販売費': 120, '一般管理費': 121,
                # 営業外
                '営業外収益': 130, '営業外費用': 131,
                # 特別損益
                '特別利益': 140, '特別損失': 141,
                # 税金
                '法人税等': 150
            }
            sub_categories = sorted(
                [{'name': name, 'count': count} for name, count in sub_results if name],
                key=lambda x: sub_order_map.get(x['name'], 999)
            )
        
        return render_template(
            'account_items/list.html',
            items=items,
            search_query=search_query,
            page=page,
            total_pages=total_pages,
            total_items=total_items,
            category_filter=category_filter,
            mid_filter=mid_filter,
            sub_filter=sub_filter,
            category_counts=category_counts,
            mid_categories=mid_categories,
            sub_categories=sub_categories
        )
    finally:
        db.close()

# 勘定科目新規追加ページ
# 勘定科目新規追加ページ


@bp.route('/account-items/new', methods=['GET', 'POST'])
@login_required
def account_item_create():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # フォームデータを取得
            account_name = request.form.get('account_name', '').strip()
            display_name = request.form.get('display_name', '').strip()
            major_category = request.form.get('major_category', '').strip()
            mid_category = request.form.get('mid_category', '').strip()
            sub_category = request.form.get('sub_category', '').strip()
            income_counterpart = request.form.get('income_counterpart', '').strip()
            expense_counterpart = request.form.get('expense_counterpart', '').strip()
            tax_category = request.form.get('tax_category', '').strip()
            
            # 表示順序関連
            bs_rank_str = request.form.get('bs_rank', '').strip()
            liquidity_rank_str = request.form.get('liquidity_rank', '').strip()
            bs_rank = int(bs_rank_str) if bs_rank_str else None
            liquidity_rank = int(liquidity_rank_str) if liquidity_rank_str else None
            
            # バリデーション
            if not account_name:
                flash('勘定科目名は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not display_name:
                flash('表示名は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not major_category:
                flash('大分類は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not mid_category:
                flash('中分類は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not sub_category:
                flash('小分類は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not income_counterpart:
                flash('収入取引相手方は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not expense_counterpart:
                flash('支出取引相手方は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            if not tax_category:
                flash('税区分は必須です', 'error')
                return redirect(url_for('account_item_create'))
            
            # 重複チェック
            existing = db.query(AccountItem).filter(
                AccountItem.organization_id == session['organization_id'],
                AccountItem.account_name == account_name
            ).first()
            
            if existing:
                flash('この勘定科目名は既に登録されています', 'error')
                return redirect(url_for('account_item_create'))
            
            # 新規作成
            new_item = AccountItem(
                account_name=account_name,
                display_name=display_name,
                major_category=major_category,
                mid_category=mid_category,
                sub_category=sub_category,
                income_counterpart=income_counterpart,
                expense_counterpart=expense_counterpart,
                tax_category=tax_category,
                bs_rank=bs_rank,
                liquidity_rank=liquidity_rank,
                organization_id=session['organization_id']
            )
            
            db.add(new_item)
            db.commit()
            
            flash(f'勘定科目「{account_name}」を追加しました', 'success')
            return redirect(url_for('account_items_list'))
        
        # 分類階層データを読み込む
        import json
        categories_path = os.path.join(os.path.dirname(__file__), 'account_item_categories.json')
        with open(categories_path, 'r', encoding='utf-8') as f:
            categories = json.load(f)
        
        # 選択肢データを読み込む
        options_path = os.path.join(os.path.dirname(__file__), 'account_item_options.json')
        with open(options_path, 'r', encoding='utf-8') as f:
            options = json.load(f)
        
        return render_template('account_items/form.html', categories=categories, options=options)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('account_items_list'))
    finally:
        db.close()

# 勘定科目編集ページ


@bp.route('/account-items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def account_item_edit(item_id):
    db = SessionLocal()
    try:
        item = db.query(AccountItem).filter(
            AccountItem.id == item_id,
            AccountItem.organization_id == session['organization_id']
        ).first()
        if not item:
            flash('勘定科目が見つかりません', 'error')
            return redirect(url_for('account_items_list'))
        
        if request.method == 'POST':
            # フォームデータを取得
            account_name = request.form.get('account_name', '').strip()
            display_name = request.form.get('display_name', '').strip()
            major_category = request.form.get('major_category', '').strip()
            mid_category = request.form.get('mid_category', '').strip()
            sub_category = request.form.get('sub_category', '').strip()
            income_counterpart = request.form.get('income_counterpart', '').strip()
            expense_counterpart = request.form.get('expense_counterpart', '').strip()
            tax_category = request.form.get('tax_category', '').strip()
            
            # 表示順序関連
            bs_rank_str = request.form.get('bs_rank', '').strip()
            liquidity_rank_str = request.form.get('liquidity_rank', '').strip()
            bs_rank = int(bs_rank_str) if bs_rank_str else None
            liquidity_rank = int(liquidity_rank_str) if liquidity_rank_str else None
            
            # バリデーション
            if not account_name:
                flash('勘定科目名は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not display_name:
                flash('表示名は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not major_category:
                flash('大分類は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not mid_category:
                flash('中分類は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not sub_category:
                flash('小分類は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not income_counterpart:
                flash('収入取引相手方は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not expense_counterpart:
                flash('支出取引相手方は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            if not tax_category:
                flash('税区分は必須です', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            # 重複チェック（自分自身は除外）
            existing = db.query(AccountItem).filter(
                AccountItem.organization_id == session['organization_id'],
                AccountItem.account_name == account_name,
                AccountItem.id != item_id
            ).first()
            
            if existing:
                flash('この勘定科目名は既に登録されています', 'error')
                return redirect(url_for('account_item_edit', item_id=item_id))
            
            # 更新
            item.account_name = account_name
            item.display_name = display_name
            item.major_category = major_category
            item.mid_category = mid_category
            item.sub_category = sub_category
            item.income_counterpart = income_counterpart
            item.expense_counterpart = expense_counterpart
            item.tax_category = tax_category
            item.bs_rank = bs_rank
            item.liquidity_rank = liquidity_rank
            
            db.commit()
            
            flash(f'勘定科目「{account_name}」を更新しました', 'success')
            return redirect(url_for('account_items_list'))
        
        # 分類階層データを読み込む
        import json
        categories_path = os.path.join(os.path.dirname(__file__), 'account_item_categories.json')
        with open(categories_path, 'r', encoding='utf-8') as f:
            categories = json.load(f)
        
        # 選択肢データを読み込む
        options_path = os.path.join(os.path.dirname(__file__), 'account_item_options.json')
        with open(options_path, 'r', encoding='utf-8') as f:
            options = json.load(f)
        
        return render_template('account_items/form.html', item=item, categories=categories, options=options)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('account_items_list'))
    finally:
        db.close()



@bp.route('/api/account-items/by-major-category', methods=['GET'])
@login_required
def get_account_items_by_major_category():
    db = SessionLocal()
    try:
        major_category = request.args.get('major_category')
        
        if not major_category:
            return jsonify({'success': False, 'message': 'major_category is required'}), 400
        
        items = db.query(AccountItem).filter(
            AccountItem.organization_id == session['organization_id'],
            AccountItem.major_category == major_category
        ).order_by(AccountItem.account_name.asc()).all()
        
        # JSON形式に変換
        account_items_data = [
            {
                'id': item.id,
                'account_name': item.account_name,
                'display_name': item.display_name
            } for item in items
        ]
        return jsonify({'success': True, 'account_items': account_items_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()


