from sqlalchemy import create_engine
import os
from sqlalchemy.sql import text

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # 替換為實際的 Key
SECRET_KEY = os.getenv("SECRET_KEY")  # 用於 JWT，例如 'python -c "import secrets; print(secrets.token_hex(16))"'
DATABASE = "database.db"  # SQLite 資料庫檔案名稱
DATABASE_URL = f"sqlite:///{os.getenv('DATABASE', 'database.db')}?timeout=10"
ENGINE = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
with ENGINE.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))