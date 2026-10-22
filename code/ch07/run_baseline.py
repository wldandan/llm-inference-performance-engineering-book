#!/usr/bin/env python3
"""Run a reproducible Baseline from a Chapter 6 workload description.

The point of a Baseline is not to produce a good number, it is to produce a
number somebody else can reproduce. So this script refuses to emit a report
that is missing any of the four blocks: workload, protocol, environment,
results.

How load is generated (7.7), and which earlier sections each rule comes from:

* Open-loop modes (``poisson``, ``constant``) follow a planned send schedule
  drawn from the workload seed. Requests are sent concurrently, and latency is
  measured from the *planned* send time, so a client that falls behind does not
  hide the delay it caused (coordinated omission, 6.3).
* ``closed`` keeps exactly ``concurrency`` requests in flight. It has no
  schedule, so latency starts at the actual send time; the report says so.
* Every run replays the same request sequence (same lengths, same send
  times), because "request content differs between runs" is one of the noise
  sources 7.3 tells you to remove.
* Prompt texts are prefix-free: each one starts with a tag unique to its run
  and index, so no prompt is a prefix of another, within a run or across runs
  (7.5). The chat template's own system prefix is still shared; that part is
  the same for every request in production too.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ch06"))
from workload_builder import WorkloadError, validate_workload  # noqa: E402

ENVIRONMENT_FIELDS = (
    "python_version",
    "vllm_version",
    "model_name",
    "model_revision",
    "gpu_name",
    "driver_version",
    "launch_command",
)

SUPPORTED_ARRIVALS = ("poisson", "constant", "closed")
PREFIX_CACHE_STATES = ("on", "off")

# Two-sided 97.5% quantile of Student's t, by degrees of freedom.
_T975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056,
    27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042, 40: 2.021, 60: 2.000,
    120: 1.980,
}

# A neutral word list. Words, not characters, so the token count of a prompt
# roughly follows the number of words; the exact count depends on the
# tokenizer, which is why the report keeps the target length, not a claim.
_WORDS = (
    "river", "window", "garden", "number", "letter", "market", "planet",
    "silver", "button", "candle", "forest", "harbor", "island", "jacket",
    "kettle", "ladder", "meadow", "needle", "orange", "pencil", "rabbit",
    "saddle", "tunnel", "valley", "wagon", "yellow", "anchor", "bridge",
    "copper", "desert", "engine", "feather", "glacier", "hammer", "lantern",
    "marble", "pepper", "quartz", "ribbon", "spider", "timber", "velvet",
)


class BaselineError(RuntimeError):
    """Raised when a Baseline cannot be produced or is not reproducible."""


def nearest_rank_percentile(values: list[float], percentile: float) -> float:
    """Same algorithm as Chapter 5, so the two chapters' numbers are comparable."""
    if not values:
        raise BaselineError("cannot take a percentile of an empty sample")
    if not 0 < percentile <= 100:
        raise BaselineError("percentile must be in (0, 100]")
    ordered = sorted(values)
    rank = math.ceil(percentile / 100 * len(ordered))
    return ordered[rank - 1]


def coefficient_of_variation(values: list[float]) -> float:
    """Sample standard deviation over mean. See 7.3 on the n-1 convention."""
    if len(values) < 2:
        raise BaselineError("CV needs at least two runs")
    mean = statistics.mean(values)
    if mean <= 0:
        raise BaselineError("mean must be positive")
    return statistics.stdev(values) / mean


def t_critical(df: int) -> float:
    """97.5% quantile of Student's t; conservative step lookup above df 30."""
    if df < 1:
        raise BaselineError("degrees of freedom must be at least 1")
    usable = [k for k in _T975 if k <= df]
    return _T975[max(usable)] if df <= 120 else 1.960


def line_factor(runs_per_group: int) -> float:
    """t x sqrt(2/n): the multiple of CV that a difference must exceed (7.3).

    Two groups of n runs each; the difference of their means fluctuates by
    about CV x sqrt(2/n), and ~95% confidence needs t times that.
    n = 3 gives about 2.3, n = 12 about 0.85.
    """
    n = runs_per_group
    if n < 2:
        raise BaselineError("need at least two runs per group")
    return t_critical(2 * n - 2) * math.sqrt(2 / n)


def detectable_difference(values: list[float], runs_per_group: int | None = None) -> float:
    """The 7.3 line, as a fraction of the mean.

    ``values`` are the per-run results of the Baseline. The comparison is
    assumed to run the same number of rounds on the other side unless
    ``runs_per_group`` says otherwise. The line belongs to this metric, this
    percentile and this requests-per-run; change any of them and recompute.
    """
    n = runs_per_group or len(values)
    return line_factor(n) * coefficient_of_variation(values)


def check_environment(env: dict) -> None:
    missing = [f for f in ENVIRONMENT_FIELDS if not str(env.get(f, "")).strip()]
    if missing:
        raise BaselineError(
            "environment fingerprint is incomplete, refusing to write a report "
            f"that nobody can reproduce: missing {missing}"
        )


def make_prompt(tag: str, words: int, rng: random.Random) -> str:
    """A prompt that starts with a unique tag, so it shares no prefix (7.5)."""
    body = " ".join(rng.choice(_WORDS) for _ in range(max(words - 1, 0)))
    return f"{tag} {body}".strip()


class HttpTransport:
    """Minimal OpenAI-compatible streaming client. Requires a real server."""

    def __init__(self, base_url: str, model: str, timeout_s: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def send(self, prompt: str, max_tokens: int) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
            "stream": True,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        sent = time.perf_counter()
        first_chunk: float | None = None
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    if first_chunk is None and line != "data: [DONE]":
                        first_chunk = time.perf_counter()
            done = time.perf_counter()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise BaselineError(f"request failed: {exc}") from exc
        if first_chunk is None:
            raise BaselineError("no content chunk received")
        return {
            "ok": True,
            "ttft_ms": (first_chunk - sent) * 1000,
            "e2e_ms": (done - sent) * 1000,
        }


def _sample_length(block: dict, rng: random.Random) -> int:
    """Draw a length from the four recorded quantiles, keeping the long tail."""
    roll = rng.random()
    if roll < 0.50:
        low, high = 1, block["p50"]
    elif roll < 0.90:
        low, high = block["p50"], block["p90"]
    elif roll < 0.99:
        low, high = block["p90"], block["p99"]
    else:
        low, high = block["p99"], block["max"]
    return int(rng.uniform(low, high)) or 1


def plan_requests(doc: dict, request_count: int) -> list[dict]:
    """The request sequence of one run. Identical for every run (7.3).

    Lengths and planned send offsets come from the workload seed only. The
    prompt text is generated later, per run, so that runs do not hit each
    other's Prefix Cache.
    """
    arrival = doc["arrival"]
    mode = arrival["mode"]
    if mode not in SUPPORTED_ARRIVALS:
        raise BaselineError(
            f"arrival.mode={mode} is not implemented by this Demo; "
            f"use one of {SUPPORTED_ARRIVALS}"
        )
    rng = random.Random(arrival["seed"])
    plan: list[dict] = []
    offset = 0.0
    for i in range(request_count):
        if mode == "poisson":
            offset += rng.expovariate(arrival["rate"]) if i else 0.0
        elif mode == "constant":
            offset = i / arrival["rate"]
        plan.append(
            {
                "index": i,
                "planned_offset_s": offset if mode != "closed" else None,
                "prompt_tokens_target": _sample_length(doc["length"]["prompt"], rng),
                "max_tokens": _sample_length(doc["length"]["output"], rng),
            }
        )
    return plan


def _one_request(transport, item: dict, prompt: str, planned: float | None,
                 clock) -> dict:
    actual = clock()
    record = {
        "index": item["index"],
        "prompt_tokens_target": item["prompt_tokens_target"],
        "max_tokens": item["max_tokens"],
    }
    # Open loop: latency starts at the planned send time, so time the client
    # spent behind schedule is charged to the request (6.3). Closed loop has
    # no schedule and starts at the actual send time.
    lag_ms = 0.0 if planned is None else max(actual - planned, 0.0) * 1000
    try:
        result = transport.send(prompt, item["max_tokens"])
    except BaselineError as exc:
        record.update({"ok": False, "error": str(exc), "send_lag_ms": lag_ms})
        record["finished_at"] = clock()
        return record
    record.update(
        {
            "ok": bool(result.get("ok", True)),
            "send_lag_ms": lag_ms,
            "ttft_ms": result["ttft_ms"] + lag_ms,
            "e2e_ms": result["e2e_ms"] + lag_ms,
            "finished_at": clock(),
        }
    )
    return record


def run_once(
    doc: dict,
    transport,
    *,
    run_index: int,
    request_count: int,
    max_in_flight: int = 256,
    clock=time.perf_counter,
    sleep=time.sleep,
) -> dict:
    """One measured run: same plan every time, prompts salted by run index."""
    plan = plan_requests(doc, request_count)
    mode = doc["arrival"]["mode"]
    text_rng = random.Random(f"{doc['arrival']['seed']}-run{run_index}")
    prompts = [
        make_prompt(f"[r{run_index}-q{item['index']}]", item["prompt_tokens_target"], text_rng)
        for item in plan
    ]

    window_start = clock()
    records: list[dict] = []
    if mode == "closed":
        concurrency = doc["arrival"]["concurrency"]
        lock = threading.Lock()
        cursor = iter(range(len(plan)))

        def worker() -> None:
            while True:
                with lock:
                    i = next(cursor, None)
                if i is None:
                    return
                rec = _one_request(transport, plan[i], prompts[i], None, clock)
                with lock:
                    records.append(rec)

        threads = [threading.Thread(target=worker) for _ in range(concurrency)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    else:
        with ThreadPoolExecutor(max_workers=max_in_flight) as pool:
            futures = []
            for item, prompt in zip(plan, prompts):
                planned = window_start + item["planned_offset_s"]
                wait = planned - clock()
                if wait > 0:
                    sleep(wait)
                futures.append(
                    pool.submit(_one_request, transport, item, prompt, planned, clock)
                )
            records = [f.result() for f in futures]
    # Every request sent in the window is waited for and counted ("drained"),
    # so the window ends when the last counted request finished (7.4).
    window_end = max((r["finished_at"] for r in records), default=clock())
    records.sort(key=lambda r: r["index"])

    ok = [r for r in records if r.get("ok")]
    if not ok:
        raise BaselineError(f"run {run_index}: no successful request")
    ttfts = [r["ttft_ms"] for r in ok]
    e2es = [r["e2e_ms"] for r in ok]
    for r in records:
        r.pop("finished_at", None)
    return {
        "run": run_index,
        "window_start_event": "first counted request planned",
        "window_end_event": "last counted request finished",
        "window_seconds": window_end - window_start,
        "in_flight_at_end": "drained",
        "requests": len(records),
        "successful": len(ok),
        "failed": len(records) - len(ok),
        "max_send_lag_ms": max(r["send_lag_ms"] for r in records),
        "ttft_p50_ms": nearest_rank_percentile(ttfts, 50),
        "ttft_p95_ms": nearest_rank_percentile(ttfts, 95),
        "e2e_p95_ms": nearest_rank_percentile(e2es, 95),
        "raw": records,
    }


def build_report(
    doc: dict,
    environment: dict,
    runs: list[dict],
    *,
    warmup_requests: int,
    prefix_cache: str,
) -> dict:
    validate_workload(doc)
    check_environment(environment)
    if prefix_cache not in PREFIX_CACHE_STATES:
        raise BaselineError(
            "say whether the server's Prefix Cache was on or off; without it two "
            "Baselines are not comparable (7.5)"
        )
    if len(runs) < 3:
        raise BaselineError(
            "a Baseline needs at least three runs: one run is a single sample "
            "from the distribution, not a baseline (7.3)"
        )
    per_run = {r["requests"] for r in runs}
    if len(per_run) != 1:
        raise BaselineError("every run must send the same number of requests")
    requests_per_run = per_run.pop()

    p95s = [r["ttft_p95_ms"] for r in runs]
    cv = coefficient_of_variation(p95s)
    line = detectable_difference(p95s)
    mode = doc["arrival"]["mode"]
    tail_samples = int(requests_per_run * (1 - 0.95))
    return {
        "workload": doc,
        "protocol": {
            "warmup_requests": warmup_requests,
            "warmup_excluded": True,
            "runs": len(runs),
            "requests_per_run": requests_per_run,
            "arrival_mode": mode,
            "latency_origin": (
                "actual send time (closed loop, no schedule)"
                if mode == "closed"
                else "planned send time (open loop)"
            ),
            "request_sequence": "same seed every run: identical lengths and send times",
            "prompt_text": "prefix-free, salted per run and per request",
            "prefix_cache": prefix_cache,
            "window_start_event": "first counted request planned",
            "window_end_event": "last counted request finished",
            "in_flight_at_end": "drained",
            "percentile_algorithm": "nearest-rank",
            "stdev_convention": "sample (n-1)",
        },
        "environment": dict(environment),
        "results": {
            "per_run": runs,
            "ttft_p95_ms": {
                "values": p95s,
                "median": statistics.median(p95s),
                "range": max(p95s) - min(p95s),
                "mean": statistics.mean(p95s),
                "stdev": statistics.stdev(p95s),
                "cv": cv,
                "detectable_difference": line,
                "detectable_difference_rule": (
                    f"t(0.975, 2n-2) x sqrt(2/n) x CV = {line_factor(len(runs)):.2f} x CV, "
                    f"for {len(runs)} runs against {len(runs)} runs; belongs to this "
                    "metric, this percentile and this requests_per_run"
                ),
                "tail_samples_per_run": tail_samples,
            },
            "warnings": (
                [
                    f"only about {tail_samples} samples per run lie above P95; "
                    "the per-run P95 itself is noisy, use about 200 requests per run (5.5)"
                ]
                if tail_samples < 10
                else []
            ),
            "verdict": (
                "usable"
                if line <= 0.20
                else "too noisy, find the variance source before comparing (7.3)"
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--requests-per-run", type=int, default=200)
    parser.add_argument("--max-in-flight", type=int, default=256)
    parser.add_argument("--prefix-cache", choices=PREFIX_CACHE_STATES, default=None,
                        help="whether the server was started with Prefix Cache on")
    parser.add_argument("--vllm-version", default="")
    parser.add_argument("--model-revision", default="")
    parser.add_argument("--gpu-name", default="")
    parser.add_argument("--driver-version", default="")
    parser.add_argument("--launch-command", default="")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    doc = json.loads(args.workload.read_text(encoding="utf-8"))
    try:
        validate_workload(doc)
    except WorkloadError as exc:
        print(f"REJECTED workload: {exc}")
        return 1
    if doc["arrival"]["mode"] not in SUPPORTED_ARRIVALS:
        print(f"REJECTED: arrival.mode={doc['arrival']['mode']} is not implemented "
              f"by this Demo; use one of {SUPPORTED_ARRIVALS}")
        return 1
    if args.prefix_cache is None:
        print("REJECTED: --prefix-cache on|off is required (7.5)")
        return 1

    environment = {
        "python_version": platform.python_version(),
        "vllm_version": args.vllm_version,
        "model_name": args.model,
        "model_revision": args.model_revision,
        "gpu_name": args.gpu_name,
        "driver_version": args.driver_version,
        "launch_command": args.launch_command,
    }
    try:
        check_environment(environment)
    except BaselineError as exc:
        print(f"REJECTED: {exc}")
        return 1

    transport = HttpTransport(args.base_url, args.model)
    warm_rng = random.Random("warmup")
    for i in range(args.warmup):
        transport.send(make_prompt(f"[warmup-{i}]", 64, warm_rng), 32)

    runs = [
        run_once(doc, transport, run_index=i + 1,
                 request_count=args.requests_per_run,
                 max_in_flight=args.max_in_flight)
        for i in range(args.runs)
    ]
    report = build_report(doc, environment, runs, warmup_requests=args.warmup,
                          prefix_cache=args.prefix_cache)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
