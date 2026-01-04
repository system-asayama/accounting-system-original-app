# 取引明細インポート機能 仕様書

## 概要
銀行の取引明細をCSV/Excelファイルからインポートし、勘定科目を登録して仕訳データに変換する機能。

## 機能要件

### 1. 取引明細のインポート
- CSV/Excelファイルのアップロード
- 口座名の選択（登録済み口座のみ）
- インポートされた明細を`imported_transactions`テーブルに保存

### 2. 明細一覧の表示
- 口座ごとにグループ化して表示
- 検索条件：口座名、取引日範囲、ステータス（未処理/処理済み）
- 表示項目：
  - 取引日
  - 摘要/内容
  - 入金金額
  - 出金金額
  - 残高
  - ステータス（未処理/処理済み）

### 3. 明細の詳細編集
- 勘定科目の選択
- 摘要の編集
- 仕訳プレビューの表示
- 登録ボタンで仕訳データ（`journal_entries`）に変換

### 4. ステータス管理
- 未処理（status=0）: 勘定科目未登録
- 処理済み（status=1）: 勘定科目登録済み、仕訳データ作成済み

## データモデル

### imported_transactions テーブル
```sql
CREATE TABLE imported_transactions (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    account_name VARCHAR(255) NOT NULL,
    transaction_date VARCHAR(10) NOT NULL,
    description TEXT,
    income_amount INTEGER DEFAULT 0,
    expense_amount INTEGER DEFAULT 0,
    status INTEGER DEFAULT 0,
    journal_entry_id INTEGER,
    imported_at VARCHAR(19),
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id)
);
```

## ルート設計

### 1. インポートページ
- URL: `/transactions/import`
- Method: GET, POST
- 機能: CSV/Excelファイルのアップロードと処理

### 2. 明細一覧ページ
- URL: `/transactions/imported`
- Method: GET
- 機能: インポートされた明細の一覧表示

### 3. 明細詳細編集ページ
- URL: `/transactions/imported/<int:id>/edit`
- Method: GET, POST
- 機能: 明細の詳細編集と勘定科目登録

### 4. 明細削除API
- URL: `/api/transactions/imported/<int:id>/delete`
- Method: POST
- 機能: 明細の削除

## CSVフォーマット

### 想定フォーマット（freee銀行明細）
```csv
取引日,摘要,入金金額,出金金額,残高
2025-08-01,振込入金,0,220,56370
2025-08-01,ﾊﾟﾜｰ振込,0,93600,56590
```

### インポート処理
1. CSVファイルを読み込み
2. 各行をパースして`imported_transactions`テーブルに保存
3. `account_name`は選択された口座名を使用
4. `organization_id`は現在のユーザーの事業所IDを使用
5. `status`は0（未処理）で初期化

## UI設計

### 明細一覧画面
- 検索条件フォーム（口座名、取引日範囲、ステータス）
- 明細一覧テーブル
- 各行に「編集」ボタン
- ページネーション

### 明細詳細編集画面
- 取引情報表示（取引日、摘要、金額）
- 勘定科目選択ドロップダウン
- 摘要編集フィールド
- 仕訳プレビュー
- 登録ボタン
- キャンセルボタン

## 実装順序

1. ✅ データモデルの作成（`ImportedTransaction`）
2. テーブルの作成（マイグレーション）
3. インポート機能の実装
4. 明細一覧ページの実装
5. 明細詳細編集ページの実装
6. 仕訳データへの変換処理の実装
7. テストとデバッグ
