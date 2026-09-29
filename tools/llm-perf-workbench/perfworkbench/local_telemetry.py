"""Opt-in, read-only local observations. No generation, shell commands or privilege escalation."""

import json
import os
import time

import httpx
import psutil

from .config import local_ollama_url

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
LOCAL_UNITS = {
    "host_memory_total_bytes": "bytes",
    "host_memory_available_bytes": "bytes",
    "host_swap_used_bytes": "bytes",
    "host_swap_total_bytes": "bytes",
    "model_memory_bytes": "bytes",
    "model_context_tokens": "tokens",
}


def _metric(key, value=None, reason="field_unavailable", *, field=None, labels=None):
    valid = type(value) is int and 0 <= value <= 2**63 - 1
    if key in {"model_context_tokens", "host_memory_total_bytes"} and value == 0:
        valid = False
    return {
        "value": value if valid else None,
        "unit": LOCAL_UNITS[key],
        "kind": "gauge",
        "status": "available" if valid else "missing",
        "reason": None if valid else reason,
        "series": [{"value": value, "metric": field or key, "labels": labels or {}}] if valid else [],
    }


def _frame(kind, keys):
    return {
        "timestamp": time.time(),
        "source": "local-system" if kind == "local_system" else "local-ollama",
        "source_kind": kind,
        "status": "ok",
        "metrics": {key: _metric(key) for key in keys},
    }


def collect_system() -> dict:
    """Backend host memory, not GPU memory and not macOS memory-pressure state."""
    frame = _frame("local_system", [key for key in LOCAL_UNITS if key.startswith("host_")])
    groups = [
        (
            psutil.virtual_memory,
            {"host_memory_total_bytes": "total", "host_memory_available_bytes": "available"},
        ),
        (psutil.swap_memory, {"host_swap_total_bytes": "total", "host_swap_used_bytes": "used"}),
    ]
    for read, fields in groups:
        try:
            values = read()
            total = getattr(values, "total", None)
            for key, field in fields.items():
                value = getattr(values, field, None)
                if type(total) is int and type(value) is int and value > total:
                    value = None
                frame["metrics"][key] = _metric(key, value, "invalid_value", field=f"psutil_{field}")
        except (OSError, RuntimeError, NotImplementedError):
            for key in fields:
                frame["metrics"][key] = _metric(key, reason="system_unavailable")
    if all(metric["value"] is None for metric in frame["metrics"].values()):
        frame.update(status="error", error="system_unavailable")
    return frame


def _reject_constant(_value):
    raise ValueError("invalid_response")


def _read_ps(endpoint, timeout_s):
    url = local_ollama_url(endpoint["base_url"])
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    if endpoint.get("api_key_env"):
        key = os.environ.get(endpoint["api_key_env"])
        if not key:
            raise ValueError("missing_api_key")
        headers["Authorization"] = f"Bearer {key}"
    deadline = time.monotonic() + timeout_s
    with (
        httpx.Client(timeout=timeout_s, follow_redirects=False, trust_env=False) as client,
        client.stream("GET", url, headers=headers) as response,
    ):
        if 300 <= response.status_code < 400:
            raise ValueError("redirect_rejected")
        if not 200 <= response.status_code < 300:
            raise ValueError(f"http_{response.status_code}")
        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise ValueError("unsupported_encoding")
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_RESPONSE_BYTES:
            raise ValueError("response_too_large")
        body = bytearray()
        for chunk in response.iter_raw():
            if time.monotonic() >= deadline:
                raise ValueError("timeout")
            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise ValueError("response_too_large")
            body.extend(chunk)
        if time.monotonic() >= deadline:
            raise ValueError("timeout")
    return json.loads(body.decode("utf-8"), parse_constant=_reject_constant)


def collect_ollama(endpoint: dict, timeout_s: float = 2.0) -> dict:
    """GET only the configured service's running-model metadata; never infer cache occupancy."""
    fields = {"model_memory_bytes": "size_vram", "model_context_tokens": "context_length"}
    frame = _frame("local_ollama", fields)
    reason = None
    try:
        data = _read_ps(endpoint, timeout_s)
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise TypeError("invalid_response")
        if any(not isinstance(model, dict) for model in data["models"]):
            raise ValueError("invalid_response")
        matches = [model for model in data["models"] if model.get("name") == endpoint["model"]]
        if not matches:
            reason = "model_not_loaded"
        elif len(matches) > 1:
            raise ValueError("ambiguous_model")
        else:
            model = matches[0]
            for key, field in fields.items():
                frame["metrics"][key] = _metric(
                    key,
                    model.get(field),
                    "invalid_value" if field in model else "field_unavailable",
                    field=field,
                    labels={"model": endpoint["model"]},
                )
    except httpx.TimeoutException:
        reason = "timeout"
    except httpx.HTTPError:
        reason = "network_error"
    except (ValueError, TypeError, UnicodeError, RecursionError, KeyError) as error:
        allowed = {
            "redirect_rejected",
            "unsupported_encoding",
            "response_too_large",
            "timeout",
            "missing_api_key",
            "ambiguous_model",
        }
        message = str(error)
        reason = (
            message
            if message in allowed or (message.startswith("http_") and message[5:].isdigit())
            else "invalid_response"
        )
    if reason:
        frame["metrics"] = {key: _metric(key, reason=reason) for key in fields}
        if reason != "model_not_loaded":
            frame.update(status="error", error=reason)
    return frame
