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
        # Regex này kiểm tra:
        # - Bắt đầu bằng '+'
        # - Theo sau là 1-15 chữ số
        # - Không chứa khoảng trắng hoặc các ký tự đặc biệt khác ngoài dấu '+'
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
        # Chỉ kiểm tra nếu nó là một đường dẫn tương đối hoặc tuyệt đối có vẻ hợp lệ
        # và không chứa các ký tự cấm đối với tên thư mục (hệ điều hành không phải là vấn đề ở đây)
        # pathlib.Path sẽ xử lý các đường dẫn không hợp lệ khi tạo folder
        try:
            path = Path(path_str)
            # Kiểm tra nếu đường dẫn có thể được tạo (mà không thực sự tạo nó)
            # hoặc nếu nó đã tồn tại và là một thư mục
            return not (path.is_file()) # Không nên là một file
        except Exception:
            return False

    @staticmethod
    def is_valid_peer_identifier(identifier: Union[int, str]) -> bool:
        """
        Kiểm tra xem một định danh peer (chat ID, username, phone number) có hợp lệ không.
        """
        if isinstance(identifier, int):
            return identifier > 0 # ID chat/user thường là số dương
        elif isinstance(identifier, str):
            identifier = identifier.strip()
            if not identifier:
                return False
            # Có thể là @username, ID số dưới dạng chuỗi, hoặc +phone
            if identifier.startswith('@'):
                return bool(re.fullmatch(r'^@[a-zA-Z0-9_]{5,32}$', identifier)) # Username Telegram min 5, max 32
            elif identifier.startswith('+'):
                return InputValidator.is_valid_phone(identifier)
            else:
                # Có thể là ID số dạng chuỗi, hoặc tên chat
                # Để đơn giản, coi chuỗi không bắt đầu bằng @ hoặc + là hợp lệ
                # (sẽ được Telethon giải quyết)
                try:
                    int(identifier)
                    return True # Là một ID số dạng chuỗi
                except ValueError:
                    return True # Là một tên chat/kênh
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
        # Sắp xếp để hash ổn định, tránh lệch thứ tự
        b = ",".join(str(i) for i in sorted(set(int(x) for x in ids))).encode("utf-8")
        return hashlib.sha256(b).hexdigest()
