"""Pure math connecting a model's config to its KV cache footprint.

This is the "why" behind the diagram:

    Qwen2.5-0.5B -> Prefill/Decode -> KV Cache -> num_kv_heads=2 (GQA)
    -> KV Cache 较小 -> vLLM/PagedAttention -> Continuous Batching

Everything here is a pure function of a handful of architecture numbers, so
it's testable without loading any model or touching a GPU. `explore.py` in
this same directory does the GPU-touching, non-testable half: actually
loading a real model, printing its real config, and running Prefill/Decode
to watch the KV cache grow for real.
"""

from __future__ import annotations

from dataclasses import dataclass


def kv_cache_bytes_per_token(num_layers: int, num_kv_heads: int, head_dim: int, dtype_bytes: int) -> int:
    """Bytes of KV cache added per token, per sequence.

    Standard formula: 2 (one K tensor + one V tensor) x layers x kv_heads x
    head_dim x bytes_per_element. This is exactly what grows by one token's
    worth every Decode step, and what a Prefill of length N allocates N of
    in one shot.
    """
    return 2 * num_layers * num_kv_heads * head_dim * dtype_bytes


def kv_cache_bytes_for_context(
    context_len: int, num_layers: int, num_kv_heads: int, head_dim: int, dtype_bytes: int
) -> int:
    per_token = kv_cache_bytes_per_token(num_layers, num_kv_heads, head_dim, dtype_bytes)
    return per_token * context_len


def bytes_to_mb(n: int | float) -> float:
    return n / (1024 * 1024)


def mha_equivalent_savings(
    num_attention_heads: int, num_kv_heads: int, num_layers: int, head_dim: int, dtype_bytes: int
) -> dict[str, float]:
    """Compare actual (GQA) KV cache size against what it would be under
    plain Multi-Head Attention (num_kv_heads == num_attention_heads) -- the
    concrete number behind "num_kv_heads=2 -> KV Cache 较小" in the diagram.
    """
    gqa_bytes = kv_cache_bytes_per_token(num_layers, num_kv_heads, head_dim, dtype_bytes)
    mha_bytes = kv_cache_bytes_per_token(num_layers, num_attention_heads, head_dim, dtype_bytes)
    reduction_pct = 0.0 if mha_bytes == 0 else (1 - gqa_bytes / mha_bytes) * 100.0
    return {
        "gqa_bytes_per_token": gqa_bytes,
        "mha_bytes_per_token": mha_bytes,
        "reduction_pct": reduction_pct,
    }


@dataclass
class ArchSummary:
    hidden_size: int
    num_layers: int
    num_attention_heads: int
    num_kv_heads: int
    head_dim: int
    query_groups: int
    uses_gqa: bool
    intermediate_size: int
    vocab_size: int
    max_position_embeddings: int


def summarize_architecture(config) -> ArchSummary:
    """Pull the handful of numbers that matter for this demo out of a
    HF `model.config` object (or anything duck-typed the same way, which is
    what makes this testable without transformers/torch installed).
    """
    num_attention_heads = config.num_attention_heads
    num_kv_heads = getattr(config, "num_key_value_heads", num_attention_heads)
    hidden_size = config.hidden_size
    head_dim = getattr(config, "head_dim", hidden_size // num_attention_heads)
    return ArchSummary(
        hidden_size=hidden_size,
        num_layers=config.num_hidden_layers,
        num_attention_heads=num_attention_heads,
        num_kv_heads=num_kv_heads,
        head_dim=head_dim,
        query_groups=num_attention_heads // num_kv_heads,
        uses_gqa=num_kv_heads < num_attention_heads,
        intermediate_size=config.intermediate_size,
        vocab_size=config.vocab_size,
        max_position_embeddings=config.max_position_embeddings,
    )
