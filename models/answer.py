# models/answer.py
import sqlite3
import config

def init_questions_db():
    conn = sqlite3.connect(config.DATABASE)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            question_order INTEGER NOT NULL,
            theme TEXT NOT NULL,
            story_id INTEGER NOT NULL,  -- 新增 story_id
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            answer TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (question_id) REFERENCES questions(id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Questions and answers tables created.")

if __name__ == "__main__":
    init_questions_db()