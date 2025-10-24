import asyncio
import os
import sys
import time
import re
import json
import signal
import hashlib
import argparse  # For CLI
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Callable, Union
from pathlib import Path

try:
    from telethon import TelegramClient
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
        PasswordHashInvalidError,
        FloodWaitError,
        PeerFloodError  # Added PeerFloodError
    )
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, User, Chat, Channel
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install telethon")
    sys.exit(1)

try:
    from colorama import Fore, Style
    import colorama
except ImportError:
    class NoColor:
        def __getattr__(self, name):
            return ''


    Fore = NoColor()
    Style = NoColor()
    colorama = None

try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, **kwargs: x

try:
    import humanize
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install humanize")
    sys.exit(1)

try:
    from dotenv import load_dotenv, set_key, dotenv_values
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install python-dotenv")
    sys.exit(1)

import getpass  # For sensitive input in CLI

# ============================ CẤU HÌNH UI (Console-specific, for default behavior) =============================

WIDTH = 78
USE_COLOR = True
BAR_CHAR = "─"

if colorama:
    colorama.init(autoreset=True)


def c(text: str, color: str) -> str:
    if not USE_COLOR:
        return text
    return f"{color}{text}{Style.RESET_ALL}"


def pad(text: str, width: int = WIDTH, align: str = "left") -> str:
    text = text if text is not None else ""
    if len(text) > width:
        text = text[: width - 3] + "..."
    if align == "left":
        return text.ljust(width)
    elif align == "right":
        return text.rjust(width)
    else:
        return text.center(width)


def line(char: str = BAR_CHAR, width: int = WIDTH) -> str:
    return char * width


def box(lines: List[str], width: int = WIDTH) -> str:
    top = "┌" + ("─" * (width - 2)) + "┐"
    bottom = "└" + ("─" * (width - 2)) + "┘"
    inner = "\n".join("│" + s[: width - 2].ljust(width - 2) + "│" for s in lines)
    return f"{top}\n{inner}\n{bottom}"


# Simple console logger
def console_log_func(message: str, color_tag: Optional[str] = None):
    color_map = {
        "red": Fore.RED,
        "green": Fore.GREEN,
        "yellow": Fore.YELLOW,
        "blue": Fore.BLUE,
        "cyan": Fore.CYAN,
        "reset": Style.RESET_ALL  # Not used directly but for completeness
    }
    prefix = color_map.get(color_tag, "")
    suffix = Style.RESET_ALL if color_tag else ""
    print(f"{prefix}{message}{suffix}")


# Simple console input
def console_input_func(prompt: str, default: Optional[str] = None, hide_input: bool = False) -> str:
    if hide_input:
        try:
            return getpass.getpass(prompt + ": ")
        except Exception:
            # Fallback if getpass fails (e.g., non-interactive console)
            console_log_func("Warning: getpass failed, input will be echoed.", "yellow")
            return input(prompt + ": ")

    full_prompt = prompt
    if default is not None:
        full_prompt += f" (default: {default})"

    user_input = input(full_prompt + ": ")
    return user_input.strip() or (default or "")


# ============================ QUẢN LÝ .ENV =============================

ENV_TEMPLATE = """# Multi-account Telegram Tool
CURRENT_ACCOUNT=0
# Example:
# ACCOUNT_1_PHONE=+84123456789
# ACCOUNT_1_API_ID=123456
# ACCOUNT_1_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxx
# ACCOUNT_1_DOWNLOAD_DIR=/absolute/path/to/downloads
"""


def ensure_env_exists(env_path: Path) -> None:
    if not env_path.exists():
        env_path.write_text(ENV_TEMPLATE, encoding="utf-8")


def load_env(env_path: Path) -> Dict[str, str]:
    # Use dotenv_values to get all current .env values
    # set_key does not automatically load everything into os.environ,
    # so we explicitly parse if needed for consistency across systems
    load_dotenv(dotenv_path=str(env_path))  # ensure os.environ is updated
    return dotenv_values(dotenv_path=str(env_path))


def save_env(env_path: Path, data: Dict[str, str]) -> None:
    # Use set_key to update .env file cleanly
    for k, v in data.items():
        set_key(dotenv_path=str(env_path), key_to_set=k, value_to_set=v)

    # After saving, reload to ensure internal state is consistent
    load_dotenv(dotenv_path=str(env_path), override=True)


def get_current_account_index(data: Dict[str, str]) -> int:
    try:
        return int(str(data.get("CURRENT_ACCOUNT", "0")).strip())
    except Exception:
        return 0


def get_account_config(data: Dict[str, str], idx: int) -> Dict[str, str]:
    # Prioritize account-specific config, fallback to global defaults if idx=0 or not found
    phone = data.get(f"ACCOUNT_{idx}_PHONE")
    api_id = data.get(f"ACCOUNT_{idx}_API_ID")
    api_hash = data.get(f"ACCOUNT_{idx}_API_HASH")
    download_dir = data.get(f"ACCOUNT_{idx}_DOWNLOAD_DIR")

    # If account-specific config is incomplete, try to use global defaults for 0
    if not (phone and api_id and api_hash) and idx == 0:
        phone = data.get("API_PHONE", phone)  # Fallback to a global API_PHONE if you have one
        api_id = data.get("API_ID", api_id)
        api_hash = data.get("API_HASH", api_hash)
        download_dir = data.get("DOWNLOAD_DIR", download_dir)

    return {
        "PHONE": phone if phone else "",
        "API_ID": api_id if api_id else "",
        "API_HASH": api_hash if api_hash else "",
        "DOWNLOAD_DIR": download_dir if download_dir else "downloads",
    }


def set_current_account_index(envd: Dict[str, str], idx: int) -> Dict[str, str]:
    envd["CURRENT_ACCOUNT"] = str(idx)
    return envd


def find_next_account_index(envd: Dict[str, str]) -> int:
    existing_idxs = {
        int(k.split("_")[1])
        for k in envd.keys()
        if k.startswith("ACCOUNT_") and k.endswith("_PHONE") and k.split("_")[1].isdigit()
    }
    return 1 if not existing_idxs else max(existing_idxs) + 1


async def do_login_flow(
        envd: Dict[str, str],
        log_func: Callable[[str, Optional[str]], None],
        input_func: Callable[[str, Optional[str], bool], str],
        phone: Optional[str] = None,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        download_dir: Optional[str] = None,
        account_idx_to_use: Optional[int] = None  # For explicitly selecting an existing index
) -> Tuple[Dict[str, str], int]:
    """Handles the interactive login flow for CLI/GUI."""

    # If account_idx_to_use is not provided, try to pick one (CLI interactive) or use next available (GUI new account)
    if account_idx_to_use is None:
        accounts = []
        idxs = sorted({
            int(k.split("_")[1])
            for k in envd.keys()
            if k.startswith("ACCOUNT_") and k.endswith("_PHONE") and k.split("_")[1].isdigit()
        })
        for idx in idxs:
            accounts.append({'id': idx, 'phone': envd[f"ACCOUNT_{idx}_PHONE"]})

        if accounts:
            log_func(pad("Existing accounts:", WIDTH, "left"), "blue")
            for acc in accounts:
                log_func(pad(f"  {acc['id']}: {acc['phone']}", WIDTH, "left"))

            while True:
                choice = input_func("Enter account index to use or 'new' to add a new account", hide_input=False)
                if choice.lower() == 'new':
                    account_idx_to_use = find_next_account_index(envd)
                    break
                try:
                    chosen_idx = int(choice)
                    if chosen_idx in idxs:
                        account_idx_to_use = chosen_idx
                        break
                    else:
                        log_func("Invalid index. Please try again.", "red")
                except ValueError:
                    log_func("Invalid input. Enter an index or 'new'.", "red")
        else:
            log_func("No existing accounts. Creating a new one.", "yellow")
            account_idx_to_use = find_next_account_index(envd)

    current_cfg = get_account_config(envd, account_idx_to_use)

    # Prompt for missing info, or use provided args/env values
    resolved_phone = phone or (current_cfg["PHONE"] if current_cfg["PHONE"] else None) or input_func(
        "Enter phone number (e.g., +84123456789)", hide_input=False)
    resolved_api_id_str = str(api_id) if api_id else (current_cfg["API_ID"] if current_cfg["API_ID"] else None)
    if resolved_api_id_str is None:
        while True:
            try:
                resolved_api_id_str = input_func("Enter API ID (from my.telegram.org)", hide_input=False)
                int(resolved_api_id_str)  # Validate it's an int
                break
            except ValueError:
                log_func("API ID must be a number.", "red")
    resolved_api_hash = api_hash or (current_cfg["API_HASH"] if current_cfg["API_HASH"] else None) or input_func(
        "Enter API Hash (from my.telegram.org)", hide_input=False)
    resolved_download_dir = download_dir or (
        current_cfg["DOWNLOAD_DIR"] if current_cfg["DOWNLOAD_DIR"] else None) or input_func("Enter download directory",
                                                                                            default="downloads",
                                                                                            hide_input=False)

    # Update envd with resolved details for the selected index
    envd[f"ACCOUNT_{account_idx_to_use}_PHONE"] = resolved_phone
    envd[f"ACCOUNT_{account_idx_to_use}_API_ID"] = resolved_api_id_str
    envd[f"ACCOUNT_{account_idx_to_use}_API_HASH"] = resolved_api_hash
    envd[f"ACCOUNT_{account_idx_to_use}_DOWNLOAD_DIR"] = resolved_download_dir
    envd = set_current_account_index(envd, account_idx_to_use)

    # Initialize and connect downloader to verify credentials
    downloader = TelegramDownloader(
        api_id=int(resolved_api_id_str),
        api_hash=resolved_api_hash,
        phone=resolved_phone,
        download_dir=resolved_download_dir,
        account_index=account_idx_to_use,
        log_func=log_func,
        input_func=input_func
    )

    log_func(pad(f"Attempting to connect with account #{account_idx_to_use} ({resolved_phone})...", WIDTH, "left"),
             "blue")
    try:
        if await downloader.connect_client():
            log_func(pad(f"Successfully logged in with account #{account_idx_to_use}.", WIDTH, "left"), "green")
            await downloader.client.disconnect()  # Disconnect after successful auth
            return envd, account_idx_to_use
        else:
            log_func(pad("Login verification failed. Please check your credentials.", WIDTH, "left"), "red")
            return envd, 0  # Return 0 for failure
    except Exception as e:
        log_func(pad(f"An error occurred during login verification: {e}", WIDTH, "left"), "red")
        return envd, 0


async def do_logout_flow(
        envd: Dict[str, str],
        log_func: Callable[[str, Optional[str]], None],
        account_index: Optional[int] = None
) -> Dict[str, str]:
    """Handles logout for a specific or current account."""
    idx_to_logout = account_index if account_index is not None else get_current_account_index(envd)

    if idx_to_logout == 0:
        log_func(pad("No account is currently logged in or specified for logout.", WIDTH, "left"), "yellow")
        return envd

    log_func(pad(f"Logging out account #{idx_to_logout}...", WIDTH, "left"), "blue")

    # Clear relevant env vars
    envd.pop(f"ACCOUNT_{idx_to_logout}_PHONE", None)
    envd.pop(f"ACCOUNT_{idx_to_logout}_API_ID", None)
    envd.pop(f"ACCOUNT_{idx_to_logout}_API_HASH", None)
    envd.pop(f"ACCOUNT_{idx_to_logout}_DOWNLOAD_DIR", None)

    # If the current active account is being logged out, reset CURRENT_ACCOUNT
    if get_current_account_index(envd) == idx_to_logout:
        envd["CURRENT_ACCOUNT"] = "0"
        log_func(pad("Current active account reset.", WIDTH, "left"), "yellow")

    # Purge session file for this account
    try:
        session_file = Path("sessions") / f"session_{idx_to_logout}.session"
        state_file = Path(f"session_{idx_to_logout}_state.json")  # State file might be directly in base dir
        if session_file.exists():
            session_file.unlink()
            log_func(pad(f"Deleted session file: {session_file}", WIDTH, "left"), "blue")
        if state_file.exists():
            state_file.unlink()
            log_func(pad(f"Deleted state file: {state_file}", WIDTH, "left"), "blue")

    except Exception as e:
        log_func(pad(f"Error purging session/state files for account #{idx_to_logout}: {e}", WIDTH, "left"), "red")

    log_func(pad(f"Account #{idx_to_logout} logged out successfully.", WIDTH, "left"), "green")
    return envd


async def do_reset_flow(
        envd: Dict[str, str],
        log_func: Callable[[str, Optional[str]], None],
        confirm: bool = False  # Added confirm parameter for GUI/CLI direct calls
) -> Dict[str, str]:
    """Resets all configurations and deletes all session files."""
    if not confirm:
        log_func(pad("Reset cancelled.", WIDTH, "left"), "yellow")
        return envd

    log_func(pad("Resetting all configurations and deleting all session files...", WIDTH, "left"), "red")

    # Clear all account-specific entries and global API keys (if any)
    keys_to_delete = [k for k in envd.keys() if k.startswith("ACCOUNT_") or k in ["API_ID", "API_HASH", "DOWNLOAD_DIR"]]
    for key in keys_to_delete:
        envd.pop(key, None)

    envd["CURRENT_ACCOUNT"] = "0"  # Reset current account to 0

    # Purge all session files
    try:
        session_dir = Path("sessions")
        base_dir = Path(".")
        if session_dir.exists():
            for f in session_dir.iterdir():
                if f.is_file() and f.name.startswith("session_"):
                    f.unlink()
            log_func(pad(f"Deleted all files in {session_dir}", WIDTH, "left"), "blue")

        # Also check base directory for state files (e.g., session_1_state.json)
        for f in base_dir.iterdir():
            if f.is_file() and f.name.startswith("session_") and f.name.endswith("_state.json"):
                f.unlink()
        log_func(pad("Deleted all state files.", WIDTH, "left"), "blue")

    except Exception as e:
        log_func(pad(f"Error purging session/state files: {e}", WIDTH, "left"), "red")

    log_func(pad("All configurations and session files have been reset.", WIDTH, "left"), "green")
    return envd


# ============================ STATE (RESUME) =============================

class StateManager:

    def __init__(self, account_index: int):  # Removed download_dir from __init__
        self.account_index = int(account_index)
        # State file now in base directory, named with account index
        self.state_file = Path(f"session_{self.account_index}_state.json")
        self.state = {
            "account_index": self.account_index,
            "source": {},  # {"type": "saved|dialogs|all", "dialog_ids": []}
            "completed_ids": [],  # list[int] các message.id đã tải xong
            "total_found": 0,
            "ids_hash": "",  # sha256 của danh sách message.id
            "last_filter": "3",  # 1=photos, 2=videos, 3=both
            "last_updated": None,
        }
        self._load()

    def _load(self):
        try:
            if self.state_file.exists():
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                # chỉ đọc nếu cùng account_index
                if int(data.get("account_index", -1)) == self.account_index:
                    self.state.update(data)
        except Exception:
            pass

    def save(self):
        self.state["last_updated"] = datetime.utcnow().isoformat() + "Z"
        try:
            # Ensure the directory for the state file exists (current directory)
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # -- API tiện dụng --
    def set_source(self, source_type: str, dialog_ids: list[int] | list[str], total_found: int = 0, ids_hash: str = "",
                   last_filter: Optional[str] = None):
        self.state["source"] = {"type": source_type, "dialog_ids": dialog_ids}
        if total_found:
            self.state["total_found"] = int(total_found)
        if ids_hash:
            self.state["ids_hash"] = ids_hash
        if last_filter is not None:
            self.state["last_filter"] = str(last_filter)
        self.save()

    def mark_completed(self, message_id: int):
        if message_id not in self.state["completed_ids"]:
            self.state["completed_ids"].append(int(message_id))
            self.save()

    def is_completed(self, message_id: int) -> bool:
        return int(message_id) in set(self.state.get("completed_ids", []))

    def completed_count(self) -> int:
        return len(self.state.get("completed_ids", []))

    def total_found(self) -> int:
        return int(self.state.get("total_found", 0))

    def source_label(self) -> str:
        s = self.state.get("source", {})
        typ = s.get("type", "unknown")
        ids = s.get("dialog_ids", [])
        if typ == "saved":
            return "Saved Messages (me)"
        if typ == "all":
            return f"Tất cả dialogs/channels ({len(ids)} nguồn)"
        if typ == "dialogs":
            return f"Dialogs chọn lọc ({len(ids)} nguồn)"
        return "unknown"

    def get_status_lines(self, download_dir: Path) -> list[str]:  # Added download_dir param
        return [
            f"Tài khoản: #{self.account_index}",
            f"Nguồn: {self.source_label()}",
            f"Tiến độ: {self.completed_count()}/{self.total_found()}",
            f"Download dir: {download_dir}",
            f"Hash media list: {self.state.get('ids_hash') or '-'}",
            f"Bộ lọc cuối: {self.state.get('last_filter', '3')}",
            f"Lần cập nhật: {self.state.get('last_updated') or '-'}",
        ]

    def get_source(self) -> Dict[str, Any]:
        return self.state.get("source", {})

    def get_last_filter(self) -> str:
        return str(self.state.get("last_filter", "3"))

    def clear_progress(self):
        self.state["completed_ids"] = []
        self.state["total_found"] = 0
        self.state["ids_hash"] = ""
        self.save()


# ============================ DOWNLOADER LÕI =============================

class TelegramDownloader:
    def __init__(self, api_id: int, api_hash: str, phone: str, download_dir: str, account_index: int,
                 log_func: Callable[[str, Optional[str]], None],
                 input_func: Callable[[str, Optional[str], bool], str]):  # Added hide_input to input_func type hint

        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.download_dir = Path(download_dir)
        self.pic_dir = self.download_dir / "PIC"
        self.vid_dir = self.download_dir / "VID"

        session_dir = Path("sessions")
        session_dir.mkdir(exist_ok=True)
        session_path = session_dir / f"session_{account_index}"
        self.client = TelegramClient(str(session_path), api_id, api_hash)

        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.pic_dir.mkdir(exist_ok=True)
        self.vid_dir.mkdir(exist_ok=True)

        # UI interaction functions
        self._log_output = log_func
        self._get_input = input_func

        # State per-account
        self.account_index = account_index
        self.state = StateManager(self.account_index)  # StateManager now takes only account_index

        self.stats = {
            'total_found': 0,
            'images_found': 0,
            'videos_found': 0,
            'downloaded': 0,
            'skipped': 0,
            'errors': 0,
            'total_size': 0,
        }

    def print_banner(self) -> None:
        lines = [
            pad("TELEGRAM MEDIA TOOL", WIDTH - 2),  # Updated title
            pad("UI-flexible · Multi-account · Download · Upload · Login/Logout/Reset · Resume", WIDTH - 2),
            # Updated subtitle
            pad(f"Download dir: {self.download_dir}", WIDTH - 2),
        ]
        self._log_output(c(box(lines), Fore.CYAN))
        self._log_output(line())

    # --- Telethon Callbacks for input ---
    def _code_callback(self) -> str:
        """Callback for Telethon to get OTP code."""
        return self._get_input("Enter the code from Telegram", hide_input=False)  # Pass hide_input=False

    def _password_callback(self) -> str:
        """Callback for Telethon to get 2FA password."""
        return self._get_input("Enter your 2FA password", hide_input=True)  # Pass hide_input=True for password masking

    async def connect_client(self) -> bool:
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                self._log_output(pad("Authorization required. Signing in...", WIDTH, "left"))
                try:
                    # In thông tin tài khoản đang đăng nhập (mask số điện thoại)
                    masked_phone = self.phone[:3] + "****" + self.phone[-4:]
                    self._log_output(
                        c(pad(f"Attempting to login account #{self.account_index} ({masked_phone}) → sending code...",
                              WIDTH,
                              "left"), Fore.YELLOW))
                    await self.client.send_code_request(self.phone)
                except FloodWaitError as e:
                    self._log_output(
                        c(pad(f"Too many attempts. Please wait {e.seconds} seconds.", WIDTH, "left"), Fore.RED))
                    return False

                # Handle sign-in after code request
                try:
                    await self.client.sign_in(self.phone, code=self._code_callback())
                except SessionPasswordNeededError:
                    await self.client.sign_in(password=self._password_callback())
                except PhoneCodeInvalidError:
                    self._log_output(c(pad(" Wrong OTP, please try again", WIDTH, "left"), Fore.RED))
                    # Allow a retry for OTP, but not handled automatically here (caller should decide)
                    return False
                except PhoneCodeExpiredError:
                    self._log_output(
                        c(pad(" The OTP code has expired. Please resend the code", WIDTH, "left"), Fore.YELLOW))
                    return False
                except PasswordHashInvalidError:
                    self._log_output(c(pad(" Incorrect 2FA password. Please try again.", WIDTH, "left"), Fore.RED))
                    return False
                except Exception as e:
                    self._log_output(c(pad(f"Login error: {e}", WIDTH, "left"), Fore.RED))
                    return False

            me = await self.client.get_me()
            display = f"{(me.first_name or '').strip()} {(me.last_name or '').strip()}".strip()
            username = f"@{me.username}" if getattr(me, 'username', None) else ""
            ok = f"Connected: {display} {username}".strip()
            self._log_output(c(pad(ok, WIDTH, "left"), Fore.GREEN))
            self._log_output(line("-"))
            return True
        except Exception as e:
            self._log_output(c(pad(f"Connection error: {e}", WIDTH, "left"), Fore.RED))
            self._log_output(line("-"))
            return False

    # ========== LIỆT KÊ & QUÉT ==========

    async def list_dialogs(self) -> List[dict]:
        self._log_output(pad("Fetching dialogs (chats/channels)...", WIDTH, "left"))
        rows = []
        idx = 0
        async for d in self.client.iter_dialogs():
            entity = d.entity
            etype = entity.__class__.__name__
            title = (getattr(d, "name", None) or getattr(entity, "title", None)
                     or getattr(entity, "first_name", None) or "Unknown").strip()
            uname = f"@{getattr(entity, 'username', '')}" if getattr(entity, 'username', None) else ""
            idx += 1
            rows.append({
                "index": idx,
                "dialog": d,
                "entity": entity,
                "title": title,
                "username": uname,
                "etype": etype,
            })
        # CLI print only - GUI will render its own
        if self._log_output == console_log_func:  # Only print box for CLI
            lines = [pad("LIST OF DIALOGS", WIDTH - 2), pad("", WIDTH - 2)]
            for r in rows:
                label = f"[{r['index']:>3}] {r['title']} {r['username']}  ({r['etype']})"
                lines.append(pad(label, WIDTH - 2))
            self._log_output(c(box(lines), Fore.CYAN))
        return rows

    async def scan_media_in_dialogs(self, dialogs: List[Any],
                                    progress_callback: Optional[Callable[[int, Optional[int]], None]] = None) -> List[
        Dict[str, Any]]:
        self._log_output(pad(f"Scanning {len(dialogs)} dialog(s) for media...", WIDTH, "left"))
        media_messages: List[Dict[str, Any]] = []
        message_count = 0
        self.stats = {
            'total_found': 0, 'images_found': 0, 'videos_found': 0,
            'downloaded': 0, 'skipped': 0, 'errors': 0, 'total_size': 0,
        }

        # Use tqdm only if in CLI mode and tqdm is available
        iterable_dialogs = dialogs
        if self._log_output == console_log_func and tqdm is not type(
                lambda x, **kwargs: x):  # Check if tqdm is actually imported
            iterable_dialogs = tqdm(dialogs, desc="Scanning Dialogs", ncols=WIDTH, ascii=True,
                                    bar_format="{desc}: {n_fmt}/{total_fmt} |{bar}| {rate_fmt}")

        for d in iterable_dialogs:
            async for message in self.client.iter_messages(d):
                message_count += 1
                if progress_callback:
                    # Pass total found media, total messages is hard to get upfront
                    # For GUI, we might pass (current_messages_scanned, total_dialog_messages)
                    progress_callback(message_count, None)

                if not getattr(message, "media", None):
                    continue
                if isinstance(message.media, MessageMediaPhoto):
                    self.stats['images_found'] += 1
                    media_messages.append({'message': message, 'type': 'photo', 'date': message.date})
                elif isinstance(message.media, MessageMediaDocument):
                    doc = message.media.document
                    mime = getattr(doc, "mime_type", "") or ""
                    if mime.startswith("video/"):
                        self.stats['videos_found'] += 1
                        media_messages.append({'message': message, 'type': 'video', 'date': message.date})
                    elif mime.startswith("image/"):
                        self.stats['images_found'] += 1
                        media_messages.append({'message': message, 'type': 'photo', 'date': message.date})

        self.stats['total_found'] = len(media_messages)
        # Final update for CLI progress if it was counting messages scanned
        if progress_callback:
            progress_callback(message_count, message_count)

        self._log_output(
            pad(f"Found {len(media_messages)} media in {message_count} messages across {len(dialogs)} dialog(s).",
                WIDTH, "left"))
        self._log_output(line("-"))
        return media_messages

    async def scan_saved_messages(self, progress_callback: Optional[Callable[[int, Optional[int]], None]] = None) -> \
            List[Dict[str, Any]]:
        self._log_output(pad("Scanning Saved Messages...", WIDTH, "left"))
        media_messages: List[Dict[str, Any]] = []
        message_count = 0
        self.stats = {
            'total_found': 0, 'images_found': 0, 'videos_found': 0,
            'downloaded': 0, 'skipped': 0, 'errors': 0, 'total_size': 0,
        }

        async for message in self.client.iter_messages('me'):
            message_count += 1
            if progress_callback:
                progress_callback(message_count, None)  # Current count, total unknown during iteration

            if not getattr(message, "media", None):
                continue
            if isinstance(message.media, MessageMediaPhoto):
                self.stats['images_found'] += 1
                media_messages.append({'message': message, 'type': 'photo', 'date': message.date})
            elif isinstance(message.media, MessageMediaDocument):
                doc = message.media.document
                mime = getattr(doc, "mime_type", "") or ""
                if mime.startswith("video/"):
                    self.stats['videos_found'] += 1
                    media_messages.append({'message': message, 'type': 'video', 'date': message.date})
                elif mime.startswith("image/"):
                    self.stats['images_found'] += 1
                    media_messages.append({'message': message, 'type': 'photo', 'date': message.date})

        self.stats['total_found'] = len(media_messages)
        if progress_callback:
            progress_callback(message_count, message_count)  # Final count with total messages scanned

        self._log_output(pad(f"Found {len(media_messages)} media in {message_count} messages.", WIDTH, "left"))
        self._log_output(line("-"))
        return media_messages

    # ===================== FILE NAMING & HASH =======================

    def _ext_from_mime_or_name(self, mime: str, name: Optional[str]) -> str:
        if name and "." in name:
            return "." + name.split(".")[-1]
        if mime.startswith("video/"):
            return ".mp4"
        if mime.startswith("image/"):
            return ".jpg"
        return ""

    def _target_path_for(self, media_info: Dict[str, Any]) -> Path:
        message = media_info['message']
        file_type = media_info['type']

        # Create year/month subfolders
        year_folder = self.download_dir / str(message.date.year)
        month_folder = year_folder / f"{message.date.month:02d}"
        month_folder.mkdir(parents=True, exist_ok=True)  # Ensure path exists

        if file_type == 'photo':
            return month_folder / f"photo_{message.id}.jpg"
        else:  # video
            doc = message.media.document
            mime = getattr(doc, "mime_type", "") or ""
            orig_name = None
            for attr in getattr(doc, "attributes", []):
                if hasattr(attr, 'file_name') and getattr(attr, 'file_name'):
                    orig_name = attr.file_name
                    break
            ext = self._ext_from_mime_or_name(mime, orig_name)
            return month_folder / f"video_{message.id}{ext}"

    @staticmethod
    def _hash_ids(ids: List[int]) -> str:
        # sắp xếp để hash ổn định, tránh lệch thứ tự
        b = ",".join(str(i) for i in sorted(set(int(x) for x in ids))).encode("utf-8")
        return hashlib.sha256(b).hexdigest()

    # ===================== DOWNLOAD CORE =======================

    def print_stats(self) -> None:
        lines = [
            pad("CURRENT STATS", WIDTH - 2),
            pad(f"Photos found: {self.stats['images_found']}", WIDTH - 2),
            pad(f"Videos found: {self.stats['videos_found']}", WIDTH - 2),
            pad(f"Total media: {self.stats['total_found']}", WIDTH - 2),
            pad(f"Downloaded: {self.stats['downloaded']}", WIDTH - 2),
            pad(f"Skipped: {self.stats['skipped']}", WIDTH - 2),
            pad(f"Errors: {self.stats['errors']}", WIDTH - 2),
            pad(f"Total size: {humanize.naturalsize(self.stats['total_size'])}", WIDTH - 2),
        ]
        self._log_output(c(box(lines), Fore.CYAN))

    def prompt_download_choice(self, default: Optional[str] = None) -> str:
        lines = [
            pad("Select what to download (1/2/3, other to cancel):", WIDTH - 2),
            pad("1) Photos only   -> PIC", WIDTH - 2),
            pad("2) Videos only   -> VID", WIDTH - 2),
            pad("3) Photos & Videos (both)", WIDTH - 2),
        ]
        self._log_output(c(box(lines), Fore.YELLOW))
        p = "Your choice"
        choice = self._get_input(p, default, hide_input=False).strip()
        self._log_output(line("-"))
        return choice

    async def download_all_media(self, media_list: List[Dict[str, Any]], stop_flag: Callable[[], bool],
                                 progress_callback: Optional[
                                     Callable[[float, int, int, Dict[str, Any]], None]] = None) -> None:
        """
        Downloads media files from the given list.
        stop_flag: a callable that returns True if the download should stop.
        progress_callback: a callable (progress, current, total, stats) for UI updates.
        """
        total_items = len(media_list)
        current_processed = 0

        # Use tqdm only if in CLI mode and tqdm is available
        iterable_media = media_list
        if self._log_output == console_log_func and tqdm is not type(lambda x, **kwargs: x):
            iterable_media = tqdm(media_list, total=total_items, desc="Downloading", unit="file", ncols=WIDTH,
                                  ascii=True,
                                  bar_format="{desc}: {n_fmt}/{total_fmt} |{bar}| {rate_fmt}")

        for item in iterable_media:
            if stop_flag():
                self._log_output(pad("Download stopped by user.", WIDTH, "left"), "red")
                break

            msg = item["message"]
            target_path = self._target_path_for(item)

            # Use message.peer_id to get dialog ID for StateManager
            dialog_id = getattr(msg.peer_id, 'user_id',
                                getattr(msg.peer_id, 'channel_id', getattr(msg.peer_id, 'chat_id', None)))
            if dialog_id is None:  # For 'Saved Messages' (msg.peer_id might be None for older versions)
                dialog_id = msg.sender_id  # Fallback to sender_id
            if dialog_id is None: dialog_id = -1  # A generic ID for 'me' or if sender also None

            # Check if already completed from state or file exists
            if self.state.is_completed(int(msg.id)) or (target_path.exists() and os.path.getsize(target_path) > 0):
                self.stats['skipped'] += 1
                self.state.mark_completed(int(msg.id))  # Ensure marked as completed
                if isinstance(iterable_media, tqdm): iterable_media.update(1)
            else:
                try:
                    self._log_output(pad(f"Downloading Message ID {msg.id} to {target_path.name}...", WIDTH, "left"),
                                     "blue")
                    path = await self.client.download_media(msg, file=str(target_path))

                    if path and Path(path).exists():
                        size = os.path.getsize(path)
                        self.stats['downloaded'] += 1
                        self.stats['total_size'] += size
                        self.state.mark_completed(int(msg.id))
                        self._log_output(pad(f"Successfully downloaded: {target_path.name}", WIDTH, "left"), "green")
                    else:
                        raise Exception("Downloaded file path is invalid or file not found.")

                except FloodWaitError as e:
                    self._log_output(
                        pad(f"Flood wait error while downloading: Waiting {e.seconds} seconds...", WIDTH, "left"),
                        "yellow")
                    await asyncio.sleep(e.seconds + 5)
                    self.stats['errors'] += 1
                except PeerFloodError:
                    self._log_output(
                        pad(f"Peer flood error. Too many requests to this peer. Skipping for now.", WIDTH, "left"),
                        "yellow")
                    self.stats['errors'] += 1
                except Exception as e:
                    self.stats['errors'] += 1
                    self._log_output(pad(f"Error downloading message ID {msg.id}: {e}", WIDTH, "left"), "red")
                if isinstance(iterable_media, tqdm): iterable_media.update(1)

            current_processed += 1
            progress = current_processed / total_items if total_items > 0 else 0
            if progress_callback:
                # progress, current_items_processed, total_items_to_process, current_stats
                progress_callback(progress, current_processed, total_items, self.stats.copy())

        # Ensure final progress update
        if progress_callback:
            progress_callback(1.0, total_items, total_items, self.stats.copy())

        self._log_output(pad("All media download attempts processed.", WIDTH, "left"), "blue")

    # ===================== NEW UPLOAD METHOD =====================
    async def upload_media(
            self,
            peer: Union[User, Chat, Channel, int, str],
            file_path: Path,
            caption: Optional[str] = None,
            progress_callback: Optional[Callable[[float, int, int], None]] = None
    ):
        """
        Uploads a media file to a specified peer (user/chat/channel).
        """
        if not self.client.is_connected():
            raise ConnectionError("Telegram client is not connected. Please ensure you are logged in.")

        if not file_path.is_file():
            self._log_output(pad(f"File not found at '{file_path}'.", WIDTH, "left"), "red")
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get entity of peer if it's ID or username
        peer_entity = None
        try:
            if isinstance(peer, (int, str)):
                self._log_output(pad(f"Resolving destination '{peer}'...", WIDTH, "left"), "blue")
                peer_entity = await self.client.get_entity(peer)
            else:
                peer_entity = peer

            # Use entity's title or first_name for logging
            peer_name = peer_entity.title if hasattr(peer_entity, 'title') else peer_entity.first_name if hasattr(
                peer_entity, 'first_name') else str(peer)
            self._log_output(pad(f"Attempting to upload '{file_path.name}' to '{peer_name}'...", WIDTH, "left"), "blue")

        except Exception as e:
            self._log_output(pad(f"Error resolving destination '{peer}': {e}", WIDTH, "left"), "red")
            raise ValueError(f"Invalid destination '{peer}'. Please check the ID or username.") from e

        try:
            # Telethon's send_file can take a progress_callback
            # The callback arguments are (current, total) bytes
            def telethon_progress_adapter(current, total):
                if progress_callback:
                    progress = current / total if total > 0 else 0
                    progress_callback(progress, current, total)

            message = await self.client.send_file(
                peer_entity,
                file=str(file_path),
                caption=caption,
                progress_callback=telethon_progress_adapter
            )
            self._log_output(
                pad(f"Successfully uploaded '{file_path.name}' to '{peer_name}'. Message ID: {message.id}", WIDTH,
                    "left"), "green")
            return message
        except Exception as e:
            self._log_output(pad(f"Error uploading '{file_path.name}' to '{peer_name}': {e}", WIDTH, "left"), "red")
            raise  # Re-raise for GUI/CLI to catch and display

    # ===================== CHẠY THEO NGUỒN =======================

    async def _run_with_source(self, src_type: str, chosen_entities: Optional[List[Any]] = None,
                               confirm_callback: Optional[Callable[[str, str], bool]] = None,
                               # For GUI confirmation dialog
                               progress_callback_scan: Optional[Callable[[int, Optional[int]], None]] = None,
                               # For GUI scan progress
                               progress_callback_download: Optional[
                                   Callable[[float, int, int, Dict[str, Any]], None]] = None
                               # For GUI download progress
                               ) -> bool:
        """
        Thực thi chu trình quét + tải theo nguồn đã biết.
        src_type: "saved" | "dialogs" | "all"
        chosen_entities: danh sách entity (nếu dialogs/all), có thể None nếu saved
        confirm_callback: a callable (title, message) for user confirmation (e.g., reset progress)
        progress_callback_scan: a callable (current_messages_scanned, total_messages_in_dialog) for scan updates.
        progress_callback_download: a callable (progress, current_items_processed, total_items_to_process, current_stats) for UI updates.
        """
        # 1) Scan theo nguồn
        if src_type == "saved":
            media_list = await self.scan_saved_messages(progress_callback_scan)
            dialog_ids = ["me"]
        else:
            if chosen_entities is None:
                self._log_output(pad("Không có entities để quét.", WIDTH, "left"), "red")
                return True
            media_list = await self.scan_media_in_dialogs(chosen_entities, progress_callback_scan)
            # rút id entity (int)
            dialog_ids = []
            for ent in chosen_entities:
                try:
                    dialog_ids.append(int(getattr(ent, "id", 0)))
                except Exception:
                    pass

        if not media_list:
            self._log_output(pad("No media found.", WIDTH, "left"), "yellow")
            return True

        # 2) Tính hash danh sách message ids
        current_ids = [int(m['message'].id) for m in media_list]
        ids_hash = self._hash_ids(current_ids)

        # 3) Kiểm tra hash với state cũ (nếu cùng loại nguồn + danh sách dialog_ids)
        prev_source = self.state.get_source()
        hash_mismatch = False
        if prev_source and prev_source.get("type") == src_type:
            # so khớp danh sách dialog ids (bỏ các 0)
            prev_dialog_ids = [int(x) if isinstance(x, (int, str)) and str(x).isdigit() else -1 for x in
                               prev_source.get("dialog_ids", [])]
            cur_dialog_ids = [int(x) if isinstance(x, (int, str)) and str(x).isdigit() else -1 for x in dialog_ids]

            if sorted(prev_dialog_ids) == sorted(cur_dialog_ids):
                # so khớp hash
                prev_hash = self.state.state.get("ids_hash", "")
                if prev_hash and prev_hash != ids_hash:
                    hash_mismatch = True

        # 4) Lưu source + total + hash (và giữ last_filter cũ)
        # Note: self.state.set_source will save the state automatically
        self.state.set_source(src_type, dialog_ids, total_found=len(media_list), ids_hash=ids_hash)

        # 5) Nếu hash khác -> hỏi reset
        if hash_mismatch:
            self._log_output(
                c(pad("Media list changed since last session (hash mismatch).", WIDTH, "left"), Fore.YELLOW))
            should_reset = False
            if confirm_callback:
                should_reset = confirm_callback("Confirm Reset Progress",
                                                "Media list has changed since last session. Reset progress?")
            else:  # Fallback to console input if no GUI callback
                ans = self._get_input(
                    pad("Reset progress to rescan/redownload from scratch? (yes/no) [no]", WIDTH, "left"), "no",
                    hide_input=False).strip().lower()
                self._log_output(line("-"))
                if ans == "yes":
                    should_reset = True

            if should_reset:
                self.state.clear_progress()
                self._log_output(c(pad("Progress reset.", WIDTH, "left"), Fore.CYAN))
            else:
                self._log_output(c(pad("Continuing with existing progress.", WIDTH, "left"), Fore.YELLOW))

        # 6) In stats + chọn filter (mặc định lấy last_filter)
        if self._log_output == console_log_func:  # Only print for CLI
            self.print_stats()

        choice = self.prompt_download_choice(
            default=self.state.get_last_filter()) if self._log_output == console_log_func else self.state.get_last_filter()  # GUI will set filter directly
        if choice not in {"1", "2", "3"}:
            self._log_output(pad("Canceled by user choice.", WIDTH, "left"), "yellow")
            return True
        # lưu bộ lọc vào state
        self.state.set_source(src_type, dialog_ids, total_found=len(media_list), ids_hash=ids_hash, last_filter=choice)

        # 7) Lọc theo loại
        if choice == "1":  # Photos only
            filtered = [m for m in media_list if m['type'] == 'photo']
        elif choice == "2":  # Videos only
            filtered = [m for m in media_list if m['type'] == 'video']
        else:  # Both photos & videos or invalid filter (default to both)
            filtered = media_list

        # 8) Áp dụng resume: bỏ completed + file tồn tại
        resumable = []
        for m in filtered:
            mid = int(m['message'].id)
            target = self._target_path_for(m)
            # Note: _target_path_for now creates intermediate directories automatically
            # So, we only need to check if the file itself exists and is not zero-sized
            if self.state.is_completed(mid) or (target.exists() and os.path.getsize(target) > 0):
                self.stats['skipped'] += 1
                continue
            resumable.append(m)

        if not resumable:
            self._log_output(pad("No items left to download (all completed).", WIDTH, "left"), "green")
            if self._log_output == console_log_func: self.print_stats()  # Only print for CLI
            return True

        # 9) Tải
        start_time = time.time()
        # Pass the stop_flag and progress_callback_download directly
        await self.download_all_media(resumable, stop_flag=lambda: False,
                                      progress_callback=progress_callback_download)  # CLI does not typically have an external stop_flag or UI progress, unless passed.
        elapsed = time.time() - start_time
        self._log_output(pad("Download finished.", WIDTH, "left"), "blue")
        self._log_output(pad(f"Elapsed: {humanize.naturaldelta(elapsed)}", WIDTH, "left"), "blue")
        if self._log_output == console_log_func: self.print_stats()
        if self.stats['downloaded'] > 0 and elapsed > 0:
            avg_speed = self.stats['total_size'] / elapsed
            self._log_output(pad(f"Average speed: {humanize.naturalsize(avg_speed)}/s", WIDTH, "left"), "blue")
        return True

    # ===================== LUỒNG CHÍNH (CLI) =======================

    async def run_cli_main_loop(self) -> bool:  # Renamed from run to avoid conflict and specify CLI context
        self.print_banner()
        if not await self.connect_client():
            return False
        try:
            # NGUỒN QUÉT
            lines = [
                pad("Select SOURCE to scan media:", WIDTH - 2),
                pad("1) Saved Messages (me)", WIDTH - 2),
                pad("2) Select specific dialogs/channels", WIDTH - 2),
                pad("3) All dialogs/channels", WIDTH - 2),
                pad("4) Continue LAST SESSION", WIDTH - 2),
            ]
            self._log_output(c(box(lines), Fore.YELLOW))
            src_choice = self._get_input("Your choice", hide_input=False).strip()
            self._log_output(line("-"))

            if src_choice == "4":
                # Continue last session
                prev = self.state.get_source()
                if not prev or not prev.get("type"):
                    self._log_output(pad("No previous session to continue.", WIDTH, "left"), "yellow")
                    return True
                typ = prev.get("type")
                if typ == "saved":
                    return await self._run_with_source("saved")
                else:
                    # dựng lại entities từ id
                    want_ids = [int(x) for x in prev.get("dialog_ids", []) if str(x).isdigit() and int(x) != 0]
                    rows = await self.list_dialogs()  # This prints dialogs to CLI
                    ents = []
                    for r in rows:
                        try:
                            if int(getattr(r["entity"], "id", 0)) in want_ids:
                                ents.append(r["dialog"].entity)
                        except Exception:
                            pass
                    if not ents:
                        self._log_output(pad("Could not restore dialog list from previous session.", WIDTH, "left"),
                                         "yellow")
                        return True
                    return await self._run_with_source(typ, ents)

            if src_choice == "1":
                return await self._run_with_source("saved")

            elif src_choice == "2":
                rows = await self.list_dialogs()  # This prints dialogs to CLI
                if not rows:
                    self._log_output(pad("No dialogs found.", WIDTH, "left"), "yellow")
                    return True
                self._log_output(
                    pad("Enter indexes of dialogs to scan (e.g.: 1,3,5-7). Enter to cancel.", WIDTH, "left"))
                pick = self._get_input("Pick", hide_input=False).strip()
                self._log_output(line("-"))
                if not pick:
                    self._log_output(pad("Canceled by user.", WIDTH, "left"), "yellow")
                    return True

                selected = set()
                for part in pick.split(","):
                    part = part.strip()
                    if "-" in part:
                        a, b = part.split("-", 1)
                        if a.isdigit() and b.isdigit():
                            for k in range(int(a), int(b) + 1):
                                selected.add(k)
                    elif part.isdigit():
                        selected.add(int(part))

                chosen = [r["dialog"].entity for r in rows if r["index"] in selected]
                if not chosen:
                    self._log_output(pad("No valid selection.", WIDTH, "left"), "yellow")
                    return True
                return await self._run_with_source("dialogs", chosen)

            elif src_choice == "3":
                rows = await self.list_dialogs()  # This prints dialogs to CLI
                ents = [r["dialog"].entity for r in rows]
                return await self._run_with_source("all", ents)

            else:
                self._log_output(pad("Invalid choice. Canceled.", WIDTH, "left"), "yellow")
                return True

        except KeyboardInterrupt:
            self._log_output(pad("Interrupted by user.", WIDTH, "left"), "red")
            return False
        except Exception as e:
            self._log_output(pad(f"Unexpected error: {e}", WIDTH, "left"), "red")
            return False
        finally:
            await self.client.disconnect()


# ============================ CLI-SPECIFIC FUNCTIONS AND MAIN ENTRY =============================

# CLI progress callback for download and upload
def cli_progress_callback(progress: float, current: int, total: int, stats: Optional[Dict[
    str, Any]] = None):  # Renamed current_bytes to current and total_bytes to total for download_all_media's specific needs
    bar_length = 50
    filled_length = int(bar_length * progress)
    bar = '#' * filled_length + '-' * (bar_length - filled_length)
    percent = f"{progress * 100:.1f}"

    # Adapt for both total items and total bytes for upload
    if stats:  # It's a download progress callback (from download_all_media)
        # Use current and total items for the main bar, but show size from stats
        downloaded_size = stats.get('total_size', 0)
        sys.stdout.write(
            f'\rDownload: |{bar}| {percent}% ({current}/{total} files, {humanize.naturalsize(downloaded_size)} total)')
    else:  # It's an upload progress callback (from upload_media)
        sys.stdout.write(
            f'\rUpload: |{bar}| {percent}% ({humanize.naturalsize(current)}/{humanize.naturalsize(total)})')

    sys.stdout.flush()
    if progress >= 1.0:
        sys.stdout.write('\n')


# Dummy callback for scan progress in CLI, as total messages isn't known
def cli_scan_progress_callback(current_messages_scanned: int, total_messages: Optional[int]):
    sys.stdout.write(
        f'\rScanning... Scanned {current_messages_scanned} messages. Found {current_messages_scanned if total_messages is None else total_messages} media items.')
    sys.stdout.flush()


async def initialize_downloader(envd: Dict[str, str], account_index: int) -> Optional[TelegramDownloader]:
    """Helper to initialize and connect the downloader for CLI commands."""
    cfg = get_account_config(envd, account_index)

    if not all([cfg["PHONE"], cfg["API_ID"], cfg["API_HASH"]]):
        console_log_func(
            pad(f"Account configuration for index {account_index} is incomplete. Please ensure PHONE, API_ID, API_HASH are set.",
                WIDTH, "left"), "red")
        return None

    try:
        api_id_int = int(cfg["API_ID"])
    except ValueError:
        console_log_func(
            pad(f"Invalid API_ID '{cfg['API_ID']}' for account #{account_index}. Must be a number.", WIDTH, "left"),
            "red")
        return None

    downloader = TelegramDownloader(
        api_id=api_id_int,
        api_hash=cfg["API_HASH"],
        phone=cfg["PHONE"],
        download_dir=cfg["DOWNLOAD_DIR"],
        account_index=account_index,
        log_func=console_log_func,
        input_func=console_input_func
    )

    if not await downloader.connect_client():
        return None
    return downloader


async def run_cli_login(args):
    env_path = Path(".env")
    envd = load_env(env_path)

    # For CLI login, if parameters are provided, use them directly for a new login or update.
    # Otherwise, it will be interactive.
    _envd, _idx = await do_login_flow(envd, console_log_func, console_input_func,
                                      phone=args.phone, api_id=args.api_id,
                                      api_hash=args.api_hash, download_dir=args.download_dir,
                                      account_idx_to_use=None)  # Pass None to allow interactive pick/new logic
    save_env(env_path, _envd)
    if _idx > 0:
        console_log_func(pad(f"Login command finished. Active account set to #{_idx}.", WIDTH, "left"), "green")
    else:
        console_log_func(pad("Login command failed.", WIDTH, "left"), "red")


async def run_cli_logout(args):
    env_path = Path(".env")
    envd = load_env(env_path)

    _envd = await do_logout_flow(envd, console_log_func, args.account_index)
    save_env(env_path, _envd)
    console_log_func(pad("Logout command finished.", WIDTH, "left"), "green")


async def run_cli_reset(args):
    env_path = Path(".env")
    envd = load_env(env_path)

    confirm_reset = console_input_func("Are you sure you want to reset all config and delete session files? (yes/no)",
                                       hide_input=False).lower() == 'yes'
    _envd = await do_reset_flow(envd, console_log_func, confirm=confirm_reset)
    save_env(env_path, _envd)
    console_log_func(pad("Reset command finished.", WIDTH, "left"), "green")


async def run_cli_upload(args):
    env_path = Path(".env")
    envd = load_env(env_path)
    current_account_idx = get_current_account_index(envd)

    if current_account_idx == 0:
        console_log_func(pad("No active account found. Please login first using 'cli_app.py login'.", WIDTH, "left"),
                         "red")
        return

    downloader = await initialize_downloader(envd, current_account_idx)
    if not downloader:
        return

    try:
        file_path = Path(args.file)
        destination = args.to
        caption = args.caption

        console_log_func(pad(f"Starting upload of '{file_path.name}' to '{destination}'...", WIDTH, "left"), "blue")
        await downloader.upload_media(
            peer=destination,
            file_path=file_path,
            caption=caption,
            progress_callback=cli_progress_callback
        )
        console_log_func(pad(f"Upload completed successfully for '{file_path.name}'.", WIDTH, "left"), "green")
    except Exception as e:
        console_log_func(pad(f"Error during upload: {e}", WIDTH, "left"), "red")
    finally:
        if downloader and downloader.client.is_connected():
            await downloader.client.disconnect()


async def run_cli_download(args):
    env_path = Path(".env")
    envd = load_env(env_path)
    current_account_idx = get_current_account_index(envd)

    if current_account_idx == 0:
        console_log_func(pad("No active account found. Please login first using 'cli_app.py login'.", WIDTH, "left"),
                         "red")
        return

    downloader = await initialize_downloader(envd, current_account_idx)
    if not downloader:
        return

    try:
        source_type = args.source
        filter_type = args.filter
        dialog_selection = args.dialogs

        media_list = []
        selected_entities: List[Any] = []

        if source_type == "saved":
            selected_entities = ['me']
            await downloader._run_with_source("saved",
                                              confirm_callback=lambda t, m: console_input_func(m + " (yes/no)", "no",
                                                                                               False).lower() == 'yes',
                                              progress_callback_scan=cli_scan_progress_callback,
                                              progress_callback_download=cli_progress_callback)
        elif source_type == "all":
            dialogs_info = await downloader.list_dialogs()  # This prints dialogs to CLI
            selected_entities = [d['entity'] for d in dialogs_info]
            await downloader._run_with_source("all", selected_entities,
                                              confirm_callback=lambda t, m: console_input_func(m + " (yes/no)", "no",
                                                                                               False).lower() == 'yes',
                                              progress_callback_scan=cli_scan_progress_callback,
                                              progress_callback_download=cli_progress_callback)
        elif source_type == "dialogs":
            if not dialog_selection:
                raise ValueError(
                    "For 'dialogs' source, --dialogs argument is required (e.g., --dialogs 12345 @mychannel).")

            console_log_func(pad("Fetching all dialogs to resolve selections...", WIDTH, "left"), "blue")
            all_dialogs_from_api = await downloader.list_dialogs()  # This prints dialogs to CLI

            for selector in dialog_selection:
                found = False
                try:  # Try by ID first
                    target_id = int(selector)
                    for d_info in all_dialogs_from_api:
                        if hasattr(d_info["entity"], "id") and d_info["entity"].id == target_id:
                            selected_entities.append(d_info["entity"])
                            found = True
                            break
                except ValueError:  # Not an int, try by title/username
                    for d_info in all_dialogs_from_api:
                        title_lower = d_info['title'].lower()
                        selector_lower = selector.lower()
                        if title_lower == selector_lower:
                            selected_entities.append(d_info["entity"])
                            found = True
                            break
                        if hasattr(d_info["entity"], "username") and d_info["entity"].username and d_info[
                            "entity"].username.lower() == selector_lower.lstrip('@'):
                            selected_entities.append(d_info["entity"])
                            found = True
                            break
                if not found:
                    console_log_func(pad(f"Warning: Could not find dialog '{selector}'. Skipping.", WIDTH, "left"),
                                     "yellow")

            if not selected_entities:
                raise ValueError("No valid dialogs selected for download.")

            await downloader._run_with_source("dialogs", selected_entities,
                                              confirm_callback=lambda t, m: console_input_func(m + " (yes/no)", "no",
                                                                                               False).lower() == 'yes',
                                              progress_callback_scan=cli_scan_progress_callback,
                                              progress_callback_download=cli_progress_callback)
        elif source_type == "continue":
            console_log_func(pad("Attempting to continue last session...", WIDTH, "left"), "blue")
            state_source = downloader.state.get_source()
            if not state_source:
                raise ValueError("No previous session found to continue.")

            last_source_type = state_source.get("type")
            last_dialog_ids = state_source.get("dialog_ids")

            if last_source_type == "saved":
                selected_entities = ['me']
                await downloader._run_with_source("saved",
                                                  confirm_callback=lambda t, m: console_input_func(m + " (yes/no)",
                                                                                                   "no",
                                                                                                   False).lower() == 'yes',
                                                  progress_callback_scan=cli_scan_progress_callback,
                                                  progress_callback_download=cli_progress_callback)
            else:  # "dialogs" or "all"
                console_log_func(pad("Fetching all dialogs to restore previous selection...", WIDTH, "left"), "blue")
                all_dialogs_from_api = await downloader.list_dialogs()  # This prints dialogs to CLI
                restored_entities = []
                for d_info in all_dialogs_from_api:
                    # state stores dialog_ids as int or 'me'
                    if last_dialog_ids and hasattr(d_info["entity"], "id") and d_info["entity"].id in last_dialog_ids:
                        restored_entities.append(d_info["entity"])
                if not restored_entities:
                    raise ValueError("Could not restore dialogs from previous session.")
                selected_entities = restored_entities
                await downloader._run_with_source(last_source_type, selected_entities,
                                                  confirm_callback=lambda t, m: console_input_func(m + " (yes/no)",
                                                                                                   "no",
                                                                                                   False).lower() == 'yes',
                                                  progress_callback_scan=cli_scan_progress_callback,
                                                  progress_callback_download=cli_progress_callback)

            # After _run_with_source completes, the downloader.state will have the chosen filter
            # If a filter was specifically provided via CLI, it will override the last session's filter
            # This is already handled in _run_with_source internally by default parameter logic.

        else:
            raise ValueError(f"Unknown source type: {source_type}. Choose from 'saved', 'dialogs', 'all', 'continue'.")


    except Exception as e:
        console_log_func(pad(f"Error during download: {e}", WIDTH, "left"), "red")
    finally:
        if downloader and downloader.client.is_connected():
            await downloader.client.disconnect()


async def cli_main_entry():
    parser = argparse.ArgumentParser(
        description="Telegram Media Downloader and Uploader CLI",
        formatter_class=argparse.RawTextHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- Login/Auth Command ---
    login_parser = subparsers.add_parser("login", help="Log in to a Telegram account or manage accounts.")
    login_parser.add_argument("--phone", help="Phone number for login (e.g., +84123456789)")
    login_parser.add_argument("--api-id", type=int, help="Telegram API ID")
    login_parser.add_argument("--api-hash", help="Telegram API Hash")
    login_parser.add_argument("--download-dir", default="downloads",
                              help="Default download directory for this account.")

    # --- Logout Command ---
    logout_parser = subparsers.add_parser("logout", help="Logout the current active account or a specific one.")
    logout_parser.add_argument("--account-index", type=int, default=None,
                               help="Optional: Logout a specific account index instead of the current active one.")

    # --- Reset Command ---
    reset_parser = subparsers.add_parser("reset", help="Reset all configurations and delete session files.")

    # --- Upload Command ---
    upload_parser = subparsers.add_parser("upload", help="Upload a file to Telegram.")
    upload_parser.add_argument("-f", "--file", required=True, help="Path to the file to upload.")
    upload_parser.add_argument("-t", "--to", required=True, help="Destination (chat ID, @username, or phone number).")
    upload_parser.add_argument("-c", "--caption", default="", help="Optional caption for the file.")

    # --- Download Command ---
    download_parser = subparsers.add_parser("download", help="Download media from Telegram.")
    download_parser.add_argument("-s", "--source", choices=["saved", "dialogs", "all", "continue"], default="all",
                                 help=(
                                     "Source to download from:\n"
                                     "  - saved: Your 'Saved Messages'\n"
                                     "  - dialogs: Specific chats/channels (requires --dialogs)\n"
                                     "  - all: All chats/channels you are part of\n"
                                     "  - continue: Continue last download session"
                                 ))
    download_parser.add_argument("--dialogs", nargs='*', help="List of dialog IDs or @usernames to download from "
                                                              "(required for --source dialogs, e.g., --dialogs 12345 @mychannel)")
    download_parser.add_argument("-F", "--filter", choices=["1", "2", "3"], default="3",
                                 help=(
                                     "Media type filter:\n"
                                     "  - 1: Photos only\n"
                                     "  - 2: Videos only\n"
                                     "  - 3: Both photos and videos (default)"
                                 ))

    # --- Status Command ---
    status_parser = subparsers.add_parser("status", help="Show current account status and last session progress.")

    args = parser.parse_args()

    env_path = Path(".env")
    ensure_env_exists(env_path)

    # All commands will reload envd from file, execute, and save it.
    # No need for the main_menu loop now, as CLI args handle everything.
    if args.command == "login":
        await run_cli_login(args)
    elif args.command == "logout":
        await run_cli_logout(args)
    elif args.command == "reset":
        await run_cli_reset(args)
    elif args.command == "upload":
        await run_cli_upload(args)
    elif args.command == "download":
        await run_cli_download(args)
    elif args.command == "status":
        envd = load_env(env_path)
        print_account_status(envd, console_log_func)
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        asyncio.run(cli_main_entry())
    except KeyboardInterrupt:
        console_log_func(pad("CLI operation interrupted. Goodbye!", WIDTH, "left"), "red")
    except Exception as e:
        console_log_func(pad(f"Fatal CLI error: {e}", WIDTH, "left"), "red")
        sys.exit(1)




