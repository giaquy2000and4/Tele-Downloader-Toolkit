import os
import asyncio
from storage.config import Config
from telethon import utils


class Downloader:
    def __init__(self, client, session_name):
        self.client = client
        self.session_name = session_name  # Lưu tên acc để tạo folder riêng

        # Tạo thư mục riêng cho từng account
        self.base_path = os.path.join(Config.DOWNLOAD_PATH, self.session_name)
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)

    async def download_with_resume(self, message, file_name, task_id, db_instance, progress_callback, cancel_event):
        """
        Tải xuống hỗ trợ Resume.
        cancel_event: threading.Event hoặc asyncio.Event để báo hiệu dừng.
        """
        file_path = os.path.join(self.base_path, file_name)

        # Check file đã tải được bao nhiêu byte
        current_size = 0
        if os.path.exists(file_path):
            current_size = os.path.getsize(file_path)

        mode = 'ab' if current_size > 0 else 'wb'  # Append (nối tiếp) hoặc Write mới

        total = message.file.size

        if current_size >= total:
            # Đã tải xong từ trước
            db_instance.update_progress(task_id, total, 'completed')
            if progress_callback: progress_callback(1.0, current_size, total)
            return file_path

        # Mở file để ghi tiếp
        with open(file_path, mode) as f:
            # Telethon cho phép tải từng chunk (mảnh)
            async for chunk in self.client.iter_download(message.media, offset=current_size, request_size=1024 * 1024):
                if cancel_event.is_set():
                    db_instance.update_progress(task_id, current_size, 'paused')
                    return None  # Dừng tải

                f.write(chunk)
                current_size += len(chunk)

                # Cập nhật DB và UI
                if progress_callback:
                    percentage = current_size / total
                    progress_callback(percentage, current_size, total)

        # Hoàn thành
        db_instance.update_progress(task_id, total, 'completed')
        return file_path