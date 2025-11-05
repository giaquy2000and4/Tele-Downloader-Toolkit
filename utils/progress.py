# tele-downloader-toolkit/utils/progress.py

import sys
import asyncio
import humanize
import time
from typing import Dict, Any, Optional, Callable, Coroutine

ProgressCallback = Callable[[float, int, int, Dict[str, Any]], None]


class ProgressTracker:
    """
    A generic class to track progress for long-running operations.
    It can be configured with a callback to report updates to a UI.
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
        self._min_report_interval = 0.1

        self.stats: Dict[str, Any] = {
            'description': self._description,
            'total_found': total_items,
            'processed': 0,
            'skipped': 0,
            'errors': 0,
            'total_size_bytes': 0,
            'start_time': None,
            'end_time': None,
            'elapsed_time': 0,
            'average_speed_bps': 0
        }

    def start(self, total_items: Optional[int] = None):
        """Starts or resets the progress tracking."""
        self._start_time = time.time()
        self._last_report_time = self._start_time
        self._current_items_processed = 0
        self._total_items = total_items if total_items is not None else self._total_items

        self.stats = {
            'description': self._description,
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
        """Sets or updates the total number of items to process."""
        self._total_items = total
        self.stats['total_found'] = total
        self._report_progress()

    def item_processed(self, increment: int = 1, item_size_bytes: int = 0, status: str = "processed", **kwargs):
        """
        Registers that an item has been processed.
        status: "processed", "skipped", "error"
        **kwargs: Any additional stats to update (e.g., 'images_found', 'videos_found').
        """
        self._current_items_processed += increment

        if status == "processed":
            self.stats['processed'] += increment
            self.stats['total_size_bytes'] += item_size_bytes
        elif status == "skipped":
            self.stats['skipped'] += increment
        elif status == "error":
            self.stats['errors'] += increment

        for key, value in kwargs.items():
            if key in self.stats:
                self.stats[key] += value
            else:
                self.stats[key] = value

        self._report_progress()

    def _report_progress(self, force: bool = False):
        """
        Calls the progress callback if enough time has passed or if forced.
        Calculates percentage, elapsed time, and average speed.
        """
        current_time = time.time()
        if not force and self._last_report_time and (current_time - self._last_report_time < self._min_report_interval):
            return

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

        self._progress_callback(
            progress_percent,
            self._current_items_processed,
            self._total_items,
            self.stats.copy()
        )

    def complete(self):
        """Marks the operation as complete."""
        self.stats['end_time'] = time.time()
        self.stats['elapsed_time'] = self.stats['end_time'] - (self._start_time or self.stats['end_time'])
        self._report_progress(force=True)

    def get_progress_string(self) -> str:
        """Returns a formatted string of current progress."""
        progress_percent = 0.0
        if self._total_items > 0:
            progress_percent = self._current_items_processed / self._total_items

        return (f"{self._description}: {self._current_items_processed}/{self._total_items} "
                f"({progress_percent:.1%}) - {humanize.naturalsize(self.stats['total_size_bytes'])} "
                f"({humanize.naturaldelta(self.stats['elapsed_time'])})")

    def get_final_summary(self) -> Dict[str, Any]:
        """Returns a summary of the completed operation."""
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


def _cli_dummy_callback(progress: float, current: int, total: int, stats: Dict[str, Any]):
    bar_length = 30
    filled_length = int(bar_length * progress)
    bar = '#' * filled_length + '-' * (bar_length - filled_length)

    message_content = (f"{stats['description']}: |{bar}| {progress:.1%} {current}/{total} "
                       f"Size: {humanize.naturalsize(stats['total_size_bytes'])} "
                       f"Elapsed: {humanize.naturaldelta(stats['elapsed_time'])}")
    sys.stdout.write("\r" + message_content)
    sys.stdout.flush()
    if progress >= 1.0:
        sys.stdout.write('\n')


async def _simulate_work(tracker: ProgressTracker, total: int):
    tracker.start(total_items=total)
    for i in range(total):
        if i % 5 == 0:
            item_size = 1024 * (i + 1)
            tracker.item_processed(item_size_bytes=item_size)
        else:
            tracker.item_processed(status="skipped")
        await asyncio.sleep(0.05)
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

