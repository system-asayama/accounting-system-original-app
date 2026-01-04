"""
organizations Blueprint
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

bp = Blueprint('organizations', __name__, url_prefix='')

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


@bp.route('/organizations')
def organizations_list():
    """事業所一覧ページ（ログアウト状態でのみアクセス可能）"""
    # ログイン中の場合はホーム画面にリダイレクト
    if 'organization_id' in session:
        flash('事業所管理はログアウト状態でのみアクセスできます。', 'warning')
        return redirect(url_for('index'))
    
    db = SessionLocal()
    try:
        search_query = request.args.get('search', '')
        
        query = db.query(Organization)
        if search_query:
            query = query.filter(Organization.name.like(f'%{search_query}%'))
        
        organizations = query.order_by(Organization.id.asc()).all()
        return render_template('organizations/list.html', organizations=organizations, search_query=search_query)
    finally:
        db.close()



@bp.route('/organizations/new', methods=['GET', 'POST'])
def organization_create():
    """事業所新規作成ページ"""
    if request.method == 'POST':
        db = SessionLocal()
        try:
            name = request.form.get('name', '').strip()
            code = request.form.get('code', '').strip()
            business_type = request.form.get('business_type', 'corporate')
            postal_code = request.form.get('postal_code', '').strip()
            address = request.form.get('address', '').strip()
            phone = request.form.get('phone', '').strip()
            fax = request.form.get('fax', '').strip()
            email = request.form.get('email', '').strip()
            representative = request.form.get('representative', '').strip()
            established_date = request.form.get('established_date', '').strip()
            notes = request.form.get('notes', '').strip()
            
            if not name:
                flash('事業所名は必須です', 'danger')
                return redirect(url_for('organization_create'))
            
            # 事業所コードの重複チェック
            if code:
                existing = db.query(Organization).filter(Organization.code == code).first()
                if existing:
                    flash(f'事業所コード「{code}」は既に使用されています', 'danger')
                    return redirect(url_for('organization_create'))
            
            new_org = Organization(
                name=name,
                code=code if code else None,
                business_type=business_type,
                postal_code=postal_code if postal_code else None,
                address=address if address else None,
                phone=phone if phone else None,
                fax=fax if fax else None,
                email=email if email else None,
                representative=representative if representative else None,
                established_date=established_date if established_date else None,
                notes=notes if notes else None,
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.add(new_org)
            db.commit()
            flash(f'事業所「{name}」を作成しました', 'success')
            return redirect(url_for('organizations_list'))
        except Exception as e:
            db.rollback()
            flash(f'エラーが発生しました: {str(e)}', 'danger')
            return redirect(url_for('organization_create'))
        finally:
            db.close()
    
    return render_template('organizations/form.html', organization=None)



@bp.route('/organizations/<int:organization_id>/edit', methods=['GET', 'POST'])
def organization_edit(organization_id):
    """事業所編集ページ（ログアウト状態でのみアクセス可能）"""
    # ログイン中の場合はホーム画面にリダイレクト
    if 'organization_id' in session:
        flash('事業所管理はログアウト状態でのみアクセスできます。', 'warning')
        return redirect(url_for('index'))
    
    db = SessionLocal()
    try:
        organization = db.query(Organization).filter(Organization.id == organization_id).first()
        if not organization:
            flash('事業所が見つかりません', 'danger')
            return redirect(url_for('organizations_list'))
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            code = request.form.get('code', '').strip()
            business_type = request.form.get('business_type', 'corporate')
            postal_code = request.form.get('postal_code', '').strip()
            address = request.form.get('address', '').strip()
            phone = request.form.get('phone', '').strip()
            fax = request.form.get('fax', '').strip()
            email = request.form.get('email', '').strip()
            representative = request.form.get('representative', '').strip()
            established_date = request.form.get('established_date', '').strip()
            notes = request.form.get('notes', '').strip()
            
            if not name:
                flash('事業所名は必須です', 'danger')
                return redirect(url_for('organization_edit', organization_id=organization_id))
            
            # 事業所コードの重複チェック（自分以外）
            if code:
                existing = db.query(Organization).filter(
                    Organization.code == code,
                    Organization.id != organization_id
                ).first()
                if existing:
                    flash(f'事業所コード「{code}」は既に使用されています', 'danger')
                    return redirect(url_for('organization_edit', organization_id=organization_id))
            
            organization.name = name
            organization.code = code if code else None
            organization.business_type = business_type
            organization.postal_code = postal_code if postal_code else None
            organization.address = address if address else None
            organization.phone = phone if phone else None
            organization.fax = fax if fax else None
            organization.email = email if email else None
            organization.representative = representative if representative else None
            organization.established_date = established_date if established_date else None
            organization.notes = notes if notes else None
            organization.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            db.commit()
            flash(f'事業所「{name}」を更新しました', 'success')
            return redirect(url_for('organizations_list'))
        
        return render_template('organizations/form.html', organization=organization)
    finally:
        db.close()



@bp.route('/api/organizations/<int:organization_id>/delete', methods=['POST'])
def organization_delete(organization_id):
    """事業所削除API（ログアウト状態でのみアクセス可能）"""
    # ログイン中の場合はエラーを返す
    if 'organization_id' in session:
        return jsonify({'success': False, 'message': '事業所管理はログアウト状態でのみアクセスできます。'}), 403
    
    db = SessionLocal()
    try:
        organization = db.query(Organization).filter(Organization.id == organization_id).first()
        if not organization:
            return jsonify({'success': False, 'message': '事業所が見つかりません'}), 404
        
        org_name = organization.name
        db.delete(organization)
        db.commit()
        
        return jsonify({'success': True, 'message': f'事業所「{org_name}」を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()



# ========== 期首残高設定 ==========


@bp.route('/organization/create', methods=['GET', 'POST'])
def organization_create_page():
    """事業所追加ページと追加処理（開発用）"""
    if request.method == 'GET':
        return render_template('organization_create.html')
    
    # POSTリクエストの場合
    db = SessionLocal()
    try:
        # フォームデータを取得
        org = Organization(
            name=request.form.get('name'),
            code=request.form.get('code'),
            business_type=request.form.get('business_type'),
            representative=request.form.get('representative'),
            established_date=request.form.get('established_date') or None,
            postal_code=request.form.get('postal_code'),
            address=request.form.get('address'),
            phone=request.form.get('phone'),
            fax=request.form.get('fax'),
            email=request.form.get('email'),
            notes=request.form.get('notes'),
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        
        db.add(org)
        db.commit()
        db.refresh(org)
        
        flash(f'事業所「{org.name}」を追加しました', 'success')
        return redirect(url_for('login'))
    except Exception as e:
        db.rollback()
        import traceback
        error_msg = traceback.format_exc()
        print(f'Error creating organization: {error_msg}')
        flash(f'事業所の追加に失敗しました: {str(e)}', 'danger')
        return redirect(url_for('organization_create_page'))
    finally:
        db.close()

# 総勘定元帳


@bp.route('/organization_settings', methods=['GET', 'POST'])
@login_required
def organization_settings():
    """事業所設定画面"""
    db = SessionLocal()
    try:
        org_id = session.get('organization_id')
        organization = db.query(Organization).filter(Organization.id == org_id).first()
        
        if not organization:
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            # フォームデータの処理
            tab = request.form.get('tab', 'basic-info')
            
            if tab == 'basic-info':
                # 基本情報の更新
                organization.name = request.form.get('name', organization.name)
                organization.code = request.form.get('code', organization.code)
                organization.business_type = request.form.get('business_type', organization.business_type)
                organization.postal_code = request.form.get('postal_code', organization.postal_code)
                organization.address = request.form.get('address', organization.address)
                organization.phone = request.form.get('phone', organization.phone)
                organization.fax = request.form.get('fax', organization.fax)
                organization.email = request.form.get('email', organization.email)
                organization.representative = request.form.get('representative', organization.representative)
                organization.established_date = request.form.get('established_date', organization.established_date)
                organization.notes = request.form.get('notes', organization.notes)
                organization.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                db.commit()
                return render_template('organization_settings.html', 
                                     organization=organization,
                                     active_menu='settings',
                                     active_submenu='organization_settings',
                                     success_message='基本情報を保存しました。')
            
            elif tab == 'accounting-period':
                # 会計期間の更新（FiscalPeriodテーブルに保存）
                start_date = request.form.get('start_date')
                end_date = request.form.get('end_date')
                period_number_str = request.form.get('period_number', '').strip()
                period_number = int(period_number_str) if period_number_str else None
                
                # 既存の会計期間を取得
                fiscal_period = db.query(FiscalPeriod).filter(
                    FiscalPeriod.organization_id == org_id
                ).first()
                
                if not fiscal_period:
                    fiscal_period = FiscalPeriod(
                        organization_id=org_id,
                        start_date=start_date,
                        end_date=end_date,
                        period_number=period_number
                    )
                    db.add(fiscal_period)
                else:
                    fiscal_period.start_date = start_date
                    fiscal_period.end_date = end_date
                    fiscal_period.period_number = period_number
                
                db.commit()
                return render_template('organization_settings.html', 
                                     organization=organization,
                                     active_menu='settings',
                                     active_submenu='organization_settings',
                                     success_message='会計期間を保存しました。')
            
            else:
                # その他の設定（将来の拡張用）
                db.commit()
                return render_template('organization_settings.html', 
                                     organization=organization,
                                     active_menu='settings',
                                     active_submenu='organization_settings',
                                     success_message='設定を保存しました。')
        
        # GET リクエスト：設定画面を表示
        fiscal_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.organization_id == org_id
        ).first()
        
        fiscal_year_start = fiscal_period.start_date if fiscal_period else ''
        fiscal_year_end = fiscal_period.end_date if fiscal_period else ''
        period_number = fiscal_period.period_number if fiscal_period else ''
        
        # 貸借対照表科目を流動性配列で取得
        bs_accounts_query = db.query(AccountItem).filter(
            AccountItem.organization_id == org_id,
            AccountItem.major_category.in_(['資産', '負債', '純資産'])
        ).order_by(AccountItem.bs_rank.nullslast(), AccountItem.account_name).all()
        
        # カテゴリ別に整理（sub_categoryでグループ化）
        from collections import OrderedDict
        bs_accounts_by_category = OrderedDict()
        
        # カテゴリの順序を定義（sub_categoryベース）
        category_order = [
            # 流動資産
            '現金及び預金',
            '売上債権',
            '有価証券',
            '棚卸資産',
            'その他流動資産',
            # 固定資産
            '有形固定資産',
            '無形固定資産',
            '投資その他の資産',
            # 繰延資産
            '繰延資産',
            # 流動負債
            '仕入債務',
            'その他流動負債',
            # 固定負債
            '固定負債',
            # 純資産
            '資本金',
            '新株式申込証拠金',
            '資本準備金',
            'その他資本剰余金',
            '利益準備金',
            'その他利益剰余金',
            '自己株式',
            '自己株式申込証拠金',
            '新株予約権',
            '他有価証券評価差額金',
            '繰延ヘッジ損益',
            '土地再評価差額金',
            '請口'
        ]
        
        for item in bs_accounts_query:
            sub_cat = item.sub_category or 'その他'
            if sub_cat not in bs_accounts_by_category:
                bs_accounts_by_category[sub_cat] = []
            bs_accounts_by_category[sub_cat].append({
                'id': item.id,
                'account_name': item.account_name,
                'display_name': item.display_name
            })
        
        # カテゴリを定義された順序に並べ替え
        sorted_bs_accounts = OrderedDict()
        for cat in category_order:
            if cat in bs_accounts_by_category:
                sorted_bs_accounts[cat] = bs_accounts_by_category[cat]
        # 定義にないカテゴリを追加
        for cat, items in bs_accounts_by_category.items():
            if cat not in sorted_bs_accounts:
                sorted_bs_accounts[cat] = items
        
        # 期首残高を取得
        opening_balances = []
        opening_balance_dict = {}
        if fiscal_period:
            opening_balances = db.query(OpeningBalance).filter(
                OpeningBalance.organization_id == org_id,
                OpeningBalance.fiscal_period_id == fiscal_period.id
            ).all()
            # account_item_idをキーとした辞書を作成
            opening_balance_dict = {ob.account_item_id: ob for ob in opening_balances}
        
        return render_template('organization_settings.html',
                             organization=organization,
                             start_date=fiscal_year_start,
                             end_date=fiscal_year_end,
                             period_number=period_number,
                             bs_accounts_by_category=sorted_bs_accounts,
                             opening_balance_dict=opening_balance_dict,
                             active_menu='settings',
                             active_submenu='organization_settings')
    
    except Exception as e:
        db.rollback()
        # エラー発生時もorganizationを渡すように修正
        organization = organization if 'organization' in locals() else None
        return render_template('organization_settings.html',
                             organization=organization,
                             active_menu='settings',
                             active_submenu='organization_settings',
                             error_message=f'エラーが発生しました: {str(e)}')
    finally:
        db.close()


# ========== 期首残高保存API ==========


@bp.route('/organization_settings/opening_balances', methods=['POST'])
@login_required
def save_organization_opening_balances():
    """事業所設定画面から期首残高を保存"""
    db = SessionLocal()
    try:
        org_id = session.get('organization_id')
        data = request.get_json()
        opening_balances_data = data.get('opening_balances', [])
        
        # 会計期間を取得
        fiscal_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.organization_id == org_id
        ).first()
        
        if not fiscal_period:
            return jsonify({'success': False, 'error': '会計期間が設定されていません。'})
        
        # 既存の期首残高を削除
        db.query(OpeningBalance).filter(
            OpeningBalance.organization_id == org_id,
            OpeningBalance.fiscal_period_id == fiscal_period.id
        ).delete()
        
        # 新しい期首残高を追加
        for ob_data in opening_balances_data:
            opening_balance = OpeningBalance(
                organization_id=org_id,
                fiscal_period_id=fiscal_period.id,
                account_item_id=ob_data['account_item_id'],
                debit_amount=ob_data['debit_amount'],
                credit_amount=ob_data['credit_amount'],
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.add(opening_balance)
        
        db.commit()
        return jsonify({'success': True})
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.close()


# ========== アプリケーション起動 ===========
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)

