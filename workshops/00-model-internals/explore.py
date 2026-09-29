"""Model-internals-to-serving demo.

Walks the diagram end to end, using a real loaded model where it matters:

    <model> -> Prefill/Decode -> KV Cache -> num_kv_heads (GQA)
    -> KV Cache 较小 -> vLLM/PagedAttention -> Continuous Batching

Adapted from two notebooks in *Hands-On LLM Serving and Optimization*
(Chi Wang & Peiheng Hu, O'Reilly) -- see
../common/naive_baseline_server/NOTICE.md for the attribution note that
applies to every book-derived file in this workshops/ tree:

- `ch02/ch2_Inside_the_Mind_of_a_Transformer.ipynb`: inspects `model.config`
  and walks the module tree but doesn't compute the GQA KV-cache-size story
  explicitly; that's what kv_cache_math.py adds.
- `ch02/ch2_Workthrough_LLM_execution.ipynb`: times each generation step by
  hand, with and without KV cache, and plots how the "without cache" times
  climb while "with cache" times stay flat. This script's timing functions
  are a rewrite of that idea (not a copy -- e.g. the notebook's with-cache
  loop passes `max_new_tokens`/`min_new_tokens` into a raw forward pass,
  which those kwargs don't apply to; this version drops that) plus
  timing_stats.py to turn "look at the chart" into a testable check.

Also cross-references https://poloclub.github.io/transformer-explainer/, an
interactive GPT-2 forward-pass visualizer (a live web app, not something we
can embed/copy) -- transformer_walkthrough.py walks the same stages
(embedding -> attention -> MLP -> output) but against the real loaded model
here, hooks the real modules to show ACTUAL runtime shapes (not just the
static config numbers the visualizer and the first notebook show), and is
explicit about the four ways a modern model like Qwen2.5 differs from the
GPT-2 the visualizer shows (RoPE vs learned position embeddings, GQA vs
plain MHA, RMSNorm vs LayerNorm, SwiGLU vs plain GELU MLP).

Needs a real environment with `transformers` + `torch` installed (and
ideally a GPU) -- this is the GPU-touching half of the demo. The other half,
kv_cache_math.py, is pure and unit-tested (test_kv_cache_math.py) without
needing either.

Usage:
    python3 explore.py --model Qwen/Qwen2.5-0.5B --context-lens 2048 8192 32768
"""

from __future__ import annotations

import argparse

from kv_cache_math import (
    bytes_to_mb,
    kv_cache_bytes_for_context,
    mha_equivalent_savings,
    summarize_architecture,
)
from timing_stats import describe_timing_pattern
from transformer_walkthrough import architecture_family_diff, walk_forward_pass

DTYPE_BYTES = {"float32": 4, "float16": 2, "bfloat16": 2}


def load_model_and_config(model_name: str, dtype: str):
    import torch
    from transformers import AutoModelForCausalLM

    torch_dtype = getattr(torch, dtype)
    model = AutoModelForCausalLM.from_pretrained(model_name, trust_remote_code=True, torch_dtype=torch_dtype, device_map="auto")
    return model, model.config


def print_architecture(model_name: str, arch) -> None:
    print(f"\n=== {model_name}: 从模型结构看起 ===")
    print(f"hidden_size            = {arch.hidden_size}")
    print(f"num_hidden_layers      = {arch.num_layers}")
    print(f"num_attention_heads    = {arch.num_attention_heads}  (Query 头数)")
    print(f"num_key_value_heads    = {arch.num_kv_heads}  (K/V 头数 -- 这就是图里的 num_kv_heads)")
    print(f"head_dim               = {arch.head_dim}")
    print(f"query_groups           = {arch.query_groups}  (每 {arch.query_groups} 个 Query 头共享 1 组 K/V)")
    print(f"uses GQA (Grouped Query Attention) = {arch.uses_gqa}")
    print(f"intermediate_size      = {arch.intermediate_size}")
    print(f"vocab_size             = {arch.vocab_size}")
    print(f"max_position_embeddings= {arch.max_position_embeddings}")


def print_kv_cache_story(arch, dtype_bytes: int, context_lens: list[int]) -> None:
    print("\n=== KV Cache 为什么较小：GQA 的直接账 ===")
    savings = mha_equivalent_savings(
        num_attention_heads=arch.num_attention_heads,
        num_kv_heads=arch.num_kv_heads,
        num_layers=arch.num_layers,
        head_dim=arch.head_dim,
        dtype_bytes=dtype_bytes,
    )
    print(f"如果没有 GQA（num_kv_heads == num_attention_heads == {arch.num_attention_heads}）：")
    print(f"  每 token KV Cache = {savings['mha_bytes_per_token']} bytes")
    print(f"实际（GQA，num_kv_heads = {arch.num_kv_heads}）：")
    print(f"  每 token KV Cache = {savings['gqa_bytes_per_token']} bytes")
    print(f"GQA 省了 {savings['reduction_pct']:.1f}% 的 KV Cache -- 这就是图里 \"KV Cache 较小\" 的具体数字。")

    print("\n不同上下文长度下，一条序列要占多少 KV Cache：")
    for context_len in context_lens:
        total_bytes = kv_cache_bytes_for_context(
            context_len=context_len,
            num_layers=arch.num_layers,
            num_kv_heads=arch.num_kv_heads,
            head_dim=arch.head_dim,
            dtype_bytes=dtype_bytes,
        )
        print(f"  context_len={context_len:>6}: {bytes_to_mb(total_bytes):.2f} MB / 条序列")

    print(
        "\n这条数字链接下去就是图里剩下的部分：KV Cache 越小，同样显存能同时装下的序列越多；"
        "\nvLLM 用 PagedAttention 把这些 KV Cache 分页管理、避免碎片浪费（对应课程样板一 PagedAttention、"
        "\nChapter 16）；能同时装下更多序列，才谈得上 Continuous Batching 让新请求随时插进来"
        "\n（对应 workshops/02-batching-tiers、Chapter 20）。这三步不是三个独立技巧，是同一条内存"
        "\n账目从模型结构一路推到调度策略。"
    )


def print_architecture_family_diff() -> None:
    print("\n=== 这个模型和 transformer-explainer 可视化的 GPT-2 有什么不一样 ===")
    print("参考：https://poloclub.github.io/transformer-explainer/（GPT-2，交互式可视化，建议先玩一遍再看下面的对照）")
    print("下面这张表是固定写死对比 Qwen2.5 家族，如果 --model 换成了非 Qwen2 模型（比如 gpt2 本身），")
    print("这张表和后面的逐层核对（walk_forward_pass）就不适用了，加 --skip-walkthrough-demo 跳过。")
    for row in architecture_family_diff():
        print(f"\n{row['aspect']}：")
        print(f"  GPT-2（可视化工具里的）: {row['gpt2']}")
        print(f"  Qwen2.5（这里真实加载的）: {row['qwen']}")


def kv_cache_seq_length(past_key_values) -> int:
    """transformers has changed the `past_key_values` shape across versions:
    older releases return a tuple of (key, value) tensor pairs per layer,
    newer releases return a `Cache` object with `.get_seq_length()`. Handle
    both rather than betting on one -- this is exactly the kind of API drift
    flagged elsewhere in workshops/README.md for CLI flags.
    """
    get_seq_length = getattr(past_key_values, "get_seq_length", None)
    if callable(get_seq_length):
        return get_seq_length()
    # Legacy tuple-of-tuples: past_key_values[layer][0] is the key tensor,
    # shaped [batch, num_kv_heads, seq_len, head_dim].
    return past_key_values[0][0].shape[2]


def run_prefill_decode_demo(model, tokenizer, prompt: str, decode_steps: int) -> None:
    import torch

    print(f"\n=== 亲眼看 KV Cache 增长：Prefill 一次，Decode {decode_steps} 步 ===")
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    prompt_len = inputs.input_ids.shape[1]

    with torch.no_grad():
        # Prefill: the whole prompt goes in as one forward pass.
        out = model(**inputs, use_cache=True)
        past_key_values = out.past_key_values
        print(f"Prefill 完成：prompt_len={prompt_len} tokens -> KV Cache 长度={kv_cache_seq_length(past_key_values)}")

        next_token = out.logits[:, -1, :].argmax(dim=-1, keepdim=True)
        for step in range(decode_steps):
            out = model(input_ids=next_token, past_key_values=past_key_values, use_cache=True)
            past_key_values = out.past_key_values
            next_token = out.logits[:, -1, :].argmax(dim=-1, keepdim=True)
            print(f"Decode step {step + 1}: KV Cache 长度={kv_cache_seq_length(past_key_values)}  (+1 token，符合逐 token 生成)")


def time_generate_without_cache(model, tokenizer, prompt: str, decode_steps: int) -> list[float]:
    """Every step re-feeds the WHOLE growing sequence with use_cache=False --
    step k reprocesses prompt_len + k tokens from scratch. Step times should
    climb roughly linearly with k.
    """
    import time

    import torch

    idx = tokenizer(prompt, return_tensors="pt").input_ids.to(model.device)
    times = []
    with torch.no_grad():
        for _ in range(1 + decode_steps):  # step 0 is Prefill, the rest are Decode
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            start = time.perf_counter()
            out = model(idx, use_cache=False)
            next_token = out.logits[:, -1, :].argmax(dim=-1, keepdim=True)
            if torch.cuda.is_available():
                torch.cuda.synchronize()  # CUDA ops are async -- sync before stopping the clock
            times.append(time.perf_counter() - start)
            idx = torch.cat((idx, next_token), dim=1)
    return times


def time_generate_with_cache(model, tokenizer, prompt: str, decode_steps: int) -> list[float]:
    """Prefill once, then each Decode step only feeds the ONE new token and
    reuses past_key_values. Step times should stay roughly flat after the
    (always-slow) first Prefill step.
    """
    import time

    import torch

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    times = []
    cuda = torch.cuda.is_available()
    with torch.no_grad():
        if cuda:
            torch.cuda.synchronize()
        start = time.perf_counter()
        out = model(**inputs, use_cache=True)
        next_token = out.logits[:, -1, :].argmax(dim=-1, keepdim=True)
        if cuda:
            torch.cuda.synchronize()
        times.append(time.perf_counter() - start)
        past_key_values = out.past_key_values

        for _ in range(decode_steps):
            if cuda:
                torch.cuda.synchronize()
            start = time.perf_counter()
            out = model(input_ids=next_token, past_key_values=past_key_values, use_cache=True)
            next_token = out.logits[:, -1, :].argmax(dim=-1, keepdim=True)
            if cuda:
                torch.cuda.synchronize()
            times.append(time.perf_counter() - start)
            past_key_values = out.past_key_values
    return times


def run_timing_comparison_demo(model, tokenizer, prompt: str, decode_steps: int) -> None:
    print(f"\n=== 时间账：有/无 KV Cache，逐步计时（Prefill 1 步 + Decode {decode_steps} 步）===")

    no_cache_times = time_generate_without_cache(model, tokenizer, prompt, decode_steps)
    with_cache_times = time_generate_with_cache(model, tokenizer, prompt, decode_steps)

    no_cache_pattern = describe_timing_pattern(no_cache_times)
    with_cache_pattern = describe_timing_pattern(with_cache_times)

    print("\n不用 KV Cache（每步重算整个不断变长的序列）：")
    print(f"  step 0 (Prefill): {no_cache_times[0] * 1000:.1f} ms")
    print(f"  之后每步耗时: {[round(t * 1000, 1) for t in no_cache_times[1:]]} ms")
    print(f"  是否随步数明显变慢: {no_cache_pattern['is_growing']}")

    print("\n用 KV Cache（每步只算新来的 1 个 token）：")
    print(f"  step 0 (Prefill): {with_cache_times[0] * 1000:.1f} ms")
    print(f"  之后每步耗时: {[round(t * 1000, 1) for t in with_cache_times[1:]]} ms")
    print(f"  是否随步数明显变慢: {with_cache_pattern['is_growing']}")

    print(
        "\n两组的 step 0（Prefill）耗时应该接近——都是处理一整段 prompt；差别在后面的 Decode 步："
        "\n不用 KV Cache 的每一步都要把之前生成的 token 重新算一遍，序列越长每步越慢（is_growing=True）；"
        "\n用 KV Cache 之后每步只算 1 个新 token，耗时应该基本持平（is_growing=False）。"
        "\n这就是为什么 Decode 阶段被归类为 Memory-bound（读 KV Cache 的带宽是瓶颈，不是算力）——"
        "\n对应 Chapter 3 GPU 架构基础、Chapter 15 Decode 性能分析。"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B")
    parser.add_argument("--dtype", default="float16", choices=list(DTYPE_BYTES))
    parser.add_argument("--context-lens", type=int, nargs="+", default=[2048, 8192, 32768])
    parser.add_argument("--prompt", default="用一句话解释什么是 KV Cache。")
    parser.add_argument("--decode-steps", type=int, default=5)
    parser.add_argument("--skip-kv-growth-demo", action="store_true", help="Skip the Prefill+Decode run that shows past_key_values growing")
    parser.add_argument("--skip-timing-demo", action="store_true", help="Skip the with/without-KV-cache step-timing comparison (this one runs generation twice, so it's the slowest part)")
    parser.add_argument("--skip-walkthrough-demo", action="store_true", help="Skip the predicted-vs-actual shape walkthrough (transformer-explainer-style)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    model, config = load_model_and_config(args.model, args.dtype)
    arch = summarize_architecture(config)

    print_architecture(args.model, arch)
    print_kv_cache_story(arch, DTYPE_BYTES[args.dtype], args.context_lens)
    print_architecture_family_diff()

    if args.skip_kv_growth_demo and args.skip_timing_demo and args.skip_walkthrough_demo:
        return

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if not args.skip_kv_growth_demo:
        run_prefill_decode_demo(model, tokenizer, args.prompt, args.decode_steps)
    if not args.skip_timing_demo:
        run_timing_comparison_demo(model, tokenizer, args.prompt, args.decode_steps)
    if not args.skip_walkthrough_demo:
        walk_forward_pass(model, tokenizer, args.prompt, arch)


if __name__ == "__main__":
    main()
