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
ACCOUNT_1_API_HASH=9ac968fa4e5a1b4bfe086560ce8e94c6
ACCOUNT_1_DOWNLOAD_DIR=downloads_saved_videos
ACCOUNT_2_PHONE=...
...

Vẫn tương thích ngược với kiểu .env đơn:
TELEGRAM_API_ID=..., TELEGRAM_API_HASH=..., TELEGRAM_PHONE=..., DOWNLOAD_DIR=...
(khi gặp kiểu cũ, chương trình sẽ tự "di cư" sang kiểu đa tài khoản)
"""

import asyncio
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ===================== TÙY CHỈNH GIAO DIỆN =====================
WIDTH = 80
USE_COLOR = True
BAR_CHAR = "="
# ================================================================

try:
    from telethon import TelegramClient
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
    import colorama
    from colorama import Fore, Style
    from tqdm import tqdm
    import humanize
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install telethon colorama tqdm humanize python-dotenv")
    sys.exit(1)

colorama.init(autoreset=True)

def c(text: str, color: str) -> str:
    if not USE_COLOR:
        return text
    return f"{color}{text}{Style.RESET_ALL}"

def line(char: str = BAR_CHAR, width: int = WIDTH) -> str:
    return char * width

def center(text: str, width: int = WIDTH) -> str:
    return text.center(width)

def pad(text: str, width: int, align: str = "left") -> str:
    if len(text) > width:
        return text[:max(0, width - 3)] + "..."
    if align == "right":
        return text.rjust(width)
    if align == "center":
        return text.center(width)
    return text.ljust(width)

def box(lines: List[str]) -> str:
    top = "┌" + "─" * (WIDTH - 2) + "┐"
    bottom = "└" + "─" * (WIDTH - 2) + "┘"
    body = []
    for ln in lines:
        s = pad(ln, WIDTH - 2, "left")
        body.append("│" + s + "│")
    return "\n".join([top] + body + [bottom])

# ======================= TIỆN ÍCH .env & NHIỀU TÀI KHOẢN =======================

ENV_PATH = Path(".env")

def read_env_file() -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not ENV_PATH.exists():
        return data
    try:
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if not raw or raw.strip().startswith("#"):
                continue
            if "=" not in raw:
                continue
            k, v = raw.split("=", 1)
            data[k.strip()] = v.strip()
    except Exception:
        return {}
    return data

def write_env_file(data: Dict[str, str]) -> None:
    # Ghi theo thứ tự khoá để dễ nhìn
    lines = []
    for k in sorted(data.keys()):
        lines.append(f"{k}={data[k]}")
    lines.append("")  # newline ở cuối
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")

def reset_env_file() -> None:
    ENV_PATH.write_text("", encoding="utf-8")

def migrate_single_account(envd: Dict[str, str]) -> Dict[str, str]:
    # Nếu phát hiện định dạng đơn, chuyển sang ACCOUNT_1_*
    api = envd.get("TELEGRAM_API_ID", "").strip()
    ah = envd.get("TELEGRAM_API_HASH", "").strip()
    ph = envd.get("TELEGRAM_PHONE", "").strip()
    dd = envd.get("DOWNLOAD_DIR", "").strip() or "downloads_saved_videos"
    if api and ah and ph:
        # Chỉ migrates nếu chưa có ACCOUNT_1_*
        if not any(k.startswith("ACCOUNT_1_") for k in envd.keys()):
            envd[f"ACCOUNT_1_API_ID"] = api
            envd[f"ACCOUNT_1_API_HASH"] = ah
            envd[f"ACCOUNT_1_PHONE"] = ph
            envd[f"ACCOUNT_1_DOWNLOAD_DIR"] = dd
            envd["CURRENT_ACCOUNT"] = "1"
        # Xoá khoá cũ
        for k in ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_PHONE", "DOWNLOAD_DIR"]:
            if k in envd:
                del envd[k]
    return envd

ACCOUNT_KEY_RE = re.compile(r"^ACCOUNT_(\d+)_(API_ID|API_HASH|PHONE|DOWNLOAD_DIR)$")

def get_account_indices(envd: Dict[str, str]) -> List[int]:
    idxs = set()
    for k in envd.keys():
        m = ACCOUNT_KEY_RE.match(k)
        if m:
            idxs.add(int(m.group(1)))
    return sorted(idxs)

def get_account(envd: Dict[str, str], idx: int) -> Dict[str, str]:
    return {
        "API_ID": envd.get(f"ACCOUNT_{idx}_API_ID", "").strip(),
        "API_HASH": envd.get(f"ACCOUNT_{idx}_API_HASH", "").strip(),
        "PHONE": envd.get(f"ACCOUNT_{idx}_PHONE", "").strip(),
        "DOWNLOAD_DIR": envd.get(f"ACCOUNT_{idx}_DOWNLOAD_DIR", "").strip() or "downloads_saved_videos",
    }

def set_account(envd: Dict[str, str], idx: int, api_id: str, api_hash: str, phone: str, download_dir: str) -> Dict[str, str]:
    envd[f"ACCOUNT_{idx}_API_ID"] = api_id.strip()
    envd[f"ACCOUNT_{idx}_API_HASH"] = api_hash.strip()
    envd[f"ACCOUNT_{idx}_PHONE"] = phone.strip()
    envd[f"ACCOUNT_{idx}_DOWNLOAD_DIR"] = download_dir.strip()
    return envd

def get_current_account_index(envd: Dict[str, str]) -> int:
    v = envd.get("CURRENT_ACCOUNT", "").strip()
    if v.isdigit():
        return int(v)
    return 0

def set_current_account_index(envd: Dict[str, str], idx: int) -> Dict[str, str]:
    envd["CURRENT_ACCOUNT"] = str(idx)
    return envd

ENV_TEMPLATE_HINT = [
    "Bạn có thể thêm nhiều tài khoản sau. Mỗi tài khoản lưu ở dạng ACCOUNT_n_*.",
    "Ví dụ:",
    "CURRENT_ACCOUNT=1",
    "ACCOUNT_1_API_ID=20431364",
    "ACCOUNT_1_API_HASH=9ac968fa4e5a1b4bfe086560ce8e94c6",
    "ACCOUNT_1_PHONE=+84901572620",
    "ACCOUNT_1_DOWNLOAD_DIR=downloads_saved_videos",
]

def print_env_wizard_header():
    lines = [
        pad("ENV SETUP WIZARD - Thiết lập cấu hình .env", WIDTH - 2),
        pad("Chưa có tài khoản hoặc thông tin chưa đủ. Hãy nhập thông tin bên dưới.", WIDTH - 2),
        *[pad(s, WIDTH - 2) for s in ENV_TEMPLATE_HINT],
    ]
    print(c(box(lines), Fore.YELLOW))

def _ask_input(prompt: str, default: str = "") -> str:
    show = f"{prompt.strip()} [{'default: ' + default if default else 'required'}]: "
    val = input(show).strip()
    if not val and default:
        return default
    return val

def _choose_download_dir(default_dir: str = "downloads_saved_videos") -> str:
    lines = [
        pad("Chọn NƠI LƯU và TÊN FOLDER tải xuống", WIDTH - 2),
        pad(f"Thư mục mặc định: ./{default_dir}", WIDTH - 2),
        pad("Bạn có thể nhập đường dẫn tổng (ví dụ: D:/Media) và tên folder (ví dụ: MyTG).", WIDTH - 2),
        pad("Kết quả sẽ là: <đường dẫn tổng>/<tên folder>", WIDTH - 2),
    ]
    print(c(box(lines), Fore.CYAN))
    base_path = _ask_input("Nhập đường dẫn tổng (mặc định là thư mục hiện tại)", default=str(Path.cwd()))
    folder_name = _ask_input("Nhập tên folder lưu file", default=default_dir)
    try:
        base = Path(base_path).expanduser().resolve()
    except Exception:
        base = Path.cwd().resolve()
    final_path = (base / folder_name).as_posix()
    confirm_lines = [pad("DOWNLOAD DIR được đặt là:", WIDTH - 2), pad(final_path, WIDTH - 2)]
    print(c(box(confirm_lines), Fore.GREEN))
    return final_path

def wizard_add_account(envd: Dict[str, str]) -> Tuple[Dict[str, str], int]:
    print_env_wizard_header()
    # Tìm index mới
    idxs = get_account_indices(envd)
    new_idx = (idxs[-1] + 1) if idxs else 1

    while True:
        api_id_str = _ask_input("TELEGRAM_API_ID (số nguyên)")
        if not api_id_str.isdigit():
            print(c(pad("Lỗi: TELEGRAM_API_ID phải là số nguyên.", WIDTH, "left"), Fore.RED))
            continue
        break
    api_hash = _ask_input("TELEGRAM_API_HASH")
    while not api_hash:
        print(c(pad("Lỗi: TELEGRAM_API_HASH không được rỗng.", WIDTH, "left"), Fore.RED))
        api_hash = _ask_input("TELEGRAM_API_HASH")

    phone = _ask_input("TELEGRAM_PHONE")
    while not phone:
        print(c(pad("Lỗi: TELEGRAM_PHONE không được rỗng.", WIDTH, "left"), Fore.RED))
        phone = _ask_input("TELEGRAM_PHONE")

    download_dir = _choose_download_dir(default_dir="downloads_saved_videos")
    envd = set_account(envd, new_idx, api_id_str, api_hash, phone, download_dir)
    envd = set_current_account_index(envd, new_idx)

    write_env_file(envd)
    lines = [
        pad("ĐÃ THÊM TÀI KHOẢN MỚI & LƯU .env:", WIDTH - 2),
        pad(f"ACCOUNT_{new_idx}_PHONE={phone}", WIDTH - 2),
        pad(f"DOWNLOAD_DIR={download_dir}", WIDTH - 2),
    ]
    print(c(box(lines), Fore.GREEN))
    return envd, new_idx

def show_menu(options: List[str], title: str = "MENU") -> int:
    lines = [pad(title, WIDTH - 2), pad("", WIDTH - 2)]
    for i, opt in enumerate(options, 1):
        lines.append(pad(f"{i}) {opt}", WIDTH - 2))
    print(c(box(lines), Fore.MAGENTA))
    choice = input("Your choice: ").strip()
    print(line("-"))
    if not choice.isdigit():
        return 0
    n = int(choice)
    if 1 <= n <= len(options):
        return n
    return 0

def show_accounts_and_choose(envd: Dict[str, str]) -> int:
    idxs = get_account_indices(envd)
    if not idxs:
        return 0
    listing: List[str] = []
    for i in idxs:
        acc = get_account(envd, i)
        label = f"[{i}] {acc['PHONE']} -> dir: {acc['DOWNLOAD_DIR']}"
        listing.append(label)
    lines = [pad("CHỌN TÀI KHOẢN ĐỂ ĐĂNG NHẬP", WIDTH - 2), pad("", WIDTH - 2)]
    for s in listing:
        lines.append(pad(s, WIDTH - 2))
    print(c(box(lines), Fore.CYAN))
    sel = _ask_input("Nhập số index tài khoản muốn dùng", default=str(idxs[0]))
    if sel.isdigit() and int(sel) in idxs:
        return int(sel)
    return 0

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
            'total_size': 0
        }

    def print_banner(self):
        title = "TELEGRAM MEDIA DOWNLOADER"
        lines = [pad("", WIDTH - 2), center(title, WIDTH - 2), pad("", WIDTH - 2)]
        print(c(box(lines), Fore.CYAN))
        info_lines = [
            f"Phone: {self.phone}",
            f"Download Directory: {self.download_dir.absolute()}",
            f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        print(c(box(info_lines), Fore.MAGENTA))
        print(line("-"))

    def print_stats(self):
        rows = [
            ("Images Found", str(self.stats['images_found'])),
            ("Videos Found", str(self.stats['videos_found'])),
            ("Total Items",  str(self.stats['total_found'])),
            ("Downloaded",   str(self.stats['downloaded'])),
            ("Skipped",      str(self.stats['skipped'])),
            ("Errors",       str(self.stats['errors'])),
            ("Total Size",   humanize.naturalsize(self.stats['total_size'])),
        ]
        header = pad("STATISTICS", WIDTH - 2, "center")
        out = [" " * (WIDTH - 2), header, " " * (WIDTH - 2)]
        for k, v in rows:
            left = pad(k + ":", 20)
            right = pad(v, 12, "right")
            out.append(f"{left} {right}")
        out.append(" " * (WIDTH - 2))
        print(c(box(out), Fore.CYAN))
        print(line("-"))

    def print_fixed_row(self, file_type: str, filename: str, size: int):
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

    async def connect_client(self) -> bool:
        print(pad("Connecting to Telegram...", WIDTH, "left"))
        try:
            await self.client.start(phone=self.phone)
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
                ext = (getattr(doc, "mime_type", "application/octet-stream").split('/')[-1]) or "bin"
                filename = f"video_{message.date.strftime('%Y%m%d_%H%M%S')}_{message.id}.{ext}"
            file_size = getattr(doc, "size", 0)
        return filename, file_size

    async def download_media_file(self, media_info: dict) -> bool:
        message = media_info['message']
        file_type = media_info['type']
        try:
            filename, file_size = self._build_filename_and_size(media_info)
            target_dir = self.pic_dir if file_type == 'photo' else self.vid_dir
            file_path = target_dir / filename
            self.print_fixed_row(file_type, filename, file_size)
            if file_path.exists():
                self.stats['skipped'] += 1
                print(pad("Status: SKIPPED (already exists)", WIDTH, "left"))
                return True
            await message.download_media(file=str(file_path))
            self.stats['downloaded'] += 1
            self.stats['total_size'] += file_size or 0
            print(pad("Status: DOWNLOADED", WIDTH, "left"))
            return True
        except Exception as e:
            self.stats['errors'] += 1
            print(pad(f"Status: ERROR - {e}", WIDTH, "left"))
            return False

    async def download_all_media(self, media_list: list):
        if not media_list:
            print(pad("Nothing to download.", WIDTH, "left"))
            return
        print(pad(f"Start downloading {len(media_list)} items...", WIDTH, "left"))
        with tqdm(
            total=len(media_list),
            desc="Progress",
            ncols=WIDTH,
            ascii=True,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            colour=None
        ) as main_pbar:
            for m in media_list:
                await self.download_media_file(m)
                main_pbar.update(1)
                print(line(" "))

    async def run(self) -> bool:
        self.print_banner()
        if not await self.connect_client():
            return False
        try:
            media_list = await self.scan_saved_messages()
            if not media_list:
                print(pad("No media found in Saved Messages.", WIDTH, "left"))
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

# ============================ LOGIN / LOGOUT / RESET ============================

def remove_session_files():
    # Telethon mặc định lưu 'session.session' (với base name 'session')
    # Xoá an toàn nếu tồn tại
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
    acc = get_account(envd, idx)
    lines = [
        pad("ĐANG ĐĂNG XUẤT PHIÊN HIỆN TẠI", WIDTH - 2),
        pad(f"PHONE: {acc['PHONE']}", WIDTH - 2),
    ]
    print(c(box(lines), Fore.MAGENTA))
    try:
        api_id = int(acc["API_ID"])
        client = TelegramClient("session", api_id, acc["API_HASH"])
        await client.connect()
        try:
            # Nếu có thể, gọi log_out() để Telegram xoá các key server-side
            await client.log_out()
        except Exception:
            pass
        await client.disconnect()
    except Exception:
        pass
    # Xoá session local + bỏ đánh dấu CURRENT_ACCOUNT
    remove_session_files()
    if "CURRENT_ACCOUNT" in envd:
        del envd["CURRENT_ACCOUNT"]
    write_env_file(envd)
    print(c(pad("Đã logout. Trở về màn hình chính.", WIDTH, "left"), Fore.GREEN))
    return envd

def do_reset_flow() -> Dict[str, str]:
    lines = [
        pad("RESET: XÓA SẠCH .env & SESSION", WIDTH - 2),
        pad("Chức năng này sẽ đưa chương trình về trạng thái ban đầu.", WIDTH - 2),
    ]
    print(c(box(lines), Fore.YELLOW))
    ans = _ask_input("Gõ 'YES' để xác nhận", default="")
    if ans.strip().upper() == "YES":
        try:
            reset_env_file()
        except Exception:
            pass
        remove_session_files()
        print(c(pad("Đã reset. .env trống & session đã xoá.", WIDTH, "left"), Fore.GREEN))
    else:
        print(c(pad("Huỷ reset.", WIDTH, "left"), Fore.YELLOW))
    return read_env_file()

def ensure_env_loaded_and_migrated() -> Dict[str, str]:
    # Nạp env (dotenv để hỗ trợ os.getenv nếu người dùng đã export)
    load_dotenv(override=False)
    envd = read_env_file()
    # Di cư nếu là định dạng cũ
    old = envd.copy()
    envd = migrate_single_account(envd)
    if envd != old:
        write_env_file(envd)
    return envd

def do_login_flow() -> Tuple[Dict[str, str], int]:
    envd = ensure_env_loaded_and_migrated()
    idxs = get_account_indices(envd)

    if not idxs:
        # Chưa có tài khoản, mở wizard thêm
        envd, idx = wizard_add_account(envd)
        return envd, idx

    # Có tài khoản -> hiển thị & cho chọn, hoặc thêm mới
    choice = show_menu(["Chọn tài khoản có sẵn", "Thêm tài khoản mới", "Huỷ"], title="LOGIN")
    if choice == 1:
        idx = show_accounts_and_choose(envd)
        if idx == 0:
            print(c(pad("Lựa chọn không hợp lệ.", WIDTH, "left"), Fore.RED))
            return envd, 0
        envd = set_current_account_index(envd, idx)
        write_env_file(envd)
        return envd, idx
    elif choice == 2:
        envd, idx = wizard_add_account(envd)
        return envd, idx
    else:
        return envd, 0

# ================================ MAIN MENU =================================

def main_menu() -> int:
    return show_menu(
        ["Login (đăng nhập)", "Logout (đăng xuất)", "Reset (.env trống)", "Exit"],
        title="MAIN"
    )

def render_header():
    title = "TELEGRAM MEDIA DOWNLOADER - CONTROL PANEL"
    lines = [pad("", WIDTH - 2), center(title, WIDTH - 2), pad("", WIDTH - 2)]
    print(c(box(lines), Fore.CYAN))

async def start_downloader_for_account(envd: Dict[str, str], idx: int) -> None:
    acc = get_account(envd, idx)
    try:
        api_id = int(acc["API_ID"])
    except Exception:
        print(c(pad("Lỗi: API_ID không hợp lệ.", WIDTH, "left"), Fore.RED))
        return
    api_hash = acc["API_HASH"]
    phone = acc["PHONE"]
    download_dir = acc["DOWNLOAD_DIR"] or "downloads_saved_videos"

    downloader = TelegramDownloader(api_id, api_hash, phone, download_dir)
    await downloader.run()

async def main():
    if sys.version_info < (3, 7):
        print("Python 3.7+ required")
        sys.exit(1)

    while True:
        render_header()
        envd = ensure_env_loaded_and_migrated()
        cur = get_current_account_index(envd)
        status = f"Current: #{cur}" if cur else "Current: <not logged in>"
        print(c(pad(status, WIDTH, "left"), Fore.YELLOW))
        print(line("-"))

        choice = main_menu()

        if choice == 1:  # LOGIN
            envd, idx = do_login_flow()
            if idx:
                # Bắt đầu downloader với tài khoản đã chọn
                await start_downloader_for_account(envd, idx)
            # Sau khi tải xong, quay về main (không tự logout)

        elif choice == 2:  # LOGOUT
            envd = await do_logout_flow(envd)

        elif choice == 3:  # RESET
            envd = do_reset_flow()

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
