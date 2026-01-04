# AI主導開発のベース環境

## これに含まれるもの
- Python 3.12 / pip
- SQLAlchemy / Alembic（DBマイグレーション）
- 環境変数ローダー（python-dotenv）
- Postgresは外部（Neonなど）を利用

## 使い方
1. `.env` を作成（`.env.sample` をコピーして値を入れる）
2. 依存インストール： `pip install -r requirements.txt`
3. モデルを追加したら：
   - `alembic revision --autogenerate -m "xxxx"`
   - `alembic upgrade head`

> アプリ本体はまだありません。機能を作るときに `app.py` や FastAPI/FlaskをAIに作らせてください。
