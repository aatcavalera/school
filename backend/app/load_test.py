import asyncio
import os
import statistics
import time

import httpx


async def main() -> None:
    base_url = os.environ.get("LOAD_TEST_URL", "http://127.0.0.1:8000")
    token = os.environ.get("LOAD_TEST_TOKEN")
    if not token:
        from app.security import create_access_token
        token = create_access_token("admin")
    requests = int(os.environ.get("LOAD_TEST_REQUESTS", "200"))
    concurrency = int(os.environ.get("LOAD_TEST_CONCURRENCY", "20"))
    semaphore = asyncio.Semaphore(concurrency)
    timings: list[float] = []
    statuses: list[int] = []

    async with httpx.AsyncClient(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=10) as client:
        async def one() -> None:
            async with semaphore:
                started = time.perf_counter()
                response = await client.get("/api/analytics")
                timings.append((time.perf_counter() - started) * 1000)
                statuses.append(response.status_code)
        await asyncio.gather(*(one() for _ in range(requests)))
    ordered = sorted(timings)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * .95))]
    print(f"requests={requests} concurrency={concurrency} success={statuses.count(200)} p50_ms={statistics.median(ordered):.1f} p95_ms={p95:.1f} max_ms={max(ordered):.1f}")
    if statuses.count(200) != requests or p95 >= 800:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
