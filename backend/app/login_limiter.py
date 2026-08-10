import threading
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    def __init__(self, attempts: int = 5, window_seconds: int = 300):
        self.attempts = attempts
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            failures = self._failures[key]
            while failures and failures[0] < now - self.window:
                failures.popleft()
            return len(failures) < self.attempts

    def fail(self, key: str) -> None:
        with self._lock:
            self._failures[key].append(time.monotonic())

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = LoginRateLimiter()
