# tele-downloader-toolkit/core/client.py

import asyncio
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable, Union

try:
    from telethon import TelegramClient
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
        PasswordHashInvalidError,
        FloodWaitError,
        PeerFloodError
    )
    from telethon.tl.types import User, Chat, Channel
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install telethon")
    sys.exit(1)

LogFuncType = Callable[[str, Optional[str]], None]
InputFuncType = Callable[[str, Optional[str], bool], str]


class TelegramClientWrapper:
    """
    Wraps the Telethon TelegramClient, handling connection, authorization,
    and session management. It accepts UI-specific logging and input functions
    to remain UI-agnostic.
    """

    def __init__(self,
                 api_id: int,
                 api_hash: str,
                 phone: str,
                 account_index: int,
                 log_func: LogFuncType,
                 input_func: InputFuncType):

        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.account_index = account_index
        self._log_func = log_func
        self._input_func = input_func

        session_dir = Path("sessions")
        session_dir.mkdir(exist_ok=True)
        session_path = session_dir / f"session_{account_index}"

        self._client = TelegramClient(str(session_path), api_id, api_hash)

        self.client = self._client

    async def connect_client(self) -> bool:
        """
        Connects to Telegram and handles the authorization flow if necessary.
        Returns True if connected and authorized, False otherwise.
        """
        self._log_func(f"Attempting to connect with account #{self.account_index} ({self.phone})...", "blue")
        try:
            await self._client.connect()

            if not await self._client.is_user_authorized():
                self._log_func("Authorization required. Signing in...", "yellow")
                try:
                    masked_phone = self.phone[:3] + "****" + self.phone[-4:] if len(self.phone) > 7 else self.phone
                    self._log_func(
                        f"Attempting to login account #{self.account_index} ({masked_phone}) → sending code...",
                        "yellow"
                    )
                    await self._client.send_code_request(self.phone)
                except FloodWaitError as e:
                    self._log_func(f"Too many attempts. Please wait {e.seconds} seconds.", "red")
                    return False

                try:
                    code = self._input_func("Enter the code from Telegram", None, False)
                    await self._client.sign_in(self.phone, code=code)
                except SessionPasswordNeededError:
                    password = self._input_func("Enter your 2FA password", None, True)
                    await self._client.sign_in(password=password)
                except (PhoneCodeInvalidError, PhoneCodeExpiredError) as e:
                    self._log_func(f"OTP error: {e}. Please try again.", "red")
                    return False
                except PasswordHashInvalidError:
                    self._log_func("Incorrect 2FA password. Please try again.", "red")
                    return False
                except Exception as e:
                    self._log_func(f"Login error during sign-in: {e}", "red")
                    return False

            me = await self._client.get_me()
            display_name = f"{(me.first_name or '').strip()} {(me.last_name or '').strip()}".strip()
            username = f"@{me.username}" if getattr(me, 'username', None) else ""
            self._log_func(f"Connected: {display_name} {username}".strip(), "green")
            return True

        except FloodWaitError as e:
            self._log_func(f"Telegram FloodWaitError: Waiting {e.seconds} seconds before next attempt.", "yellow")
            await asyncio.sleep(e.seconds + 5)
            return False
        except Exception as e:
            self._log_func(f"Connection error: {e}", "red")
            return False

    async def disconnect_client(self) -> None:
        """Disconnects the Telethon client if it's connected."""
        if self._client.is_connected():
            try:
                self._log_func(f"Disconnecting client for account #{self.account_index}...", "blue")
                await self._client.disconnect()
                self._log_func(f"Client for account #{self.account_index} disconnected.", "green")
            except Exception as e:
                self._log_func(f"Error disconnecting client for account #{self.account_index}: {e}", "red")

    def is_connected(self) -> bool:
        """Checks if the client is currently connected."""
        return self._client.is_connected()

    async def is_authorized(self) -> bool:
        """Checks if the user is authorized."""
        return await self._client.is_user_authorized()