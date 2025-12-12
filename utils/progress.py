import humanize
import time


class ProgressTracker:
    def __init__(self, update_ui_func):
        self.update_ui_func = update_ui_func
        self.last_update = time.time()

    async def callback(self, current, total):
        now = time.time()
        # Cập nhật mỗi 0.5 giây để tránh lag UI
        if now - self.last_update > 0.5 or current == total:
            percentage = (current / total)
            readable_current = humanize.naturalsize(current)
            readable_total = humanize.naturalsize(total)
            msg = f"{readable_current} / {readable_total}"

            # Gọi hàm cập nhật UI
            if self.update_ui_func:
                self.update_ui_func(percentage, msg)

            self.last_update = now