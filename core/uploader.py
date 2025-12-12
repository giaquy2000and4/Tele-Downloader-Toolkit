import os

class Uploader:
    def __init__(self, client):
        self.client = client

    async def upload_file(self, entity, file_path, caption=None, progress_callback=None):
        try:
            # force_document=True: Gửi dạng file gốc, tránh lỗi nén ảnh của Telethon/Pillow
            await self.client.send_file(
                entity,
                file_path,
                caption=caption,
                progress_callback=progress_callback,
                force_document=True
            )
            return True
        except Exception as e:
            print(f"Upload Error: {e}")
            raise e