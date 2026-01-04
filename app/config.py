import os
from dataclasses import dataclass
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

@dataclass
class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DEBUG: bool = os.getenv("DEBUG", "1") in ("1", "true", "True")
    ENV: str = os.getenv("ENV", "dev")
    VERSION: str = os.getenv("APP_VERSION", "0.1.0")
    TZ: str = os.getenv("TZ", "Asia/Tokyo")

settings = Settings()
