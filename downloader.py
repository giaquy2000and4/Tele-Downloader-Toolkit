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
CURRENT_ACCOUNT=1
ACCOUNT_1_PHONE=+84901572620
ACCOUNT_1_API_ID=20431364
ACCOUNT_1_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ACCOUNT_1_DOWNLOAD_DIR=/path/dir1

ACCOUNT_2_PHONE=+84123456789
ACCOUNT_2_API_ID=12345678
ACCOUNT_2_API_HASH=yyyyyyyyyyyyyyyyyyyyyyyyyyyyy
ACCOUNT_2_DOWNLOAD_DIR=/path/dir2
"""

import asyncio
import os
import sys
import time
import re
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

try:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
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
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
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

def purge_session_files() -> None:
    names = ["session.session", "session.session-journal", "session"]
    for n in names:
        p = Path(n)
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass

async def do_logout_flow(envd: Dict[str, str]) -> Dict[str, str]:
    idx = get_current_account_index(envd)
    if idx == 0:
        print(c(pad("Chưa đăng nhập. Không có phiên nào để logout.", WIDTH, "left"), Fore.YELLOW))
        return envd
    purge_session_files()
    print(c(pad("Đã xoá session local. Nếu muốn đăng nhập lại, chọn LOGIN.", WIDTH, "left"), Fore.GREEN))
    return envd

# ============================ DOWNLOADER LÕI =============================

class TelegramDownloader:
    def __init__(self, api_id: int, api_hash: str, phone: str, download_dir: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.download_dir = Path(download_dir)
        self.pic_dir = self.download_dir / "PIC"
        self.vid_dir = self.download_dir / "VID"
        self.client = TelegramClient('session', api_id, api_hash)

        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.pic_dir.mkdir(exist_ok=True)
        self.vid_dir.mkdir(exist_ok=True)

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
            pad("WIDTH-fixed console UI · Multi-account · Login/Logout/Reset", WIDTH - 2),
            pad(f"Download dir: {self.download_dir}", WIDTH - 2),
        ]
        print(c(box(lines), Fore.CYAN))
        print(line())

    async def connect_client(self) -> bool:
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                print(pad("Signing in...", WIDTH, "left"))
                await self.client.send_code_request(self.phone)
                code = input("Enter the login code: ").strip()
                try:
                    await self.client.sign_in(self.phone, code)
                except SessionPasswordNeededError:
                    pw = input("2FA password: ").strip()
                    await self.client.sign_in(password=pw)
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

    # ========== BỔ SUNG: LIỆT KÊ DIALOGS VÀ QUÉT NHIỀU DIALOGS ==========
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
    # ===================== HẾT PHẦN BỔ SUNG (NEW) =======================

    def _build_filename_and_size(self, media_info: Dict[str, Any]) -> Tuple[str, int]:
        message = media_info['message']
        file_type = media_info['type']
        if file_type == 'photo':
            filename = f"photo_{message.date.strftime('%Y%m%d_%H%M%S')}_{message.id}.jpg"
            file_size = 0
        else:
            doc = message.media.document
            filename = None
            for attr in getattr(doc, "attributes", []):
                if hasattr(attr, 'file_name') and getattr(attr, 'file_name'):
                    filename = attr.file_name
                    break
            if not filename:
                filename = f"video_{message.date.strftime('%Y%m%d_%H%M%S')}_{message.id}.mp4"
            file_size = getattr(doc, "size", 0)
        return filename, file_size

    def print_stats(self) -> None:
        lines = [
            pad("CURRENT STATS", WIDTH - 2),
            pad(f"Photos found: {self.stats['images_found']}", WIDTH - 2),
            pad(f"Videos found: {self.stats['videos_found']}", WIDTH - 2),
            pad(f"Total media: {self.stats['total_found']}", WIDTH - 2),
            pad(f"Downloaded: {self.stats['downloaded']}", WIDTH - 2),
            pad(f"Total size: {humanize.naturalsize(self.stats['total_size'])}", WIDTH - 2),
        ]
        print(c(box(lines), Fore.CYAN))

    def print_sample_table_header(self) -> None:
        print(pad("TYPE  |" + pad("FILENAME", 57, "left") + "|" + pad("SIZE", 15, "right"), WIDTH, "left"))
        print(line())

    def print_sample_row(self, file_type: str, filename: str, size: int):
        type_col = pad(file_type.upper(), 6)
        name_col = pad(filename, 57, "left")
        size_col = pad(humanize.naturalsize(size) if size else "-", 15, "right")
        print(f"{type_col}|{name_col}|{size_col}")

    def prompt_download_choice(self) -> str:
        lines = [
            pad("Select what to download (1/2/3, other to cancel):", WIDTH - 2),
            pad("1) Photos only   -> PIC", WIDTH - 2),
            pad("2) Videos only   -> VID", WIDTH - 2),
            pad("3) Photos & Videos (both)", WIDTH - 2),
        ]
        print(c(box(lines), Fore.YELLOW))
        choice = input("Your choice: ").strip()
        print(line("-"))
        return choice

    async def download_all_media(self, media_list: List[Dict[str, Any]]) -> None:
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
                ftype = item["type"]
                target_dir = self.pic_dir if ftype == "photo" else self.vid_dir
                target_dir.mkdir(exist_ok=True)
                try:
                    path = await self.client.download_media(msg, file=str(target_dir / ""))
                    if path:
                        size = os.path.getsize(path)
                        self.stats['downloaded'] += 1
                        self.stats['total_size'] += size
                except Exception as e:
                    self.stats['errors'] += 1
                    print(c(pad(f"Download error: {e}", WIDTH, "left"), Fore.RED))
                pbar.update(1)

    # Giữ nguyên hàm cũ để tương thích lựa chọn "Saved Messages"
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

    async def run(self) -> bool:
        self.print_banner()
        if not await self.connect_client():
            return False
        try:
            # NGUỒN QUÉT (mới)
            lines = [
                pad("Chọn NGUỒN để quét media:", WIDTH - 2),
                pad("1) Saved Messages (me)", WIDTH - 2),
                pad("2) Chọn dialogs/channels cụ thể", WIDTH - 2),
                pad("3) Tất cả dialogs/channels", WIDTH - 2),
            ]
            print(c(box(lines), Fore.YELLOW))
            src_choice = input("Your choice: ").strip()
            print(line("-"))

            if src_choice == "1":
                media_list = await self.scan_media_in_dialogs(['me'])
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
                media_list = await self.scan_media_in_dialogs(chosen)
            elif src_choice == "3":
                rows = await self.list_dialogs()
                media_list = await self.scan_media_in_dialogs([r["dialog"].entity for r in rows])
            else:
                print(pad("Lựa chọn không hợp lệ. Huỷ.", WIDTH, "left"))
                return True

            if not media_list:
                print(pad("No media found.", WIDTH, "left"))
                return True

            self.print_stats()
            choice = self.prompt_download_choice()
            if choice not in {"1", "2", "3"}:
                print(pad("Canceled by user choice.", WIDTH, "left"))
                return True

            if choice == "1":
                filtered = [m for m in media_list if m['type'] == 'photo']
            elif choice == "2":
                filtered = [m for m in media_list if m['type'] == 'video']
            else:
                filtered = media_list

            if not filtered:
                print(pad("No items match your selection.", WIDTH, "left"))
                return True
            start_time = time.time()
            await self.download_all_media(filtered)
            elapsed = time.time() - start_time
            print(pad("Download finished.", WIDTH, "left"))
            print(pad(f"Elapsed: {humanize.naturaldelta(elapsed)}", WIDTH, "left"))
            self.print_stats()
            if self.stats['downloaded'] > 0 and elapsed > 0:
                avg_speed = self.stats['total_size'] / elapsed
                print(pad(f"Average speed: {humanize.naturalsize(avg_speed)}/s", WIDTH, "left"))
            return True
        except KeyboardInterrupt:
            print(pad("Interrupted by user.", WIDTH, "left"))
            return False
        except Exception as e:
            print(pad(f"Unexpected error: {e}", WIDTH, "left"))
            return False
        finally:
            await self.client.disconnect()

# ============================ ENTRYPOINT / MENU =============================

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
    # tạo thư mục download nếu cần
    Path(cfg["DOWNLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    # chạy downloader
    app = TelegramDownloader(
        api_id=int(cfg["API_ID"]),
        api_hash=str(cfg["API_HASH"]),
        phone=str(cfg["PHONE"]),
        download_dir=str(cfg["DOWNLOAD_DIR"]),
    )
    await app.run()

def main_menu() -> int:
    lines = [
        pad("MAIN MENU", WIDTH - 2),
        pad("1) LOGIN  - cấu hình/đổi tài khoản", WIDTH - 2),
        pad("2) LOGOUT - xoá session local", WIDTH - 2),
        pad("3) RESET  - xoá .env về mặc định", WIDTH - 2),
        pad("4) EXIT", WIDTH - 2),
        pad("0) EXIT (phím khác)", WIDTH - 2),
        pad("", WIDTH - 2),
        pad("Hoặc nhấn Enter để CHẠY DOWNLOADER ngay với tài khoản hiện tại.", WIDTH - 2),
    ]
    print(c(box(lines), Fore.GREEN))
    raw = input("Chọn: ").strip()
    print(line("-"))
    if raw == "":
        return 9  # run
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
        elif choice == 2:
            envd = await do_logout_flow(envd)
        elif choice == 3:
            envd = do_reset_flow()
            save_env(env_path, envd)
            print(c(pad("Đã reset .env.", WIDTH, "left"), Fore.CYAN))
            envd = load_env(env_path)
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
