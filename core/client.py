import asyncio
from telethon import TelegramClient
from storage.config import Config


class TeleClient:
    # Bỏ Singleton (_instance) để hỗ trợ đa tài khoản login cùng lúc nếu cần
    # Hoặc đơn giản là khởi tạo lại khi đổi acc

    def __init__(self, session_name=None):
        # Nếu không truyền tên session, dùng tên mặc định trong config
        self.session_name = session_name if session_name else Config.SESSION_NAME

        self.client = TelegramClient(
            f"storage/{self.session_name}",
            Config.API_ID,
            Config.API_HASH
        )

    async def connect(self):
        await self.client.connect()

    async def disconnect(self):
        await self.client.disconnect()

    async def is_user_authorized(self):
        return await self.client.is_user_authorized()

    async def send_code(self, phone):
        await self.client.send_code_request(phone)

    async def sign_in(self, phone=None, code=None, password=None):
        await self.client.sign_in(phone=phone, code=code, password=password)

    async def get_me(self):
        return await self.client.get_me()

    def get_client(self):
        return self.client

    async def get_dialogs(self, limit=100):
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
                await asyncio.sleep(0.001)
        except Exception as e:
            print(f"Error getting dialogs: {e}")
        return dialogs