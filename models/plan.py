 
# models/plan.py
import sqlite3
import config

def init_plans_db():
    conn = sqlite3.connect(config.DATABASE)
    cursor = conn.cursor()

    # 創建 plans 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            word_limit INTEGER NOT NULL
        )
    ''')

    # 創建 user_plans 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (plan_id) REFERENCES plans(id)
        )
    ''')

    # 插入預設方案
    cursor.execute("INSERT OR IGNORE INTO plans (id, name, word_limit) VALUES (?, ?, ?)", (1, "免費", 500))
    cursor.execute("INSERT OR IGNORE INTO plans (id, name, word_limit) VALUES (?, ?, ?)", (2, "進階", 1000))
    cursor.execute("INSERT OR IGNORE INTO plans (id, name, word_limit) VALUES (?, ?, ?)", (3, "高級", 0))

    conn.commit()
    conn.close()
    print("Plans database initialized.")

if __name__ == "__main__":
    init_plans_db()