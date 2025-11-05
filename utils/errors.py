# tele-downloader-toolkit/utils/errors.py

class TelegramToolkitError(Exception):
    """Lớp cơ sở cho tất cả các lỗi tùy chỉnh trong Telegram Toolkit."""
    pass

class AccountConfigError(TelegramToolkitError):
    """Lỗi xảy ra khi cấu hình tài khoản không hợp lệ hoặc thiếu."""
    def __init__(self, message: str = "Account configuration is incomplete or invalid."):
        super().__init__(message)

class AuthError(TelegramToolkitError):
    """Lỗi liên quan đến quá trình xác thực Telegram (OTP, 2FA, v.v.)."""
    def __init__(self, message: str = "Telegram authentication failed."):
        super().__init__(message)

class ConnectionError(TelegramToolkitError):
    """Lỗi xảy ra khi không thể kết nối với máy chủ Telegram."""
    def __init__(self, message: str = "Could not connect to Telegram servers."):
        super().__init__(message)

class DownloadError(TelegramToolkitError):
    """Lỗi xảy ra trong quá trình tải xuống media."""
    def __init__(self, message: str = "Media download failed."):
        super().__init__(message)

class DownloadCancelledError(DownloadError):
    """Lỗi chỉ ra rằng quá trình tải xuống đã bị hủy bởi người dùng."""
    def __init__(self, message: str = "Media download was cancelled by the user."):
        super().__init__(message)

class UploadError(TelegramToolkitError):
    """Lỗi xảy ra trong quá trình tải lên media."""
    def __init__(self, message: str = "Media upload failed."):
        super().__init__(message)

class UploadCancelledError(UploadError):
    """Lỗi chỉ ra rằng quá trình tải lên đã bị hủy bởi người dùng."""
    def __init__(self, message: str = "Media upload was cancelled by the user."):
        super().__init__(message)

class MediaNotFoundError(TelegramToolkitError):
    """Lỗi xảy ra khi không tìm thấy media theo các tiêu chí đã cho."""
    def __init__(self, message: str = "No media found matching the criteria."):
        super().__init__(message)

class InvalidInputError(TelegramToolkitError):
    """Lỗi xảy ra khi dữ liệu đầu vào không hợp lệ."""
    def __init__(self, message: str = "Invalid input provided."):
        super().__init__(message)
