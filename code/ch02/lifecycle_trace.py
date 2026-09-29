"""Normalize request lifecycle events and decompose stage durations."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable


TERMINAL_EVENTS = {"finished", "cancelled", "failed"}
ALLOWED_TRANSITIONS = {
    None: {"request_received"},
    "request_received": {"queued", "cancelled", "failed"},
    "queued": {"scheduled", "cancelled", "failed"},
    "scheduled": {"first_token", "cancelled", "failed"},
    "first_token": {"token", "last_token", "cancelled", "failed"},
    "token": {"token", "last_token", "cancelled", "failed"},
    "last_token": {"finished", "failed"},
}


def _duration(timestamps: dict[str, float], start: str, end: str) -> float | None:
    if start not in timestamps or end not in timestamps:
        return None
    return timestamps[end] - timestamps[start]


def analyze_request(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        raise ValueError("request trace must contain at least one event")

    request_id = events[0].get("request_id")
    timestamps: dict[str, float] = {}
    previous_event: str | None = None
    previous_timestamp: float | None = None

    for item in events:
        if item.get("request_id") != request_id:
            raise ValueError("all events must have the same request_id")
        event = item.get("event")
        timestamp = item.get("ts_ms")
        if not isinstance(event, str) or not isinstance(timestamp, (int, float)):
            raise ValueError("each event needs a string event and numeric ts_ms")
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise ValueError("timestamps must be nondecreasing")
        if event not in ALLOWED_TRANSITIONS.get(previous_event, set()):
            raise ValueError(f"invalid transition: {previous_event!r} -> {event!r}")
        if event != "token":
            timestamps[event] = timestamp
        previous_event = event
        previous_timestamp = timestamp

    terminal_state = previous_event if previous_event in TERMINAL_EVENTS else "incomplete"
    terminal_timestamp = previous_timestamp
    received_timestamp = timestamps.get("request_received")
    end_to_end = (
        terminal_timestamp - received_timestamp
        if terminal_state != "incomplete" and received_timestamp is not None and terminal_timestamp is not None
        else None
    )
    return {
        "request_id": request_id,
        "terminal_state": terminal_state,
        "durations_ms": {
            "admission": _duration(timestamps, "request_received", "queued"),
            "queue": _duration(timestamps, "queued", "scheduled"),
            "scheduled_to_first_token": _duration(timestamps, "scheduled", "first_token"),
            "decode": _duration(timestamps, "first_token", "last_token"),
            "response_tail": _duration(timestamps, "last_token", "finished"),
            "end_to_end": end_to_end,
        },
    }


def analyze_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for item in events:
        request_id = item.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("each event needs a non-empty request_id")
        grouped.setdefault(request_id, []).append(item)

    requests = [analyze_request(items) for items in grouped.values()]
    return {
        "summary": {
            "requests": len(requests),
            "finished": sum(item["terminal_state"] == "finished" for item in requests),
            "cancelled": sum(item["terminal_state"] == "cancelled" for item in requests),
            "failed": sum(item["terminal_state"] == "failed" for item in requests),
        },
        "requests": requests,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {line_number}: {exc.msg}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"line {line_number} must contain a JSON object")
        events.append(item)
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze normalized LLM request lifecycle events")
    parser.add_argument("--input", type=Path, required=True, help="JSONL lifecycle event file")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path")
    args = parser.parse_args()

    report_text = json.dumps(analyze_events(load_jsonl(args.input)), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(report_text + "\n", encoding="utf-8")
    print(report_text)


if __name__ == "__main__":
    main()
