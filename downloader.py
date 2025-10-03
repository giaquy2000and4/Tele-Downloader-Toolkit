#!/usr/bin/env python3
"""
Telegram Saved Messages Media Downloader

- Flexible UI: Can be used with console (default) or integrated with GUI.
- Self-checks/creates .env if configuration is missing.
- Supports multiple accounts via .env (ACCOUNT_n_*), account selection on login.
- LOGOUT: Logs out current Telethon session + deletes login marker.
- RESET: Clears .env contents and reverts to initial state (can be recreated on LOGIN).
- Allows users to CHOOSE folder name and LOCATION -> saves to account's DOWNLOAD_DIR.

.env structure (multi-account):
CURRENT_ACCOUNT=0
# Example:
# ACCOUNT_1_PHONE=+84123456789
# ACCOUNT_1_API_ID=123456
# ACCOUNT_1_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxx
# ACCOUNT_1_DOWNLOAD_DIR=/absolute/path/to/downloads
"""

import asyncio
import os
import sys
import time
import re
import json
import signal
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Callable
from pathlib import Path

try:
    from telethon import TelegramClient
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
        PasswordHashInvalidError,
        FloodWaitError,
    )
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install telethon")
    sys.exit(1)

# Only import colorama and tqdm if we are potentially running in a console
# This is handled by the `if __name__ == "__main__":` block for console-specific UI.
try:
    from colorama import Fore, Style
    import colorama
except ImportError:
    # Fallback for no colorama (e.g., in GUI context where it's not needed)
    class NoColor:
        def __getattr__(self, name):
            return ''


    Fore = NoColor()
    Style = NoColor()
    colorama = None

try:
    from tqdm import tqdm
except ImportError:
    # Fallback for no tqdm
    tqdm = lambda x, **kwargs: x  # No-op tqdm

try:
    import humanize
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install humanize")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install python-dotenv")
    sys.exit(1)

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


# ============================ QUẢN LÝ .ENV =============================

ENV_TEMPLATE = """# Multi-account Telegram Downloader
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
    load_dotenv(dotenv_path=str(env_path), override=True)
    data = {}
    try:
        with env_path.open("r", encoding="utf-8") as f:
            for line_ in f:
                line_ = line_.strip()
                if not line_ or line_.startswith("#"):
                    continue
                if "=" in line_:
                    k, v = line_.split("=", 1)
                    data[k.strip()] = v.strip()
    except Exception:
        pass
    return data


def save_env(env_path: Path, data: Dict[str, str]) -> None:
    lines = ["# Multi-account Telegram Downloader"]
    cur = str(data.get("CURRENT_ACCOUNT", "0")).strip()
    lines.append(f"CURRENT_ACCOUNT={cur}")
    # Dump account blocks by index
    indexes = sorted(
        {int(k.split("_")[1]) for k in data.keys() if k.startswith("ACCOUNT_") and k.split("_")[1].isdigit()})
    for idx in indexes:
        for key in ["PHONE", "API_ID", "API_HASH", "DOWNLOAD_DIR"]:
            dk = f"ACCOUNT_{idx}_{key}"
            if dk in data:
                lines.append(f"{dk}={data[dk]}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def pick_account_index(data: Dict[str, str], input_func: Callable[[str, Optional[str]], str],
                       log_func: Callable[[str], None]) -> int:
    # tìm tất cả ACCOUNT_n_PHONE để liệt kê
    idxs = sorted({int(k.split("_")[1]) for k in data.keys() if
                   k.startswith("ACCOUNT_") and k.endswith("_PHONE") and k.split("_")[1].isdigit()})
    if not idxs:
        return 0
    # hiển thị
    lines = [pad("ACCOUNTS", WIDTH - 2)]
    for i in idxs:
        phone = data.get(f"ACCOUNT_{i}_PHONE", "")
        lines.append(pad(f"[{i}] {phone}", WIDTH - 2))
    log_func(c(box(lines), Fore.CYAN))
    sel = input_func("Nhập index tài khoản muốn dùng: ").strip()
    if sel.isdigit() and int(sel) in idxs:
        return int(sel)
    return 0


def get_current_account_index(data: Dict[str, str]) -> int:
    try:
        return int(str(data.get("CURRENT_ACCOUNT", "0")).strip())
    except Exception:
        return 0


def get_account_config(data: Dict[str, str], idx: int) -> Dict[str, str]:
    return {
        "PHONE": data.get(f"ACCOUNT_{idx}_PHONE", ""),
        "API_ID": data.get(f"ACCOUNT_{idx}_API_ID", ""),
        "API_HASH": data.get(f"ACCOUNT_{idx}_API_HASH", ""),
        "DOWNLOAD_DIR": data.get(f"ACCOUNT_{idx}_DOWNLOAD_DIR", ""),
    }


def set_current_account_index(data: Dict[str, str], idx: int) -> Dict[str, str]:
    data["CURRENT_ACCOUNT"] = str(idx)
    return data


def input_nonempty(prompt: str, input_func: Callable[[str, Optional[str]], str], default: Optional[str] = None) -> str:
    p = prompt  # + (f" [{default}]" if default else "") # GUI input handles default differently
    while True:
        val = input_func(p, default).strip()
        if not val and default is not None:
            return default
        if val:
            return val
        print("Vui lòng nhập lại.")


def do_login_flow(envd: Dict[str, str], input_func: Callable[[str, Optional[str]], str],
                  log_func: Callable[[str], None]) -> Dict[str, str]:
    # thêm / sửa 1 account
    idx = pick_account_index(envd, input_func, log_func)
    if idx == 0:
        # tạo mới index
        existing_idxs = [int(k.split("_")[1]) for k in envd.keys() if
                         k.startswith("ACCOUNT_") and k.endswith("_PHONE") and k.split("_")[1].isdigit()]
        idx = 1 if not existing_idxs else max(existing_idxs) + 1

    phone = input_nonempty("PHONE (kèm mã quốc gia)", input_func, envd.get(f"ACCOUNT_{idx}_PHONE", ""))
    api_id = input_nonempty("API_ID", input_func, envd.get(f"ACCOUNT_{idx}_API_ID", ""))
    api_hash = input_nonempty("API_HASH", input_func, envd.get(f"ACCOUNT_{idx}_API_HASH", ""))
    download_dir = input_nonempty("DOWNLOAD_DIR (thư mục tuyệt đối hoặc tương đối)", input_func,
                                  envd.get(f"ACCOUNT_{idx}_DOWNLOAD_DIR", "downloads"))

    envd[f"ACCOUNT_{idx}_PHONE"] = phone
    envd[f"ACCOUNT_{idx}_API_ID"] = api_id
    envd[f"ACCOUNT_{idx}_API_HASH"] = api_hash
    envd[f"ACCOUNT_{idx}_DOWNLOAD_DIR"] = download_dir
    envd = set_current_account_index(envd, idx)
    return envd


def do_reset_flow(input_func: Callable[[str, Optional[str]], str], log_func: Callable[[str], None]) -> Dict[str, str]:
    confirm = input_func("Bạn chắc chắn RESET .env? (yes/no): ").strip().lower()
    if confirm == "yes":
        return {"CURRENT_ACCOUNT": "0"}
    else:
        log_func("Huỷ RESET.")
        return load_env(Path(".env"))  # Reload original env


def purge_session_files_for(account_index: int) -> None:
    base = Path(f"sessions/session_{account_index}")
    extensions = ["", ".session", ".session-journal"]
    for ext in extensions:
        path = base.with_suffix(ext)
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass


async def do_logout_flow(envd: Dict[str, str], log_func: Callable[[str], None]) -> Dict[str, str]:
    idx = get_current_account_index(envd)
    if idx == 0:
        log_func(c(pad("Chưa đăng nhập. Không có phiên nào để logout.", WIDTH, "left"), Fore.YELLOW))
        return envd
    purge_session_files_for(idx)
    log_func(c(pad("Đã xoá session local. Nếu muốn đăng nhập lại, chọn LOGIN.", WIDTH, "left"), Fore.GREEN))
    return envd


# ============================ STATE (RESUME) =============================

class StateManager:
    """
    Lưu/truy hồi trạng thái tải cho từng tài khoản (per-account)
    Lưu tại: <DOWNLOAD_DIR>/.resume.json
    """

    def __init__(self, download_dir: Path, account_index: int):
        self.download_dir = Path(download_dir)
        self.state_file = self.download_dir / ".resume.json"
        self.account_index = int(account_index)
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

    def get_status_lines(self) -> list[str]:
        return [
            f"Tài khoản: #{self.account_index}",
            f"Nguồn: {self.source_label()}",
            f"Tiến độ: {self.completed_count()}/{self.total_found()}",
            f"Download dir: {self.download_dir}",
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
                 log_func: Callable[[str, Optional[str]], None], input_func: Callable[[str, Optional[str]], str]):

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
        self.state = StateManager(self.download_dir, self.account_index)

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
            pad("TELEGRAM SAVED MESSAGES DOWNLOADER", WIDTH - 2),
            pad("UI-flexible · Multi-account · Login/Logout/Reset · Resume", WIDTH - 2),
            pad(f"Download dir: {self.download_dir}", WIDTH - 2),
        ]
        self._log_output(c(box(lines), Fore.CYAN))
        self._log_output(line())

    # --- Telethon Callbacks for input ---
    def _code_callback(self) -> str:
        """Callback for Telethon to get OTP code."""
        return self._get_input("Nhập mã OTP: ")

    def _password_callback(self) -> str:
        """Callback for Telethon to get 2FA password."""
        return self._get_input("Nhập mật khẩu 2FA: ")

    async def connect_client(self) -> bool:
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                self._log_output(pad("Signing in...", WIDTH, "left"))
                try:
                    # In thông tin tài khoản đang đăng nhập (mask số điện thoại)
                    masked_phone = self.phone[:3] + "****" + self.phone[-4:]
                    self._log_output(
                        c(pad(f"Đang đăng nhập tài khoản #{self.account_index} ({masked_phone}) → gửi mã...", WIDTH,
                              "left"), Fore.YELLOW))
                    await self.client.send_code_request(self.phone)  # Removed code_callback here, handled by sign_in
                except FloodWaitError as e:
                    self._log_output(c(pad(f"Quá nhiều lần thử. Hãy chờ {e.seconds} giây.", WIDTH, "left"), Fore.RED))
                    return False

                # Handle sign-in after code request
                try:
                    await self.client.sign_in(self.phone, code=self._code_callback())  # Pass blocking input function
                except SessionPasswordNeededError:
                    await self.client.sign_in(password=self._password_callback())  # Pass blocking input function
                except PhoneCodeInvalidError:
                    self._log_output(c(pad("❌ Mã OTP không đúng. Vui lòng thử lại.", WIDTH, "left"), Fore.RED))
                    return False
                except PhoneCodeExpiredError:
                    self._log_output(c(pad("⏰ Mã OTP đã hết hạn. Vui lòng gửi lại mã.", WIDTH, "left"), Fore.YELLOW))
                    return False
                except PasswordHashInvalidError:
                    self._log_output(c(pad("❌ Sai mật khẩu 2FA. Vui lòng thử lại.", WIDTH, "left"), Fore.RED))
                    return False
                except Exception as e:
                    self._log_output(c(pad(f"Lỗi đăng nhập: {e}", WIDTH, "left"), Fore.RED))
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
        lines = [pad("DANH SÁCH DIALOGS", WIDTH - 2), pad("", WIDTH - 2)]
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

        # Use simple iteration if tqdm is not available (e.g., in GUI mode)
        iterable_dialogs = tqdm(dialogs, desc="Scanning Dialogs", ncols=WIDTH, ascii=True,
                                bar_format="{desc}: {n_fmt}/{total_fmt} |{bar}| {rate_fmt}") if tqdm else dialogs

        for d in iterable_dialogs:
            async for message in self.client.iter_messages(d):
                message_count += 1
                if progress_callback:
                    # Pass a dummy total for now, actual total media unknown until scan complete
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
        if progress_callback:
            progress_callback(message_count, message_count)  # Final count with total messages scanned

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
        if file_type == 'photo':
            return self.pic_dir / f"photo_{message.id}.jpg"
        else:
            doc = message.media.document
            mime = getattr(doc, "mime_type", "") or ""
            orig_name = None
            for attr in getattr(doc, "attributes", []):
                if hasattr(attr, 'file_name') and getattr(attr, 'file_name'):
                    orig_name = attr.file_name
                    break
            ext = self._ext_from_mime_or_name(mime, orig_name)
            return self.vid_dir / f"video_{message.id}{ext}"

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
        choice = self._get_input(p, default).strip()
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

        # Use simple iteration if tqdm is not available or if in GUI mode
        iterable_media = tqdm(media_list, total=total_items, desc="Downloading", unit="file", ncols=WIDTH, ascii=True,
                              bar_format="{desc}: {n_fmt}/{total_fmt} |{bar}| {rate_fmt}") if tqdm else media_list

        for item in iterable_media:
            if stop_flag():
                self._log_output("Download stopped by user.", "red")
                break

            msg = item["message"]
            target_path = self._target_path_for(item)
            target_dir = target_path.parent
            target_dir.mkdir(exist_ok=True)

            # Check if already exists
            if self.state.is_completed(int(msg.id)) or (target_path.exists() and os.path.getsize(target_path) > 0):
                self.stats['skipped'] += 1
                self.state.mark_completed(int(msg.id))
                if isinstance(iterable_media, tqdm): iterable_media.update(1)  # Update tqdm if using
            else:
                try:
                    path = await self.client.download_media(msg, file=str(target_path))
                    if path and os.path.exists(path):
                        size = os.path.getsize(path)
                        self.stats['downloaded'] += 1
                        self.stats['total_size'] += size
                        self.state.mark_completed(int(msg.id))
                    else:
                        self.stats['errors'] += 1
                except Exception as e:
                    self.stats['errors'] += 1
                    self._log_output(f"Download error (msg {msg.id}): {e}", "red")
                if isinstance(iterable_media, tqdm): iterable_media.update(1)  # Update tqdm if using

            current_processed += 1
            progress = current_processed / total_items if total_items > 0 else 0
            if progress_callback:
                progress_callback(progress, current_processed, total_items, self.stats.copy())

    # ===================== CHẠY THEO NGUỒN =======================

    async def _run_with_source(self, src_type: str, chosen_entities: Optional[List[Any]] = None,
                               confirm_callback: Optional[Callable[[str, str], bool]] = None) -> bool:
        """
        Thực thi chu trình quét + tải theo nguồn đã biết.
        src_type: "saved" | "dialogs" | "all"
        chosen_entities: danh sách entity (nếu dialogs/all), có thể None nếu saved
        confirm_callback: a callable (title, message) for user confirmation (e.g., reset progress)
        """
        # 1) Scan theo nguồn
        if src_type == "saved":
            media_list = await self.scan_saved_messages()
            dialog_ids = ["me"]
        else:
            if chosen_entities is None:
                self._log_output(pad("Không có entities để quét.", WIDTH, "left"))
                return True
            media_list = await self.scan_media_in_dialogs(chosen_entities)
            # rút id entity (int)
            dialog_ids = []
            for ent in chosen_entities:
                try:
                    dialog_ids.append(int(getattr(ent, "id", 0)))
                except Exception:
                    pass

        if not media_list:
            self._log_output(pad("No media found.", WIDTH, "left"))
            return True

        # 2) Tính hash danh sách message ids
        current_ids = [int(m['message'].id) for m in media_list]
        ids_hash = self._hash_ids(current_ids)

        # 3) Kiểm tra hash với state cũ (nếu cùng loại nguồn + danh sách dialog_ids)
        prev_source = self.state.get_source()
        hash_mismatch = False
        if prev_source and prev_source.get("type") == src_type:
            # so khớp danh sách dialog ids (bỏ các 0)
            prev_ids = [int(x) if str(x).isdigit() else -1 for x in prev_source.get("dialog_ids", [])]
            cur_ids = [int(x) if str(x).isdigit() else -1 for x in dialog_ids]
            if sorted(prev_ids) == sorted(cur_ids):
                # so khớp hash
                prev_hash = self.state.state.get("ids_hash", "")
                if prev_hash and prev_hash != ids_hash:
                    hash_mismatch = True

        # 4) Lưu source + total + hash (và giữ last_filter cũ)
        self.state.set_source(src_type, dialog_ids, total_found=len(media_list), ids_hash=ids_hash)

        # 5) Nếu hash khác -> hỏi reset
        if hash_mismatch:
            self._log_output(
                c(pad("Danh sách media đã thay đổi so với lần trước (hash khác).", WIDTH, "left"), Fore.YELLOW))
            if confirm_callback and confirm_callback("Confirm Reset Progress",
                                                     "Media list has changed since last session. Reset progress?"):
                self.state.clear_progress()
                self._log_output(c(pad("Đã reset tiến độ.", WIDTH, "left"), Fore.CYAN))
            else:  # Fallback to console input if no callback or user declines
                ans = self._get_input("Reset tiến độ để quét/tải lại từ đầu? (yes/no) [no]: ", "no").strip().lower()
                self._log_output(line("-"))
                if ans == "yes":
                    self.state.clear_progress()
                    self._log_output(c(pad("Đã reset tiến độ.", WIDTH, "left"), Fore.CYAN))

        # 6) In stats + chọn filter (mặc định lấy last_filter)
        self.print_stats()
        choice = self.prompt_download_choice(default=self.state.get_last_filter())
        if choice not in {"1", "2", "3"}:
            self._log_output(pad("Canceled by user choice.", WIDTH, "left"))
            return True
        # lưu bộ lọc vào state
        self.state.set_source(src_type, dialog_ids, total_found=len(media_list), ids_hash=ids_hash, last_filter=choice)

        # 7) Lọc theo loại
        if choice == "1":
            filtered = [m for m in media_list if m['type'] == 'photo']
        elif choice == "2":
            filtered = [m for m in media_list if m['type'] == 'video']
        else:
            filtered = media_list

        # 8) Áp dụng resume: bỏ completed + file tồn tại
        resumable = []
        for m in filtered:
            mid = int(m['message'].id)
            target = self._target_path_for(m)
            if self.state.is_completed(mid) or (target.exists() and os.path.getsize(target) > 0):
                self.stats['skipped'] += 1
                continue
            resumable.append(m)

        if not resumable:
            self._log_output(pad("Không còn item nào cần tải (đã hoàn tất).", WIDTH, "left"))
            self.print_stats()
            return True

        # 9) Tải
        start_time = time.time()
        await self.download_all_media(resumable, stop_flag=lambda: False)  # No stop flag in console, or provide dummy
        elapsed = time.time() - start_time
        self._log_output(pad("Download finished.", WIDTH, "left"))
        self._log_output(pad(f"Elapsed: {humanize.naturaldelta(elapsed)}", WIDTH, "left"))
        self.print_stats()
        if self.stats['downloaded'] > 0 and elapsed > 0:
            avg_speed = self.stats['total_size'] / elapsed
            self._log_output(pad(f"Average speed: {humanize.naturalsize(avg_speed)}/s", WIDTH, "left"))
        return True

    # ===================== LUỒNG CHÍNH =======================

    async def run(self, confirm_callback: Optional[Callable[[str, str], bool]] = None) -> bool:
        self.print_banner()
        if not await self.connect_client():
            return False
        try:
            # NGUỒN QUÉT
            lines = [
                pad("Chọn NGUỒN để quét media:", WIDTH - 2),
                pad("1) Saved Messages (me)", WIDTH - 2),
                pad("2) Chọn dialogs/channels cụ thể", WIDTH - 2),
                pad("3) Tất cả dialogs/channels", WIDTH - 2),
                pad("4) Continue LAST SESSION", WIDTH - 2),
            ]
            self._log_output(c(box(lines), Fore.YELLOW))
            src_choice = self._get_input("Your choice: ").strip()
            self._log_output(line("-"))

            if src_choice == "4":
                # Continue last session
                prev = self.state.get_source()
                if not prev or not prev.get("type"):
                    self._log_output(pad("Chưa có phiên trước để tiếp tục.", WIDTH, "left"))
                    return True
                typ = prev.get("type")
                if typ == "saved":
                    return await self._run_with_source("saved", confirm_callback=confirm_callback)
                else:
                    # dựng lại entities từ id
                    want_ids = [int(x) for x in prev.get("dialog_ids", []) if str(x).isdigit() and int(x) != 0]
                    rows = await self.list_dialogs()
                    ents = []
                    for r in rows:
                        try:
                            if int(getattr(r["entity"], "id", 0)) in want_ids:
                                ents.append(r["dialog"].entity)
                        except Exception:
                            pass
                    if not ents:
                        self._log_output(pad("Không khôi phục được danh sách dialogs từ phiên trước.", WIDTH, "left"))
                        return True
                    return await self._run_with_source(typ, ents, confirm_callback=confirm_callback)

            if src_choice == "1":
                return await self._run_with_source("saved", confirm_callback=confirm_callback)

            elif src_choice == "2":
                rows = await self.list_dialogs()
                if not rows:
                    self._log_output(pad("Không có dialog nào.", WIDTH, "left"))
                    return True
                self._log_output(pad("Nhập chỉ số dialogs muốn quét (ví dụ: 1,3,5-7). Enter để huỷ.", WIDTH, "left"))
                pick = self._get_input("Pick: ").strip()
                self._log_output(line("-"))
                if not pick:
                    self._log_output(pad("Huỷ bởi người dùng.", WIDTH, "left"))
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
                    self._log_output(pad("Không có lựa chọn hợp lệ.", WIDTH, "left"))
                    return True
                return await self._run_with_source("dialogs", chosen, confirm_callback=confirm_callback)

            elif src_choice == "3":
                rows = await self.list_dialogs()
                ents = [r["dialog"].entity for r in rows]
                return await self._run_with_source("all", ents, confirm_callback=confirm_callback)

            else:
                self._log_output(pad("Lựa chọn không hợp lệ. Huỷ.", WIDTH, "left"))
                return True

        except KeyboardInterrupt:
            self._log_output(pad("Interrupted by user.", WIDTH, "left"))
            return False
        except Exception as e:
            self._log_output(pad(f"Unexpected error: {e}", WIDTH, "left"))
            return False
        finally:
            await self.client.disconnect()


# ============================ MENU PHỤ TRỢ (Console-specific) =============================

# Default console log function
def console_log_func(message: str, color: Optional[str] = None):
    # 'color' parameter for future use if needed, for now just prints
    print(message)


# Default console input function
def console_input_func(prompt: str, default: Optional[str] = None) -> str:
    full_prompt = prompt
    if default is not None:
        full_prompt += f" [{default}]"
    full_prompt += ": "
    return input(full_prompt)


def print_account_status(envd: Dict[str, str], log_func: Callable[[str, Optional[str]], None]) -> None:
    idx = get_current_account_index(envd)
    if idx == 0:
        log_func(c(pad("Chưa chọn tài khoản.", WIDTH, "left"), Fore.YELLOW))
        return
    cfg = get_account_config(envd, idx)
    dldir = cfg.get("DOWNLOAD_DIR", "").strip() or "downloads"
    sm = StateManager(Path(dldir), idx)
    lines = [pad("ACCOUNT STATUS", WIDTH - 2), ""]
    lines.extend([pad(s, WIDTH - 2) for s in sm.get_status_lines()])
    log_func(c(box(lines), Fore.CYAN))


async def run_downloader_with_env(envd: Dict[str, str]) -> None:
    idx = get_current_account_index(envd)
    if idx == 0:
        console_log_func(c(pad("Chưa chọn tài khoản. Vào LOGIN để cấu hình.", WIDTH, "left"), Fore.YELLOW))
        return
    cfg = get_account_config(envd, idx)
    missing = [k for k, v in cfg.items() if not str(v).strip()]
    if missing:
        console_log_func(c(pad(f"Thiếu cấu hình: {', '.join(missing)}", WIDTH, "left"), Fore.RED))
        return
    Path(cfg["DOWNLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    app = TelegramDownloader(
        api_id=int(cfg["API_ID"]),
        api_hash=str(cfg["API_HASH"]),
        phone=str(cfg["PHONE"]),
        download_dir=str(cfg["DOWNLOAD_DIR"]),
        account_index=idx,  # per-account state
        log_func=console_log_func,
        input_func=console_input_func,
    )
    await app.run()


def main_menu() -> int:
    lines = [
        pad("MAIN MENU", WIDTH - 2),
        pad("1) LOGIN  - cấu hình/đổi tài khoản", WIDTH - 2),
        pad("2) LOGOUT - xoá session local", WIDTH - 2),
        pad("3) RESET  - xoá .env về mặc định", WIDTH - 2),
        pad("4) EXIT", WIDTH - 2),
        pad("5) STATUS - xem tiến độ tài khoản hiện tại", WIDTH - 2),
        pad("6) CONTINUE LAST SESSION", WIDTH - 2),
        pad("0) EXIT (phím khác)", WIDTH - 2),
        pad("", WIDTH - 2),
        pad("Hoặc nhấn Enter để CHẠY DOWNLOADER ngay với tài khoản hiện tại.", WIDTH - 2),
    ]
    console_log_func(c(box(lines), Fore.GREEN))
    raw = console_input_func("Chọn: ").strip()
    console_log_func(line("-"))
    if raw == "":
        return 9  # run immediately
    try:
        val = int(raw)
        return val
    except Exception:
        return 0


async def main():
    env_path = Path(".env")
    ensure_env_exists(env_path)
    envd = load_env(env_path)

    while True:
        choice = main_menu()
        if choice == 9:
            await run_downloader_with_env(envd)
        elif choice == 1:
            envd = do_login_flow(envd, console_input_func, console_log_func)
            save_env(env_path, envd)
            console_log_func(c(pad("Đã lưu cấu hình.", WIDTH, "left"), Fore.CYAN))
            print_account_status(envd, console_log_func)  # in trạng thái ngay sau login
        elif choice == 2:
            envd = await do_logout_flow(envd, console_log_func)
            save_env(env_path, envd)  # Save env after logout to update current_account=0
        elif choice == 3:
            envd = do_reset_flow(console_input_func, console_log_func)
            save_env(env_path, envd)
            console_log_func(c(pad("Đã reset .env.", WIDTH, "left"), Fore.CYAN))
            envd = load_env(env_path)  # Reload to ensure consistency
        elif choice == 5:
            print_account_status(envd, console_log_func)
        elif choice == 6:
            # chạy nhanh "Continue last session"
            idx = get_current_account_index(envd)
            if idx == 0:
                console_log_func(c(pad("Chưa chọn tài khoản.", WIDTH, "left"), Fore.YELLOW))
                continue
            cfg = get_account_config(envd, idx)
            missing = [k for k, v in cfg.items() if not str(v).strip()]
            if missing:
                console_log_func(c(pad(f"Thiếu cấu hình: {', '.join(missing)}", WIDTH, "left"), Fore.RED))
                continue
            Path(cfg["DOWNLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
            app = TelegramDownloader(
                api_id=int(cfg["API_ID"]),
                api_hash=str(cfg["API_HASH"]),
                phone=str(cfg["PHONE"]),
                download_dir=str(cfg["DOWNLOAD_DIR"]),
                account_index=idx,
                log_func=console_log_func,
                input_func=console_input_func,
            )
            # Bỏ qua menu nguồn, gọi trực tiếp đường tắt
            try:
                if not await app.connect_client():
                    continue
                prev = app.state.get_source()
                if not prev or not prev.get("type"):
                    console_log_func(pad("Chưa có phiên trước để tiếp tục.", WIDTH, "left"))
                    await app.client.disconnect()
                    continue
                typ = prev.get("type")
                if typ == "saved":
                    await app._run_with_source("saved")
                else:
                    want_ids = [int(x) for x in prev.get("dialog_ids", []) if str(x).isdigit() and int(x) != 0]
                    rows = await app.list_dialogs()
                    ents = []
                    for r in rows:
                        try:
                            if int(getattr(r["entity"], "id", 0)) in want_ids:
                                ents.append(r["dialog"].entity)
                        except Exception:
                            pass
                    if not ents:
                        console_log_func(pad("Không khôi phục được danh sách dialogs từ phiên trước.", WIDTH, "left"))
                    else:
                        await app._run_with_source(typ, ents)
            finally:
                try:
                    await app.client.disconnect()
                except Exception:
                    pass
        elif choice == 4 or choice == 0:  # EXIT hoặc chọn sai -> thoát
            console_log_func(c(pad("Goodbye.", WIDTH, "left"), Fore.CYAN))
            break


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console_log_func("Goodbye.")
    except Exception as e:
        console_log_func(f"Fatal: {e}")
        sys.exit(1)

