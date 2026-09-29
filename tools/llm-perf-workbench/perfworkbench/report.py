"""Standalone shareable exports built from an allowlist, never raw run serialization."""

import hashlib
import html
import json
import math
import re

from .analysis import METRIC_DEFINITIONS

_DISTRIBUTIONS = {"ttft_ms", "tpot_ms", "e2e_ms", "inter_chunk_ms"}
_SCALARS = {
    "duration_s",
    "requests_per_s",
    "actual_sent_per_s",
    "offered",
    "target_rate",
    "input_tokens_per_s",
    "output_tokens_per_s",
    "goodput_per_s",
    "error_rate",
    "sent",
    "succeeded",
    "failed",
    "client_rejected",
    "interrupted",
}
_GOALS = {
    "min_requests_per_s",
    "max_p95_e2e_ms",
    "max_p95_ttft_ms",
    "max_p95_tpot_ms",
    "min_quality_pass_rate",
    "max_error_rate",
    "deadline_s",
}
_DIAGNOSTICS = {
    "insufficient_evidence": "Insufficient evidence; collect corroborating measurements.",
    "service_errors": "Service failures require investigation before performance tuning.",
    "queueing": "Queueing is a candidate contributor; verify time alignment and repeat.",
    "kv_pressure": "KV pressure is a candidate only with corroborating queue and preemption evidence.",
    "admission_rejection": "Client admission rejected measured arrivals; inspect client load bounds.",
    "generator_shortfall": "Observed dispatch rate is below the configured arrival rate.",
}

_ENV_NUMERIC = {
    "device_count",
    "gpu_count",
    "num_gpus",
    "num_devices",
    "tensor_parallel_size",
    "pipeline_parallel_size",
    "data_parallel_size",
    "max_model_len",
    "max_num_seqs",
    "max_num_batched_tokens",
    "gpu_memory_utilization",
    "device_memory_bytes",
    "memory_gb",
}
_ENV_ENUMS = {
    "precision": {"fp32", "fp16", "bf16", "fp8", "int8", "int4"},
    "dtype": {"float32", "float16", "bfloat16", "fp32", "fp16", "bf16", "fp8", "int8", "int4"},
    "engine": {"vllm", "sglang", "tgi", "trtllm", "llamacpp"},
    "device_type": {"cpu", "gpu", "cuda", "npu", "ascend", "nvidia"},
    "quantization": {"none", "fp8", "int8", "int4", "awq", "gptq"},
}
_LOAD_FIELDS = {"mode", "concurrency", "rate", "count", "warmup", "repeats", "seed", "scan", "mix"}
_GEN_FIELDS = {"stream", "max_tokens", "temperature", "top_p", "extra"}
_EXTRA_NUMERIC = {"top_k", "repetition_penalty", "presence_penalty", "frequency_penalty", "seed"}
_QUALITY_FIELDS = {"mode", "min_chars", "require_json", "json_fields", "required_text", "reject_truncated"}
_SAFETY_FIELDS = {
    "max_requests",
    "max_concurrency",
    "max_duration_s",
    "request_timeout_s",
    "max_output_tokens",
    "max_response_bytes",
}
_CHANGE_PATHS = {
    "dataset",
    "endpoint.model",
    "endpoint.context_length",
    "endpoint.environment",
    "cache_condition",
    "tokenizer_path",
    "telemetry",
    "telemetry.interval_s",
    "telemetry.sources",
    "telemetry.local",
    "telemetry.local.enabled",
}
for _parent, _fields in (
    ("load", _LOAD_FIELDS),
    ("generation", _GEN_FIELDS),
    ("quality", _QUALITY_FIELDS),
    ("goals", _GOALS | {"mode", "target_requests"}),
    ("safety", _SAFETY_FIELDS),
    ("endpoint.environment", _ENV_NUMERIC | _ENV_ENUMS.keys()),
):
    _CHANGE_PATHS.add(_parent)
    _CHANGE_PATHS.update(f"{_parent}.{field}" for field in _fields)
_CHANGE_PATHS.update(f"generation.extra.{field}" for field in _EXTRA_NUMERIC | {"enable_thinking"})
_RETEST_METRICS = {
    "requests_per_s",
    "input_tokens_per_s",
    "output_tokens_per_s",
    "goodput_per_s",
    "error_rate",
}
_RETEST_METRICS.update(
    f"{metric}.{stat}" for metric in _DISTRIBUTIONS for stat in ("mean", "p50", "p95", "p99")
)
_TELEMETRY = {
    "queue_waiting": ("requests", "gauge"),
    "requests_running": ("requests", "gauge"),
    "kv_cache_usage_ratio": ("ratio", "gauge"),
    "preemptions_total": ("events", "counter"),
    "prefix_hits_total": ("tokens", "counter"),
    "prefix_queries_total": ("tokens", "counter"),
    "device_utilization_ratio": ("ratio", "gauge"),
    "device_memory_used_bytes": ("bytes", "gauge"),
    "device_memory_total_bytes": ("bytes", "gauge"),
    "host_memory_total_bytes": ("bytes", "gauge"),
    "host_memory_available_bytes": ("bytes", "gauge"),
    "host_swap_used_bytes": ("bytes", "gauge"),
    "host_swap_total_bytes": ("bytes", "gauge"),
    "model_memory_bytes": ("bytes", "gauge"),
    "model_context_tokens": ("tokens", "gauge"),
}
_ADVICE = {
    "insufficient_evidence": (
        "Collect complete measured requests and aligned resource telemetry.",
        "Missing data cannot establish a bottleneck or an optimization.",
        "Verify quality and timing coverage, then repeat with one recorded change.",
    ),
    "service_errors": (
        "Inspect private failure categories and service health before changing load.",
        "Service failures reduce useful throughput; error bodies may contain private data.",
        "Repeat the aligned workload and require error, quality, and performance goals to pass.",
    ),
    "queueing": (
        "Inspect arrival rate, admission, and scheduling; change one bounded load setting.",
        "Client TTFT also includes transport and prefill; queueing is not an isolated root cause.",
        "Align queue observations with TTFT and retest quality and goodput under the same constraints.",
    ),
    "kv_pressure": (
        "Inspect KV allocation, request lengths, and scheduler preemption before changing one setting.",
        "High occupancy alone is normal; summary counter values do not prove pressure or exclude resets.",
        "Verify same-source stable series, no resets or gaps, and co-observed queue pressure; then retest.",
    ),
    "admission_rejection": (
        "Inspect client concurrency bounds and arrival scheduling; test one declared load change.",
        "Client rejection is not a service failure or a server root cause.",
        "Compare offered, sent, rejected, quality, and completion rates within the same safety bounds.",
    ),
    "generator_shortfall": (
        "Inspect generator scheduling, transport, and admission using measured request-start evidence.",
        "Start-span rate and completion throughput have different windows; shortfall does not isolate a root cause.",
        "Repeat with enough starts and compare target arrivals, actual sends, rejection, and completion rates.",
    ),
}


def _number(value, *, signed=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and (signed or value >= 0) else None
    except OverflowError:
        return None


def _enum(value, choices, default="unknown"):
    return value if isinstance(value, str) and value in choices else default


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _bool(value):
    return value if isinstance(value, bool) else None


def _hex(value, length=None):
    pattern = rf"[a-fA-F0-9]{{{length}}}" if length else r"[a-fA-F0-9]{1,128}"
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else None


def _sha256(value):
    if value is None:
        return None
    try:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError, OverflowError):
        return None
    return hashlib.sha256(data).hexdigest()


def _environment(spec):
    endpoint = _dict(spec.get("endpoint"))
    environment = _dict(endpoint.get("environment"))
    return {
        "model_sha256": _sha256(endpoint.get("model")),
        "environment_sha256": _sha256(endpoint.get("environment")),
        "context_length": _number(endpoint.get("context_length")),
        "declaration_source": "experiment_spec",
        "verification": "user_declared",
        "settings": {
            **{key: _number(environment.get(key)) for key in sorted(_ENV_NUMERIC) if key in environment},
            **{
                key: _enum(environment.get(key), values)
                for key, values in _ENV_ENUMS.items()
                if key in environment
            },
        },
    }


def _profile(raw, spec, aliases):
    profile = _dict(raw)
    dataset_hash = _sha256(spec.get("dataset"))
    result = {
        "dataset_sha256": dataset_hash,
        "profile_sha256": _sha256(raw),
        "version": _hex(profile.get("version"), 64) or dataset_hash,
        "sample_count": _number(profile.get("sample_count"))
        if "sample_count" in profile
        else len(spec["dataset"])
        if isinstance(spec.get("dataset"), list)
        else None,
        "prompt_hashes": [value for item in _list(profile.get("prompt_hashes")) if (value := _hex(item, 64))],
        "token_count_source": _enum(
            profile.get("token_count_source"), {"unavailable", "local_tokenizer_chat_template"}
        ),
        "duplicate_prompts": _number(profile.get("duplicate_prompts")),
        "shared_prefix_chars": _number(profile.get("shared_prefix_chars")),
        "categories": {
            aliases[key]: _number(value)
            for key, value in _dict(profile.get("categories")).items()
            if key in aliases
        },
        "declaration_source": "stored_profile" if profile else "experiment_spec",
    }
    for key in ("characters", "input_tokens"):
        distribution = profile.get(key)
        result[key] = (
            {
                name: _number(distribution.get(name))
                for name in ("count", "min", "max", "mean", "p50", "p95", "p99")
            }
            if isinstance(distribution, dict)
            else None
        )
    return result


def _latest_resource(frame):
    """Current sample, not the last successful sample; only allowlisted values leave the host."""
    metrics = {}
    reasons = {
        "model_not_loaded",
        "field_unavailable",
        "invalid_value",
        "invalid_response",
        "ambiguous_model",
        "missing_api_key",
        "timeout",
        "network_error",
        "system_unavailable",
        "redirect_rejected",
        "response_too_large",
        "unsupported_encoding",
        "metric_not_found",
        "labels_not_matched",
        "non_finite_value",
        "ratio_out_of_range",
        "negative_counter",
        "duplicate_series",
        "counter_reset",
        "counter_unavailable",
        "series_changed",
    }
    for key, (unit, _) in _TELEMETRY.items():
        raw_entry = _dict(frame.get("metrics")).get(key)
        entry = _dict(raw_entry)
        value = _number(entry.get("value") if isinstance(raw_entry, dict) else raw_entry)
        if (
            frame.get("error")
            or frame.get("status") == "error"
            or entry.get("status", "available") != "available"
        ):
            value = None
        if value is not None and unit == "ratio" and value > 1:
            value = None
        reason = entry.get("reason") or frame.get("error")
        if not isinstance(reason, str) or (
            reason not in reasons and not re.fullmatch(r"http_[1-5][0-9]{2}", reason)
        ):
            reason = "unavailable"
        metrics[key] = {"value": value, "unit": unit, "reason": None if value is not None else reason}
    return {"timestamp": _number(frame.get("timestamp")), "metrics": metrics}


def _telemetry_summary(raw):
    frames = _list(raw) if isinstance(raw, list) else _list(_dict(raw).get("samples"))
    groups = {}
    for frame in frames:
        frame = _dict(frame)
        kind = _enum(frame.get("source_kind"), {"local_system", "local_ollama"}, "prometheus")
        identity = _sha256([kind, frame.get("source")])
        groups.setdefault((kind, identity), []).append(frame)
    sources = []
    for (source_kind, identity), samples in groups.items():
        metrics = {}
        for key, (unit, kind) in _TELEMETRY.items():
            values = []
            for frame in samples:
                entry = _dict(frame.get("metrics")).get(key)
                if frame.get("error") or frame.get("status") == "error":
                    continue
                if isinstance(entry, dict):
                    entry = entry.get("value") if entry.get("status", "available") == "available" else None
                value = _number(entry)
                if value is not None and (unit != "ratio" or value <= 1):
                    values.append(value)
            metrics[key] = {
                "count": len(values),
                "missing": len(samples) - len(values),
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "mean": _number(sum(value / len(values) for value in values)) if values else None,
                "last": values[-1] if values else None,
                "unit": unit,
                "kind": kind,
            }
        sources.append(
            {
                "source_sha256": identity,
                "source_kind": source_kind,
                "sample_count": len(samples),
                "error_count": sum(
                    bool(frame.get("error")) or frame.get("status") == "error" for frame in samples
                ),
                "metrics": metrics,
                "latest": _latest_resource(samples[-1]),
            }
        )
    return {
        "sample_count": len(frames),
        "sources": sources,
        "definition": "Per-source observed values over the collection lifetime, including possible warmup. "
        "Counter summaries are absolute readings, not rates or validated deltas. Missing samples stay explicit. "
        "Summary last is the last valid historical value; latest is the final sample including missing values. "
        "Local system memory belongs to the workbench host. Model memory is Ollama size_vram, not device-wide "
        "memory or KV occupancy; model context is configured capacity, not usage.",
    }


def _differences(raw):
    result = []
    seen = set()
    for entry in _list(raw):
        entry = _dict(entry)
        field = _enum(entry.get("field"), _CHANGE_PATHS, None)
        if field is not None:
            safe = {
                "run_id": _hex(entry.get("run_id")),
                "field": field,
                "before": _number(entry.get("before")),
                "after": _number(entry.get("after")),
            }
            identity = tuple(safe.values())
            if identity not in seen:
                result.append(safe)
                seen.add(identity)
    return result


def _retest(raw, run):
    if not isinstance(raw, dict) or not raw:
        return None
    criterion = _dict(raw.get("criterion"))
    result = _dict(raw.get("result")) if "result" in raw else raw
    declaration = _dict(criterion.get("change"))
    safe_criterion = {
        "metric": _enum(criterion.get("metric"), _RETEST_METRICS),
        "direction": _enum(criterion.get("direction"), {"increase", "decrease"}),
        "min_relative_change": _number(criterion.get("min_relative_change", 0)),
    }
    field = _enum(declaration.get("field"), {"load.concurrency", "load.rate"}, None)
    changed_fields = {entry["field"] for entry in _differences(result.get("differences"))}
    changed_fields.update(entry["field"] for entry in _differences(raw.get("differences")))
    if field:
        safe_criterion["change"] = {
            "field": field,
            "before": _number(declaration.get("before")),
            "after": _number(declaration.get("after")),
        }
        changed_fields.add(field)
    allowed = [
        path
        for path in _list(criterion.get("allowed_changes"))
        if isinstance(path, str) and path in _CHANGE_PATHS
    ]
    if allowed:
        safe_criterion["allowed_changes"] = allowed
    baseline_id = _hex(raw.get("baseline_id"))
    candidate_id = _hex(raw.get("candidate_id", run.get("id")))
    status = _enum(
        result.get("status"), {"effective", "ineffective", "insufficient_evidence"}, "insufficient_evidence"
    )
    if _dict(run.get("spec")).get("protocol_fixture") or (
        status == "effective"
        and (
            not baseline_id
            or not candidate_id
            or "unknown" in (safe_criterion["metric"], safe_criterion["direction"])
            or safe_criterion["min_relative_change"] is None
        )
    ):
        status = "insufficient_evidence"
    return {
        "baseline_id": baseline_id,
        "candidate_id": candidate_id,
        "criterion": safe_criterion,
        "result": {
            "status": status,
            "change": _number(result.get("change"), signed=True),
            "before": _number(result.get("before")),
            "after": _number(result.get("after")),
        },
        "changed_fields": sorted(changed_fields),
        "verification_source": "recorded_retest",
        "limitation": "Saved assessment, not a new benchmark or independent re-evaluation. "
        "Protocol fixtures cannot prove optimization; missing evidence remains unknown.",
    }


def _diagnostics(raw, summary, telemetry):
    result = []
    evidence_metrics = {
        "insufficient_evidence": ("sent", "succeeded"),
        "service_errors": ("failed", "error_rate"),
        "queueing": ("ttft_ms",),
        "kv_pressure": ("ttft_ms",),
        "admission_rejection": ("offered", "sent", "client_rejected", "actual_sent_per_s"),
        "generator_shortfall": ("target_rate", "actual_sent_per_s", "client_rejected"),
    }
    for entry in _list(raw):
        identifier = _enum(_dict(entry).get("id"), _DIAGNOSTICS, None)
        if identifier is None:
            continue
        evidence = []
        for metric in evidence_metrics[identifier]:
            value = summary["metrics"].get(metric)
            value = value.get("p95") if isinstance(value, dict) else value
            evidence.append(
                {
                    "metric": metric + ".p95" if metric in _DISTRIBUTIONS else metric,
                    "value": _number(value),
                    "source": "measured_summary",
                }
            )
        if identifier in {"queueing", "kv_pressure"}:
            keys = (
                ("queue_waiting",)
                if identifier == "queueing"
                else ("queue_waiting", "kv_cache_usage_ratio", "preemptions_total")
            )
            for source in telemetry["sources"]:
                for key in keys:
                    evidence.append(
                        {
                            "metric": key + ".max",
                            "value": source["metrics"][key]["max"],
                            "source": source["source_sha256"],
                        }
                    )
        adjustment, risk, validation = _ADVICE[identifier]
        result.append(
            {
                "id": identifier,
                "title": _DIAGNOSTICS[identifier],
                "evidence": evidence,
                "confidence": "low",
                "adjustment": adjustment,
                "risk": risk,
                "validation": validation,
                "status": "pending",
            }
        )
    return result


def _metrics(source):
    result = {key: _number(source.get(key)) for key in sorted(_SCALARS)}
    for key in sorted(_DISTRIBUTIONS):
        distribution = source.get(key)
        distribution = distribution if isinstance(distribution, dict) else {}
        result[key] = {
            name: _number(distribution.get(name)) for name in ("count", "mean", "p50", "p95", "p99")
        }
    return result


def _safe_spec(spec):
    load, generation, quality = (spec.get(key) or {} for key in ("load", "generation", "quality"))
    extra = _dict(generation.get("extra"))
    return {
        "protocol_fixture": spec.get("protocol_fixture") is True,
        "dataset_sample_count": len(spec.get("dataset") or []),
        "cache_condition": _enum(spec.get("cache_condition"), {"unknown", "declared_cold", "declared_warm"}),
        "load": {
            "mode": _enum(load.get("mode"), {"concurrency", "rate"}),
            **{
                key: _number(load.get(key))
                for key in ("concurrency", "rate", "count", "warmup", "repeats", "seed")
            },
        },
        "generation": {
            "stream": generation.get("stream") if isinstance(generation.get("stream"), bool) else None,
            **{key: _number(generation.get(key)) for key in ("max_tokens", "temperature", "top_p")},
            "extra": {
                **{
                    key: _number(extra.get(key), signed=key in {"presence_penalty", "frequency_penalty"})
                    for key in sorted(_EXTRA_NUMERIC)
                    if key in extra
                },
                **(
                    {"enable_thinking": _bool(extra.get("enable_thinking"))}
                    if "enable_thinking" in extra
                    else {}
                ),
            },
            "extra_sha256": _sha256(generation.get("extra")),
        },
        "quality": {
            "mode": _enum(quality.get("mode"), {"rules", "manual", "none"}),
            "min_chars": _number(quality.get("min_chars")),
            "require_json": _bool(quality.get("require_json")),
            "reject_truncated": _bool(quality.get("reject_truncated")),
            "json_field_count": len(_list(quality.get("json_fields"))),
            "required_text_count": len(_list(quality.get("required_text"))),
            "rules_sha256": _sha256(spec.get("quality")),
        },
        "goals": {
            "mode": _enum(_dict(spec.get("goals")).get("mode"), {"online", "offline"}),
            **{
                key: _number(_dict(spec.get("goals")).get(key))
                for key in sorted(_GOALS | {"target_requests"})
            },
        },
        "safety": {key: _number(_dict(spec.get("safety")).get(key)) for key in sorted(_SAFETY_FIELDS)},
        "telemetry": {
            "local": {
                "enabled": _bool(_dict(_dict(spec.get("telemetry")).get("local")).get("enabled", False))
            }
        },
    }


def _safe_run(run):
    summary, spec = run.get("summary") or {}, run.get("spec") or {}
    quality = summary.get("quality") or {}
    categories = _dict(_dict(run.get("profile")).get("categories"))
    groups = _dict(summary.get("groups"))
    aliases = {
        key: f"category_{index}"
        for index, key in enumerate(
            sorted(key for key in categories.keys() | groups.keys() if isinstance(key, str)), 1
        )
    }
    identifier = run.get("id")
    safe_id = (
        identifier
        if isinstance(identifier, str) and re.fullmatch(r"[a-fA-F0-9]{1,128}", identifier)
        else "redacted"
    )
    warnings = [
        "Free-form source text is omitted. Category labels are replaced with numbered aliases.",
        "Use the private local run identifier for raw-record traceability; this export contains no raw records.",
    ]
    if spec.get("protocol_fixture"):
        warnings.append("Protocol fixture only: cannot prove model performance or optimization.")
    if summary.get("warnings"):
        warnings.append(
            "Source analysis has warnings; free-form details are omitted from this shareable export."
        )
    metrics = _metrics(summary.get("metrics") or {})
    for field in sorted(_SCALARS):
        if metrics[field] is None:
            warnings.append(f"{field} is unknown; missing data must not be interpreted as zero.")
    if run.get("error"):
        warnings.append("A run error was recorded; exception details are omitted.")
    safe = {
        "id": safe_id,
        "status": _enum(
            run.get("status"),
            {"queued", "running", "completed", "cancelled", "failed", "partial", "interrupted", "timed_out"},
        ),
        "spec": _safe_spec(spec),
        "summary": {
            "sample_count": _number(summary.get("sample_count")),
            "metrics": metrics,
            "quality": {
                key: _number(quality.get(key)) for key in ("pass", "fail", "unknown", "coverage", "pass_rate")
            },
            "goals": [
                {
                    "name": goal["name"],
                    "target": _number(goal.get("target")),
                    "actual": _number(goal.get("actual")),
                    "status": _enum(goal.get("status"), {"pass", "fail", "unknown"}),
                }
                for goal in (summary.get("goals") or [])
                if goal.get("name") in _GOALS
            ],
            "groups": {
                aliases[key]: _metrics(_dict(values)) for key, values in groups.items() if key in aliases
            },
            "definitions": dict(METRIC_DEFINITIONS),
            "warnings": warnings,
        },
    }
    safe["parent_id"] = _hex(run.get("parent_id"))
    safe["environment"] = _environment(spec)
    safe["profile"] = _profile(run.get("profile"), spec, aliases)
    safe["telemetry"] = _telemetry_summary(run.get("telemetry"))
    safe["retest"] = _retest(run.get("retest"), run)
    differences = _list(run.get("differences")) + _list(_dict(run.get("comparison")).get("differences"))
    retest = _dict(run.get("retest"))
    differences += _list(retest.get("differences")) + _list(_dict(retest.get("result")).get("differences"))
    declaration = _dict(_dict(_dict(safe["retest"]).get("criterion")).get("change"))
    if declaration:
        differences.append({"run_id": _hex(run.get("id")), **declaration})
    safe["differences"] = _differences(differences)
    safe["diagnostics"] = _diagnostics(run.get("diagnostics"), safe["summary"], safe["telemetry"])
    warnings.append(
        "SHA256 fingerprints support matching; they are not encryption or proof of hardware verification."
    )
    return safe


def _display(value):
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return format(value, ".6g")
    return str(value)


def _rows(value, prefix=""):
    """Flatten already-sanitized data for human tables, never traverse raw input."""
    rows = []
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            rows.extend(_rows(item, name))
        elif isinstance(item, list):
            rows.append((name, ", ".join(_display(entry) for entry in item) or "none"))
        else:
            rows.append((name, item))
    return rows


def _sections(safe):
    summary = safe["summary"]
    sections = [
        ("Run", ("Field", "Value"), [(key, safe[key]) for key in ("id", "parent_id", "status")]),
        ("Environment", ("Field", "Value"), _rows(safe["environment"])),
        ("Dataset profile", ("Field", "Value"), _rows(safe["profile"])),
        ("Configuration", ("Field", "Value"), _rows(safe["spec"])),
        (
            "Measured performance",
            ("Metric", "Value"),
            [(key, summary["metrics"][key]) for key in sorted(_SCALARS)],
        ),
        (
            "Latency distributions",
            ("Metric", "Unit", "Count", "Mean", "p50", "p95", "p99"),
            [
                (
                    key,
                    "ms/token" if key == "tpot_ms" else "ms",
                    *(summary["metrics"][key][stat] for stat in ("count", "mean", "p50", "p95", "p99")),
                )
                for key in sorted(_DISTRIBUTIONS)
            ],
        ),
        ("Quality", ("Field", "Value"), _rows(summary["quality"])),
        (
            "Goals",
            ("Goal", "Target", "Actual", "Status"),
            [(goal["name"], goal["target"], goal["actual"], goal["status"]) for goal in summary["goals"]],
        ),
        (
            "Categories",
            ("Alias", "Sent", "Succeeded", "Actual sent/s", "Completed requests/s"),
            [
                (key, value["sent"], value["succeeded"], value["actual_sent_per_s"], value["requests_per_s"])
                for key, value in summary["groups"].items()
            ],
        ),
    ]
    telemetry_rows = []
    for source in safe["telemetry"]["sources"]:
        for key, value in source["metrics"].items():
            telemetry_rows.append(
                (
                    source["source_sha256"],
                    key,
                    value["unit"],
                    value["kind"],
                    value["count"],
                    value["missing"],
                    value["min"],
                    value["max"],
                    value["mean"],
                    value["last"],
                )
            )
    sections.extend(
        [
            (
                "Telemetry sources",
                ("Source SHA256", "Source kind", "Sample count", "Error count"),
                [
                    (
                        source["source_sha256"],
                        source["source_kind"],
                        source["sample_count"],
                        source["error_count"],
                    )
                    for source in safe["telemetry"]["sources"]
                ],
            ),
            (
                "Telemetry",
                (
                    "Source SHA256",
                    "Metric",
                    "Unit",
                    "Kind",
                    "Count",
                    "Missing",
                    "Min",
                    "Max",
                    "Mean",
                    "Last valid (historical)",
                ),
                telemetry_rows,
            ),
            (
                "Latest telemetry",
                (
                    "Source SHA256",
                    "Source kind",
                    "Timestamp (Unix seconds, UTC)",
                    "Metric",
                    "Unit",
                    "Value",
                    "Reason",
                ),
                [
                    (
                        source["source_sha256"],
                        source["source_kind"],
                        # Do not round epoch seconds through the generic .6g metric formatter.
                        str(source["latest"]["timestamp"])
                        if source["latest"]["timestamp"] is not None
                        else None,
                        key,
                        value["unit"],
                        value["value"],
                        value["reason"],
                    )
                    for source in safe["telemetry"]["sources"]
                    for key, value in source["latest"]["metrics"].items()
                ],
            ),
            (
                "Telemetry interpretation",
                ("Field", "Value"),
                [
                    ("Definition", safe["telemetry"]["definition"]),
                    ("Sample count", safe["telemetry"]["sample_count"]),
                ],
            ),
            (
                "Configuration differences",
                ("Run", "Changed field", "Before", "After"),
                [(row["run_id"], row["field"], row["before"], row["after"]) for row in safe["differences"]],
            ),
        ]
    )
    advice_rows = []
    for diagnosis in safe["diagnostics"]:
        evidence = "; ".join(
            f"{item['metric']}={_display(item['value'])} (source: {_display(item['source'])})"
            for item in diagnosis["evidence"]
        )
        advice_rows.append(
            (
                diagnosis["id"],
                evidence,
                diagnosis["adjustment"],
                diagnosis["risk"],
                diagnosis["validation"],
                diagnosis["status"],
            )
        )
    sections.extend(
        [
            (
                "Recommendations and verification",
                ("Candidate", "Evidence", "Adjustment", "Risk", "Validation", "Status"),
                advice_rows,
            ),
            (
                "Retest",
                ("Field", "Value"),
                _rows(safe["retest"]) if safe["retest"] else [("Evidence", "No saved retest evidence.")],
            ),
            ("Metric definitions", ("Metric", "Definition"), list(summary["definitions"].items())),
            ("Limitations", ("Notice",), [(warning,) for warning in summary["warnings"]]),
        ]
    )
    return sections


def export_report(run: dict, fmt="markdown") -> str:
    """Export only typed metrics and known vocabulary; unknown fields fail closed.

    Free text is replaced with identity hashes, known enums, numeric fields, and
    canonical advice. HTML escapes every table cell; no external resources/scripts.
    """
    if fmt not in {"markdown", "json", "html"}:
        raise ValueError("Unsupported report format; choose markdown, json or html")
    safe = _safe_run(run)
    if fmt == "json":
        return json.dumps(safe, ensure_ascii=False, indent=2, allow_nan=False)
    sections = _sections(safe)
    if fmt == "markdown":
        output = [
            "# LLM performance workbench report",
            "",
            "Redacted evidence snapshot; unknown is not zero.",
            "",
        ]
        for title, headers, rows in sections:
            output.extend(
                [
                    f"## {title}",
                    "",
                    "| " + " | ".join(headers) + " |",
                    "| " + " | ".join("---" for _ in headers) + " |",
                ]
            )
            for row in rows or [("No recorded evidence",) + (None,) * (len(headers) - 1)]:
                output.append(
                    "| "
                    + " | ".join(
                        html.escape(_display(cell)).replace("|", "&#124;").replace("\n", " ") for cell in row
                    )
                    + " |"
                )
            output.append("")
        return "\n".join(output)
    body = [
        "<h1>LLM performance workbench report</h1><p>Redacted evidence snapshot; unknown is not zero.</p>"
    ]
    for title, headers, rows in sections:
        body.append("<section><h2>" + html.escape(title) + "</h2><div class=table-wrap><table><thead><tr>")
        body.extend('<th scope="col">' + html.escape(header) + "</th>" for header in headers)
        body.append("</tr></thead><tbody>")
        for row in rows or [("No recorded evidence",) + (None,) * (len(headers) - 1)]:
            body.append(
                "<tr>"
                + "".join("<td>" + html.escape(_display(cell), quote=True) + "</td>" for cell in row)
                + "</tr>"
            )
        body.append("</tbody></table></div></section>")
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>LLM performance workbench report</title>"
        "<style>body{max-width:80rem;margin:2rem auto;padding:1rem;font-family:system-ui;line-height:1.5}"
        ".table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;margin-bottom:1.5rem}"
        "th,td{text-align:left;vertical-align:top;padding:.5rem;border:1px solid #ccc;overflow-wrap:anywhere}"
        "th{background:#edf3f2}h2{margin-top:2rem}</style>"
        "</head><body><main>" + "".join(body) + "</main></body></html>"
    )
