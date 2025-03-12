# models/biography.py
import sqlite3
import config

# models/biography.py
def init_biographies_db():
    conn = sqlite3.connect(config.DATABASE)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS biographies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            style TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT '中文',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()
    print("Biographies table created.")

if __name__ == "__main__":
    init_biographies_db()