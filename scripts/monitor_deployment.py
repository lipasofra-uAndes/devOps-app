"""Sample the deployed API during a manual Elastic Beanstalk deployment."""

import argparse
import csv
import json
import os
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def request(url, token=None, payload=None, timeout=10):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.headers, response.read(), round((time.perf_counter() - start) * 1000, 2), ""
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read(), round((time.perf_counter() - start) * 1000, 2), ""
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 0, {}, b"", round((time.perf_counter() - start) * 1000, 2), str(error)


def percentile(values, percentage):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentage / 100
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower), 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Elastic Beanstalk HTTPS origin")
    parser.add_argument("--strategy", required=True, help="Name of deployment strategy")
    parser.add_argument("--duration", type=float, default=900, help="Sampling duration in seconds")
    parser.add_argument("--interval", type=float, default=1, help="Seconds between sample starts")
    parser.add_argument("--timeout", type=float, default=10, help="Per-request timeout in seconds")
    parser.add_argument("--output-dir", default="results", help="CSV and summary JSON directory")
    args = parser.parse_args()
    if args.duration <= 0 or args.interval <= 0 or args.timeout <= 0:
        parser.error("duration, interval and timeout must be positive")
    parsed_url = urllib.parse.urlparse(args.base_url)
    if parsed_url.scheme != "https" and not (
        parsed_url.scheme == "http" and parsed_url.hostname in {"localhost", "127.0.0.1"}
    ):
        parser.error("Use HTTPS for deployed environments; HTTP is allowed only for localhost")

    username = os.getenv("AUTH_USERNAME")
    password = os.getenv("AUTH_PASSWORD")
    if not username or not password:
        parser.error("Set AUTH_USERNAME and AUTH_PASSWORD in the current shell")
    base_url = args.base_url.rstrip("/")
    status, _, body, _, error = request(
        base_url + "/auth/token",
        payload={"username": username, "password": password},
        timeout=args.timeout,
    )
    if status != 200:
        parser.error(f"JWT request failed (HTTP {status}): {error or body[:200].decode('utf-8', 'replace')}")
    try:
        token = json.loads(body)["access_token"]
    except (ValueError, KeyError, TypeError):
        parser.error("JWT response did not contain access_token")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    label = "".join(char if char.isalnum() or char in "-_" else "_" for char in args.strategy)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = output_dir / f"{stamp}_{label}"
    csv_path = stem.with_suffix(".csv")
    summary_path = stem.with_suffix(".json")
    email = urllib.parse.quote(f"probe-{stamp}@example.invalid", safe="@")
    url = base_url + "/blacklists/" + email
    rows = []
    started_at = utc_now()
    start = time.monotonic()
    next_sample = start
    try:
        while time.monotonic() - start < args.duration:
            now = time.monotonic()
            if now < next_sample:
                time.sleep(min(next_sample - now, 0.2))
                continue
            timestamp = utc_now()
            status, headers, body, latency, error = request(url, token=token, timeout=args.timeout)
            version = headers.get("X-App-Version", "")
            try:
                payload = json.loads(body)
                valid = status == 200 and payload.get("blacklisted") is False
            except (ValueError, AttributeError):
                valid = False
            row = {
                "timestamp_utc": timestamp,
                "status": status,
                "latency_ms": latency,
                "version": version,
                "success": valid,
                "error": error or ("unexpected API response" if not valid else ""),
            }
            rows.append(row)
            print(f"{timestamp} status={status} ms={latency} version={version or '?'} success={valid}", flush=True)
            next_sample += args.interval
            if next_sample < time.monotonic():
                next_sample = time.monotonic()
    except KeyboardInterrupt:
        print("Stopped by user; writing partial results.", flush=True)
    finally:
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["timestamp_utc", "status", "latency_ms", "version", "success", "error"])
            writer.writeheader()
            writer.writerows(rows)
        successful = [row["latency_ms"] for row in rows if row["success"]]
        summary = {
            "strategy": args.strategy,
            "base_url": base_url,
            "started_at_utc": started_at,
            "ended_at_utc": utc_now(),
            "requests": len(rows),
            "successful": len(successful),
            "failed": len(rows) - len(successful),
            "availability_percent": round(100 * len(successful) / len(rows), 2) if rows else None,
            "status_counts": dict(Counter(str(row["status"]) for row in rows)),
            "version_counts": dict(Counter(row["version"] or "unknown" for row in rows)),
            "successful_latency_ms": {
                "mean": round(statistics.mean(successful), 2) if successful else None,
                "p50": percentile(successful, 50),
                "p95": percentile(successful, 95),
                "max": max(successful) if successful else None,
            },
        }
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"CSV: {csv_path}\nSummary: {summary_path}", flush=True)


if __name__ == "__main__":
    main()
