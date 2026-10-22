#!/usr/bin/env python3
"""Collect one request's traces from every place it left a mark.

The point is the ``correlation`` block: if the ID the client sent and the ID
the server recorded do not match, the evidence chain is broken and nothing
downstream holds. This script says so out loud instead of quietly carrying on.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REQUEST_ID_HEADER = "X-Request-Id"


class TraceError(RuntimeError):
    """Raised when a single-request trace cannot be assembled."""


class HttpTransport:
    """Sends one streaming request carrying a client-generated Request ID."""

    def __init__(self, base_url: str, model: str, timeout_s: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def send(self, request_id: str, prompt: str) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 128,
            "temperature": 0,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     REQUEST_ID_HEADER: request_id},
        )
        sent = time.perf_counter()
        headers_at: float | None = None
        first_chunk: float | None = None
        server_id = None
        metrics: dict | None = None
        finish_reason: str | None = None
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                headers_at = time.perf_counter()
                # 服务端只有加了 --enable-request-id-headers 才会回带这个头。
                server_id = resp.headers.get(REQUEST_ID_HEADER)
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:") or line == "data: [DONE]":
                        continue
                    if first_chunk is None:
                        first_chunk = time.perf_counter()
                    try:
                        chunk = json.loads(line[len("data:"):].strip())
                    except json.JSONDecodeError:
                        continue
                    # 请求级指标：要 --enable-per-request-metrics 才会出现（第 2 章 2.10）。
                    if isinstance(chunk.get("metrics"), dict):
                        metrics = chunk["metrics"]
                    reason = extract_finish_reason(chunk)
                    if reason is not None:
                        finish_reason = reason
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TraceError(f"request failed: {exc}") from exc
        finished = time.perf_counter()
        return {
            "client": {
                "request_id": request_id,
                "request_sent_ms": 0.0,
                "response_headers_ms": (
                    None if headers_at is None else (headers_at - sent) * 1000
                ),
                "first_chunk_received_ms": (
                    None if first_chunk is None else (first_chunk - sent) * 1000
                ),
                "response_finished_ms": (finished - sent) * 1000,
                "retries": 0,
                "error": None,
            },
            "server": server_block(server_id, metrics, finish_reason),
        }



def extract_finish_reason(chunk: dict) -> str | None:
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    reason = choices[0].get("finish_reason")
    return reason if isinstance(reason, str) else None


def server_block(
    server_id: str | None,
    metrics: dict | None,
    finish_reason: str | None,
) -> dict:
    """Turn vLLM's per-request metrics into the card's server block.

    vLLM names this segment ``time_to_first_token_ms`` but measures it from the
    moment the request was scheduled, so the card stores it under the name
    chapter 2 gave it: ``scheduled_to_first_token_ms``. Anything the server did
    not report stays ``None``; the card never fills a gap with a guess.
    """

    def num(name: str) -> float | None:
        if not isinstance(metrics, dict):
            return None
        value = metrics.get(name)
        return float(value) if isinstance(value, (int, float)) else None

    queue = num("queue_time_ms")
    first_token = num("time_to_first_token_ms")
    generation = num("generation_time_ms")
    parts = [queue, first_token, generation]
    e2e = sum(parts) if all(p is not None for p in parts) else None
    terminal = None
    if finish_reason in ("stop", "length"):
        terminal = "finished"
    elif finish_reason is not None:
        terminal = finish_reason
    return {
        "request_id": server_id,
        "queue_ms": queue,
        "scheduled_to_first_token_ms": first_token,
        "generation_ms": generation,
        "e2e_ms": e2e,
        "e2e_note": (
            "queue + scheduled_to_first_token + generation. It starts at the "
            "server's queued event, not at request arrival, so it is always "
            "smaller than the client total by the ingress and network legs."
        ),
        "terminal_state": terminal,
        "source": (
            "per-request metrics carried in the stream; start vLLM with "
            "--enable-per-request-metrics, otherwise these stay null"
        ),
    }


def correlate(client: dict, server: dict) -> dict:
    """Compare the two IDs. A mismatch invalidates every later join."""
    client_id = client.get("request_id")
    server_id = server.get("request_id")
    if not client_id:
        return {"status": "broken", "reason": "client recorded no request_id",
                "client_id": client_id, "server_id": server_id}
    if not server_id:
        return {"status": "unknown",
                "reason": "server did not echo a request_id; the join cannot be "
                          "verified, so treat every cross-side number as unmatched",
                "client_id": client_id, "server_id": server_id}
    if client_id != server_id:
        return {"status": "broken",
                "reason": "client and server recorded different ids; the evidence "
                          "chain is cut here and nothing downstream holds",
                "client_id": client_id, "server_id": server_id}
    return {"status": "ok", "reason": "same id on both sides",
            "client_id": client_id, "server_id": server_id}


def compute_gaps(client: dict, server: dict, attempts: list[dict] | None = None) -> dict:
    """Split the client/server difference into parts we can actually name.

    Whatever is left over stays unnamed. Chapter 2's rule: do not name a
    segment whose boundaries you did not observe.
    """
    client_total = client.get("response_finished_ms")
    server_total = server.get("e2e_ms")
    if client_total is None:
        raise TraceError("client did not record response_finished_ms")
    if server_total is None:
        return {
            "client_total_ms": client_total,
            "server_total_ms": None,
            "difference_ms": None,
            "note": (
                "server total unavailable: the per-request metrics were not in "
                "the stream. Start vLLM with --enable-per-request-metrics, or "
                "fill the server block by hand from the log line that carries "
                "this Request ID. Until then the difference stays uncomputed."
            ),
        }

    attempts = attempts or []
    cancelled_ms = sum(a.get("duration_ms", 0.0) for a in attempts
                       if a.get("outcome") == "cancelled")
    backoff_ms = sum(a.get("backoff_ms", 0.0) for a in attempts)
    difference = client_total - server_total
    unattributed = difference - cancelled_ms - backoff_ms
    return {
        "client_total_ms": client_total,
        "server_total_ms": server_total,
        "difference_ms": difference,
        "attributed": {
            "cancelled_attempts_ms": cancelled_ms,
            "client_backoff_ms": backoff_ms,
        },
        "unattributed_ms": unattributed,
        "note": (
            "unattributed covers network round trip and client-side processing. "
            "It is deliberately left unnamed: no observed boundary, no name."
        ),
    }


def build_card(
    *,
    model: str,
    client: dict,
    server: dict,
    attempts: list[dict] | None = None,
    collected_at: str | None = None,
) -> dict:
    card = {
        "identity": {
            "request_id": client.get("request_id"),
            "model": model,
            "collected_at": collected_at or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
        "client": dict(client),
        "server": dict(server),
        "attempts": list(attempts or []),
        "correlation": correlate(client, server),
        "gaps": compute_gaps(client, server, attempts),
    }
    return card


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--request-id", default=None)
    parser.add_argument("--prompt", default="用一句话解释什么是 KV Cache。")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    request_id = args.request_id or f"req-{uuid.uuid4().hex[:12]}"
    transport = HttpTransport(args.base_url, args.model)
    observed = transport.send(request_id, args.prompt)
    card = build_card(model=args.model, client=observed["client"],
                      server=observed["server"])

    if card["correlation"]["status"] == "broken":
        print(f"WARNING: {card['correlation']['reason']}")

    text = json.dumps(card, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0 if card["correlation"]["status"] != "broken" else 1


if __name__ == "__main__":
    raise SystemExit(main())
