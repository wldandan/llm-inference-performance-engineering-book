#!/usr/bin/env python3
"""Build and validate a reproducible LLM workload description.

This Demo only *describes* a workload. It never sends a request and never
produces a performance number. Chapter 7 is what turns this description into
a Baseline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROFILES = ("chat", "rag", "agent")
ARRIVALS = ("closed", "constant", "poisson", "burst", "ramp")
QUANTILES = ("p50", "p90", "p99", "max")
# SLO quantiles are a different set: 6.6 writes SLOs at P95, which is not one
# of the length quantiles above.
SLO_QUANTILES = ("p50", "p90", "p95", "p99")

# Starting points only. Real numbers must come from production logs or from
# running a tokenizer over real samples (see 6.2).
DEFAULT_LENGTH = {
    "chat": {
        "prompt": {"p50": 180, "p90": 640, "p99": 7200, "max": 12000},
        "output": {"p50": 210, "p90": 520, "p99": 1100, "max": 2048},
    },
    "rag": {
        "prompt": {"p50": 1300, "p90": 3400, "p99": 9000, "max": 16000},
        "output": {"p50": 240, "p90": 560, "p99": 1200, "max": 2048},
    },
    "agent": {
        "prompt": {"p50": 900, "p90": 2600, "p99": 8800, "max": 16000},
        "output": {"p50": 160, "p90": 420, "p99": 900, "max": 2048},
    },
}

DEFAULT_AGENT_STEPS = {"p50": 4, "p90": 12, "p99": 26, "max": 40, "mean": 5.0}


class WorkloadError(ValueError):
    """Raised when a workload description is not self-consistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkloadError(message)


def _check_quantiles(where: str, block: object) -> None:
    _require(isinstance(block, dict), f"{where} must be an object")
    assert isinstance(block, dict)
    for name in QUANTILES:
        _require(name in block, f"{where} is missing {name}")
        value = block[name]
        _require(
            isinstance(value, (int, float)) and not isinstance(value, bool),
            f"{where}.{name} must be a number",
        )
        _require(value > 0, f"{where}.{name} must be positive")
    ordered = [block[name] for name in QUANTILES]
    for earlier, later, a, b in zip(ordered, ordered[1:], QUANTILES, QUANTILES[1:]):
        _require(
            earlier <= later,
            f"{where} quantiles must be non-decreasing, but {a}={earlier} > {b}={later}",
        )


def validate_workload(doc: object) -> None:
    """Raise WorkloadError unless *doc* is a self-consistent description.

    Chapter 7's ``run_baseline.py`` reuses this function, so every rule added
    here also gates Baseline runs.
    """
    _require(isinstance(doc, dict), "workload must be an object")
    assert isinstance(doc, dict)

    for block in ("identity", "length", "arrival", "slo"):
        _require(block in doc, f"missing required block: {block}")

    identity = doc["identity"]
    _require(isinstance(identity, dict), "identity must be an object")
    for field in ("name", "type", "source"):
        value = identity.get(field)
        _require(
            isinstance(value, str) and value.strip() != "",
            f"identity.{field} must be a non-empty string",
        )
    _require(
        identity["type"] in PROFILES,
        f"identity.type must be one of {PROFILES}, got {identity['type']!r}",
    )

    length = doc["length"]
    _require(isinstance(length, dict), "length must be an object")
    for side in ("prompt", "output"):
        _require(side in length, f"length is missing {side}")
        _check_quantiles(f"length.{side}", length[side])

    arrival = doc["arrival"]
    _require(isinstance(arrival, dict), "arrival must be an object")
    mode = arrival.get("mode")
    _require(mode in ARRIVALS, f"arrival.mode must be one of {ARRIVALS}, got {mode!r}")
    if mode in ("constant", "poisson", "burst", "ramp"):
        rate = arrival.get("rate")
        _require(
            isinstance(rate, (int, float)) and not isinstance(rate, bool) and rate > 0,
            f"arrival.mode={mode} is open-loop and requires a positive rate",
        )
    if mode == "closed":
        concurrency = arrival.get("concurrency")
        _require(
            isinstance(concurrency, int)
            and not isinstance(concurrency, bool)
            and concurrency > 0,
            "arrival.mode=closed is closed-loop and requires a positive concurrency",
        )
        _require(
            "rate" not in arrival,
            "arrival.mode=closed must not set a rate: under closed loop the rate is "
            "an outcome, not an input (6.4)",
        )
    duration = arrival.get("duration_s")
    _require(
        isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and duration > 0,
        "arrival.duration_s must be a positive number",
    )
    seed = arrival.get("seed")
    _require(
        isinstance(seed, int) and not isinstance(seed, bool),
        "arrival.seed must be recorded, otherwise two runs of the same config "
        "generate different requests (6.7)",
    )

    slo = doc["slo"]
    _require(isinstance(slo, dict), "slo must be an object")
    metric = slo.get("metric")
    _require(
        isinstance(metric, str) and metric.strip() != "",
        "slo.metric must be a non-empty string",
    )
    quantile = slo.get("quantile")
    _require(
        isinstance(quantile, str) and quantile in SLO_QUANTILES,
        f"slo.quantile is required and must be one of {'/'.join(SLO_QUANTILES)}: "
        "a threshold without a quantile does not say what it applies to (6.6)",
    )
    threshold = slo.get("threshold_ms")
    _require(
        isinstance(threshold, (int, float))
        and not isinstance(threshold, bool)
        and threshold > 0,
        "slo.threshold_ms must be a positive number",
    )

    if identity["type"] == "agent":
        steps = doc.get("steps")
        _require(
            steps is not None,
            "identity.type=agent requires a steps block: without a step "
            "distribution the description cannot say how many LLM calls one "
            "task produces (6.5)",
        )
        _check_quantiles("steps", {k: v for k, v in steps.items() if k in QUANTILES}
                         if isinstance(steps, dict) else steps)
        mean = steps.get("mean") if isinstance(steps, dict) else None
        _require(
            isinstance(mean, (int, float)) and not isinstance(mean, bool) and mean > 0,
            "steps.mean must be a positive number",
        )

    forbidden = {"results", "ttft_ms", "throughput", "goodput", "p95_ms"}
    present = forbidden & set(doc)
    _require(
        not present,
        f"a workload description must not carry performance numbers: {sorted(present)}",
    )


def build_workload(
    *,
    profile: str,
    arrival: str,
    rate: float | None,
    concurrency: int | None,
    duration_s: float,
    seed: int,
    slo_metric: str,
    slo_quantile: str,
    slo_threshold_ms: float,
    name: str | None = None,
    source: str = "synthetic: course default, replace with production statistics",
) -> dict:
    if profile not in PROFILES:
        raise WorkloadError(f"profile must be one of {PROFILES}, got {profile!r}")
    if arrival not in ARRIVALS:
        raise WorkloadError(f"arrival must be one of {ARRIVALS}, got {arrival!r}")

    doc: dict = {
        "identity": {
            "name": name or f"{profile}-{arrival}",
            "type": profile,
            "source": source,
        },
        "length": json.loads(json.dumps(DEFAULT_LENGTH[profile])),
        "arrival": {"mode": arrival, "duration_s": duration_s, "seed": seed},
        "slo": {
            "metric": slo_metric,
            "quantile": slo_quantile,
            "threshold_ms": slo_threshold_ms,
        },
    }
    if arrival == "closed":
        doc["arrival"]["concurrency"] = concurrency
    else:
        doc["arrival"]["rate"] = rate
    if profile == "agent":
        doc["steps"] = dict(DEFAULT_AGENT_STEPS)

    validate_workload(doc)
    return doc


def expected_concurrency(doc: dict, mean_latency_s: float) -> float:
    """Little's Law: L = lambda x W. Only meaningful for open-loop arrival."""
    mode = doc["arrival"]["mode"]
    if mode == "closed":
        raise WorkloadError(
            "under closed loop the concurrency is the input, not an outcome; "
            "Little's Law is used the other way round (6.4)"
        )
    if mean_latency_s <= 0:
        raise WorkloadError("mean_latency_s must be positive")
    return doc["arrival"]["rate"] * mean_latency_s


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="chat")
    parser.add_argument("--arrival", choices=ARRIVALS, default="poisson")
    parser.add_argument("--rate", type=float, default=10.0,
                        help="requests per second, for open-loop modes")
    parser.add_argument("--concurrency", type=int, default=None,
                        help="in-flight requests, for arrival=closed")
    parser.add_argument("--duration", type=float, default=60.0, dest="duration_s")
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--slo-metric", default="ttft")
    parser.add_argument("--slo-quantile", default="p95", choices=list(SLO_QUANTILES))
    parser.add_argument("--slo-threshold-ms", type=float, default=2000.0)
    parser.add_argument("--name", default=None)
    parser.add_argument("--validate", type=Path, default=None,
                        help="validate an existing description instead of building one")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.validate is not None:
        doc = json.loads(args.validate.read_text(encoding="utf-8"))
        try:
            validate_workload(doc)
        except WorkloadError as exc:
            print(f"REJECTED: {exc}")
            return 1
        print(f"OK: {args.validate} is self-consistent")
        return 0

    try:
        doc = build_workload(
            profile=args.profile,
            arrival=args.arrival,
            rate=args.rate,
            concurrency=args.concurrency,
            duration_s=args.duration_s,
            seed=args.seed,
            slo_metric=args.slo_metric,
            slo_quantile=args.slo_quantile,
            slo_threshold_ms=args.slo_threshold_ms,
            name=args.name,
        )
    except WorkloadError as exc:
        print(f"REJECTED: {exc}")
        return 1

    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
