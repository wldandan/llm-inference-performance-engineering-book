#!/usr/bin/env python3
"""Organise a root-cause investigation into a report, and check it holds up.

The checker does not judge whether your conclusion is right. It checks
whether the investigation was capable of being wrong: a problem statement
with scope and a baseline, hypotheses that predict something, evidence that
says where it came from, and at least one thing ruled out.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BLOCKS = (
    "problem",
    "hypotheses",
    "evidence",
    "ruled_out",
    "conclusion",
    "unknowns",
    "next_step",
)

PROBLEM_FIELDS = ("symptom", "scope", "since", "baseline")
LAYERS = ("request", "process", "framework", "device", "config")


class ReportError(ValueError):
    """Raised when a root-cause report is not self-consistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportError(message)


def validate_report(doc: object) -> None:
    _require(isinstance(doc, dict), "report must be an object")
    assert isinstance(doc, dict)
    for block in BLOCKS:
        _require(block in doc, f"missing required block: {block}")

    problem = doc["problem"]
    _require(isinstance(problem, dict), "problem must be an object")
    for field in PROBLEM_FIELDS:
        value = problem.get(field)
        _require(
            isinstance(value, str) and value.strip() != "",
            f"problem.{field} is required: without it the question is not "
            "investigable (10.1)",
        )

    hypotheses = doc["hypotheses"]
    _require(
        isinstance(hypotheses, list) and hypotheses,
        "hypotheses must be a non-empty list",
    )
    ids = []
    for i, h in enumerate(hypotheses):
        _require(isinstance(h, dict), f"hypotheses[{i}] must be an object")
        hid = h.get("id")
        _require(
            isinstance(hid, str) and hid.strip() != "",
            f"hypotheses[{i}].id must be a non-empty string",
        )
        ids.append(hid)
        _require(
            isinstance(h.get("statement"), str) and h["statement"].strip() != "",
            f"{hid}: statement is required",
        )
        expected = h.get("expected_evidence")
        _require(
            isinstance(expected, str) and expected.strip() != "",
            f"{hid}: expected_evidence is required, otherwise the hypothesis "
            "cannot be falsified (10.2)",
        )
        _require(
            h.get("layer") in LAYERS,
            f"{hid}: layer must be one of {LAYERS}",
        )
        _require(
            isinstance(h.get("threshold"), str) and h["threshold"].strip() != "",
            f"{hid}: threshold is required, otherwise 'high' is still a "
            "judgement call (10.2)",
        )
        _require(
            h.get("verdict") in ("supported", "ruled_out", "unconfirmed"),
            f"{hid}: verdict must be supported / ruled_out / unconfirmed",
        )
    _require(len(set(ids)) == len(ids), "hypothesis ids must be unique")

    evidence = doc["evidence"]
    _require(isinstance(evidence, list), "evidence must be a list")
    evidence_ids = []
    for i, e in enumerate(evidence):
        _require(isinstance(e, dict), f"evidence[{i}] must be an object")
        eid = e.get("id")
        _require(
            isinstance(eid, str) and eid.strip() != "",
            f"evidence[{i}].id must be a non-empty string",
        )
        evidence_ids.append(eid)
        _require(
            isinstance(e.get("finding"), str) and e["finding"].strip() != "",
            f"{eid}: finding is required",
        )
        _require(e.get("layer") in LAYERS, f"{eid}: layer must be one of {LAYERS}")
        condition = e.get("collection_condition")
        _require(
            isinstance(condition, str) and condition.strip() != "",
            f"{eid}: collection_condition is required (Chapter 9): a profile "
            "without its collection conditions cannot be compared to a Baseline",
        )
    _require(
        len(set(evidence_ids)) == len(evidence_ids), "evidence ids must be unique"
    )

    ruled_out = doc["ruled_out"]
    _require(isinstance(ruled_out, list), "ruled_out must be a list")
    for i, r in enumerate(ruled_out):
        _require(isinstance(r, dict), f"ruled_out[{i}] must be an object")
        for field in ("claim", "basis"):
            _require(
                isinstance(r.get(field), str) and r[field].strip() != "",
                f"ruled_out[{i}].{field} is required",
            )

    _require(
        not (len(hypotheses) == 1 and not ruled_out),
        "a single hypothesis with nothing ruled out is usually a conclusion "
        "looking for evidence (10.7)",
    )

    conclusion = doc["conclusion"]
    _require(isinstance(conclusion, dict), "conclusion must be an object")
    _require(
        isinstance(conclusion.get("statement"), str)
        and conclusion["statement"].strip() != "",
        "conclusion.statement is required",
    )
    _require(
        conclusion.get("confidence") in ("high", "medium", "low"),
        "conclusion.confidence must be high / medium / low",
    )
    supports = conclusion.get("supported_by")
    _require(
        isinstance(supports, list) and supports,
        "conclusion.supported_by must reference at least one evidence id",
    )
    dangling = [s for s in supports if s not in evidence_ids]
    _require(
        not dangling,
        f"conclusion references evidence that does not exist: {dangling}",
    )

    unknowns = doc["unknowns"]
    _require(isinstance(unknowns, list), "unknowns must be a list")
    for i, u in enumerate(unknowns):
        _require(isinstance(u, dict), f"unknowns[{i}] must be an object")
        for field in ("item", "reason", "impact"):
            _require(
                isinstance(u.get(field), str) and u[field].strip() != "",
                f"unknowns[{i}].{field} is required",
            )

    unconfirmed = [h["id"] for h in hypotheses if h["verdict"] == "unconfirmed"]
    if unconfirmed:
        mentioned = json.dumps(unknowns, ensure_ascii=False)
        missing = [h for h in unconfirmed if h not in mentioned]
        _require(
            not missing,
            f"hypotheses {missing} are unconfirmed but do not appear in "
            "unknowns: an unfinished thread must be written down (10.4)",
        )

    nxt = doc["next_step"]
    _require(isinstance(nxt, dict), "next_step must be an object")
    for field in ("change", "tier", "verification"):
        _require(
            isinstance(nxt.get(field), str) and nxt[field].strip() != "",
            f"next_step.{field} is required",
        )
    _require(
        nxt["tier"] in ("config", "parameter", "code", "architecture"),
        "next_step.tier must be config / parameter / code / architecture (10.5)",
    )
    _require(
        "同流量" in nxt["verification"] or "same workload" in nxt["verification"],
        "next_step.verification must state that the same workload is replayed "
        "(10.5); a different load makes the measured gain meaningless",
    )


def summarize(doc: dict) -> dict:
    hyps = doc["hypotheses"]
    return {
        "hypotheses": len(hyps),
        "supported": [h["id"] for h in hyps if h["verdict"] == "supported"],
        "ruled_out": [h["id"] for h in hyps if h["verdict"] == "ruled_out"],
        "unconfirmed": [h["id"] for h in hyps if h["verdict"] == "unconfirmed"],
        "evidence_items": len(doc["evidence"]),
        "explicit_exclusions": len(doc["ruled_out"]),
        "open_questions": len(doc["unknowns"]),
        "confidence": doc["conclusion"]["confidence"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    doc = json.loads(args.input.read_text(encoding="utf-8"))
    try:
        validate_report(doc)
    except ReportError as exc:
        print(f"REJECTED: {exc}")
        return 1

    doc = dict(doc)
    doc["summary"] = summarize(doc)
    print("OK: report is self-consistent")
    print(json.dumps(doc["summary"], ensure_ascii=False, indent=2))
    if args.output is not None:
        args.output.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
