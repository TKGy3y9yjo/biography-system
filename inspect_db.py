import sqlite3

DB_PATH = "database.db"

def inspect_tables():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("📋 資料表清單：")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cur.fetchall()]
    for t in tables:
        print(" -", t)
    print()

    for t in tables:
        print(f"🧱 表格結構：{t}")
        cur.execute(f"PRAGMA table_info({t});")
        for col in cur.fetchall():
            print(f"   {col[1]} ({col[2]})")
        print()
    conn.close()

# ---------- 舊有工具 ----------

def ensure_title_column():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(biographies);")
    cols = [c[1] for c in cur.fetchall()]
    if "title" not in cols:
        print("🛠️  新增 biographies.title")
        cur.execute("ALTER TABLE biographies ADD COLUMN title TEXT;")
        conn.commit()
    conn.close()

def create_answer_images_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='answer_images';")
    if not cur.fetchone():
        print("🛠️  建立 answer_images 表")
        cur.execute("""
            CREATE TABLE answer_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question_id INTEGER,
                image_path TEXT,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    conn.close()

# ---------- 新增：追問相關欄位 ----------

def ensure_follow_up_columns():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # questions 新欄位
    cur.execute("PRAGMA table_info(questions);")
    q_cols = [c[1] for c in cur.fetchall()]
    for col_def in [
        ("follow_up_strategy", "VARCHAR(50)"),
        ("context_keywords",   "TEXT"),
        ("expected_answer_type", "VARCHAR(20)")
    ]:
        if col_def[0] not in q_cols:
            print(f"🛠️  新增 questions.{col_def[0]}")
            cur.execute(f"ALTER TABLE questions ADD COLUMN {col_def[0]} {col_def[1]};")

    # answers 新欄位
    cur.execute("PRAGMA table_info(answers);")
    a_cols = [c[1] for c in cur.fetchall()]
    for col_def in [
        ("emotion_score",     "INTEGER"),   # 1–10
        ("completeness_score","INTEGER"),   # 1–10
        ("key_entities",      "TEXT") ,      # JSON 格式字串
        ("detail_score",      "REAL") , 
        ("reflection_score",      "REAL") , 
        ("redundancy",      "REAL") , 
        ("length","INTEGER")
        
    ]:
        if col_def[0] not in a_cols:
            print(f"🛠️  新增 answers.{col_def[0]}")
            cur.execute(f"ALTER TABLE answers ADD COLUMN {col_def[0]} {col_def[1]};")

    conn.commit()
    conn.close()

# ---------- 執行區 ----------

if __name__ == "__main__":
    print("🔍 檢查資料庫結構...\n")
    inspect_tables()
    ensure_title_column()
    create_answer_images_table()
    ensure_follow_up_columns()
    print("\n✅ 資料庫結構檢查／升級完成")
