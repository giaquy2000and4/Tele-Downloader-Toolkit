# tele-downloader-toolkit/utils/progress.py

import sys  # Đã thêm import sys
import asyncio  # Đã thêm import asyncio
import humanize
import time
from typing import Dict, Any, Optional, Callable, Coroutine  # Coroutine cần thiết cho type hinting async funcs

# Một kiểu callable cho các cập nhật tiến độ
# (progress_percentage, current_value, total_value, extra_info_dict)
ProgressCallback = Callable[[float, int, int, Dict[str, Any]], None]


class ProgressTracker:
    """
    Một lớp chung để theo dõi tiến độ cho các hoạt động chạy dài.
    Nó có thể được cấu hình với một callback để báo cáo cập nhật cho một UI.
    """

    def __init__(self,
                 total_items: int = 0,
                 description: str = "Operation",
                 progress_callback: Optional[ProgressCallback] = None):

        self._total_items = total_items
        self._current_items_processed = 0
        self._description = description
        self._progress_callback = progress_callback
        self._start_time: Optional[float] = None
        self._last_report_time: Optional[float] = None
        self._min_report_interval = 0.1  # Khoảng thời gian tối thiểu giữa các lần gọi callback (giây)

        # Các số liệu thống kê chung có thể được theo dõi, tương tự như MediaDownloader sử dụng
        self.stats: Dict[str, Any] = {
            'description': self._description,  # Thêm mô tả vào stats
            'total_found': total_items,
            'processed': 0,
            'skipped': 0,
            'errors': 0,
            'total_size_bytes': 0,
            'start_time': None,
            'end_time': None,
            'elapsed_time': 0,
            'average_speed_bps': 0  # bytes mỗi giây
        }

    def start(self, total_items: Optional[int] = None):
        """Bắt đầu hoặc đặt lại theo dõi tiến độ."""
        self._start_time = time.time()
        self._last_report_time = self._start_time
        self._current_items_processed = 0
        self._total_items = total_items if total_items is not None else self._total_items

        self.stats = {
            'description': self._description,  # Đảm bảo mô tả được giữ lại
            'total_found': self._total_items,
            'processed': 0,
            'skipped': 0,
            'errors': 0,
            'total_size_bytes': 0,
            'start_time': self._start_time,
            'end_time': None,
            'elapsed_time': 0,
            'average_speed_bps': 0
        }
        self._report_progress(force=True)

    def set_total_items(self, total: int):
        """Đặt hoặc cập nhật tổng số mục cần xử lý."""
        self._total_items = total
        self.stats['total_found'] = total
        self._report_progress()

    def item_processed(self, increment: int = 1, item_size_bytes: int = 0, status: str = "processed", **kwargs):
        """
        Đăng ký một mục đã được xử lý.
        status: "processed", "skipped", "error"
        **kwargs: Bất kỳ số liệu thống kê bổ sung nào cần cập nhật (ví dụ: 'images_found', 'videos_found').
        """
        self._current_items_processed += increment

        if status == "processed":
            self.stats['processed'] += increment
            self.stats['total_size_bytes'] += item_size_bytes
        elif status == "skipped":
            self.stats['skipped'] += increment
        elif status == "error":
            self.stats['errors'] += increment

        # Cập nhật các số liệu thống kê bổ sung
        for key, value in kwargs.items():
            if key in self.stats:
                self.stats[key] += value
            else:
                self.stats[key] = value  # Thêm số liệu thống kê mới nếu chưa tồn tại

        self._report_progress()

    def _report_progress(self, force: bool = False):
        """
        Gọi callback tiến độ nếu đủ thời gian đã trôi qua hoặc nếu được yêu cầu.
        Tính toán phần trăm, thời gian đã trôi qua và tốc độ trung bình.
        """
        current_time = time.time()
        if not force and self._last_report_time and (current_time - self._last_report_time < self._min_report_interval):
            return  # Không báo cáo quá thường xuyên

        if self._progress_callback is None:
            return

        progress_percent = 0.0
        if self._total_items > 0:
            progress_percent = self._current_items_processed / self._total_items

        elapsed = current_time - (self._start_time or current_time)
        self.stats['elapsed_time'] = elapsed

        avg_speed = 0
        if elapsed > 0 and self.stats['total_size_bytes'] > 0:
            avg_speed = self.stats['total_size_bytes'] / elapsed
        self.stats['average_speed_bps'] = avg_speed

        self._last_report_time = current_time

        # Gọi callback với dữ liệu đã tính toán
        self._progress_callback(
            progress_percent,
            self._current_items_processed,
            self._total_items,
            self.stats.copy()  # Truyền một bản sao để ngăn chặn sửa đổi bên ngoài
        )

    def complete(self):
        """Đánh dấu hoạt động đã hoàn thành."""
        self.stats['end_time'] = time.time()
        self.stats['elapsed_time'] = self.stats['end_time'] - (self._start_time or self.stats['end_time'])
        self._report_progress(force=True)  # Đảm bảo báo cáo cuối cùng

    # --- Các phương thức tiện ích để hiển thị tiến độ chung ---
    def get_progress_string(self) -> str:
        """Trả về một chuỗi được định dạng của tiến độ hiện tại."""
        progress_percent = 0.0
        if self._total_items > 0:
            progress_percent = self._current_items_processed / self._total_items

        return (f"{self._description}: {self._current_items_processed}/{self._total_items} "
                f"({progress_percent:.1%}) - {humanize.naturalsize(self.stats['total_size_bytes'])} "
                f"({humanize.naturaldelta(self.stats['elapsed_time'])})")

    def get_final_summary(self) -> Dict[str, Any]:
        """Trả về một bản tóm tắt của hoạt động đã hoàn thành."""
        return {
            "description": self._description,
            "total_items": self._total_items,
            "processed": self.stats['processed'],
            "skipped": self.stats['skipped'],
            "errors": self.stats['errors'],
            "total_size": humanize.naturalsize(self.stats['total_size_bytes']),
            "elapsed_time": humanize.naturaldelta(self.stats['elapsed_time']),
            "average_speed": f"{humanize.naturalsize(self.stats['average_speed_bps'])}/s" if self.stats[
                                                                                                 'average_speed_bps'] > 0 else "N/A"
        }


# Ví dụ sử dụng với một callback kiểu CLI dummy
def _cli_dummy_callback(progress: float, current: int, total: int, stats: Dict[str, Any]):
    bar_length = 30
    filled_length = int(bar_length * progress)
    bar = '#' * filled_length + '-' * (bar_length - filled_length)

    # Đảm bảo không có \r trong f-string
    message_content = (f"{stats['description']}: |{bar}| {progress:.1%} {current}/{total} "
                       f"Size: {humanize.naturalsize(stats['total_size_bytes'])} "
                       f"Elapsed: {humanize.naturaldelta(stats['elapsed_time'])}")
    sys.stdout.write("\r" + message_content)  # Đã tách \r ra khỏi f-string
    sys.stdout.flush()
    if progress >= 1.0:
        sys.stdout.write('\n')


async def _simulate_work(tracker: ProgressTracker, total: int):
    tracker.start(total_items=total)
    for i in range(total):
        if i % 5 == 0:
            item_size = 1024 * (i + 1)  # Mô phỏng các kích thước mục khác nhau
            tracker.item_processed(item_size_bytes=item_size)
        else:
            tracker.item_processed(status="skipped")
        await asyncio.sleep(0.05)  # Mô phỏng một số công việc bất đồng bộ
    tracker.complete()


def _test_progress_tracker_cli():
    print("--- CLI Progress Tracker Test ---")
    tracker = ProgressTracker(description="Downloading Files", progress_callback=_cli_dummy_callback)

    asyncio.run(_simulate_work(tracker, 100))

    print("\n--- Summary ---")
    summary = tracker.get_final_summary()
    for k, v in summary.items():
        print(f"{k.replace('_', ' ').capitalize()}: {v}")


if __name__ == "__main__":
    _test_progress_tracker_cli()