import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    # HerokuのDATABASE_URLは "postgres://" で始まるが、
    # SQLAlchemy 1.4以降は "postgresql://" を要求するため変換が必要
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./accounting.db")
    
    # Herokuの古いpostgres://形式をpostgresql://に変換
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    DEBUG = os.getenv("DEBUG", "1") == "1"

settings = Settings()
