"""
journal_entries Blueprint
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

bp = Blueprint('journal_entries', __name__, url_prefix='')

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


@bp.route('/journal-entries', methods=['GET'])
def journal_entries_list():
    db = SessionLocal()
    try:
        # 検索フィルター
        search_query = request.args.get('search', '', type=str)
        # 口座フィルター（動定科目ID）
        account_item_id = request.args.get('account_item_id', type=int)
        
        # 取引明細から登録されたjournal_entry_idを取得
        imported_journal_entry_ids = db.query(ImportedTransaction.journal_entry_id).filter(
            ImportedTransaction.journal_entry_id.isnot(None)
        ).all()
        imported_journal_entry_ids = [item[0] for item in imported_journal_entry_ids]
        
        # クエリ構築（取引明細から登録された仕訳を除外）
        query = db.query(JournalEntry).filter(
            ~JournalEntry.id.in_(imported_journal_entry_ids)
        )
        
        # 口座フィルター（借方または貸方が指定された動定科目）
        if account_item_id:
            query = query.filter(
                (JournalEntry.debit_account_item_id == account_item_id) |
                (JournalEntry.credit_account_item_id == account_item_id)
            )
        
        if search_query:
            query = query.filter(
                (JournalEntry.summary.ilike(f'%{search_query}%')) |
                (JournalEntry.remarks.ilike(f'%{search_query}%'))
            )
        
        # 取引日降順でソート
        items = query.order_by(JournalEntry.transaction_date.desc()).all()
        
        return render_template(
            'journal_entries/list.html',
            items=items,
            search_query=search_query,
            account_item_id=account_item_id
        )
    finally:
        db.close()

# 振替伝票新規追加ページ


@bp.route('/journal-entries/new', methods=['GET', 'POST'])
def journal_entry_create():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # フォームデータを取得
            transaction_date = request.form.get('transaction_date', '').strip()
            debit_account_item_id_str = request.form.get('debit_account_item_id[]', '').strip()
            debit_amount = request.form.get('debit_amount[]', type=int)
            debit_tax_category_id = request.form.get('debit_tax_category_id[]', type=int)
            credit_account_item_id_str = request.form.get('credit_account_item_id[]', '').strip()
            credit_amount = request.form.get('credit_amount[]', type=int)
            credit_tax_category_id = request.form.get('credit_tax_category_id[]', type=int)
            summary = request.form.get('summary', '').strip()
            remarks = request.form.get('remarks', '').strip()
            counterparty_id = request.form.get('counterparty_id', type=int) or None
            department_id = request.form.get('department_id', type=int) or None
            item_id = request.form.get('item_id', type=int) or None
            project_tag_id = request.form.get('project_tag_id', type=int) or None
            memo_tag_id = request.form.get('memo_tag_id', type=int) or None
            
            # 借方: 口座IDの場合は勘定科目IDに変換
            if not debit_account_item_id_str:
                debit_account_item_id = None
            elif debit_account_item_id_str.startswith('account_'):
                account_id = int(debit_account_item_id_str.replace('account_', ''))
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    debit_account_item_id = account.account_item_id
                else:
                    flash('指定された口座が見つかりません', 'error')
                    return redirect(url_for('journal_entry_create'))
            else:
                debit_account_item_id = int(debit_account_item_id_str)
            
            # 貸方: 口座IDの場合は勘定科目IDに変換
            if not credit_account_item_id_str:
                credit_account_item_id = None
            elif credit_account_item_id_str.startswith('account_'):
                account_id = int(credit_account_item_id_str.replace('account_', ''))
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    credit_account_item_id = account.account_item_id
                else:
                    flash('指定された口座が見つかりません', 'error')
                    return redirect(url_for('journal_entry_create'))
            else:
                credit_account_item_id = int(credit_account_item_id_str)
            
            # バリドーション
            if not transaction_date:
                flash('取引日は必須です', 'error')
                return redirect(url_for('journal_entry_create'))
            
            if not debit_account_item_id or not credit_account_item_id:
                flash('勘定科目は必須です', 'error')
                return redirect(url_for('journal_entry_create'))
            
            if debit_amount != credit_amount:
                flash('借方金額と賯方金額が一致していません', 'error')
                return redirect(url_for('journal_entry_create'))
            
            # 新規作成
            new_entry = JournalEntry(
                organization_id=get_current_organization_id(),
                transaction_date=transaction_date,
                debit_account_item_id=debit_account_item_id,
                debit_amount=debit_amount,
                debit_tax_category_id=debit_tax_category_id,
                credit_account_item_id=credit_account_item_id,
                credit_amount=credit_amount,
                credit_tax_category_id=credit_tax_category_id,
                summary=summary,
                remarks=remarks,
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            db.add(new_entry)
            db.commit()
            
            # 仕訳帳マスタにも登録
            general_ledger_entry = GeneralLedger(
                organization_id=get_current_organization_id(),
                transaction_date=transaction_date,
                debit_account_item_id=debit_account_item_id,
                debit_amount=debit_amount,
                debit_tax_category_id=debit_tax_category_id,
                credit_account_item_id=credit_account_item_id,
                credit_amount=credit_amount,
                credit_tax_category_id=credit_tax_category_id,
                summary=summary,
                remarks=remarks,
                counterparty_id=counterparty_id,
                department_id=department_id,
                item_id=item_id,
                project_tag_id=project_tag_id,
                memo_tag_id=memo_tag_id,
                source_type='journal_entry',
                source_id=new_entry.id,
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.add(general_ledger_entry)
            db.commit()
            
            flash('振替伝票を追加しました', 'success')
            return redirect(url_for('journal_entries_list'))
        
        # GETリクエスト時のデータ取得
        today = datetime.now().strftime('%Y-%m-%d')
        
        return render_template('journal_entries/form.html', 
                             today=today)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('journal_entries_list'))
    finally:
        db.close()

# 振替伝票編集ページ


@bp.route('/journal-entries/<int:entry_id>/edit', methods=['GET', 'POST'])
def journal_entry_edit(entry_id):
    db = SessionLocal()
    try:
        entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
        if not entry:
            flash('振替伝票が見つかりません', 'error')
            return redirect(url_for('journal_entries_list'))
        
        if request.method == 'POST':
            # フォームデータを取得
            transaction_date = request.form.get('transaction_date', '').strip()
            debit_account_item_id_str = request.form.get('debit_account_item_id[]', '').strip()
            debit_amount = request.form.get('debit_amount[]', type=int)
            debit_tax_category_id = request.form.get('debit_tax_category_id[]', type=int)
            credit_account_item_id_str = request.form.get('credit_account_item_id[]', '').strip()
            credit_amount = request.form.get('credit_amount[]', type=int)
            credit_tax_category_id = request.form.get('credit_tax_category_id[]', type=int)
            summary = request.form.get('summary', '').strip()
            remarks = request.form.get('remarks', '').strip()
            counterparty_id = request.form.get('counterparty_id', type=int) or None
            department_id = request.form.get('department_id', type=int) or None
            item_id = request.form.get('item_id', type=int) or None
            project_tag_id = request.form.get('project_tag_id', type=int) or None
            memo_tag_id = request.form.get('memo_tag_id', type=int) or None
            
            # 借方: 口座IDの場合は勘定科目IDに変換
            if not debit_account_item_id_str:
                debit_account_item_id = None
            elif debit_account_item_id_str.startswith('account_'):
                account_id = int(debit_account_item_id_str.replace('account_', ''))
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    debit_account_item_id = account.account_item_id
                else:
                    flash('指定された口座が見つかりません', 'error')
                    return redirect(url_for('journal_entry_create'))
            else:
                debit_account_item_id = int(debit_account_item_id_str)
            
            # 貸方: 口座IDの場合は勘定科目IDに変換
            if not credit_account_item_id_str:
                credit_account_item_id = None
            elif credit_account_item_id_str.startswith('account_'):
                account_id = int(credit_account_item_id_str.replace('account_', ''))
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    credit_account_item_id = account.account_item_id
                else:
                    flash('指定された口座が見つかりません', 'error')
                    return redirect(url_for('journal_entry_create'))
            else:
                credit_account_item_id = int(credit_account_item_id_str)
            
            # バリドーション
            if not transaction_date:
                flash('取引日は必須です', 'error')
                return redirect(url_for('journal_entry_edit', entry_id=entry_id))
            
            if debit_amount != credit_amount:
                flash('借方金額と賯方金額が一致していません', 'error')
                return redirect(url_for('journal_entry_edit', entry_id=entry_id))
            
            # 更新
            entry.transaction_date = transaction_date
            entry.debit_account_item_id = debit_account_item_id
            entry.debit_amount = debit_amount
            entry.debit_tax_category_id = debit_tax_category_id
            entry.credit_account_item_id = credit_account_item_id
            entry.credit_amount = credit_amount
            entry.credit_tax_category_id = credit_tax_category_id
            entry.summary = summary
            entry.remarks = remarks
            entry.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # GeneralLedgerも更新
            gl_entry = db.query(GeneralLedger).filter(
                GeneralLedger.source_type == 'journal_entry',
                GeneralLedger.source_id == entry_id
            ).first()
            
            if gl_entry:
                gl_entry.transaction_date = transaction_date
                gl_entry.debit_account_item_id = debit_account_item_id
                gl_entry.debit_amount = debit_amount
                gl_entry.debit_tax_category_id = debit_tax_category_id
                gl_entry.credit_account_item_id = credit_account_item_id
                gl_entry.credit_amount = credit_amount
                gl_entry.credit_tax_category_id = credit_tax_category_id
                gl_entry.summary = summary
                gl_entry.remarks = remarks
                gl_entry.counterparty_id = counterparty_id
                gl_entry.department_id = department_id
                gl_entry.item_id = item_id
                gl_entry.project_tag_id = project_tag_id
                gl_entry.memo_tag_id = memo_tag_id
                gl_entry.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            db.commit()
            
            flash('振替伝票を更新しました', 'success')
            return redirect(url_for('journal_entries_list'))
        
        # GETリクエスト時のデータ取得
        return render_template('journal_entries/form.html', 
                             entry=entry)
    except Exception as e:
        db.rollback()
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('journal_entries_list'))
    finally:
        db.close()

# 振替伝票削除API


@bp.route('/api/journal-entries/<int:entry_id>/delete', methods=['POST'])
def journal_entry_delete(entry_id):
    db = SessionLocal()
    try:
        entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
        if not entry:
            return jsonify({'success': False, 'message': '振替伝票が見つかりません'}), 404
        
        db.delete(entry)
        db.commit()
        return jsonify({'success': True, 'message': '振替伝票を削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()

# 連続仕訳登録ページ


@bp.route('/journal-entries/continuous', methods=['GET'])
def journal_entries_continuous():
    # 出納帳の連続仕訳登録ページにリダイレクト
    return redirect(url_for('batch_create_cash_books_page'))

# 取引明細登録ページ


@bp.route('/journal-entries/detail', methods=['GET'])
def journal_entries_detail():
    # 取引明細インポートページにリダイレクト
    return redirect(url_for('transactions.transaction_import'))


# ========== 出納帳マスター管理 ==========
# 出納帳マスター一覧ページ

