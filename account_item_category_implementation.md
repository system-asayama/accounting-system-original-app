# 勘定科目登録フォームのプルダウン化実装

## 実装概要

勘定科目の手動登録時に、大分類・中分類・小分類をプルダウンで選択できるように修正しました。添付されたfreeeの勘定科目CSVファイルの分類階層に従っています。

## 実装した変更点

### 1. 分類階層データの作成

**ファイル**: `/accounting-system-app/account_item_categories.json`

freeeのCSVファイルから抽出した分類階層データをJSON形式で保存しました。

**階層構造**:
- **大分類**: 資産、負債及び純資産、損益
- **中分類**: 流動資産、固定資産、負債、純資産、売上高、売上原価、販売費及び一般管理費など
- **小分類**: 売上債権、棚卸資産、有形固定資産、販売管理費など

### 2. バックエンド処理の修正

#### 2.1 勘定科目新規追加ルート (`account_item_create`)

**ファイル**: `app.py` (925行目～)

**変更内容**:
- POSTリクエスト時に `mid_category`（中分類）と `sub_category`（小分類）を取得
- GETリクエスト時に分類階層データ（`categories`）をテンプレートに渡す

```python
# 分類階層データを読み込む
import json
categories_path = os.path.join(os.path.dirname(__file__), 'account_item_categories.json')
with open(categories_path, 'r', encoding='utf-8') as f:
    categories = json.load(f)

return render_template('account_items/form.html', categories=categories)
```

#### 2.2 勘定科目編集ルート (`account_item_edit`)

**ファイル**: `app.py` (988行目～)

**変更内容**:
- 新規追加と同様に、中分類・小分類の取得と保存を追加
- 編集時にも分類階層データをテンプレートに渡す

### 3. フロントエンド（HTMLフォーム）の修正

**ファイル**: `/templates/account_items/form.html`

#### 3.1 プルダウン（select要素）への変更

**変更前**:
```html
<input type="text" id="major_category" name="major_category" placeholder="例: 資産">
<input type="text" id="mid_category" name="mid_category" placeholder="例: 流動資産">
<input type="text" id="sub_category" name="sub_category" placeholder="例: 現金・預金">
```

**変更後**:
```html
<select id="major_category" name="major_category" required>
    <option value="">-- 選択してください --</option>
    {% for major in categories.keys() %}
    <option value="{{ major }}">{{ major }}</option>
    {% endfor %}
</select>

<select id="mid_category" name="mid_category">
    <option value="">-- 選択してください --</option>
</select>

<select id="sub_category" name="sub_category">
    <option value="">-- 選択してください --</option>
</select>
```

#### 3.2 JavaScriptによる連動処理

**実装内容**:
- 大分類を選択すると、対応する中分類の選択肢が表示される
- 中分類を選択すると、対応する小分類の選択肢が表示される
- 編集モードの場合、既存の値に基づいて中分類・小分類が自動的に設定される

```javascript
// 大分類が変更されたとき
majorSelect.addEventListener('change', function() {
    const major = this.value;
    
    // 中分類をリセット
    midSelect.innerHTML = '<option value="">-- 選択してください --</option>';
    subSelect.innerHTML = '<option value="">-- 選択してください --</option>';
    
    if (major && categoriesData[major]) {
        const midCategories = Object.keys(categoriesData[major]);
        midCategories.forEach(mid => {
            const option = document.createElement('option');
            option.value = mid;
            option.textContent = mid;
            midSelect.appendChild(option);
        });
    }
});
```

## 使用方法

### 新規登録時

1. 勘定科目一覧ページから「新規追加」ボタンをクリック
2. 大分類のプルダウンから選択（例: 資産）
3. 中分類のプルダウンが自動的に更新されるので選択（例: 流動資産）
4. 小分類のプルダウンが自動的に更新されるので選択（例: 売上債権）
5. その他の項目を入力して「追加」ボタンをクリック

### 編集時

1. 勘定科目一覧ページから編集したい項目の「編集」ボタンをクリック
2. 既存の大分類・中分類・小分類が自動的に選択された状態で表示される
3. 必要に応じて変更して「更新」ボタンをクリック

## 分類の種類

### 大分類（3種類）
- 資産
- 負債及び純資産
- 損益

### 中分類（14種類）
- 流動資産
- 固定資産
- 繰延資産
- 負債
- 純資産
- 売上高
- 売上原価
- 販売費及び一般管理費
- 営業外収益
- 営業外費用
- 特別利益
- 特別損失
- 法人税等
- 法人税等調整額

### 小分類（35種類）
売上債権、棚卸資産、有形固定資産、販売管理費など、各中分類に応じた小分類が用意されています。

## 技術的な詳細

### データ構造

分類階層データは以下のような3階層のJSON構造で管理されています:

```json
{
  "資産": {
    "流動資産": [
      "他流動資産",
      "売上債権",
      "有価証券",
      "棚卸資産"
    ],
    "固定資産": [
      "投資その他の資産",
      "有形固定資産",
      "無形固定資産"
    ]
  }
}
```

### バリデーション

- 大分類は必須項目として設定
- 中分類・小分類は任意項目
- 大分類を選択しないと中分類・小分類は選択できない仕様

## 注意事項

1. **既存データへの影響**: 既存の勘定科目データには影響しません。編集時に分類を再選択することで新しい分類体系に移行できます。

2. **データベーススキーマ**: `AccountItem`モデルの`mid_category`と`sub_category`カラムが既に存在することを前提としています。存在しない場合はマイグレーションが必要です。

3. **分類データの更新**: 分類を追加・変更する場合は、`account_item_categories.json`ファイルを編集してください。

## 今後の拡張案

1. 分類マスターをデータベースで管理し、管理画面から編集可能にする
2. 分類に応じたデフォルト値の自動設定（税区分、取引相手方など）
3. 分類別の勘定科目一覧表示機能
