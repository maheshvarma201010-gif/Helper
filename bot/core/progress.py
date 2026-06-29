import time
from typing import Optional

class ProgressTracker:
    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = time.time()
        self.last_update_time = 0

    def increment_success(self):
        self.current += 1
        self.success += 1

    def increment_failed(self):
        self.current += 1
        self.failed += 1

    def increment_skipped(self):
        self.current += 1
        self.skipped += 1

    def get_progress_bar(self, length: int = 15) -> str:
        percent = (self.current / self.total) * 100 if self.total > 0 else 0
        filled_length = int(length * self.current // self.total) if self.total > 0 else 0
        bar = '█' * filled_length + '░' * (length - filled_length)
        return f"[{bar}] {percent:.1f}%"

    def get_eta(self) -> str:
        elapsed_time = time.time() - self.start_time
        if self.current == 0:
            return "Calculating..."

        speed = self.current / elapsed_time # messages per second
        remaining = self.total - self.current
        eta_seconds = remaining / speed if speed > 0 else 0

        return self._format_time(eta_seconds)

    def get_speed(self) -> str:
        elapsed_time = time.time() - self.start_time
        if elapsed_time == 0:
            return "0 msg/s"
        speed = self.current / elapsed_time
        return f"{speed:.2f} msg/s"

    def _format_time(self, seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"

    def should_update(self, interval: int = 5) -> bool:
        now = time.time()
        if now - self.last_update_time >= interval:
            self.last_update_time = now
            return True
        return False
