#!/usr/bin/env python3
# Nâng cấp từ bản gốc: tự kiểm tra / tạo .env và cho phép chọn vị trí + tên thư mục tải xuống
# Source gốc: Telegram Saved Messages Media Downloader  :contentReference[oaicite:0]{index=0}
"""
Telegram Saved Messages Media Downloader (Console-UI Fixed Width)
- Đọc cấu hình từ .env (tự kiểm tra, nếu thiếu sẽ hỏi và tự tạo .env)
- Cho phép người dùng CHỌN tên folder và NƠI LƯU folder đó -> lưu vào DOWNLOAD_DIR trong .env
- Quét Saved Messages, chọn tải Ảnh / Video / Cả hai
- Ảnh -> <DOWNLOAD_DIR>/PIC ; Video -> <DOWNLOAD_DIR>/VID
- Giao diện console cố định bề ngang, căn dòng gọn gàng, không icon
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ===================== TÙY CHỈNH GIAO DIỆN =====================
WIDTH = 80               # Độ rộng cố định cho toàn bộ giao diện
USE_COLOR = True         # Đổi sang False nếu muốn tắt màu
BAR_CHAR = "="           # Ký tự đường kẻ
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

# Init color
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
        # đảm bảo mỗi dòng dài chính xác WIDTH-2
        s = pad(ln, WIDTH - 2, "left")
        body.append("│" + s + "│")
    return "\n".join([top] + body + [bottom])

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

    # ---------------- UI ----------------
    def print_banner(self):
        title = "TELEGRAM MEDIA DOWNLOADER"
        lines = [
            pad("", WIDTH - 2),
            center(title, WIDTH - 2),
            pad("", WIDTH - 2),
        ]
        print(c(box(lines), Fore.CYAN))

        info_lines = [
            f"Phone: {self.phone}",
            f"Download Directory: {self.download_dir.absolute()}",
            f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        print(c(box(info_lines), Fore.MAGENTA))
        print(line("-"))

    def print_stats(self):
        # Bảng thống kê căn cột cố định
        # COLS: LABEL(20) | VALUE(10) | SPACER | SIZE(remaining for readability)
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
        """
        Dòng thông tin file cố định độ rộng:
        TYPE(6) | FILENAME(57) | SIZE(15)  => tổng 6 + 1 + 57 + 1 + 15 = 80
        """
        type_col = pad(file_type.upper(), 6)
        name_col = pad(filename, 57, "left")
        size_col = pad(humanize.naturalsize(size) if size else "-", 15, "right")
        print(f"{type_col}|{name_col}|{size_col}")

    def prompt_download_choice(self) -> str:
        # Cố định khung hỏi lựa chọn
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

    # ------------- LOGIC -------------
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
            ncols=WIDTH,           # cố định chiều rộng
            ascii=True,            # dùng ascii để ổn định layout
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

            # In dòng thông tin (trước hành động)
            self.print_fixed_row(file_type, filename, file_size)

            if file_path.exists():
                self.stats['skipped'] += 1
                # In thêm trạng thái ở dòng kế tiếp nhưng vẫn giữ width
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
                # khoảng trắng ngăn cách từng mục, vẫn đúng WIDTH
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


# ============= NÂNG CẤP: TỰ KIỂM TRA / TẠO .env + CHỌN THƯ MỤC =============

ENV_TEMPLATE_HINT = [
    "Nếu bạn bỏ trống, sẽ dùng giá trị mặc định trong ngoặc vuông [].",
    "Ví dụ file .env sẽ như sau:",
    "TELEGRAM_API_ID=20431364",
    "TELEGRAM_API_HASH=9ac968fa4e5a1b4bfe086560ce8e94c6",
    "TELEGRAM_PHONE=+84901572620",
    "DOWNLOAD_DIR=downloads_saved_videos",
]

def print_env_wizard_header():
    lines = [
        pad("ENV SETUP WIZARD - Thiết lập cấu hình .env", WIDTH - 2),
        pad("Chương trình chưa tìm thấy đủ cấu hình. Hãy nhập thông tin bên dưới.", WIDTH - 2),
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
    # Hỏi nơi lưu và tên thư mục, vẫn giữ UI console gọn gàng
    lines = [
        pad("Chọn NƠI LƯU và TÊN FOLDER tải xuống", WIDTH - 2),
        pad(f"Thư mục mặc định: ./{default_dir}", WIDTH - 2),
        pad("Bạn có thể nhập đường dẫn TỔNG (ví dụ: D:/Media) và tên folder (ví dụ: MyTG).", WIDTH - 2),
        pad("Kết quả sẽ là: <đường dẫn tổng>/<tên folder>", WIDTH - 2),
    ]
    print(c(box(lines), Fore.CYAN))

    base_path = _ask_input("Nhập đường dẫn tổng (mặc định là thư mục hiện tại)", default=str(Path.cwd()))
    folder_name = _ask_input("Nhập tên folder lưu file", default=default_dir)

    # Chuẩn hoá đường dẫn
    try:
        base_path = Path(base_path).expanduser().resolve()
    except Exception:
        base_path = Path.cwd().resolve()

    final_path = (base_path / folder_name).as_posix()
    confirm_lines = [
        pad("DOWNLOAD DIR được đặt là:", WIDTH - 2),
        pad(final_path, WIDTH - 2),
    ]
    print(c(box(confirm_lines), Fore.GREEN))
    return final_path


def _write_env_file(path: Path, data: Dict[str, str]) -> None:
    # Ghi đầy đủ các khoá cần thiết (ghi đè nếu đã tồn tại)
    content = [
        f"TELEGRAM_API_ID={data['TELEGRAM_API_ID']}",
        f"TELEGRAM_API_HASH={data['TELEGRAM_API_HASH']}",
        f"TELEGRAM_PHONE={data['TELEGRAM_PHONE']}",
        f"DOWNLOAD_DIR={data['DOWNLOAD_DIR']}",
        "",
    ]
    path.write_text("\n".join(content), encoding="utf-8")


def _ensure_env() -> None:
    """
    - Kiểm tra sự tồn tại của .env
    - Nếu chưa có HOẶC thiếu biến, mở wizard hỏi thông tin và tạo/ghi .env
    - Vẫn giữ nguyên cấu trúc chương trình, chỉ bổ sung bước trước khi load cấu hình
    """
    env_path = Path(".env")
    # Đọc trước (nếu có)
    load_dotenv(override=False)

    existing = {
        "TELEGRAM_API_ID": os.getenv("TELEGRAM_API_ID", "").strip(),
        "TELEGRAM_API_HASH": os.getenv("TELEGRAM_API_HASH", "").strip(),
        "TELEGRAM_PHONE": os.getenv("TELEGRAM_PHONE", "").strip(),
        "DOWNLOAD_DIR": os.getenv("DOWNLOAD_DIR", "").strip(),
    }

    need_wizard = (not env_path.exists()) or (not all(existing.values()))

    if need_wizard:
        print_env_wizard_header()

        # Hỏi các trường còn thiếu / hoặc hỏi lại để chắc chắn
        while True:
            api_id_str = _ask_input("TELEGRAM_API_ID (số nguyên)", default=existing["TELEGRAM_API_ID"] or "")
            if not api_id_str.isdigit():
                print(c(pad("Lỗi: TELEGRAM_API_ID phải là số nguyên.", WIDTH, "left"), Fore.RED))
                continue
            break

        api_hash = _ask_input("TELEGRAM_API_HASH", default=existing["TELEGRAM_API_HASH"] or "")
        while not api_hash:
            print(c(pad("Lỗi: TELEGRAM_API_HASH không được rỗng.", WIDTH, "left"), Fore.RED))
            api_hash = _ask_input("TELEGRAM_API_HASH", default="")

        phone = _ask_input("TELEGRAM_PHONE", default=existing["TELEGRAM_PHONE"] or "")
        while not phone:
            print(c(pad("Lỗi: TELEGRAM_PHONE không được rỗng.", WIDTH, "left"), Fore.RED))
            phone = _ask_input("TELEGRAM_PHONE", default="")

        # Cho phép chọn nơi lưu + tên folder
        download_dir = _choose_download_dir(default_dir=existing["DOWNLOAD_DIR"] or "downloads_saved_videos")

        env_data = {
            "TELEGRAM_API_ID": api_id_str,
            "TELEGRAM_API_HASH": api_hash,
            "TELEGRAM_PHONE": phone,
            "DOWNLOAD_DIR": download_dir,
        }

        # Ghi file .env (tự tạo nếu chưa có)
        try:
            _write_env_file(env_path, env_data)
            note_lines = [
                pad(".env đã được tạo/cập nhật thành công với nội dung:", WIDTH - 2),
                pad(f"TELEGRAM_API_ID={env_data['TELEGRAM_API_ID']}", WIDTH - 2),
                pad(f"TELEGRAM_API_HASH={env_data['TELEGRAM_API_HASH']}", WIDTH - 2),
                pad(f"TELEGRAM_PHONE={env_data['TELEGRAM_PHONE']}", WIDTH - 2),
                pad(f"DOWNLOAD_DIR={env_data['DOWNLOAD_DIR']}", WIDTH - 2),
            ]
            print(c(box(note_lines), Fore.GREEN))
        except Exception as e:
            print(c(pad(f"Lỗi khi ghi .env: {e}", WIDTH, "left"), Fore.RED))
            sys.exit(1)

        # Nạp lại biến môi trường từ file vừa ghi
        load_dotenv(override=True)
    else:
        # Có đủ rồi -> thông báo ngắn gọn (giữ giao diện)
        info_lines = [
            pad(".env đã sẵn sàng. Dùng cấu hình hiện tại.", WIDTH - 2),
            pad(f"DOWNLOAD_DIR={existing['DOWNLOAD_DIR'] or 'downloads_saved_videos'}", WIDTH - 2),
        ]
        print(c(box(info_lines), Fore.CYAN))


def load_config_from_env() -> Tuple[int, str, str, str]:
    # Đảm bảo .env tồn tại/đủ biến; nếu thiếu thì mở wizard và tạo file
    _ensure_env()

    # Sau khi chắc chắn có .env, đọc biến
    load_dotenv(override=False)

    api_id_str = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    phone = os.getenv("TELEGRAM_PHONE", "").strip()
    download_dir = os.getenv("DOWNLOAD_DIR", "downloads_saved_videos").strip()

    # Chốt kiểm tra
    missing = []
    if not api_id_str:
        missing.append("TELEGRAM_API_ID")
    if not api_hash:
        missing.append("TELEGRAM_API_HASH")
    if not phone:
        missing.append("TELEGRAM_PHONE")

    if missing:
        print(c(pad(f"Missing .env config: {', '.join(missing)}", WIDTH, "left"), Fore.RED))
        sys.exit(1)

    try:
        api_id = int(api_id_str)
    except ValueError:
        print(c(pad("TELEGRAM_API_ID must be integer.", WIDTH, "left"), Fore.RED))
        sys.exit(1)

    return api_id, api_hash, phone, download_dir


async def main():
    api_id, api_hash, phone, download_dir = load_config_from_env()
    downloader = TelegramDownloader(api_id, api_hash, phone, download_dir)
    success = await downloader.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    if sys.version_info < (3, 7):
        print("Python 3.7+ required")
        sys.exit(1)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Goodbye.")
    except Exception as e:
        print(f"Fatal: {e}")
        sys.exit(1)
