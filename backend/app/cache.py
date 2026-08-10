import threading
import time


class TTLCache:
    def __init__(self, ttl_seconds: float = 30.0, max_items: int = 256):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._items: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            item = self._items.get(key)
            if not item or item[0] <= time.monotonic():
                self._items.pop(key, None)
                return None
            return item[1]

    def set(self, key: str, value):
        with self._lock:
            if len(self._items) >= self.max_items:
                oldest = min(self._items, key=lambda candidate: self._items[candidate][0])
                self._items.pop(oldest, None)
            self._items[key] = (time.monotonic() + self.ttl, value)


dashboard_cache = TTLCache()
analytics_cache = TTLCache(ttl_seconds=60.0, max_items=128)
