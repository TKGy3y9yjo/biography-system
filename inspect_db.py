 
# inspect_db.py
import sqlite3
import config

def inspect_database():
    # 連接到資料庫
    conn = sqlite3.connect(config.DATABASE)
    cursor = conn.cursor()

    # 查詢所有表的名稱
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("資料庫中的表：", [table[0] for table in tables])

    # 查詢每個表的內容
    for table in tables:
        table_name = table[0]
        print(f"\n表：{table_name}")
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        # 打印欄位名稱
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        print("欄位：", columns)
        # 打印數據
        print("數據：")
        for row in rows:
            print(row)

    conn.close()

if __name__ == "__main__":
    inspect_database()