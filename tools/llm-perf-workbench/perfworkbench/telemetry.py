"""Explicit experiment telemetry; metric values never infer missing data as zero."""

import copy
import json
import math
import os
import threading
import time
from pathlib import Path
from typing import TextIO

import httpx
from prometheus_client.parser import text_string_to_metric_families

MAX_RESPONSE_BYTES = 2 * 1024 * 1024

_UNITS = {
    "queue_waiting": "requests",
    "requests_running": "requests",
    "kv_cache_usage_ratio": "ratio",
    "preemptions_total": "events",
    "prefix_hits_total": "tokens",
    "prefix_queries_total": "tokens",
    "device_utilization_ratio": "ratio",
    "device_memory_used_bytes": "bytes",
    "device_memory_total_bytes": "bytes",
}

# Verified vLLM V1 names; Prometheus counter sample names include `_total`.
_DEFAULT_MAPPINGS = [
    {"key": "queue_waiting", "metric": "vllm:num_requests_waiting", "kind": "gauge"},
    {"key": "requests_running", "metric": "vllm:num_requests_running", "kind": "gauge"},
    {
        "key": "kv_cache_usage_ratio",
        "metric": "vllm:kv_cache_usage_perc",
        "kind": "gauge",
        "aggregation": "max",
    },
    {"key": "preemptions_total", "metric": "vllm:num_preemptions_total", "kind": "counter"},
    {"key": "prefix_hits_total", "metric": "vllm:prefix_cache_hits_total", "kind": "counter"},
    {"key": "prefix_queries_total", "metric": "vllm:prefix_cache_queries_total", "kind": "counter"},
]


def _missing(mapping: dict, reason: str) -> dict:
    return {
        "value": None,
        "unit": _UNITS[mapping["key"]],
        "kind": mapping.get("kind", "gauge"),
        "series": [],
        "status": "missing",
        "reason": reason,
    }


def _aggregate(metric: dict, mapping: dict) -> None:
    """Validate every selected observation before exposing an aggregate."""
    series = metric["series"]
    identities = [(s["metric"], tuple(sorted(s["labels"].items()))) for s in series]
    if len(set(identities)) != len(identities):
        metric["reason"] = "duplicate_series"
        return
    values = [s["value"] for s in series]
    if any(value is None for value in values):
        metric["reason"] = "non_finite_value"
        return
    if metric["kind"] == "counter" and any(value < 0 for value in values):
        metric["reason"] = "negative_counter"
        return
    values = [value * mapping.get("scale", 1.0) for value in values]
    if not all(math.isfinite(value) for value in values):
        metric["reason"] = "non_finite_value"
        return
    if metric["unit"] == "ratio" and any(not 0 <= value <= 1 for value in values):
        metric["reason"] = "ratio_out_of_range"
        return
    aggregation = mapping.get("aggregation", "sum")
    try:
        if aggregation == "mean":
            value = math.fsum(v / len(values) for v in values)
        elif aggregation == "max":
            value = max(values)
        else:
            value = math.fsum(values)
    except OverflowError:
        value = math.inf
    if not math.isfinite(value):
        metric["reason"] = "non_finite_value"
    elif metric["unit"] == "ratio" and not 0 <= value <= 1:
        metric["reason"] = "ratio_out_of_range"
    else:
        metric.update(value=value, status="available", reason=None)


def parse_metrics(text: str, mappings: list) -> dict:
    """Map Prometheus text to canonical values, keeping unscaled wire observations.

    Empty mappings select the verified vLLM defaults. Mapping validation belongs
    to ExperimentSpec. Malformed exposition raises a payload-free ValueError.
    """
    # TYPE metadata makes client_python rename unsuffixed counters to `_total`.
    # Parse samples without metadata so raw names remain exactly as exported;
    # the explicit mapping supplies kind and canonical unit semantics.
    samples_text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    indexed: dict[str, list[dict]] = {}
    try:
        for family in text_string_to_metric_families(samples_text):
            for sample in family.samples:
                value = float(sample.value)
                indexed.setdefault(sample.name, []).append(
                    {
                        "metric": sample.name,
                        "labels": dict(sample.labels),
                        "value": value if math.isfinite(value) else None,
                    }
                )
    except (ValueError, OverflowError):
        raise ValueError("invalid_metrics") from None
    result = {}
    for mapping in mappings or _DEFAULT_MAPPINGS:
        candidates = indexed.get(mapping["metric"], [])
        metric = _missing(mapping, "labels_not_matched" if candidates else "metric_not_found")
        selected = mapping.get("labels", {})
        metric["series"] = [
            {**sample, "labels": dict(sample["labels"])}
            for sample in candidates
            if all(sample["labels"].get(key) == value for key, value in selected.items())
        ]
        if metric["series"]:
            _aggregate(metric, mapping)
        result[mapping["key"]] = metric
    return result


def _scrape_error(sample: dict, mappings: list, reason: str) -> dict:
    sample.update(
        status="error",
        error=reason,
        metrics={mapping["key"]: _missing(mapping, reason) for mapping in mappings},
    )
    return sample


def scrape_source(source: dict, timeout_s: float = 3.0) -> dict:
    """Perform one bounded synchronous GET, returning safe errors as samples.

    The UTC timestamp is local request start, not an exporter timestamp.
    HTTP errors never include exception text, a response body, or a URL.
    """
    sample = {"timestamp": time.time(), "source": source["name"], "status": "ok", "metrics": {}}
    mappings = source.get("mappings") or _DEFAULT_MAPPINGS
    try:
        url = httpx.URL(source["url"])
    except (httpx.InvalidURL, ValueError):
        return _scrape_error(sample, mappings, "invalid_url")
    if url.scheme not in {"http", "https"} or not url.host or url.userinfo:
        return _scrape_error(sample, mappings, "invalid_url")
    headers = {"Accept": "text/plain; version=0.0.4", "Accept-Encoding": "identity"}
    if source.get("api_key_env"):
        key = os.environ.get(source["api_key_env"])
        if not key:
            return _scrape_error(sample, mappings, "missing_api_key")
        headers["Authorization"] = f"Bearer {key}"
    deadline = time.monotonic() + timeout_s
    try:
        with (
            httpx.Client(timeout=timeout_s, follow_redirects=False, trust_env=False) as client,
            client.stream("GET", url, headers=headers) as response,
        ):
            if 300 <= response.status_code < 400:
                return _scrape_error(sample, mappings, "redirect_rejected")
            if not 200 <= response.status_code < 300:
                return _scrape_error(sample, mappings, f"http_{response.status_code}")
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                return _scrape_error(sample, mappings, "unsupported_encoding")
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_RESPONSE_BYTES:
                return _scrape_error(sample, mappings, "response_too_large")
            body = bytearray()
            # No fixed chunk_size: HTTPX must yield every network read so a
            # trickle cannot postpone the body-deadline check indefinitely.
            for chunk in response.iter_raw():
                if time.monotonic() >= deadline:
                    return _scrape_error(sample, mappings, "timeout")
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    return _scrape_error(sample, mappings, "response_too_large")
                body.extend(chunk)
            if time.monotonic() >= deadline:
                return _scrape_error(sample, mappings, "timeout")
        sample["metrics"] = parse_metrics(body.decode("utf-8"), mappings)
    except httpx.TimeoutException:
        return _scrape_error(sample, mappings, "timeout")
    except httpx.HTTPError:
        return _scrape_error(sample, mappings, "network_error")
    except (ValueError, UnicodeError):
        return _scrape_error(sample, mappings, "invalid_metrics")
    return sample


def counter_delta(previous: dict, current: dict) -> dict:
    """Conservative delta between canonical counter entries with the same mapping.

    A decrease in any raw series invalidates the interval even if the aggregate
    increased. Disappearing/new series are unknown, never silently treated as 0.
    """
    result = {"value": None, "status": "missing", "reason": "counter_unavailable", "reset": False}
    if any(
        metric.get("kind") != "counter" or metric.get("status") != "available"
        for metric in (previous, current)
    ):
        return result
    before, after = [
        {
            (series["metric"], tuple(sorted(series["labels"].items()))): series["value"]
            for series in metric["series"]
        }
        for metric in (previous, current)
    ]
    if before.keys() != after.keys():
        result["reason"] = "series_changed"
    elif any(after[key] < value for key, value in before.items()):
        result.update(reason="counter_reset", reset=True)
    else:
        result.update(value=current["value"] - previous["value"], status="available", reason=None)
    return result


class TelemetryCollector:
    """One experiment's polling lifetime, explicitly controlled by its runner.

    Construction and snapshot never perform network I/O. Start is idempotent
    while running; after stop, a new experiment needs a new collector. The caller
    owns experiment duration, validated source count and sampling interval.
    """

    def __init__(self, config: dict, output_path: Path):
        telemetry = copy.deepcopy(config.get("telemetry", config))
        self._sources = telemetry.get("sources", [])
        self._interval_s = telemetry.get("interval_s", 1.0)
        self._output_path = Path(output_path)
        self._samples: list[dict] = []
        self._samples_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stopped = False
        self._failure: str | None = None

    def start(self) -> None:
        """Launch the first poll immediately, only after an explicit experiment start."""
        with self._lifecycle_lock:
            if self._stopped:
                raise RuntimeError("collector_stopped")
            if self._thread is not None or not self._sources:
                return
            try:
                self._output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(self._output_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                output = os.fdopen(descriptor, "a", encoding="utf-8")
            except OSError:
                raise OSError("telemetry_output_unavailable") from None
            self._thread = threading.Thread(
                target=self._poll, args=(output,), name="experiment-telemetry", daemon=True
            )
            try:
                self._thread.start()
            except RuntimeError:
                output.close()
                self._thread = None
                raise RuntimeError("telemetry_start_failed") from None

    def _poll(self, output: TextIO) -> None:
        try:
            with output:
                while not self._stop_event.is_set():
                    for source in self._sources:
                        if self._stop_event.is_set():
                            break
                        sample = scrape_source(source)
                        output.write(json.dumps(sample, ensure_ascii=True, allow_nan=False) + "\n")
                        output.flush()
                        with self._samples_lock:
                            self._samples.append(sample)
                    # A slow sweep does not create overlapping or catch-up polls.
                    if self._stop_event.wait(self._interval_s):
                        break
        except OSError:
            self._failure = "telemetry_output_unavailable"
            self._stop_event.set()
        except Exception:  # noqa: BLE001 -- redact failures crossing the background-thread boundary.
            # A background exception must be visible to the runner without
            # printing credential-bearing exception details from its thread.
            self._failure = "telemetry_collection_failed"
            self._stop_event.set()

    def stop(self) -> None:
        """Stop scheduling, drain the active scrape and close its JSONL stream."""
        with self._lifecycle_lock:
            self._stopped = True
            self._stop_event.set()
            if self._thread is not None:
                self._thread.join()
            if self._failure == "telemetry_output_unavailable":
                raise OSError(self._failure)
            if self._failure:
                raise RuntimeError(self._failure)

    def snapshot(self) -> list[dict]:
        """Return a detached copy of this collector's successfully persisted samples."""
        with self._samples_lock:
            return copy.deepcopy(self._samples)
