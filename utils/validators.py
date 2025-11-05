# tele-downloader-toolkit/utils/validators.py

import re
import hashlib
from typing import List, Optional, Union
from pathlib import Path


class InputValidator:
    """
    Cung cấp các hàm tiện ích để xác thực đầu vào phổ biến.
    """

    @staticmethod
    def is_valid_phone(phone_number: str) -> bool:
        """
        Kiểm tra xem số điện thoại có phải là định dạng hợp lệ của Telegram không.
        Telegram thường yêu cầu định dạng quốc tế (ví dụ: +84123456789).
        """
        if not phone_number:
            return False
        return bool(re.fullmatch(r'^\+[1-9]\d{1,14}$', phone_number))

    @staticmethod
    def is_valid_api_id(api_id_str: str) -> bool:
        """
        Kiểm tra xem chuỗi API ID có phải là một số nguyên dương không.
        """
        if not api_id_str:
            return False
        try:
            api_id = int(api_id_str)
            return api_id > 0
        except ValueError:
            return False

    @staticmethod
    def is_valid_api_hash(api_hash: str) -> bool:
        """
        Kiểm tra xem API Hash có phải là một chuỗi hex dài 32 ký tự không.
        (Telethon API Hash có độ dài 32 ký tự, tất cả là hex)
        """
        if not api_hash:
            return False
        return bool(re.fullmatch(r'^[0-9a-fA-F]{32}$', api_hash))

    @staticmethod
    def is_valid_download_dir(path_str: str) -> bool:
        """
        Kiểm tra xem đường dẫn thư mục có hợp lệ để tạo/ghi không.
        Đây là một kiểm tra cơ bản. Kiểm tra quyền ghi thực tế nên được thực hiện
        tại thời điểm chạy ứng dụng.
        """
        if not path_str:
            return False
        try:
            path = Path(path_str)
            return not (path.is_file())
        except Exception:
            return False

    @staticmethod
    def is_valid_peer_identifier(identifier: Union[int, str]) -> bool:
        """
        Kiểm tra xem một định danh peer (chat ID, username, phone number) có hợp lệ không.
        """
        if isinstance(identifier, int):
            return identifier != 0
        elif isinstance(identifier, str):
            identifier = identifier.strip()
            if not identifier:
                return False
            if identifier.startswith('@'):
                return bool(re.fullmatch(r'^@[a-zA-Z0-9_]{5,32}$', identifier))
            elif identifier.startswith('+'):
                return InputValidator.is_valid_phone(identifier)
            else:
                try:
                    int(identifier)
                    return True
                except ValueError:
                    return True
        return False


class HashingUtilities:
    """
    Cung cấp các hàm tiện ích liên quan đến hashing.
    """

    @staticmethod
    def hash_message_ids(ids: List[int]) -> str:
        """
        Tạo một hash SHA256 ổn định từ một danh sách các ID tin nhắn.
        Danh sách được sắp xếp trước để đảm bảo tính nhất quán của hash.
        """
        b = ",".join(str(i) for i in sorted(set(int(x) for x in ids))).encode("utf-8")
        return hashlib.sha256(b).hexdigest()




### File: `tele-downloader-toolkit/cli_app.py`

# !/usr/bin/env python3
import sys
from pathlib import Path
import asyncio

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from ui.cli.commands import cli_main_entry  # Import the main CLI entry point

if __name__ == "__main__":
    # The cli_main_entry function now handles its own asyncio.run call
    cli_main_entry()
