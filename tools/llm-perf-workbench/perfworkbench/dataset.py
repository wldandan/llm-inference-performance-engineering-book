"""Versioned dataset profiling and deterministic, independent request mixtures."""

import copy
import hashlib
import json
import math
import os
import random
import uuid
from collections import Counter, defaultdict
from pathlib import Path

from .config import ExperimentSpec, Sample


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def load_jsonl(text: str) -> list[dict]:
    if len(text.encode()) > 16 * 1024 * 1024:
        raise ValueError("Dataset exceeds 16 MiB import limit")
    result = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            result.append(Sample.model_validate(json.loads(line)).model_dump(mode="json"))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid dataset line {number}; check Sample schema") from exc
    if not result:
        raise ValueError("Dataset is empty")
    if len({row["id"] for row in result}) != len(result):
        raise ValueError("Dataset sample ids must be unique")
    return result


def distribution(values):
    if not values:
        return None
    ordered = sorted(values)

    def percentile(p):
        position = (len(ordered) - 1) * p
        left = math.floor(position)
        right = math.ceil(position)
        return ordered[left] + (ordered[right] - ordered[left]) * (position - left)

    return {
        "count": len(values),
        "min": ordered[0],
        "max": ordered[-1],
        "mean": sum(values) / len(values),
        "p50": percentile(0.5),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
    }


def profile_dataset(samples, tokenizer_path=None) -> dict:
    rows = [Sample.model_validate(row).model_dump(mode="json") for row in samples]
    if not rows:
        raise ValueError("Dataset is empty")
    texts = ["\n".join(m["content"] for m in row["messages"]) for row in rows]
    prompt_hashes = [fingerprint(row["messages"]) for row in rows]
    tokens = None
    token_source = "unavailable"
    if tokenizer_path:
        path = Path(tokenizer_path).expanduser().resolve()
        if not path.is_dir():
            raise ValueError("tokenizer_path must be an existing local tokenizer directory")
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True, trust_remote_code=False)
        tokens = [
            len(tokenizer.apply_chat_template(row["messages"], tokenize=True, add_generation_prompt=True))
            for row in rows
        ]
        token_source = "local_tokenizer_chat_template"
    return {
        "version": fingerprint(rows),
        "sample_count": len(rows),
        "prompt_hashes": prompt_hashes,
        "characters": distribution([len(t) for t in texts]),
        "input_tokens": distribution(tokens),
        "token_count_source": token_source,
        "categories": dict(Counter(r["category"] for r in rows)),
        "duplicate_prompts": len(rows) - len(set(prompt_hashes)),
        "shared_prefix_chars": len(os.path.commonprefix(texts)) if len(texts) > 1 else 0,
        "warnings": ["字符数不等于 token 数；共享文本前缀不保证实际 KV 命中。"],
    }


def build_plan(spec) -> list[dict]:
    raw = ExperimentSpec.model_validate(spec).model_dump(mode="json")
    load = raw["load"]
    variable = "concurrency" if load["mode"] == "concurrency" else "rate"
    plans = []
    for point in load["scan"] or [load[variable]]:
        for _ in range(load["repeats"]):
            child = copy.deepcopy(raw)
            child["load"].update(
                {variable: int(point) if variable == "concurrency" else point, "repeats": 1, "scan": []}
            )
            plans.append(child)
    return plans


def _select_samples(rows, count, mix, rng):
    if not mix:
        selected = [copy.deepcopy(rows[i % len(rows)]) for i in range(count)]
    else:
        groups = defaultdict(list)
        for row in rows:
            groups[row["category"]].append(row)
        weights = {key: count * weight / sum(mix.values()) for key, weight in mix.items()}
        counts = {key: math.floor(value) for key, value in weights.items()}
        remainders = sorted(mix, key=lambda key: (-(weights[key] - counts[key]), key))
        for key in remainders[: count - sum(counts.values())]:
            counts[key] += 1
        selected = [
            copy.deepcopy(groups[key][i % len(groups[key])]) for key, n in counts.items() for i in range(n)
        ]
    rng.shuffle(selected)
    return selected


def materialize_requests(spec) -> list[dict]:
    raw = ExperimentSpec.model_validate(spec).model_dump(mode="json")
    rng = random.Random(raw["load"]["seed"])
    result = []
    for phase, count in [("warmup", raw["load"]["warmup"]), ("measure", raw["load"]["count"])]:
        for row in _select_samples(raw["dataset"], count, raw["load"]["mix"], rng):
            generation = raw["generation"]
            body = {
                "model": raw["endpoint"]["model"],
                "messages": row["messages"],
                "max_tokens": row["max_tokens"] or generation["max_tokens"],
                "stream": generation["stream"],
                "temperature": generation["temperature"],
                "top_p": generation["top_p"],
                **generation["extra"],
            }
            if generation["stream"]:
                body["stream_options"] = {"include_usage": True}
            result.append(
                {
                    "request_id": uuid.uuid4().hex,
                    "sample_id": row["id"],
                    "category": row["category"],
                    "phase": phase,
                    "body": body,
                }
            )
    return result
