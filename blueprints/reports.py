"""
reports Blueprint
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

bp = Blueprint('reports', __name__, url_prefix='')

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


@bp.route('/opening-balances', methods=['GET'])
@login_required
def opening_balances():
    """期首残高設定画面"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        # 会計期間一覧を取得
        fiscal_periods = db.query(FiscalPeriod).filter(
            FiscalPeriod.organization_id == organization_id
        ).order_by(FiscalPeriod.start_date.desc()).all()
        
        if not fiscal_periods:
            flash('会計期間が登録されていません。まず会計期間を登録してください。', 'warning')
            return redirect(url_for('fiscal_periods_index'))
        
        # 選択された会計期間ID（デフォルトは最新）
        selected_period_id = request.args.get('fiscal_period_id', type=int)
        if not selected_period_id:
            selected_period_id = fiscal_periods[0].id
        
        # 選択された会計期間を取得
        selected_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.id == selected_period_id,
            FiscalPeriod.organization_id == organization_id
        ).first()
        
        if not selected_period:
            flash('指定された会計期間が見つかりません。', 'danger')
            return redirect(url_for('opening_balances'))
        
        # 勘定科目一覧を取得（B/S科目のみ）
        account_items = db.query(AccountItem).filter(
            AccountItem.organization_id == organization_id,
            AccountItem.major_category.in_(['資産', '負債', '純資産'])
        ).order_by(
            AccountItem.liquidity_rank,
            AccountItem.account_name
        ).all()
        
        # 期首残高データを取得
        opening_balances = db.query(OpeningBalance).filter(
            OpeningBalance.organization_id == organization_id,
            OpeningBalance.fiscal_period_id == selected_period_id
        ).all()
        
        # 勘定科目IDをキーとした辞書を作成
        opening_balance_dict = {ob.account_item_id: ob for ob in opening_balances}
        
        # 表示用データを作成
        balance_data = []
        for account_item in account_items:
            ob = opening_balance_dict.get(account_item.id)
            balance_data.append({
                'account_item': account_item,
                'debit_amount': float(ob.debit_amount) if ob else 0,
                'credit_amount': float(ob.credit_amount) if ob else 0
            })
        
        # 借方合計・貸方合計を計算
        debit_total = sum([item['debit_amount'] for item in balance_data])
        credit_total = sum([item['credit_amount'] for item in balance_data])
        
        return render_template(
            'opening_balances/index.html',
            fiscal_periods=fiscal_periods,
            selected_period_id=selected_period_id,
            selected_period=selected_period,
            balance_data=balance_data,
            debit_total=debit_total,
            credit_total=credit_total
        )
    finally:
        db.close()




@bp.route('/opening-balances/save', methods=['POST'])
@login_required
def save_opening_balances():
    """期首残高を保存"""
    organization_id = get_current_organization_id()
    fiscal_period_id = request.form.get('fiscal_period_id', type=int)
    
    if not fiscal_period_id:
        flash('会計期間が指定されていません。', 'danger')
        return redirect(url_for('opening_balances'))
    
    db = SessionLocal()
    try:
        from datetime import datetime
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 既存の期首残高を取得
        existing_balances = db.query(OpeningBalance).filter(
            OpeningBalance.organization_id == organization_id,
            OpeningBalance.fiscal_period_id == fiscal_period_id
        ).all()
        
        existing_balance_dict = {ob.account_item_id: ob for ob in existing_balances}
        
        # フォームデータを処理（勘定科目ごとに借方・貸方をまとめる）
        account_data = {}
        for key, value in request.form.items():
            if key.startswith('debit_') or key.startswith('credit_'):
                parts = key.split('_')
                if len(parts) == 2:
                    field_type = parts[0]  # 'debit' or 'credit'
                    account_item_id = int(parts[1])
                    amount = float(value) if value else 0
                    
                    if account_item_id not in account_data:
                        account_data[account_item_id] = {'debit': 0, 'credit': 0}
                    account_data[account_item_id][field_type] = amount
        
        # 勘定科目ごとに期首残高を保存
        for account_item_id, amounts in account_data.items():
            debit_amount = amounts['debit']
            credit_amount = amounts['credit']
            
            # 既存のレコードを更新または新規作成
            if account_item_id in existing_balance_dict:
                ob = existing_balance_dict[account_item_id]
                ob.debit_amount = debit_amount
                ob.credit_amount = credit_amount
                ob.updated_at = current_time
            else:
                # 新規作成
                ob = OpeningBalance(
                    organization_id=organization_id,
                    fiscal_period_id=fiscal_period_id,
                    account_item_id=account_item_id,
                    debit_amount=debit_amount,
                    credit_amount=credit_amount,
                    created_at=current_time,
                    updated_at=current_time
                )
                db.add(ob)
        
        db.commit()
        flash('期首残高を保存しました。', 'success')
        return redirect(url_for('opening_balances', fiscal_period_id=fiscal_period_id))
    except Exception as e:
        db.rollback()
        flash(f'期首残高の保存に失敗しました: {str(e)}', 'danger')
        return redirect(url_for('opening_balances', fiscal_period_id=fiscal_period_id))
    finally:
        db.close()


# ========== 試算表 ==========


@bp.route('/trial-balance', methods=['GET'])
@login_required
def trial_balance():
    """試算表表示
    B/S：大分類→中分類→小分類→勘定科目
    P/L：大分類=「損益」の科目のみを対象とし、階段式に集計
    """
    from collections import OrderedDict

    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        # 会計期間一覧を取得
        fiscal_periods = (
            db.query(FiscalPeriod)
            .filter(FiscalPeriod.organization_id == organization_id)
            .order_by(FiscalPeriod.start_date.desc())
            .all()
        )

        # 選択された会計期間ID（デフォルトは最新）
        selected_period_id = request.args.get("fiscal_period_id", type=int)
        if not selected_period_id and fiscal_periods:
            selected_period_id = fiscal_periods[0].id

        # ------------------------------
        # 初期化
        # ------------------------------
        bs_data = []  # 貸借対照表用の明細（科目単位）
        pl_data = []  # 損益計算書用の明細（科目単位：大分類=損益のみ）
        bs_debit_total = 0
        bs_credit_total = 0
        pl_debit_total = 0
        pl_credit_total = 0

        # 旧ロジック互換用（集計値など）
        bs_stair_step_data = {}
        pl_stair_step_data = {}
        pl_calculations = {}

        # freee 風ツリー
        from collections import OrderedDict
        bs_tree = OrderedDict()
        pl_tree = OrderedDict()

        # --------- ★ P/Lカテゴリ判定ヘルパー（ここがポイント） ----------
        def get_pl_cat(ai):
            """
            P/L 上のカテゴリを決めるカラム
            1. pl_category が入っていればそれを優先
            2. なければ mid_category（中分類）
            3. それも無ければ sub_category（小分類）
            """
            return (ai.pl_category or ai.mid_category or ai.sub_category or "").strip()

        if selected_period_id:
            # 選択された会計期間を取得
            selected_period = (
                db.query(FiscalPeriod)
                .filter(
                    FiscalPeriod.id == selected_period_id,
                    FiscalPeriod.organization_id == organization_id,
                )
                .first()
            )

            if selected_period:
                # ------------------------------
                # 期首残高の取得
                # ------------------------------
                opening_balances_db = (
                    db.query(OpeningBalance)
                    .filter(
                        OpeningBalance.organization_id == organization_id,
                        OpeningBalance.fiscal_period_id == selected_period_id,
                    )
                    .all()
                )

                # 期首残高が登録されていない場合は、前期の仕訳から計算
                if not opening_balances_db:
                    opening_balance_entries = (
                        db.query(GeneralLedger)
                        .filter(
                            GeneralLedger.organization_id == organization_id,
                            GeneralLedger.transaction_date < selected_period.start_date,
                        )
                        .all()
                    )
                else:
                    opening_balance_entries = []

                # 当期仕訳を取得
                current_period_entries = (
                    db.query(GeneralLedger)
                    .filter(
                        GeneralLedger.organization_id == organization_id,
                        GeneralLedger.transaction_date >= selected_period.start_date,
                        GeneralLedger.transaction_date <= selected_period.end_date,
                    )
                    .all()
                )

                # ------------------------------
                # 勘定科目ごとに集計
                # ------------------------------
                account_summary = {}

                # 期首残高テーブルから期首残高を設定
                for ob in opening_balances_db:
                    account_id = ob.account_item_id
                    if account_id not in account_summary:
                        account_summary[account_id] = {
                            "account_item": ob.account_item,
                            "opening_balance": 0,
                            "current_debit": 0,
                            "current_credit": 0,
                        }

                    major_category = ob.account_item.major_category or ""
                    if major_category == "財産":
                        major_category = "負債"

                    if major_category == "資産":
                        # 資産科目: 借方がプラス
                        account_summary[account_id]["opening_balance"] += (
                            float(ob.debit_amount) - float(ob.credit_amount)
                        )
                    elif major_category in ["負債", "純資産"]:
                        # 負債・純資産科目: 貸方がプラス
                        account_summary[account_id]["opening_balance"] += (
                            float(ob.credit_amount) - float(ob.debit_amount)
                        )
                    else:
                        # その他: 借方がプラス
                        account_summary[account_id]["opening_balance"] += (
                            float(ob.debit_amount) - float(ob.credit_amount)
                        )

                # 前期の仕訳から期首残高を計算（期首残高テーブルが空の場合）
                for entry in opening_balance_entries:
                    # 借方
                    debit_account_id = entry.debit_account_item_id
                    if debit_account_id not in account_summary:
                        account_summary[debit_account_id] = {
                            "account_item": entry.debit_account_item,
                            "opening_balance": 0,
                            "current_debit": 0,
                            "current_credit": 0,
                        }
                    account_summary[debit_account_id]["opening_balance"] += entry.debit_amount

                    # 貸方
                    credit_account_id = entry.credit_account_item_id
                    if credit_account_id not in account_summary:
                        account_summary[credit_account_id] = {
                            "account_item": entry.credit_account_item,
                            "opening_balance": 0,
                            "current_debit": 0,
                            "current_credit": 0,
                        }
                    account_summary[credit_account_id]["opening_balance"] -= entry.credit_amount

                # 当期借方・貸方を集計
                for entry in current_period_entries:
                    # 借方
                    debit_account_id = entry.debit_account_item_id
                    if debit_account_id not in account_summary:
                        account_summary[debit_account_id] = {
                            "account_item": entry.debit_account_item,
                            "opening_balance": 0,
                            "current_debit": 0,
                            "current_credit": 0,
                        }
                    account_summary[debit_account_id]["current_debit"] += entry.debit_amount

                    # 貸方
                    credit_account_id = entry.credit_account_item_id
                    if credit_account_id not in account_summary:
                        account_summary[credit_account_id] = {
                            "account_item": entry.credit_account_item,
                            "opening_balance": 0,
                            "current_debit": 0,
                            "current_credit": 0,
                        }
                    account_summary[credit_account_id]["current_credit"] += entry.credit_amount

                # ------------------------------
                # 試算表データを作成 (B/S と P/L に分ける)
                #   P/L は「major_category = 損益」の科目のみ
                # ------------------------------
                for account_id, summary in account_summary.items():
                    opening = summary["opening_balance"]
                    current_debit = summary["current_debit"]
                    current_credit = summary["current_credit"]

                    account_item = summary["account_item"]
                    # account_itemがNoneの場合はスキップ
                    if account_item is None:
                        continue
                    major_category = account_item.major_category or ""

                    # major_category が '財産' の場合は '負債'
                    if major_category == "財産":
                        major_category = "負債"

                    # 残高計算（元のロジックを踏襲）
                    if major_category in ["收入", "収益"]:
                        # 収益科目: 貸方プラス、借方マイナス
                        closing = opening - current_debit + current_credit
                    elif major_category == "資産":
                        # 資産科目: 借方プラス
                        closing = opening + current_debit - current_credit
                    elif major_category in ["負債", "純資産"]:
                        # 負債・純資産科目: 貸方プラス
                        closing = opening - current_debit + current_credit
                    else:
                        # その他（費用・損益など）: 借方プラス
                        closing = opening + current_debit - current_credit

                    data_item = {
                        "account_item": account_item,
                        "opening_balance": opening,
                        "current_debit": current_debit,
                        "current_credit": current_credit,
                        "closing_balance": closing,
                    }

                    # B/S と P/L に分類
                    if major_category in ["資産", "負債", "純資産"]:
                        # 貸借対照表
                        bs_data.append(data_item)
                        bs_debit_total += current_debit
                        bs_credit_total += current_credit
                    elif major_category == "損益":
                        # 損益計算書
                        pl_data.append(data_item)
                        pl_debit_total += current_debit
                        pl_credit_total += current_credit
                    else:
                        # その他の大分類はとりあえず B/S 側に退避
                        bs_data.append(data_item)
                        bs_debit_total += current_debit
                        bs_credit_total += current_credit

                # ------------------------------
                # 並び順（B/S）
                # ------------------------------
                def bs_sort_key(item):
                    ai = item["account_item"]

                    # B/S 大分類の順番
                    bs_major_order = {
                        "資産": 1,
                        "負債": 2,
                        "純資産": 3,
                    }
                    
                    # 中分類の順番（流動性配列法）
                    bs_middle_order = {
                        # 資産
                        "流動資産": 1,
                        "固定資産": 2,
                        "繰延資産": 3,
                        # 負債
                        "流動負債": 1,
                        "固定負債": 2,
                        # 純資産
                        "資本金": 1,
                        "資本剰余金": 2,
                        "利益剰余金": 3,
                        "自己株式": 4,
                        "評価換算差額等": 5,
                        "新株予約権": 6,
                    }
                    
                    # 小分類の順番（流動性配列法：流動性が高い順）
                    bs_small_order = {
                        # 流動資産：現金化しやすい順
                        "現金及び預金": 1,
                        "売上債権": 2,
                        "有価証券": 3,
                        "棚卸資産": 4,
                        "その他流動資産": 5,
                        # 固定資産
                        "有形固定資産": 1,
                        "無形固定資産": 2,
                        "投資その他の資産": 3,
                        # 繰延資産
                        "繰延資産": 1,
                        # 流動負債
                        "仕入債務": 1,
                        "その他流動負債": 2,
                        # 固定負債
                        "固定負債": 1,
                        # 純資産
                        "資本金": 1,
                        "新株式申込証拠金": 1,
                        "資本準備金": 2,
                        "その他資本剰余金": 3,
                        "利益準備金": 1,
                        "その他利益剰余金": 2,
                        "自己株式": 1,
                        "自己株式申込証拠金": 2,
                        "他有価証券評価差額金": 1,
                        "繰延ヘッジ損益": 2,
                        "土地再評価差額金": 3,
                        "新株予約権": 1,
                        # その他
                        "諸口": 99,
                    }

                    major = ai.major_category or ""
                    middle = ai.mid_category or ""
                    small = ai.sub_category or ""

                    return (
                        bs_major_order.get(major, 99),
                        bs_middle_order.get(middle, 99),
                        bs_small_order.get(small, 99),
                        ai.bs_rank
                        if getattr(ai, "bs_rank", None) is not None
                        else (ai.liquidity_rank if getattr(ai, "liquidity_rank", None) is not None else 9999),
                        ai.account_name,
                    )

                # デバッグ: ソート前の現金及び預金科目を確認
                import sys
                for item in bs_data:
                    ai = item["account_item"]
                    if ai.sub_category == "現金及び預金":
                        print(f"[DEBUG] ソート前: {ai.account_name}, bs_rank={ai.bs_rank}", file=sys.stderr, flush=True)
                
                bs_data.sort(key=bs_sort_key)
                
                # デバッグ: ソート後の現金及び預金科目を確認
                for item in bs_data:
                    ai = item["account_item"]
                    if ai.sub_category == "現金及び預金":
                        print(f"[DEBUG] ソート後: {ai.account_name}, bs_rank={ai.bs_rank}", file=sys.stderr, flush=True)

                # ------------------------------
                # P/L 生データ側の並び
                # ------------------------------
                pl_cat_order = {
                    "売上高": 10,
                    # 売上原価の詳細（小分類の値）
                    "期首商品棚卸": 11,
                    "当期商品仕入": 12,
                    "他勘定振替高(商)": 13,
                    "期末商品棚卸": 14,
                    "売上原価": 20,
                    "売上総利益": 30,
                    "販売管理費": 40,
                    "販管費": 40,
                    "販売費及び一般管理費": 40,
                    "営業利益": 50,
                    "営業外収益": 60,
                    "営業外費用": 70,
                    "経常利益": 80,
                    "特別利益": 90,
                    "特別損失": 100,
                    "税引前当期純利益": 110,
                    "法人税等": 120,
                    "法人税等調整額": 130,
                    "当期純利益": 140,
                }

                def pl_sort_key(item):
                    ai = item["account_item"]
                    # 小分類を優先的にチェック
                    sub = (ai.sub_category or "").strip()
                    mid = (ai.mid_category or "").strip()
                    cat = get_pl_cat(ai)
                    
                    # 小分類が pl_cat_order にあればそれを使用、なければ中分類、最後にカテゴリ
                    order = pl_cat_order.get(sub, pl_cat_order.get(mid, pl_cat_order.get(cat, 999)))
                    
                    return (
                        order,
                        ai.pl_rank
                        if getattr(ai, "pl_rank", None) is not None
                        else 9999,
                        ai.account_name or "",
                    )

                pl_data.sort(key=pl_sort_key)

                # ------------------------------
                # 旧ステップ風集計（B/S・P/L 集計値）
                # ------------------------------

                # --- B/S（流動資産など）---
                bs_stair_step_data = {
                    "流動資産": [],
                    "固定資産": [],
                    "投資その他の資産": [],
                    "流動負債": [],
                    "固定負債": [],
                    "資本金": [],
                    "資本剰余金": [],
                    "利益剰余金": [],
                }
                for item in bs_data:
                    bs_category = item["account_item"].bs_category
                    if bs_category and bs_category in bs_stair_step_data:
                        bs_stair_step_data[bs_category].append(item)

                # --- P/L（階段式用）---
                pl_stair_step_data = {
                    "sales": [],
                    "cogs": [],
                    "sga": [],
                    "non_operating_income": [],
                    "non_operating_expense": [],
                    "extraordinary_income": [],
                    "extraordinary_loss": [],
                    "income_taxes": [],
                    "income_taxes_adjustments": [],
                }

                sales_total = 0
                cogs_total = 0
                sga_total = 0
                non_operating_income_total = 0
                non_operating_expense_total = 0
                extraordinary_income_total = 0
                extraordinary_loss_total = 0
                income_taxes_total = 0
                income_taxes_adjustments_total = 0

                for item in pl_data:
                    ai = item["account_item"]
                    category = get_pl_cat(ai)   # ★ ここもヘルパーで判定
                    amount = item["closing_balance"] or 0

                    if category == "売上高":
                        pl_stair_step_data["sales"].append(item)
                        sales_total += amount
                    elif category == "売上原価":
                        pl_stair_step_data["cogs"].append(item)
                        cogs_total += amount
                    elif category in ["販管費", "販売費及び一般管理費", "販売管理費"]:
                        pl_stair_step_data["sga"].append(item)
                        sga_total += amount
                    elif category == "営業外収益":
                        pl_stair_step_data["non_operating_income"].append(item)
                        non_operating_income_total += amount
                    elif category == "営業外費用":
                        pl_stair_step_data["non_operating_expense"].append(item)
                        non_operating_expense_total += amount
                    elif category == "特別利益":
                        pl_stair_step_data["extraordinary_income"].append(item)
                        extraordinary_income_total += amount
                    elif category == "特別損失":
                        pl_stair_step_data["extraordinary_loss"].append(item)
                        extraordinary_loss_total += amount
                    elif category == "法人税等":
                        pl_stair_step_data["income_taxes"].append(item)
                        income_taxes_total += amount
                    elif category == "法人税等調整額":
                        pl_stair_step_data["income_taxes_adjustments"].append(item)
                        income_taxes_adjustments_total += amount

                # 階段式の各段計算
                gross_profit = sales_total - cogs_total
                operating_income = gross_profit - sga_total
                ordinary_income = (
                    operating_income
                    + non_operating_income_total
                    - non_operating_expense_total
                )
                pre_tax_income = (
                    ordinary_income
                    + extraordinary_income_total
                    - extraordinary_loss_total
                )
                net_income = (
                    pre_tax_income
                    - income_taxes_total
                    - income_taxes_adjustments_total
                )

                pl_calculations = {
                    "sales_total": sales_total,
                    "cogs_total": cogs_total,
                    "gross_profit": gross_profit,
                    "sga_total": sga_total,
                    "operating_income": operating_income,
                    "non_operating_income_total": non_operating_income_total,
                    "non_operating_expense_total": non_operating_expense_total,
                    "ordinary_income": ordinary_income,
                    "extraordinary_income_total": extraordinary_income_total,
                    "extraordinary_loss_total": extraordinary_loss_total,
                    "pre_tax_income": pre_tax_income,
                    "income_taxes_total": income_taxes_total,
                    "income_taxes_adjustments_total": income_taxes_adjustments_total,
                    "net_income": net_income,
                }

                # =====================================================
                # B/S 用ツリー（大分類→中分類→小分類→勘定科目）
                # P/Lと同様に、取引の有無に関わらず全科目を表示
                # =====================================================
                
                # bs_data を account_id ベースでマップ化
                bs_map = {row["account_item"].id: row for row in bs_data}
                
                # 大分類が「資産」「負債」「純資産」「負債及び純資産」の全勘定科目を取得
                all_bs_accounts = (
                    db.query(AccountItem)
                    .filter(AccountItem.organization_id == organization_id)
                    .filter(AccountItem.major_category.in_(["資産", "負債", "純資産", "負債及び純資産"]))
                    .all()
                )
                
                # 全科目を含むbs_data_fullを作成
                bs_data_full = []
                for ai in all_bs_accounts:
                    row = bs_map.get(ai.id)
                    if row:
                        # 取引がある場合は実際の金額
                        bs_data_full.append(row)
                    else:
                        # 取引がない場合は0
                        major_category = ai.major_category or ""
                        if major_category == "資産":
                            opening = 0
                            closing = 0
                        elif major_category in ["負債", "純資産", "負債及び純資産"]:
                            opening = 0
                            closing = 0
                        else:
                            opening = 0
                            closing = 0
                        
                        bs_data_full.append({
                            "account_item": ai,
                            "opening_balance": opening,
                            "current_debit": 0,
                            "current_credit": 0,
                            "closing_balance": closing,
                        })
                
                # bs_data_fullを流動性配列（流動性の高い順）で並び替え
                def bs_sort_key_full(item):
                    ai = item["account_item"]
                    
                    # 大分類の順序
                    bs_major_order = {
                        "資産": 1,
                        "負債": 2,
                        "純資産": 3,
                        "負債及び純資産": 2,
                    }
                    
                    # 中分類の順序（流動性ベース）
                    mid_category_order = {
                        # 資産：流動資産 → 固定資産 → 繰延資産
                        "流動資産": 1,
                        "固定資産": 2,
                        "繰延資産": 3,
                        # 負債：流動負債 → 固定負債
                        "流動負債": 1,
                        "固定負債": 2,
                        # 純資産：資本金 → 資本剰余金 → 利益剰余金 → 自己株式 → 評価換算差額等 → 新株予約権
                        "資本金": 1,
                        "資本剰余金": 2,
                        "利益剰余金": 3,
                        "自己株式": 4,
                        "評価換算差額等": 5,
                        "新株予約権": 6,
                        # 損益：P/Lの順序
                        "売上高": 1,
                        "売上原価": 2,
                        "販売費及び一般管理費": 3,
                        "営業外収益": 4,
                        "営業外費用": 5,
                        "特別利益": 6,
                        "特別損失": 7,
                        "法人税等": 8,
                        "法人税等調整額": 9,
                    }
                    
                    # 小分類の順序（流動性配列法：流動性が高い順）
                    sub_category_order = {
                        # 流動資産：現金化しやすい順
                        "現金及び預金": 1,
                        "売上債権": 2,
                        "有価証券": 3,
                        "棚卸資産": 4,
                        "その他流動資産": 5,
                        # 固定資産
                        "有形固定資産": 1,
                        "無形固定資産": 2,
                        "投資その他の資産": 3,
                        # 繰延資産
                        "繰延資産": 1,
                        # 流動負債
                        "仕入債務": 1,
                        "その他流動負債": 2,
                        # 固定負債
                        "固定負債": 1,
                        # 純資産：資本金
                        "資本金": 1,
                        # 純資産：資本剰余金
                        "新株式申込証拠金": 1,
                        "資本準備金": 2,
                        "その他資本剰余金": 3,
                        # 純資産：利益剰余金
                        "利益準備金": 1,
                        "その他利益剰余金": 2,
                        # 純資産：自己株式
                        "自己株式": 1,
                        "自己株式申込証拠金": 2,
                        # 純資産：評価換算差額等
                        "他有価証券評価差額金": 1,
                        "繰延ヘッジ損益": 2,
                        "土地再評価差額金": 3,
                        # 純資産：新株予約権
                        "新株予約権": 1,
                        # 損益
                        "売上高": 1,
                        "期首商品棚卸": 1,
                        "当期商品仕入": 2,
                        "他勘定振替高(商)": 3,
                        "期末商品棚卸": 4,
                        "販売管理費": 1,
                        "営業外収益": 1,
                        "営業外費用": 1,
                        "特別利益": 1,
                        "特別損失": 1,
                        "法人税等": 1,
                        "法人税等調整額": 1,
                    }
                    
                    major = ai.major_category or ""
                    middle = ai.mid_category or ""
                    small = ai.sub_category or ""
                    
                    return (
                        bs_major_order.get(major, 99),
                        mid_category_order.get(middle, 99),
                        sub_category_order.get(small, 99),
                        ai.bs_rank if getattr(ai, "bs_rank", None) is not None
                        else (ai.liquidity_rank if getattr(ai, "liquidity_rank", None) is not None else 9999),
                        ai.account_name,
                    )
                
                bs_data_full.sort(key=bs_sort_key_full)
                
                def build_bs_tree(data_list, major_order=None):
                    tmp = {}
                    for row in data_list:
                        ai = row["account_item"]
                        major = (ai.major_category or "その他").strip()
                        mid = (ai.mid_category or "その他").strip()
                        sub = (ai.sub_category or "その他").strip()

                        if major not in tmp:
                            tmp[major] = OrderedDict()
                        if mid not in tmp[major]:
                            tmp[major][mid] = OrderedDict()
                        if sub not in tmp[major][mid]:
                            tmp[major][mid][sub] = []
                        tmp[major][mid][sub].append(row)

                    # 大分類の並び順を固定（定義にないものは後ろ）
                    if major_order:
                        ordered = OrderedDict()
                        for m in major_order:
                            if m in tmp:
                                ordered[m] = tmp[m]
                        for m in tmp.keys():
                            if m not in ordered:
                                ordered[m] = tmp[m]
                        return ordered
                    else:
                        return OrderedDict(tmp)

                bs_tree = build_bs_tree(bs_data_full, major_order=["資産", "負債", "純資産"])
                
                # 小分類計と中分類計を計算
                bs_subtotals = {}
                for major, mid_dict in bs_tree.items():
                    mid_totals = {}
                    for mid, sub_dict in mid_dict.items():
                        sub_totals = {}
                        for sub, rows in sub_dict.items():
                            # 小分類計
                            opening_total = sum(row.get('opening_balance', 0) or 0 for row in rows)
                            debit_total = sum(row.get('current_debit', 0) or 0 for row in rows)
                            credit_total = sum(row.get('current_credit', 0) or 0 for row in rows)
                            closing_total = sum(row.get('closing_balance', 0) or 0 for row in rows)
                            
                            sub_key = f"{major}_{mid}_{sub}"
                            bs_subtotals[sub_key] = {
                                'opening': opening_total,
                                'debit': debit_total,
                                'credit': credit_total,
                                'closing': closing_total
                            }
                            
                            # 中分類計に加算
                            if mid not in mid_totals:
                                mid_totals[mid] = {'opening': 0, 'debit': 0, 'credit': 0, 'closing': 0}
                            mid_totals[mid]['opening'] += opening_total
                            mid_totals[mid]['debit'] += debit_total
                            mid_totals[mid]['credit'] += credit_total
                            mid_totals[mid]['closing'] += closing_total
                        
                        # 中分類計を保存
                        mid_key = f"{major}_{mid}"
                        bs_subtotals[mid_key] = mid_totals[mid]

                # =====================================================
                # P/L 用ツリー（小分類 → 勘定科目）
                # =====================================================

                # pl_data を account_id ベースでマップ化（当期数字）
                pl_map = {row["account_item"].id: row for row in pl_data}

                # 大分類=損益 の全勘定科目を取得
                all_pl_accounts = (
                    db.query(AccountItem)
                    .filter(AccountItem.organization_id == organization_id)
                    .filter(AccountItem.major_category == "損益")
                    .all()
                )

                pl_tree = OrderedDict()
                sub_priority = {}

                for ai in all_pl_accounts:
                    sub = (ai.sub_category or "その他").strip()
                    if sub not in pl_tree:
                        pl_tree[sub] = {
                            "total_debit": 0,
                            "total_credit": 0,
                            "total_closing": 0,
                            "accounts": OrderedDict(),
                        }

                    row = pl_map.get(ai.id)
                    if row:
                        cd = row["current_debit"]
                        cc = row["current_credit"]
                        cb = row["closing_balance"]
                    else:
                        cd = 0
                        cc = 0
                        cb = 0

                    pl_tree[sub]["accounts"][ai.id] = {
                        "account_item": ai,
                        "current_debit": cd,
                        "current_credit": cc,
                        "closing_balance": cb,
                    }
                    pl_tree[sub]["total_debit"] += cd
                    pl_tree[sub]["total_credit"] += cc
                    pl_tree[sub]["total_closing"] += cb

                    # 並び替え用のカテゴリ優先順位（小分類優先）
                    sub_cat = (ai.sub_category or "").strip()
                    mid_cat = (ai.mid_category or "").strip()
                    cat = get_pl_cat(ai)
                    # 小分類 → 中分類 → カテゴリの順で優先的にチェック
                    cat_ord = pl_cat_order.get(sub_cat, pl_cat_order.get(mid_cat, pl_cat_order.get(cat, 999)))
                    if sub not in sub_priority or cat_ord < sub_priority[sub]:
                        sub_priority[sub] = cat_ord

                # 小分類の並び順を「カテゴリ優先順位 → 小分類名」で並べ替え
                ordered_pl_tree = OrderedDict()
                for sub_name in sorted(
                    pl_tree.keys(),
                    key=lambda s: (sub_priority.get(s, 999), s),
                ):
                    ordered_pl_tree[sub_name] = pl_tree[sub_name]
                pl_tree = ordered_pl_tree
                
                # 中分類でグループ化
                pl_mid_tree = OrderedDict()
                for sub_name, info in pl_tree.items():
                    # 小分類の最初の勘定科目から中分類を取得
                    mid_cat = "その他"
                    for acc in info["accounts"].values():
                        ai = acc["account_item"]
                        mid_cat = (ai.mid_category or "その他").strip()
                        break
                    
                    if mid_cat not in pl_mid_tree:
                        pl_mid_tree[mid_cat] = OrderedDict()
                    pl_mid_tree[mid_cat][sub_name] = info
                
                # 集計行を計算
                pl_subtotals = {}
                
                # 売上高計
                sales_total = sum(info['total_closing'] for name, info in pl_tree.items() if name == '売上高')
                pl_subtotals['売上高計'] = sales_total
                
                # 売上原価計
                cogs_total = sum(info['total_closing'] for name, info in pl_tree.items() 
                               if name in ['期首商品棚卸', '当期商品仕入', '他勘定振替高(商)', '期末商品棚卸', '売上原価'])
                pl_subtotals['売上原価計'] = cogs_total
                
                # 売上総利益 = 売上高計 - 売上原価計
                gross_profit = sales_total - cogs_total
                pl_subtotals['売上総利益'] = gross_profit
                
                # 販売管理費計
                sg_total = sum(info['total_closing'] for name, info in pl_tree.items() 
                              if name in ['販売費', '一般管理費', '販売管理費', '販管費', '販売費及び一般管理費'])
                pl_subtotals['販売管理費計'] = sg_total
                
                # 営業利益 = 売上総利益 - 販売管理費計
                operating_profit = gross_profit - sg_total
                pl_subtotals['営業利益'] = operating_profit
                
                # 営業外収益計
                non_op_income = sum(info['total_closing'] for name, info in pl_tree.items() if name == '営業外収益')
                pl_subtotals['営業外収益計'] = non_op_income
                # 営業外費用計
                non_op_expense = sum(info['total_closing'] for name, info in pl_tree.items() if name == '営業外費用')
                pl_subtotals['営業外費用計'] = non_op_expense
                
                # 経常利益 = 営業利益 + 営業外収益 - 営業外費用
                ordinary_profit = operating_profit + non_op_income - non_op_expense
                pl_subtotals['経常利益'] = ordinary_profit
                
                # 特別利益計
                special_income = sum(info['total_closing'] for name, info in pl_tree.items() if name == '特別利益')
                pl_subtotals['特別利益計'] = special_income
                # 特別損失計
                special_loss = sum(info['total_closing'] for name, info in pl_tree.items() if name == '特別損失')
                pl_subtotals['特別損失計'] = special_loss
                
                # 税引前当期純利益 = 経常利益 + 特別利益 - 特別損失
                pretax_profit = ordinary_profit + special_income - special_loss
                pl_subtotals['税引前当期純利益'] = pretax_profit
                
                # 法人税等計
                tax_total = sum(info['total_closing'] for name, info in pl_tree.items() 
                               if name in ['法人税等', '法人税等調整額'])
                pl_subtotals['法人税等計'] = tax_total
                
                # 当期純利益 = 税引前当期純利益 - 法人税等
                net_profit = pretax_profit - tax_total
                pl_subtotals['当期純利益'] = net_profit

        return render_template(
            "trial_balance/index.html",
            fiscal_periods=fiscal_periods,
            selected_period_id=selected_period_id,
            # 明細データ
            bs_data=bs_data_full,
            pl_data=pl_data,
            # freee風ツリー
            bs_tree=bs_tree,
            pl_tree=pl_tree,
            pl_mid_tree=pl_mid_tree,
            pl_subtotals=pl_subtotals,
            bs_subtotals=bs_subtotals,
            # 旧ロジックの集計値
            bs_stair_step_data=bs_stair_step_data,
            pl_stair_step_data=pl_stair_step_data,
            pl_calculations=pl_calculations,
            bs_debit_total=bs_debit_total,
            bs_credit_total=bs_credit_total,
            pl_debit_total=pl_debit_total,
            pl_credit_total=pl_credit_total,
        )
    finally:
        db.close()


# ========== 仕訳帳 ==========


@bp.route('/general-ledger')
@login_required
def general_ledger():
    """仕訳帳一覧表示"""
    organization_id = get_current_organization_id()
    db = SessionLocal()
    try:
        # 会計期間一覧を取得
        fiscal_periods = (
            db.query(FiscalPeriod)
            .filter(FiscalPeriod.organization_id == organization_id)
            .order_by(FiscalPeriod.start_date.desc())
            .all()
        )

        # 選択された会計期間ID（デフォルトは最新）
        selected_period_id = request.args.get('fiscal_period_id', type=int)

        general_ledger_entries = []
        selected_period = None

        # 会計期間が登録されているか確認し、デフォルトを選択
        if fiscal_periods:
            if not selected_period_id:
                selected_period_id = fiscal_periods[0].id

            # 選択された会計期間を取得
            selected_period = (
                db.query(FiscalPeriod)
                .filter(
                    FiscalPeriod.id == selected_period_id,
                    FiscalPeriod.organization_id == organization_id,
                )
                .first()
            )

        # クエリの基本形
        query = db.query(GeneralLedger).filter(
            GeneralLedger.organization_id == organization_id
        )

        if selected_period:
            # 会計期間内の仕訳帳データを取得
            query = query.filter(
                GeneralLedger.transaction_date >= selected_period.start_date,
                GeneralLedger.transaction_date <= selected_period.end_date,
            )

        # 仕訳帳データを取得
        general_ledger_entries = query.order_by(
            GeneralLedger.transaction_date, GeneralLedger.id
        ).all()

        # 口座の場合は口座名を上書き
        for entry in general_ledger_entries:
            # 借方が口座の場合、口座名を取得
            if entry.debit_account_item_id:
                account = (
                    db.query(Account)
                    .filter(
                        Account.account_item_id == entry.debit_account_item_id,
                        Account.organization_id == organization_id,
                    )
                    .first()
                )
                if account and entry.debit_account_item:
                    entry.debit_account_item.account_name = account.account_name

            # 貸方が口座の場合、口座名を取得
            if entry.credit_account_item_id:
                account = (
                    db.query(Account)
                    .filter(
                        Account.account_item_id == entry.credit_account_item_id,
                        Account.organization_id == organization_id,
                    )
                    .first()
                )
                if account and entry.credit_account_item:
                    entry.credit_account_item.account_name = account.account_name

        return render_template(
            "general_ledger/index.html",
            fiscal_periods=fiscal_periods,
            selected_period_id=selected_period_id,
            selected_period=selected_period,
            general_ledger_entries=general_ledger_entries,
        )
    except Exception as e:
        flash(f"エラーが発生しました: {str(e)}", "error")
        return redirect(url_for("home"))
    finally:
        db.close()


# 孤立した仕訳データを削除するAPI


@bp.route('/api/general-ledger/orphaned/<int:cash_book_id>', methods=['DELETE'])
@login_required
def delete_orphaned_journal_entry(cash_book_id):
    """出納帳データが存在しない仕訳データを削除するAPI"""
    db = SessionLocal()
    try:
        organization_id = get_current_organization_id()
        
        # source_type='batch_entry'かつsource_id=cash_book_idの仕訳データを検索
        general_ledger_entries = db.query(GeneralLedger).filter(
            GeneralLedger.source_type.in_(['batch_entry', 'batch_entry_net', 'batch_entry_tax']),
            GeneralLedger.source_id == cash_book_id,
            GeneralLedger.organization_id == organization_id
        ).all()
        
        if not general_ledger_entries:
            return jsonify({'success': False, 'message': '仕訳データが見つかりません'}), 404
        
        # 仕訳データを削除
        for entry in general_ledger_entries:
            db.delete(entry)
        
        db.commit()
        return jsonify({'success': True, 'message': f'{len(general_ledger_entries)}件の仕訳データを削除しました'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
    finally:
        db.close()



@bp.route('/ledger', methods=['GET'])
@login_required
def ledger():
    org_id = get_current_organization_id()
    db = SessionLocal()
    try:
        # 会計期間を取得
        fiscal_periods = (
            db.query(FiscalPeriod)
            .filter_by(organization_id=org_id)
            .order_by(FiscalPeriod.start_date.desc())
            .all()
        )

        # 勘定科目を取得
        account_items = (
            db.query(AccountItem)
            .filter_by(organization_id=org_id)
            .order_by(AccountItem.account_name)
            .all()
        )

        # 選択された会計期間と勘定科目
        selected_fiscal_period_id = request.args.get('fiscal_period_id', type=int)
        selected_account_item_id = request.args.get('account_item_id', type=int)

        transactions = []
        monthly_totals = []
        opening_balance = 0
        selected_fiscal_period = None
        selected_account_item = None

        if selected_fiscal_period_id and selected_account_item_id:
            selected_fiscal_period = (
                db.query(FiscalPeriod)
                .filter_by(id=selected_fiscal_period_id, organization_id=org_id)
                .first()
            )
            selected_account_item = (
                db.query(AccountItem)
                .filter_by(id=selected_account_item_id, organization_id=org_id)
                .first()
            )

            if selected_fiscal_period and selected_account_item:
                # 期首残高を計算（会計期間開始日より前の仕訳）
                opening_entries = (
                    db.query(GeneralLedger)
                    .filter(
                        GeneralLedger.organization_id == org_id,
                        GeneralLedger.transaction_date < selected_fiscal_period.start_date,
                        or_(
                            GeneralLedger.debit_account_item_id
                            == selected_account_item_id,
                            GeneralLedger.credit_account_item_id
                            == selected_account_item_id,
                        ),
                    )
                    .all()
                )

                for entry in opening_entries:
                    if entry.debit_account_item_id == selected_account_item_id:
                        opening_balance += entry.debit_amount
                    if entry.credit_account_item_id == selected_account_item_id:
                        opening_balance -= entry.credit_amount

                # 勘定科目の種類に応じて期首残高の符号を調整
                if selected_account_item.major_category in ['收入']:
                    opening_balance = -opening_balance

                # 当期の仕訳を取得
                current_entries = (
                    db.query(GeneralLedger)
                    .filter(
                        GeneralLedger.organization_id == org_id,
                        GeneralLedger.transaction_date
                        >= selected_fiscal_period.start_date,
                        GeneralLedger.transaction_date
                        <= selected_fiscal_period.end_date,
                        or_(
                            GeneralLedger.debit_account_item_id
                            == selected_account_item_id,
                            GeneralLedger.credit_account_item_id
                            == selected_account_item_id,
                        ),
                    )
                    .order_by(GeneralLedger.transaction_date)
                    .all()
                )

                # 取引データを作成
                running_balance = opening_balance
                current_month = None
                month_debit_total = 0
                month_credit_total = 0

                for entry in current_entries:
                    # transaction_date は文字列想定なので先頭7桁(YYYY-MM) を取得
                    entry_month = entry.transaction_date[:7]
                    if current_month and current_month != entry_month:
                        monthly_totals.append(
                            {
                                "month": current_month,
                                "debit_total": month_debit_total,
                                "credit_total": month_credit_total,
                            }
                        )
                        month_debit_total = 0
                        month_credit_total = 0
                    current_month = entry_month

                    # 相手勘定科目と金額を決定
                    if entry.debit_account_item_id == selected_account_item_id:
                        counterpart_account = entry.credit_account_item.account_name
                        debit_amount = entry.debit_amount
                        credit_amount = 0
                        if selected_account_item.major_category in ['收入']:
                            running_balance -= debit_amount
                        else:
                            running_balance += debit_amount
                        month_debit_total += debit_amount
                    else:
                        counterpart_account = entry.debit_account_item.account_name
                        debit_amount = 0
                        credit_amount = entry.credit_amount
                        if selected_account_item.major_category in ['收入']:
                            running_balance += credit_amount
                        else:
                            running_balance -= credit_amount
                        month_credit_total += credit_amount

                    transactions.append(
                        {
                            "date": entry.transaction_date,
                            "counterpart_account": counterpart_account,
                            "summary": entry.summary or "",
                            "debit": debit_amount,
                            "credit": credit_amount,
                            "balance": running_balance,
                        }
                    )

                # 最後の月の合計を追加
                if current_month:
                    monthly_totals.append(
                        {
                            "month": current_month,
                            "debit_total": month_debit_total,
                            "credit_total": month_credit_total,
                        }
                    )

        return render_template(
            "ledger/index.html",
            fiscal_periods=fiscal_periods,
            account_items=account_items,
            selected_fiscal_period=selected_fiscal_period,
            selected_account_item=selected_account_item,
            opening_balance=opening_balance,
            transactions=transactions,
            monthly_totals=monthly_totals,
            current_organization=get_current_organization(),
        )
    finally:
        db.close()



# ========== タグマスターAPI =========

# 取引先全件取得API (Tom Select用)

