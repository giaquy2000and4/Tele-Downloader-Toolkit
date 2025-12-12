import sqlite3
import os
from storage.config import Config


class Database:
    DB_FILE = "storage/data.db"

    def __init__(self):
        if not os.path.exists("storage"):
            os.makedirs("storage")

        self.conn = sqlite3.connect(self.DB_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # Bảng lưu Tasks Download
        self.cursor.execute("""
                            CREATE TABLE IF NOT EXISTS downloads
                            (
                                id
                                INTEGER
                                PRIMARY
                                KEY
                                AUTOINCREMENT,
                                chat_id
                                INTEGER,
                                message_id
                                INTEGER,
                                file_name
                                TEXT,
                                save_path
                                TEXT,
                                total_size
                                INTEGER,
                                downloaded_size
                                INTEGER,
                                status
                                TEXT, -- 'pending', 'downloading', 'paused', 'completed', 'error'
                                account_name
                                TEXT,
                                created_at
                                TIMESTAMP
                                DEFAULT
                                CURRENT_TIMESTAMP
                            )
                            """)
        self.conn.commit()

    def add_task(self, chat_id, message_id, file_name, save_path, total_size, account_name):
        self.cursor.execute("""
                            INSERT INTO downloads (chat_id, message_id, file_name, save_path, total_size,
                                                   downloaded_size, status, account_name)
                            VALUES (?, ?, ?, ?, ?, 0, 'pending', ?)
                            """, (chat_id, message_id, file_name, save_path, total_size, account_name))
        self.conn.commit()
        return self.cursor.lastrowid

    def update_progress(self, task_id, downloaded_size, status):
        self.cursor.execute("""
                            UPDATE downloads
                            SET downloaded_size = ?,
                                status          = ?
                            WHERE id = ?
                            """, (downloaded_size, status, task_id))
        self.conn.commit()

    def get_task(self, task_id):
        self.cursor.execute("SELECT * FROM downloads WHERE id = ?", (task_id,))
        return self.cursor.fetchone()

    def get_all_tasks(self, account_name):
        self.cursor.execute("SELECT * FROM downloads WHERE account_name = ? ORDER BY id DESC", (account_name,))
        return self.cursor.fetchall()

    def delete_task(self, task_id):
        self.cursor.execute("DELETE FROM downloads WHERE id = ?", (task_id,))
        self.conn.commit()


# Khởi tạo singleton
db = Database()