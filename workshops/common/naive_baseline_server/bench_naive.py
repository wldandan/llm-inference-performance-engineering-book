"""Bench client for the naive_baseline_server (see NOTICE.md) -- NOT the
OpenAI-compatible shape that bench_client.py expects, because this server's
endpoints (/generate, /generate_stream) predate that convention.

Two modes:
  --mode static     -> POST /generate once with a whole batch of prompts,
                        times how long the blocking call takes. No TTFT is
                        observable in this mode (the endpoint isn't
                        streaming), only total latency and aggregate
                        throughput.
  --mode continuous -> POST /generate_stream once per prompt, concurrently,
                        parses the `data: {"token": ..., "sequence_id": ...}`
                        SSE stream to get real per-request TTFT/ITL, reusing
                        the same MetricsCollector/percentile math as
                        bench_client.py so results are comparable.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench_client import MetricsCollector, load_request_plan, summarize  # noqa: E402


def parse_sse_line(line: bytes) -> dict[str, Any] | None:
    text = line.decode("utf-8").strip()
    if not text or not text.startswith("data:"):
        return None
    return json.loads(text[len("data:") :].strip())


def extract_token_text(payload: dict[str, Any]) -> str:
    token = payload.get("token")
    return token if isinstance(token, str) else ""


def continuous_request_once(base_url: str, prompt: str, timeout: float) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/generate_stream"
    body = json.dumps({"prompt": prompt}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    start = time.perf_counter()
    collector = MetricsCollector(start_time=start)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                now = time.perf_counter()
                parsed = parse_sse_line(raw_line)
                if parsed is None:
                    continue
                collector.on_token(now, extract_token_text(parsed))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"success": False, "error": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:  # pragma: no cover - real network failure path
        return {"success": False, "error": str(exc)}
    return collector.finish(end_time=time.perf_counter())


def run_continuous(base_url: str, prompts: list[str], timeout: float) -> list[dict[str, Any]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(prompts)) as executor:
        futures = [executor.submit(continuous_request_once, base_url, p, timeout) for p in prompts]
        return [f.result() for f in futures]


def run_static(base_url: str, prompts: list[str], timeout: float) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/generate"
    body = json.dumps({"prompts": prompts}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"success": False, "error": f"HTTP {exc.code}: {detail}"}
    end = time.perf_counter()
    total_seconds = max(end - start, 1e-9)
    texts = payload.get("generated_texts", [])
    return {
        "success": True,
        "batch_size": len(prompts),
        "total_latency_ms": round(total_seconds * 1000.0, 2),
        "requests_per_second": round(len(prompts) / total_seconds, 2),
        "generated_texts": texts,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=["static", "continuous"], required=True)
    parser.add_argument("--requests-file", required=True)
    parser.add_argument("--requests", type=int, default=8)
    parser.add_argument("--label", required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    plan = load_request_plan(args.requests_file, count=args.requests)
    prompts = [item["prompt"] for item in plan]

    if args.mode == "static":
        result = run_static(args.base_url, prompts, args.timeout)
        report = {"label": args.label, "mode": "static", "summary": result}
    else:
        results = run_continuous(args.base_url, prompts, args.timeout)
        report = {"label": args.label, "mode": "continuous", "summary": summarize(results), "results": results}

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
