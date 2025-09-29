#!/usr/bin/env python3
# Nâng cấp: thêm tính năng LOGIN / LOGOUT / RESET, giữ nguyên cấu trúc & giao diện console (WIDTH cố định)
"""
Telegram Saved Messages Media Downloader (Console-UI Fixed Width)

- Giao diện console bề ngang cố định (WIDTH)
- Tự kiểm tra / tạo .env nếu thiếu cấu hình
- Hỗ trợ nhiều tài khoản qua .env (ACCOUNT_n_*), chọn tài khoản khi LOGIN
- LOGOUT: đăng xuất phiên Telethon hiện tại + xoá đánh dấu đăng nhập
- RESET: xoá sạch nội dung .env và đưa về trạng thái ban đầu (có thể tạo lại khi LOGIN)
- Cho phép người dùng CHỌN tên folder và NƠI LƯU folder đó -> lưu vào DOWNLOAD_DIR của tài khoản

Cấu trúc .env (đa tài khoản):
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
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

try:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
        PasswordHashInvalidError,
        FloodWaitError,
    )
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install telethon")
    sys.exit(1)

try:
    from colorama import Fore, Style
    import colorama
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install colorama")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install tqdm")
    sys.exit(1)

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

# ============================ CẤU HÌNH UI =============================

WIDTH = 78
USE_COLOR = True
BAR_CHAR = "─"

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
    indexes = sorted({int(k.split("_")[1]) for k in data.keys() if k.startswith("ACCOUNT_") and k.split("_")[1].isdigit()})
    for idx in indexes:
        for key in ["PHONE", "API_ID", "API_HASH", "DOWNLOAD_DIR"]:
            dk = f"ACCOUNT_{idx}_{key}"
            if dk in data:
                lines.append(f"{dk}={data[dk]}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def pick_account_index(data: Dict[str, str]) -> int:
    # tìm tất cả ACCOUNT_n_PHONE để liệt kê
    idxs = sorted({int(k.split("_")[1]) for k in data.keys() if k.startswith("ACCOUNT_") and k.endswith("_PHONE") and k.split("_")[1].isdigit()})
    if not idxs:
        return 0
    # hiển thị
    lines = [pad("ACCOUNTS", WIDTH - 2)]
    for i in idxs:
        phone = data.get(f"ACCOUNT_{i}_PHONE", "")
        lines.append(pad(f"[{i}] {phone}", WIDTH - 2))
    print(c(box(lines), Fore.CYAN))
    sel = input("Nhập index tài khoản muốn dùng: ").strip()
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

def input_nonempty(prompt: str, default: Optional[str] = None) -> str:
    p = prompt + (f" [{default}]" if default else "") + ": "
    while True:
        val = input(p).strip()
        if not val and default is not None:
            return default
        if val:
            return val
        print("Vui lòng nhập lại.")

def do_login_flow(envd: Dict[str, str]) -> Dict[str, str]:
    # thêm / sửa 1 account
    idx = pick_account_index(envd)
    if idx == 0:
        # tạo mới index
        idx = 1 if "ACCOUNT_1_PHONE" not in envd else max([int(k.split("_")[1]) for k in envd if k.startswith("ACCOUNT_") and k.endswith("_PHONE") and k.split("_")[1].isdigit()]) + 1
    phone = input_nonempty("PHONE (kèm mã quốc gia)", envd.get(f"ACCOUNT_{idx}_PHONE", ""))
    api_id = input_nonempty("API_ID", envd.get(f"ACCOUNT_{idx}_API_ID", ""))
    api_hash = input_nonempty("API_HASH", envd.get(f"ACCOUNT_{idx}_API_HASH", ""))
    download_dir = input_nonempty("DOWNLOAD_DIR (thư mục tuyệt đối hoặc tương đối)", envd.get(f"ACCOUNT_{idx}_DOWNLOAD_DIR", "downloads"))
    envd[f"ACCOUNT_{idx}_PHONE"] = phone
    envd[f"ACCOUNT_{idx}_API_ID"] = api_id
    envd[f"ACCOUNT_{idx}_API_HASH"] = api_hash
    envd[f"ACCOUNT_{idx}_DOWNLOAD_DIR"] = download_dir
    envd = set_current_account_index(envd, idx)
    return envd

def do_reset_flow() -> Dict[str, str]:
    confirm = input("Bạn chắc chắn RESET .env? (yes/no): ").strip().lower()
    if confirm == "yes":
        return {"CURRENT_ACCOUNT": "0"}
    else:
        print("Huỷ RESET.")
        return load_env(Path(".env"))

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


async def do_logout_flow(envd: Dict[str, str]) -> Dict[str, str]:
    idx = get_current_account_index(envd)
    if idx == 0:
        print(c(pad("Chưa đăng nhập. Không có phiên nào để logout.", WIDTH, "left"), Fore.YELLOW))
        return envd
    purge_session_files_for(idx)
    print(c(pad("Đã xoá session local. Nếu muốn đăng nhập lại, chọn LOGIN.", WIDTH, "left"), Fore.GREEN))
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
            "source": {},              # {"type": "saved|dialogs|all", "dialog_ids": []}
            "completed_ids": [],       # list[int] các message.id đã tải xong
            "total_found": 0,
            "ids_hash": "",            # sha256 của danh sách message.id
            "last_filter": "3",        # 1=photos, 2=videos, 3=both
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
    def set_source(self, source_type: str, dialog_ids: list[int] | list[str], total_found: int = 0, ids_hash: str = "", last_filter: Optional[str] = None):
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
    def __init__(self, api_id: int, api_hash: str, phone: str, download_dir: str, account_index: int):
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
            pad("WIDTH-fixed console UI · Multi-account · Login/Logout/Reset · Resume", WIDTH - 2),
            pad(f"Download dir: {self.download_dir}", WIDTH - 2),
        ]
        print(c(box(lines), Fore.CYAN))
        print(line())

    async def connect_client(self) -> bool:
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                print(pad("Signing in...", WIDTH, "left"))
                try:
                    await self.client.send_code_request(self.phone)
                except FloodWaitError as e:
                    print(c(pad(f"Quá nhiều lần thử. Hãy chờ {e.seconds} giây.", WIDTH, "left"), Fore.RED))
                    return False

                # Retry OTP (3 lần)
                for attempt in range(3):
                    code = input(f"Nhập mã OTP ({attempt + 1}/3): ").strip()
                    try:
                        await self.client.sign_in(self.phone, code)
                        break  # thành công
                    except PhoneCodeInvalidError:
                        print(c(pad("❌ Mã OTP không đúng. Vui lòng thử lại.", WIDTH, "left"), Fore.RED))
                    except PhoneCodeExpiredError:
                        print(c(pad("⏰ Mã OTP đã hết hạn. Vui lòng gửi lại mã.", WIDTH, "left"), Fore.YELLOW))
                        return False
                    except SessionPasswordNeededError:
                        # Vào luồng 2FA
                        for pw_attempt in range(2):
                            pw = input(f"Nhập mật khẩu 2FA ({pw_attempt + 1}/2): ").strip()
                            try:
                                await self.client.sign_in(password=pw)
                                break  # thành công
                            except PasswordHashInvalidError:
                                print(c(pad("❌ Sai mật khẩu 2FA. Vui lòng thử lại.", WIDTH, "left"), Fore.RED))
                        else:
                            print(c(pad("🚫 Quá số lần nhập sai 2FA.", WIDTH, "left"), Fore.RED))
                            return False
                        break
                else:
                    print(c(pad("🚫 Quá số lần nhập sai OTP.", WIDTH, "left"), Fore.RED))
                    return False

            me = await self.client.get_me()
            display = f"{(me.first_name or '').strip()} {(me.last_name or '').strip()}".strip()
            username = f"@{me.username}" if getattr(me, 'username', None) else ""
            ok = f"Connected: {display} {username}".strip()
            print(c(pad(ok, WIDTH, "left"), Fore.GREEN))
            print(line("-"))
            return True
        except Exception as e:
            print(c(pad(f"Connection error: {e}", WIDTH, "left"), Fore.RED))
            print(line("-"))
            return False

    # ========== LIỆT KÊ & QUÉT ==========

    async def list_dialogs(self) -> List[dict]:
        print(pad("Fetching dialogs (chats/channels)...", WIDTH, "left"))
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
        print(c(box(lines), Fore.CYAN))
        return rows

    async def scan_media_in_dialogs(self, dialogs: List[Any]) -> List[Dict[str, Any]]:
        print(pad(f"Scanning {len(dialogs)} dialog(s) for media...", WIDTH, "left"))
        media_messages: List[Dict[str, Any]] = []
        message_count = 0
        with tqdm(
            desc="Scanning",
            unit="msg",
            ncols=WIDTH,
            ascii=True,
            bar_format="{desc}: {n_fmt} |{bar}| {rate_fmt}",
            colour=None
        ) as pbar:
            try:
                for d in dialogs:
                    async for message in self.client.iter_messages(d):
                        message_count += 1
                        pbar.update(1)
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
                pbar.set_description("Done")
            except Exception as e:
                print(c(pad(f"Scan error: {e}", WIDTH, "left"), Fore.RED))
        print(pad(f"Found {len(media_messages)} media in {message_count} messages across {len(dialogs)} dialog(s).", WIDTH, "left"))
        print(line("-"))
        return media_messages

    async def scan_saved_messages(self) -> List[Dict[str, Any]]:
        print(pad("Scanning Saved Messages...", WIDTH, "left"))
        media_messages: List[Dict[str, Any]] = []
        message_count = 0
        with tqdm(
            desc="Scanning",
            unit="msg",
            ncols=WIDTH,
            ascii=True,
            bar_format="{desc}: {n_fmt} |{bar}| {rate_fmt}",
            colour=None
        ) as pbar:
            try:
                async for message in self.client.iter_messages('me'):
                    message_count += 1
                    pbar.update(1)
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
                pbar.set_description("Done")
            except Exception as e:
                print(c(pad(f"Scan error: {e}", WIDTH, "left"), Fore.RED))
        print(pad(f"Found {len(media_messages)} media in {message_count} messages.", WIDTH, "left"))
        print(line("-"))
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
        print(c(box(lines), Fore.CYAN))

    def prompt_download_choice(self, default: Optional[str] = None) -> str:
        lines = [
            pad("Select what to download (1/2/3, other to cancel):", WIDTH - 2),
            pad("1) Photos only   -> PIC", WIDTH - 2),
            pad("2) Videos only   -> VID", WIDTH - 2),
            pad("3) Photos & Videos (both)", WIDTH - 2),
        ]
        print(c(box(lines), Fore.YELLOW))
        p = "Your choice"
        if default in {"1", "2", "3"}:
            p += f" [{default}]"
        p += ": "
        choice = input(p).strip() or (default if default in {"1","2","3"} else "")
        print(line("-"))
        return choice

    async def download_all_media(self, media_list: List[Dict[str, Any]]) -> None:
        def _handle_sigint(signum, frame):
            print(c(pad("Nhận tín hiệu dừng. Sẽ thoát sau file hiện tại...", WIDTH, "left"), Fore.YELLOW))
            raise KeyboardInterrupt()
        old_handler = signal.signal(signal.SIGINT, _handle_sigint)

        try:
            with tqdm(
                total=len(media_list),
                desc="Downloading",
                unit="file",
                ncols=WIDTH,
                ascii=True,
                bar_format="{desc}: {n_fmt}/{total_fmt} |{bar}| {rate_fmt}",
                colour=None
            ) as pbar:
                for item in media_list:
                    msg = item["message"]
                    target_path = self._target_path_for(item)
                    target_dir = target_path.parent
                    target_dir.mkdir(exist_ok=True)

                    # Nếu file có sẵn (đúng id) -> skip + mark completed
                    if target_path.exists() and os.path.getsize(target_path) > 0:
                        self.stats['skipped'] += 1
                        self.state.mark_completed(int(msg.id))
                        pbar.update(1)
                        continue

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
                        print(c(pad(f"Download error (msg {msg.id}): {e}", WIDTH, "left"), Fore.RED))
                    pbar.update(1)
        finally:
            try:
                signal.signal(signal.SIGINT, old_handler)
            except Exception:
                pass

    # ===================== CHẠY THEO NGUỒN =======================

    async def _run_with_source(self, src_type: str, chosen_entities: Optional[List[Any]] = None) -> bool:
        """
        Thực thi chu trình quét + tải theo nguồn đã biết.
        src_type: "saved" | "dialogs" | "all"
        chosen_entities: danh sách entity (nếu dialogs/all), có thể None nếu saved
        """
        # 1) Scan theo nguồn
        if src_type == "saved":
            media_list = await self.scan_media_in_dialogs(['me'])
            dialog_ids = ["me"]
        else:
            if chosen_entities is None:
                print(pad("Không có entities để quét.", WIDTH, "left"))
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
            print(pad("No media found.", WIDTH, "left"))
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
            print(c(pad("Danh sách media đã thay đổi so với lần trước (hash khác).", WIDTH, "left"), Fore.YELLOW))
            ans = input("Reset tiến độ để quét/tải lại từ đầu? (yes/no) [no]: ").strip().lower() or "no"
            print(line("-"))
            if ans == "yes":
                self.state.clear_progress()
                print(c(pad("Đã reset tiến độ.", WIDTH, "left"), Fore.CYAN))

        # 6) In stats + chọn filter (mặc định lấy last_filter)
        self.print_stats()
        choice = self.prompt_download_choice(default=self.state.get_last_filter())
        if choice not in {"1", "2", "3"}:
            print(pad("Canceled by user choice.", WIDTH, "left"))
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
            print(pad("Không còn item nào cần tải (đã hoàn tất).", WIDTH, "left"))
            self.print_stats()
            return True

        # 9) Tải
        start_time = time.time()
        await self.download_all_media(resumable)
        elapsed = time.time() - start_time
        print(pad("Download finished.", WIDTH, "left"))
        print(pad(f"Elapsed: {humanize.naturaldelta(elapsed)}", WIDTH, "left"))
        self.print_stats()
        if self.stats['downloaded'] > 0 and elapsed > 0:
            avg_speed = self.stats['total_size'] / elapsed
            print(pad(f"Average speed: {humanize.naturalsize(avg_speed)}/s", WIDTH, "left"))
        return True

    # ===================== LUỒNG CHÍNH =======================

    async def run(self) -> bool:
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
            print(c(box(lines), Fore.YELLOW))
            src_choice = input("Your choice: ").strip()
            print(line("-"))

            if src_choice == "4":
                # Continue last session
                prev = self.state.get_source()
                if not prev or not prev.get("type"):
                    print(pad("Chưa có phiên trước để tiếp tục.", WIDTH, "left"))
                    return True
                typ = prev.get("type")
                if typ == "saved":
                    return await self._run_with_source("saved")
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
                        print(pad("Không khôi phục được danh sách dialogs từ phiên trước.", WIDTH, "left"))
                        return True
                    return await self._run_with_source(typ, ents)

            if src_choice == "1":
                return await self._run_with_source("saved")

            elif src_choice == "2":
                rows = await self.list_dialogs()
                if not rows:
                    print(pad("Không có dialog nào.", WIDTH, "left"))
                    return True
                print(pad("Nhập chỉ số dialogs muốn quét (ví dụ: 1,3,5-7). Enter để huỷ.", WIDTH, "left"))
                pick = input("Pick: ").strip()
                print(line("-"))
                if not pick:
                    print(pad("Huỷ bởi người dùng.", WIDTH, "left"))
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
                    print(pad("Không có lựa chọn hợp lệ.", WIDTH, "left"))
                    return True
                return await self._run_with_source("dialogs", chosen)

            elif src_choice == "3":
                rows = await self.list_dialogs()
                ents = [r["dialog"].entity for r in rows]
                return await self._run_with_source("all", ents)

            else:
                print(pad("Lựa chọn không hợp lệ. Huỷ.", WIDTH, "left"))
                return True

        except KeyboardInterrupt:
            print(pad("Interrupted by user.", WIDTH, "left"))
            return False
        except Exception as e:
            print(pad(f"Unexpected error: {e}", WIDTH, "left"))
            return False
        finally:
            await self.client.disconnect()

# ============================ MENU PHỤ TRỢ =============================

def print_account_status(envd: Dict[str, str]) -> None:
    idx = get_current_account_index(envd)
    if idx == 0:
        print(c(pad("Chưa chọn tài khoản.", WIDTH, "left"), Fore.YELLOW))
        return
    cfg = get_account_config(envd, idx)
    dldir = cfg.get("DOWNLOAD_DIR", "").strip() or "downloads"
    sm = StateManager(Path(dldir), idx)
    lines = [pad("ACCOUNT STATUS", WIDTH - 2), ""]
    lines.extend([pad(s, WIDTH - 2) for s in sm.get_status_lines()])
    print(c(box(lines), Fore.CYAN))

async def run_downloader_with_env(envd: Dict[str, str]) -> None:
    idx = get_current_account_index(envd)
    if idx == 0:
        print(c(pad("Chưa chọn tài khoản. Vào LOGIN để cấu hình.", WIDTH, "left"), Fore.YELLOW))
        return
    cfg = get_account_config(envd, idx)
    missing = [k for k, v in cfg.items() if not str(v).strip()]
    if missing:
        print(c(pad(f"Thiếu cấu hình: {', '.join(missing)}", WIDTH, "left"), Fore.RED))
        return
    Path(cfg["DOWNLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    app = TelegramDownloader(
        api_id=int(cfg["API_ID"]),
        api_hash=str(cfg["API_HASH"]),
        phone=str(cfg["PHONE"]),
        download_dir=str(cfg["DOWNLOAD_DIR"]),
        account_index=idx,   # per-account state
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
    print(c(box(lines), Fore.GREEN))
    raw = input("Chọn: ").strip()
    print(line("-"))
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
            envd = do_login_flow(envd)
            save_env(env_path, envd)
            print(c(pad("Đã lưu cấu hình.", WIDTH, "left"), Fore.CYAN))
            print_account_status(envd)  # in trạng thái ngay sau login
        elif choice == 2:
            envd = await do_logout_flow(envd)
        elif choice == 3:
            envd = do_reset_flow()
            save_env(env_path, envd)
            print(c(pad("Đã reset .env.", WIDTH, "left"), Fore.CYAN))
            envd = load_env(env_path)
        elif choice == 5:
            print_account_status(envd)
        elif choice == 6:
            # chạy nhanh "Continue last session"
            idx = get_current_account_index(envd)
            if idx == 0:
                print(c(pad("Chưa chọn tài khoản.", WIDTH, "left"), Fore.YELLOW))
                continue
            cfg = get_account_config(envd, idx)
            missing = [k for k, v in cfg.items() if not str(v).strip()]
            if missing:
                print(c(pad(f"Thiếu cấu hình: {', '.join(missing)}", WIDTH, "left"), Fore.RED))
                continue
            Path(cfg["DOWNLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
            app = TelegramDownloader(
                api_id=int(cfg["API_ID"]),
                api_hash=str(cfg["API_HASH"]),
                phone=str(cfg["PHONE"]),
                download_dir=str(cfg["DOWNLOAD_DIR"]),
                account_index=idx,
            )
            # Bỏ qua menu nguồn, gọi trực tiếp đường tắt
            try:
                # Tái sử dụng logic trong run(): xây màn nhỏ "continue"
                if not await app.connect_client():
                    continue
                prev = app.state.get_source()
                if not prev or not prev.get("type"):
                    print(pad("Chưa có phiên trước để tiếp tục.", WIDTH, "left"))
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
                        print(pad("Không khôi phục được danh sách dialogs từ phiên trước.", WIDTH, "left"))
                    else:
                        await app._run_with_source(typ, ents)
            finally:
                try:
                    await app.client.disconnect()
                except Exception:
                    pass
        elif choice == 4 or choice == 0:  # EXIT hoặc chọn sai -> thoát
            print(c(pad("Goodbye.", WIDTH, "left"), Fore.CYAN))
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Goodbye.")
    except Exception as e:
        print(f"Fatal: {e}")
        sys.exit(1)
