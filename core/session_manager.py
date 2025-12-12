import os
import glob


class SessionManager:
    STORAGE_DIR = "storage"

    @staticmethod
    def get_all_sessions():
        """Lấy danh sách các file session đã lưu"""
        if not os.path.exists(SessionManager.STORAGE_DIR):
            os.makedirs(SessionManager.STORAGE_DIR)

        # Tìm tất cả file .session
        files = glob.glob(os.path.join(SessionManager.STORAGE_DIR, "*.session"))
        sessions = []
        for f in files:
            # Lấy tên file làm tên session (vd: user1.session -> user1)
            filename = os.path.basename(f)
            name = os.path.splitext(filename)[0]
            sessions.append(name)
        return sessions

    @staticmethod
    def delete_session(session_name):
        path = os.path.join(SessionManager.STORAGE_DIR, f"{session_name}.session")
        if os.path.exists(path):
            os.remove(path)
            return True
        return False