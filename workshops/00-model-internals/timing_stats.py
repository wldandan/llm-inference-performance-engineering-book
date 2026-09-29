"""Pure stats over a list of per-generation-step wall-clock times.

Adapted from the per-token timing loops in `ch2_Workthrough_LLM_execution.ipynb`
(*Hands-On LLM Serving and Optimization*, Chi Wang & Peiheng Hu, O'Reilly --
see ../common/naive_baseline_server/NOTICE.md for the attribution note that
applies to every book-derived file in this tree). That notebook prints
per-step timings and plots them but doesn't have a reusable, testable way to
say "this run's shape says no-cache" vs "this run's shape says cached
decode" -- that's what `describe_timing_pattern` adds.

The story this supports: step 0 of ANY generation loop is Prefill (the whole
prompt, one shot) and is always the slowest step. What differs is what
happens after: without KV cache, each step re-processes the whole (growing)
sequence, so step times keep climbing; with KV cache, each step only does
one new token's worth of work, so step times stay roughly flat.
"""

from __future__ import annotations


def describe_timing_pattern(times: list[float], growth_threshold: float = 1.5) -> dict[str, float | bool]:
    if not times:
        raise ValueError("times must be non-empty")

    first_token_time_s = times[0]
    subsequent = times[1:]

    if not subsequent:
        return {
            "first_token_time_s": first_token_time_s,
            "avg_subsequent_step_time_s": None,
            "is_growing": False,
        }

    avg_subsequent = sum(subsequent) / len(subsequent)

    half = max(len(subsequent) // 2, 1)
    first_half_avg = sum(subsequent[:half]) / half
    second_half_avg = sum(subsequent[-half:]) / half
    is_growing = first_half_avg > 0 and (second_half_avg / first_half_avg) >= growth_threshold

    return {
        "first_token_time_s": first_token_time_s,
        "avg_subsequent_step_time_s": avg_subsequent,
        "is_growing": is_growing,
    }
