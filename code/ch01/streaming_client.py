"""Chapter 01 streaming client: send real streaming requests to a vLLM OpenAI-compatible server.

This script records client-observed first-content time, chunk intervals,
total latency, server-reported token usage, and optional GPU snapshots.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_PROMPT = "请用中文简要解释 LLM 在线推理中的 Prefill、Decode 和 KV Cache。"
DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


def build_payload(model: str, prompt: str, max_tokens: int, temperature: float) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * pct / 100.0
    lo = int(rank)
    hi = min(lo + 1, len(values) - 1)
    weight = rank - lo
    return values[lo] * (1 - weight) + values[hi] * weight


@dataclass
class MetricsCollector:
    start_time: float
    first_token_time: float | None = None
    last_token_time: float | None = None
    token_timestamps: list[float] | None = None
    chunks: int = 0
    characters: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.token_timestamps is None:
            self.token_timestamps = []

    def on_content_chunk(self, timestamp: float, text: str) -> None:
        if text == "":
            return
        if self.first_token_time is None:
            self.first_token_time = timestamp
        self.last_token_time = timestamp
        self.token_timestamps.append(timestamp)
        self.chunks += 1
        self.characters += len(text)

    def set_usage(self, prompt_tokens: int | None, completion_tokens: int | None) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

    def finish(self, end_time: float) -> dict[str, Any]:
        timestamps = self.token_timestamps or []
        intervals = [
            (timestamps[i] - timestamps[i - 1]) * 1000.0
            for i in range(1, len(timestamps))
        ]
        total_seconds = max(end_time - self.start_time, 1e-9)
        return {
            "success": True,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.completion_tokens,
            "stream_chunks": self.chunks,
            "output_characters": self.characters,
            "time_to_first_content_chunk_ms": round((self.first_token_time - self.start_time) * 1000.0, 2)
            if self.first_token_time is not None
            else None,
            "chunk_interval_avg_ms": round(sum(intervals) / len(intervals), 2) if intervals else None,
            "chunk_interval_p50_ms": round(percentile(intervals, 50), 2) if intervals else None,
            "chunk_interval_p95_ms": round(percentile(intervals, 95), 2) if intervals else None,
            "total_latency_ms": round(total_seconds * 1000.0, 2),
            "request_output_rate_tokens_per_second": (
                round(self.completion_tokens / total_seconds, 2)
                if self.completion_tokens is not None and self.completion_tokens > 0
                else None
            ),
        }


def read_prompt(prompt: str | None, prompt_file: str | None, prompt_repeat: int) -> str:
    if prompt_file:
        text = open(prompt_file, encoding="utf-8").read()
    else:
        text = prompt or DEFAULT_PROMPT
    return "\n".join([text] * prompt_repeat)


def parse_sse_payload(line: bytes) -> dict[str, Any] | None:
    text = line.decode("utf-8").strip()
    if not text or not text.startswith("data:"):
        return None
    data = text[len("data:") :].strip()
    if data == "[DONE]":
        return {"done": True}
    return json.loads(data)


def extract_delta_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def extract_usage(payload: dict[str, Any]) -> tuple[int | None, int | None]:
    usage = payload.get("usage")
    if not usage:
        return None, None
    return usage.get("prompt_tokens"), usage.get("completion_tokens")


def request_once(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = build_payload(model=model, prompt=prompt, max_tokens=max_tokens, temperature=temperature)
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    start = time.perf_counter()
    collector = MetricsCollector(start_time=start)
    done_seen = False
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                now = time.perf_counter()
                parsed = parse_sse_payload(raw_line)
                if parsed is None:
                    continue
                if parsed.get("done"):
                    done_seen = True
                    break
                if "error" in parsed:
                    error = parsed["error"]
                    detail = error.get("message") if isinstance(error, dict) else str(error)
                    return {"success": False, "error": f"SSE error: {detail}"}
                prompt_tokens, completion_tokens = extract_usage(parsed)
                if prompt_tokens is not None or completion_tokens is not None:
                    collector.set_usage(prompt_tokens, completion_tokens)
                collector.on_content_chunk(now, extract_delta_text(parsed))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"success": False, "error": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:  # pragma: no cover - real network failure path
        return {"success": False, "error": str(exc)}
    if not done_seen:
        return {"success": False, "error": "stream ended without [DONE]"}
    if collector.chunks == 0:
        return {"success": False, "error": "stream completed with no content chunks"}
    return collector.finish(end_time=time.perf_counter())


def gpu_snapshot() -> dict[str, Any] | None:
    if not shutil.which("nvidia-smi"):
        return None
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = subprocess.check_output(cmd, text=True, timeout=5).strip()
    except Exception:
        return None
    gpus = []
    for line in output.splitlines():
        name, util, mem_used, mem_total = [part.strip() for part in line.split(",")]

        def numeric_or_none(value: str) -> float | None:
            return None if value in {"[N/A]", "N/A", ""} else float(value)

        gpus.append(
            {
                "name": name,
                "gpu_util_pct": numeric_or_none(util),
                "memory_used_mb": numeric_or_none(mem_used),
                "memory_total_mb": numeric_or_none(mem_total),
            }
        )
    return {"gpus": gpus}


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [item for item in results if item.get("success")]
    failures = [item for item in results if not item.get("success")]

    def values(key: str) -> list[float]:
        return [float(item[key]) for item in successes if item.get(key) is not None]

    return {
        "requests": len(results),
        "successes": len(successes),
        "failures": len(failures),
        "time_to_first_content_chunk_avg_ms": round(
            sum(values("time_to_first_content_chunk_ms"))
            / len(values("time_to_first_content_chunk_ms")),
            2,
        )
        if values("time_to_first_content_chunk_ms")
        else None,
        "time_to_first_content_chunk_p95_ms": round(
            percentile(values("time_to_first_content_chunk_ms"), 95), 2
        )
        if values("time_to_first_content_chunk_ms")
        else None,
        "chunk_interval_avg_ms": round(
            sum(values("chunk_interval_avg_ms")) / len(values("chunk_interval_avg_ms")), 2
        )
        if values("chunk_interval_avg_ms")
        else None,
        "total_latency_avg_ms": round(sum(values("total_latency_ms")) / len(values("total_latency_ms")), 2)
        if values("total_latency_ms")
        else None,
        "failures_detail": failures[:3],
    }


def build_report(
    started_at: str,
    base_url: str,
    model: str,
    prompt: str,
    prompt_repeat: int,
    max_tokens: int,
    concurrency: int,
    results: list[dict[str, Any]],
    before_gpu: dict[str, Any] | None,
    after_gpu: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "started_at": started_at,
        "base_url": base_url,
        "model": model,
        "prompt": prompt,
        "prompt_repeat": prompt_repeat,
        "max_tokens": max_tokens,
        "concurrency": concurrency,
        "summary": summarize(results),
        "gpu_before": before_gpu,
        "gpu_after": after_gpu,
        "results": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure real vLLM OpenAI-compatible streaming metrics",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--prompt-file", default=None)
    parser.add_argument("--prompt-repeat", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--requests", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.requests <= 0 or args.concurrency <= 0 or args.max_tokens <= 0 or args.prompt_repeat <= 0:
        raise SystemExit("--requests, --concurrency, --max-tokens, and --prompt-repeat must be > 0")

    prompt = read_prompt(args.prompt, args.prompt_file, args.prompt_repeat)
    before_gpu = gpu_snapshot()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                request_once,
                args.base_url,
                args.api_key,
                args.model,
                prompt,
                args.max_tokens,
                args.temperature,
                args.timeout,
            )
            for _ in range(args.requests)
        ]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    after_gpu = gpu_snapshot()

    report = build_report(
        started_at=started_at,
        base_url=args.base_url,
        model=args.model,
        prompt=prompt,
        prompt_repeat=args.prompt_repeat,
        max_tokens=args.max_tokens,
        concurrency=args.concurrency,
        results=results,
        before_gpu=before_gpu,
        after_gpu=after_gpu,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)

    if report["summary"]["failures"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
