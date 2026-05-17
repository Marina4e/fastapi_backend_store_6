from __future__ import annotations

import argparse
import asyncio
import time
from collections import Counter
from dataclasses import dataclass, field

import httpx


@dataclass
class Result:
    scheduled: int = 0
    sent: int = 0
    success: int = 0
    conflict: int = 0
    dropped: int = 0
    timed_out: int = 0
    errors: int = 0
    interrupted: bool = False
    latencies_ms: list[float] = field(default_factory=list)
    status_codes: Counter[int] = field(default_factory=Counter)
    error_types: Counter[str] = field(default_factory=Counter)

    @property
    def completed(self) -> int:
        return self.success + self.conflict + self.timed_out + self.errors

    @property
    def failed(self) -> int:
        return self.conflict + self.timed_out + self.errors


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((percent / 100) * (len(ordered) - 1)))
    return ordered[index]


async def worker(
    client: httpx.AsyncClient,
    queue: asyncio.Queue[dict | None],
    result: Result,
) -> None:
    while True:
        payload = await queue.get()
        if payload is None:
            queue.task_done()
            return

        result.sent += 1
        started_at = time.perf_counter()
        try:
            response = await client.post("/purchase", json=payload)
            latency_ms = (time.perf_counter() - started_at) * 1000
            result.latencies_ms.append(latency_ms)
            result.status_codes[response.status_code] += 1

            if response.status_code == 200:
                result.success += 1
            elif response.status_code == 409:
                result.conflict += 1
            else:
                result.errors += 1
        except asyncio.CancelledError:
            raise
        except httpx.TimeoutException as exc:
            result.timed_out += 1
            result.error_types[type(exc).__name__] += 1
        except httpx.HTTPError as exc:
            result.errors += 1
            result.error_types[type(exc).__name__] += 1
        finally:
            queue.task_done()


def print_summary(args: argparse.Namespace, result: Result, elapsed: float) -> None:
    target_total = int(args.rps * args.duration)
    actual_rps = result.completed / elapsed if elapsed else 0.0
    sent_rps = result.sent / elapsed if elapsed else 0.0
    success_rps = result.success / elapsed if elapsed else 0.0
    avg_latency = sum(result.latencies_ms) / len(result.latencies_ms) if result.latencies_ms else 0.0
    p95_latency = percentile(result.latencies_ms, 95)
    error_rate = (result.failed / result.completed * 100) if result.completed else 0.0
    drop_rate = (result.dropped / result.scheduled * 100) if result.scheduled else 0.0

    print()
    print("Load test summary")
    print("=" * 56)
    print(f"Status:                  {'INTERRUPTED BY USER' if result.interrupted else 'FINISHED'}")
    print(f"Base URL:                {args.base_url}")
    print(f"Endpoint:                POST /purchase")
    print(f"Product ID:              {args.product_id}")
    print(f"Purchased count:         {args.purchased_count}")
    print("-" * 56)
    print(f"Target RPS:              {args.rps:.2f}")
    print(f"Requested duration:      {args.duration:.2f}s")
    print(f"Real duration:           {elapsed:.2f}s")
    print(f"Target requests:         {target_total}")
    print(f"Scheduled requests:      {result.scheduled}")
    print(f"Sent to API:             {result.sent}")
    print(f"Completed requests:      {result.completed}")
    print(f"Dropped by tester:       {result.dropped} ({drop_rate:.2f}%)")
    print("-" * 56)
    print(f"Successful purchases:    {result.success}")
    print(f"Stock conflicts 409:     {result.conflict}")
    print(f"Timeouts:                {result.timed_out}")
    print(f"Other errors:            {result.errors}")
    print(f"Error rate:              {error_rate:.2f}%")
    print("-" * 56)
    print(f"Actual RPS:              {actual_rps:.2f}")
    print(f"Sent RPS:                {sent_rps:.2f}")
    print(f"Success RPS:             {success_rps:.2f}")
    print(f"Average latency:         {avg_latency:.2f} ms")
    print(f"P95 latency:             {p95_latency:.2f} ms")

    if result.status_codes:
        print("-" * 56)
        print("HTTP status codes:")
        for status_code, count in sorted(result.status_codes.items()):
            print(f"  {status_code}: {count}")

    if result.error_types:
        print("-" * 56)
        print("Client error types:")
        for error_type, count in sorted(result.error_types.items()):
            print(f"  {error_type}: {count}")

    print("-" * 56)
    if result.conflict:
        print("Note: 409 Conflict is expected when stock is not enough.")
    if result.dropped:
        print("Note: dropped requests mean the tester could not feed the target RPS.")
    if result.timed_out:
        print("Note: timeouts usually mean the API/DB/PC could not answer within --timeout.")
    if result.interrupted:
        print("Note: test was stopped with Ctrl+C, so numbers are partial.")


async def run_load_test(args: argparse.Namespace) -> None:
    result = Result()
    queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=args.queue_size)
    timeout = httpx.Timeout(args.timeout, connect=args.connect_timeout)
    limits = httpx.Limits(
        max_connections=args.concurrency,
        max_keepalive_connections=args.concurrency,
    )
    started_at = 0.0
    workers: list[asyncio.Task] = []

    try:
        async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout, limits=limits) as client:
            workers = [asyncio.create_task(worker(client, queue, result)) for _ in range(args.concurrency)]
            started_at = time.perf_counter()
            request_id = 0
            interval = 1 / args.rps
            next_request_at = started_at
            stop_at = started_at + args.duration

            print(f"Starting load test: {args.rps} RPS for {args.duration}s, concurrency={args.concurrency}")
            print("Press Ctrl+C once to stop and print a partial summary.")

            while time.perf_counter() < stop_at:
                now = time.perf_counter()
                if now < next_request_at:
                    await asyncio.sleep(next_request_at - now)

                request_id += 1
                result.scheduled += 1
                payload = {
                    "user_id": request_id,
                    "product_id": args.product_id,
                    "purchased_count": args.purchased_count,
                }

                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    result.dropped += 1

                next_request_at += interval

            try:
                await asyncio.wait_for(queue.join(), timeout=args.drain_timeout)
            except asyncio.TimeoutError:
                result.dropped += queue.qsize()
    except KeyboardInterrupt:
        result.interrupted = True
    except asyncio.CancelledError:
        result.interrupted = True
    finally:
        for task in workers:
            task.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        elapsed = time.perf_counter() - started_at if started_at else 0.0
        print_summary(args, result, elapsed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded async load test for /purchase endpoint.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--rps", type=int, default=500)
    parser.add_argument("--duration", type=float, default=15)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--queue-size", type=int, default=2000)
    parser.add_argument("--drain-timeout", type=float, default=10)
    parser.add_argument("--product-id", type=int, default=42)
    parser.add_argument("--purchased-count", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--connect-timeout", type=float, default=2.0)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run_load_test(parse_args()))
    except KeyboardInterrupt:
        print()
        print("Load test stopped by user.")
