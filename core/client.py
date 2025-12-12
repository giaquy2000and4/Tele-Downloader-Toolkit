import asyncio
from telethon import TelegramClient
from storage.config import Config


class TeleClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TeleClient, cls).__new__(cls)
            cls._instance.client = TelegramClient(
                f"storage/{Config.SESSION_NAME}",
                Config.API_ID,
                Config.API_HASH
            )
        return cls._instance

    async def connect(self):
        await self.client.connect()

    async def is_user_authorized(self):
        return await self.client.is_user_authorized()

    async def send_code(self, phone):
        await self.client.send_code_request(phone)

    async def sign_in(self, phone=None, code=None, password=None):
        await self.client.sign_in(phone=phone, code=code, password=password)

    def get_client(self):
        return self.client

    async def get_dialogs(self, limit=100):
        """Lấy danh sách chat (Tối ưu async để tránh treo UI)"""
        if not self.client.is_connected():
            await self.client.connect()

        dialogs = []
        try:
            async for dialog in self.client.iter_dialogs(limit=limit):
                entity_type = "User"
                if dialog.is_channel:
                    entity_type = "Channel"
                elif dialog.is_group:
                    entity_type = "Group"

                dialogs.append({
                    "id": dialog.id,
                    "name": dialog.name if dialog.name else "Deleted Account",
                    "type": entity_type,
                    "entity": dialog.entity
                })
                # Nghỉ cực ngắn để UI có thời gian vẽ lại
                await asyncio.sleep(0.001)
        except Exception as e:
            print(f"Error getting dialogs: {e}")
        return dialogs