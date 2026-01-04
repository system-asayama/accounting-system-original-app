# ベースイメージとしてPython 3.11を使用
FROM mcr.microsoft.com/devcontainers/python:3.11

# 依存関係のインストール
RUN pip install --upgrade pip
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt

# 作業ディレクトリの設定
WORKDIR /workspace

# ポート8000を公開
EXPOSE 8000

# コンテナ起動時に実行されるコマンド（Code Spacesでは通常、devcontainer.jsonのpostCreateCommandやLifecycle Hooksで設定されますが、念のため）
# CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]
