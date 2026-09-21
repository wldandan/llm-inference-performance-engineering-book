import importlib
from types import SimpleNamespace

import pytest


def worker():
    try:
        return importlib.import_module("perfworkbench.evalscope_worker")
    except ModuleNotFoundError:
        pytest.fail("F05/F07/F14 worker is not implemented", pytrace=False)


def output(stream=True, finish="stop", success=True, text="answer"):
    message = {"delta" if stream else "message": {"content": text}, "finish_reason": finish, "index": 0}
    return SimpleNamespace(
        success=success,
        is_stream=stream,
        first_chunk_latency=0.1,
        prompt_tokens=32,
        completion_tokens=8,
        status_code=200 if success else 503,
        inter_chunk_latency=[0.03, 0.04],
        response_messages=[{"choices": [message]}],
        error="Bearer secret text from upstream",
        start_time=100,
        completed_time=100.2,
    )


def test_normalize_captures_independent_end_and_estimated_tpot():
    result = worker().normalize_output(
        output(),
        {"request_id": "r", "sample_id": "s", "category": "a", "phase": "measure"},
        start=100,
        end=101,
        origin=99,
        started_at=1234,
    )
    assert result["e2e_ms"] == 1000
    assert result["end_s"] == 2
    assert result["input_tokens"] == 32
    assert result["output_tokens"] == 8
    assert result["tpot_ms"] == pytest.approx(900 / 7)
    assert result["output_text"] == "answer"
    assert "secret" not in str(result)


def test_nonstream_has_no_token_timings():
    result = worker().normalize_output(output(False), {}, start=100, end=101, origin=100, started_at=1)
    assert result["success"]
    assert result["ttft_ms"] is None and result["tpot_ms"] is None
    assert result["inter_chunk_ms"] == []


def test_sse_without_finish_is_incomplete_not_success():
    result = worker().normalize_output(output(finish=None), {}, start=100, end=101, origin=100, started_at=1)
    assert not result["success"]
    assert result["error_kind"] == "incomplete_response"


def test_http200_without_choices_is_protocol_error():
    raw = output()
    raw.response_messages = [{"oops": "not a completion"}]
    result = worker().normalize_output(raw, {}, start=100, end=101, origin=100, started_at=1)
    assert not result["success"]
    assert result["error_kind"] == "protocol_error"


def test_missing_usage_remains_unknown_and_failure_retains_long_tail():
    raw = output(success=False)
    raw.prompt_tokens = raw.completion_tokens = None
    result = worker().normalize_output(raw, {}, start=100, end=105, origin=100, started_at=1)
    assert result["input_tokens"] is None and result["output_tokens"] is None
    assert result["status"] == "failed"
    assert result["e2e_ms"] == 5000


def test_zero_and_single_token_output_never_divide_by_zero():
    for count in (0, 1):
        raw = output()
        raw.completion_tokens = count
        result = worker().normalize_output(raw, {}, start=100, end=101, origin=100, started_at=1)
        assert result["output_tokens"] == count and result["tpot_ms"] is None


def test_atomic_budget_never_refunds_unknown_consumption():
    guard = worker().AdmissionBudget(max_requests=2, max_tokens=10, max_active=1)
    assert guard.reserve(6) is None
    assert guard.reserve(1) == "client_rejected"
    guard.release()
    assert guard.reserve(5) == "token_budget_exceeded"
    assert guard.reserve(4) is None
    guard.release()
    assert guard.reserve(1) == "request_budget_exceeded"


def test_output_reasoning_does_not_pollute_quality_text():
    raw = output()
    raw.response_messages = [
        {"choices": [{"delta": {"reasoning_content": "secret reasoning"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "final"}, "finish_reason": "stop"}]},
    ]
    result = worker().normalize_output(raw, {}, start=100, end=101, origin=100, started_at=1)
    assert result["output_text"] == "final"
