import os
from storage.config import Config

class Downloader:
    def __init__(self, client):
        self.client = client

    async def download_message_media(self, message, progress_callback=None):
        try:
            path = await self.client.download_media(
                message,
                file=Config.DOWNLOAD_PATH,
                progress_callback=progress_callback
            )
            return path
        except Exception as e:
            print(f"Error downloading: {e}")
            return None