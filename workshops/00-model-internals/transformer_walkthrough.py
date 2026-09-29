"""Walk a real forward pass stage by stage, GPT-2-explainer style, but for
our actual model (Qwen2.5, not GPT-2).

Reference: https://poloclub.github.io/transformer-explainer/ -- an
interactive visualization of a GPT-2-small forward pass: Embedding
(tokenize -> token embedding -> learned positional encoding -> sum) ->
12 stacked Transformer blocks (LayerNorm -> Multi-Head Self-Attention with
causal mask -> residual -> LayerNorm -> MLP up-project 768->3072, GELU,
down-project 3072->768 -> residual) -> final LayerNorm -> output projection
to 50,257 vocab logits -> softmax.

That tool is GPT-2 specific and not something we can embed or re-host (it's
a live web app, not notebook code like the other book-derived files in this
tree), so this file does the same STAGE-BY-STAGE idea against our own model
instead, and is explicit about where a modern model like Qwen2.5 differs
from the GPT-2 architecture the visualizer shows -- see
`architecture_family_diff()`. The two headline differences that actually
show up as different tensor shapes (not just different math) are: GQA makes
Key/Value smaller than Query (already the subject of kv_cache_math.py), and
SwiGLU's MLP has two parallel projections into intermediate_size (gate_proj
and up_proj) where GPT-2's MLP has only one.

`expected_stage_shapes` is pure (testable without a model). `walk_forward_pass`
below it is the GPU-touching half: it registers forward hooks on the real
named modules of a loaded Qwen model and prints the ACTUAL shapes next to
the predicted ones.
"""

from __future__ import annotations

from kv_cache_math import ArchSummary


def architecture_family_diff() -> list[dict[str, str]]:
    """What poloclub.github.io/transformer-explainer shows (GPT-2) vs what
    this demo's model actually is (Qwen2.5). Static reference table, no
    model needed.
    """
    return [
        {
            "aspect": "位置编码",
            "gpt2": "学出来的绝对位置 embedding，和 token embedding 相加（wpe 矩阵）",
            "qwen": "RoPE（旋转位置编码），作用在 Q/K 上，没有单独的位置 embedding 矩阵",
        },
        {
            "aspect": "Attention",
            "gpt2": "标准 Multi-Head Attention，Query/Key/Value 头数相同",
            "qwen": "GQA（Grouped Query Attention），Key/Value 头数远少于 Query（这里是 2 vs 14）——见 kv_cache_math.py",
        },
        {
            "aspect": "归一化",
            "gpt2": "LayerNorm（有均值中心化，有 bias）",
            "qwen": "RMSNorm（只做均方根归一化，没有均值中心化，计算更省）",
        },
        {
            "aspect": "MLP",
            "gpt2": "两层：hidden_size -> intermediate_size（GELU）-> hidden_size，一个上投影矩阵",
            "qwen": "SwiGLU 门控结构：gate_proj 和 up_proj 两个并行的上投影矩阵，"
            "down_proj(silu(gate_proj(x)) * up_proj(x))，比 GPT-2 多一个矩阵",
        },
    ]


def expected_stage_shapes(arch: ArchSummary, seq_len: int, batch: int = 1) -> dict[str, tuple[int, ...]]:
    """Predict the tensor shape at each named pipeline stage, using Qwen's
    real architecture (GQA + SwiGLU), not GPT-2's simpler one.

    query_states/key_states/value_states are the RAW q_proj/k_proj/v_proj
    Linear-layer outputs -- (batch, seq_len, num_heads * head_dim) -- not
    the reshaped-into-heads 4D view. That reshape happens inside the
    attention module's forward code, after the Linear layer, so it isn't a
    separate hookable submodule; walk_forward_pass() below hooks the Linear
    layers themselves, so predictions here match what that hook actually
    sees. The GQA asymmetry is still visible: the last dimension differs
    (num_attention_heads*head_dim vs num_kv_heads*head_dim), just without a
    separate head axis.
    attention_scores_per_head is the one stage with no real submodule to
    hook in modern transformers (SDPA/flash-attention backends don't
    materialize a separate "scores" tensor as a distinct nn.Module output),
    so it's predicted here for the conceptual picture but walk_forward_pass()
    can't verify it against a real hook.
    """
    return {
        "token_embedding_matrix": (arch.vocab_size, arch.hidden_size),
        "hidden_states_after_embedding": (batch, seq_len, arch.hidden_size),
        "query_states": (batch, seq_len, arch.num_attention_heads * arch.head_dim),
        "key_states": (batch, seq_len, arch.num_kv_heads * arch.head_dim),
        "value_states": (batch, seq_len, arch.num_kv_heads * arch.head_dim),
        "attention_scores_per_head": (batch, arch.num_attention_heads, seq_len, seq_len),
        "attention_output": (batch, seq_len, arch.hidden_size),
        "mlp_gate_proj": (batch, seq_len, arch.intermediate_size),
        "mlp_up_proj": (batch, seq_len, arch.intermediate_size),
        "mlp_down_proj_output": (batch, seq_len, arch.hidden_size),
        "final_logits": (batch, seq_len, arch.vocab_size),
    }


# Stage name -> where to find that module on a real HF Qwen2-family model
# (`AutoModelForCausalLM.from_pretrained("Qwen/...")`). Qwen2/Qwen2.5 follows
# the same module layout as Llama in transformers, so this should hold for
# any Qwen2-family checkpoint, not just the 0.5B one this demo defaults to.
QWEN_MODULE_PATHS = {
    "hidden_states_after_embedding": "model.embed_tokens",
    "query_states": "model.layers.0.self_attn.q_proj",
    "key_states": "model.layers.0.self_attn.k_proj",
    "value_states": "model.layers.0.self_attn.v_proj",
    "mlp_gate_proj": "model.layers.0.mlp.gate_proj",
    "mlp_up_proj": "model.layers.0.mlp.up_proj",
    "mlp_down_proj_output": "model.layers.0.mlp.down_proj",
    "final_logits": "lm_head",
}


def _get_submodule(model, dotted_path: str):
    """`nn.ModuleList` (e.g. `model.layers`) is indexed with `[i]`, not
    `getattr(obj, i)` -- attribute names must be strings, and ModuleList
    isn't attribute-accessed by position anyway. Only plain attributes go
    through getattr; digit segments go through __getitem__.
    """
    module = model
    for part in dotted_path.split("."):
        module = module[int(part)] if part.isdigit() else getattr(module, part)
    return module


def walk_forward_pass(model, tokenizer, prompt: str, arch: ArchSummary) -> None:
    """Register forward hooks on the real modules named in QWEN_MODULE_PATHS,
    run one real forward pass, and print predicted (expected_stage_shapes)
    vs actual shape side by side for each stage. This is the part neither
    source notebook does -- ch2_Inside_the_Mind_of_a_Transformer.ipynb only
    inspects static module attributes (num_heads, head_dim as *numbers*),
    not the runtime activation shapes a hook captures.
    """
    import torch

    captured: dict[str, tuple[int, ...]] = {}

    def make_hook(stage_name: str):
        def hook(_module, _inputs, output):
            tensor = output[0] if isinstance(output, tuple) else output
            captured[stage_name] = tuple(tensor.shape)

        return hook

    handles = []
    for stage_name, dotted_path in QWEN_MODULE_PATHS.items():
        try:
            module = _get_submodule(model, dotted_path)
        except AttributeError:
            continue  # this checkpoint's module layout doesn't match -- skip that stage
        handles.append(module.register_forward_hook(make_hook(stage_name)))

    try:
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        seq_len = inputs.input_ids.shape[1]
        with torch.no_grad():
            model(**inputs)
    finally:
        for handle in handles:
            handle.remove()

    predicted = expected_stage_shapes(arch, seq_len=seq_len, batch=1)

    print("\n=== 逐层核对：predicted（从 config 算出来的）vs actual（真实 forward hook 捕获）===")
    print("参考 https://poloclub.github.io/transformer-explainer/ 的可视化顺序，但那是 GPT-2；这里是真实加载的模型。")
    print("注意 query/key/value_states 是 q_proj/k_proj/v_proj 这个 Linear 层自己的原始输出，")
    print("还没 reshape 成多头视图（那一步在 attention 模块内部做，不是单独的子模块）——")
    print("即便如此，GQA 的不对称已经能看出来：query 最后一维远大于 key/value。")
    for stage_name in QWEN_MODULE_PATHS:
        if stage_name not in captured:
            print(f"  {stage_name}: (跳过，这个 checkpoint 没有匹配的模块路径)")
            continue
        predicted_shape = predicted[stage_name]
        actual_shape = captured[stage_name]
        match = "match" if predicted_shape == actual_shape else "MISMATCH"
        print(f"  {stage_name}: predicted={predicted_shape}  actual={actual_shape}  [{match}]")
