import threading
import time
from collections import defaultdict, deque


class Telemetry:
    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._requests = defaultdict(int)
        self._latencies: deque[float] = deque(maxlen=2000)

    def observe_request(self, method: str, path: str, status: int, duration_ms: float) -> None:
        route = path.split("?", 1)[0]
        with self._lock:
            self._requests[(method, route, status)] += 1
            self._latencies.append(duration_ms)

    def snapshot(self) -> dict:
        with self._lock:
            samples = sorted(self._latencies)
            def percentile(fraction: float) -> float:
                if not samples:
                    return 0.0
                return round(samples[min(len(samples) - 1, int(len(samples) * fraction))], 1)
            return {
                "uptime_seconds": int(time.time() - self.started_at),
                "request_count": sum(self._requests.values()),
                "latency_ms": {"p50": percentile(.50), "p95": percentile(.95), "p99": percentile(.99)},
                "responses": [
                    {"method": key[0], "path": key[1], "status": key[2], "count": value}
                    for key, value in sorted(self._requests.items())
                ],
            }


telemetry = Telemetry()
