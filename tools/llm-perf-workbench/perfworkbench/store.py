"""Private local, append-only request evidence and atomic run snapshots."""

import copy
import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path


def write_json(path: Path, value) -> None:
    path = Path(path)
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temp:
        temporary = Path(temp.name)
        try:
            temp.write(payload)
            temp.flush()
            os.fsync(temp.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def append_jsonl(path: Path, value) -> None:
    payload = (json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "ab") as output:
        output.write(payload)
        output.flush()


class JsonlCounter:
    """Count newly appended complete records without parsing/re-reading response text."""

    def __init__(self, path):
        self.path, self.offset, self.total = path, 0, 0

    def count(self):
        if self.path.exists():
            with self.path.open("rb") as source:
                source.seek(self.offset)
                while chunk := source.read(65536):
                    self.total += chunk.count(b"\n")
                self.offset = source.tell()
        return self.total


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise ValueError("Corrupt evidence record before last line") from None
    return rows


class RunStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = threading.RLock()

    def run_dir(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("Invalid run id")
        return self.root / run_id

    def create(self, spec, profile=None, parent_id=None):
        run_id = uuid.uuid4().hex
        directory = self.run_dir(run_id)
        directory.mkdir(mode=0o700)
        run = {
            "id": run_id,
            "created_at": time.time(),
            "status": "queued",
            "spec": copy.deepcopy(spec),
            "profile": profile,
            "parent_id": parent_id,
            "summary": None,
            "diagnostics": [],
            "error": None,
            "progress": {"done": 0},
        }
        write_json(directory / "run.json", run)
        return self.get(run_id)

    def get(self, run_id):
        directory = self.run_dir(run_id)
        with self._lock:
            run = json.loads((directory / "run.json").read_text())
            run["records"] = self.records(run_id)
            run["telemetry"] = read_jsonl(directory / "telemetry.jsonl")
            return run

    def list(self):
        result = []
        for path in self.root.glob("*/run.json"):
            if re.fullmatch(r"[0-9a-f]{32}", path.parent.name):
                with self._lock:
                    result.append(json.loads(path.read_text()))
        return sorted(result, key=lambda run: run["created_at"], reverse=True)

    def update(self, run_id, *, include_evidence=True, **fields):
        if {"id", "spec", "created_at", "records", "telemetry"} & fields.keys():
            raise ValueError("Immutable snapshot/evidence fields cannot be overwritten")
        with self._lock:
            path = self.run_dir(run_id) / "run.json"
            run = json.loads(path.read_text())
            run.update(fields)
            write_json(path, run)
            return self.get(run_id) if include_evidence else run

    def records(self, run_id):
        directory = self.run_dir(run_id)
        rows = read_jsonl(directory / "records.jsonl")
        labels_path = directory / "labels.json"
        labels = json.loads(labels_path.read_text()) if labels_path.exists() else {}
        return [
            {**row, "manual_label": labels.get(row["request_id"], row.get("manual_label"))} for row in rows
        ]

    def label(self, run_id, labels):
        with self._lock:
            known = {row["request_id"] for row in self.records(run_id)}
            if (
                not isinstance(labels, dict)
                or set(labels) - known
                or any(v not in {"pass", "fail", "unknown"} for v in labels.values())
            ):
                raise ValueError("Labels must match existing request IDs and use pass/fail/unknown")
            path = self.run_dir(run_id) / "labels.json"
            existing = json.loads(path.read_text()) if path.exists() else {}
            write_json(path, {**existing, **labels})
            return self.get(run_id)
