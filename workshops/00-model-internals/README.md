# Workshop 00：模型参数入门 —— 从模型结构走进 LLM Serving

这个不是标准的"加压制造瓶颈→优化→对比"五步实验（那是样板一~十三的格式），而是一个更早、更基础的入口：先看懂一个真实模型的结构参数，再看这些参数怎么直接决定了后面所有优化技术存在的理由。对应这张图：

```
Qwen2.5-0.5B
     │
Prefill / Decode
     │
  KV Cache
     │
num_kv_heads = 2   (GQA)
     │
KV Cache 较小
     │
vLLM / PagedAttention
     │
Continuous Batching
```

改编自三个来源，归属说明同 `../common/naive_baseline_server/NOTICE.md`：

- 《Hands-On LLM Serving and Optimization》(Chi Wang & Peiheng Hu, O'Reilly) 的 `ch02/ch2_Inside_the_Mind_of_a_Transformer.ipynb`：打印 `model.config` 和模块结构，但没有把 GQA 和 KV Cache 大小的账算清楚——这正是这张图"num_kv_heads=2 → KV Cache 较小"想讲的核心，所以 `kv_cache_math.py` 是新写的，不是照抄。
- 同书的 `ch02/ch2_Workthrough_LLM_execution.ipynb`：手动拆开 generate 循环逐步计时，对比有/无 KV Cache，画图看时间变化——这是"Prefill/Decode"这条线背后的时间账，`timing_stats.py` + `explore.py` 里的计时部分是照着这个思路重写的（不是照抄；原 notebook 的 with-cache 循环把 `max_new_tokens`/`min_new_tokens` 传给了一次原始 forward 调用，这两个参数对 forward 没有意义，这版去掉了）。
- [Transformer Explainer](https://poloclub.github.io/transformer-explainer/)（Georgia Tech Polo Club，交互式网页工具，可视化 GPT-2 的完整前向过程：Embedding → 12 层 Transformer Block（Multi-Head Attention → MLP）→ 输出层 softmax）：这是个活的网页应用，没法嵌入或照抄代码，`transformer_walkthrough.py` 按同样的分段思路重做了一遍，但对着真实加载的 Qwen2.5 模型走，而且明确列出了 Qwen2.5 和它可视化的 GPT-2 在架构上的四处真实差异（不是同一个模型家族，不能假装一样）。

## 四个文件，两种性质

- **`kv_cache_math.py`** + **`timing_stats.py`** + **`transformer_walkthrough.py`**：纯函数部分，不需要 GPU、不需要装 `transformers`/`torch`。
  - `kv_cache_math.py` 把"KV Cache 有多大"变成公式：`2 × 层数 × KV头数 × head_dim × dtype字节数`。
  - `timing_stats.py` 把"这组计时是不是随步数变慢"变成一个可测试的判断（`is_growing`），不用只靠肉眼看图。
  - `transformer_walkthrough.py` 的 `architecture_family_diff()`（GPT-2 vs Qwen2.5 架构对照表）和 `expected_stage_shapes()`（从 config 算出每个阶段的张量形状）是纯函数；`walk_forward_pass()` 是 GPU-touching 的那部分，见下。
  - `python3 -m unittest test_kv_cache_math.py test_timing_stats.py test_transformer_walkthrough.py test_explore.py` 不需要任何 GPU 环境就能跑（25 个测试）——这一批测试也真的抓到过一个 bug（`_get_submodule` 一开始把 `nn.ModuleList` 的下标索引写成了 `getattr`，测试跑起来直接报 `TypeError`，已修）。
- **`explore.py`**：真正加载模型的部分，需要 `transformers` + `torch`（有 GPU 更好，CPU 也能跑 Qwen2.5-0.5B 这种小模型，只是慢）。做四件事：
  1. 打印真实模型的 config，喂给 `summarize_architecture` 算出 GQA 的具体节省比例（空间账）。
  2. 跑一次 Prefill + 几步 Decode，打印 `past_key_values` 的长度，亲眼看到 KV Cache 每 Decode 一步 +1。
  3. 分别跑一遍"不用 KV Cache"（每步重算整个变长序列）和"用 KV Cache"（每步只算 1 个新 token），逐步计时对比，用 `describe_timing_pattern` 判断哪组随步数明显变慢（时间账）。
  4. **新增**：打印 GPT-2 vs Qwen2.5 的架构对照表，然后在真实模型上注册 forward hook，跑一次前向，把 `expected_stage_shapes()` 预测的形状和 hook 真实捕获的形状逐项核对打印出来（比如 query/key/value 投影的最后一维，GQA 的不对称能直接从数字上看出来：14×64=896 vs 2×64=128）。

## 怎么跑

```bash
# 只看参数、KV Cache 空间账、GPT-2 vs Qwen2.5 架构对照表，不加载 tokenizer、不跑生成（最快，适合先过一遍）
python3 explore.py --model Qwen/Qwen2.5-0.5B --skip-kv-growth-demo --skip-timing-demo --skip-walkthrough-demo

# 加上 KV Cache 增长演示，跳过计时对比和逐层核对（计时部分要跑两遍生成，最慢）
python3 explore.py --model Qwen/Qwen2.5-0.5B --skip-timing-demo --skip-walkthrough-demo

# 完整版：空间账 + 架构对照表 + KV Cache 增长 + 有/无 Cache 计时对比 + 逐层 predicted vs actual 核对
python3 explore.py --model Qwen/Qwen2.5-0.5B --decode-steps 5
```

**计时是定性演示,不是严谨 benchmark**——单次运行、没有 warmup、没有多次重复取统计量（那一套在 `workshops/` 的五步实验里才做）。这里的目的只是让学员看到"有无 Cache，时间曲线形状不一样"这个定性差异,不是拿具体毫秒数做结论。

## 预期输出（不需要真的跑，这里是用假 config/假计时数据验证过的真实数字）

```
num_attention_heads    = 14  (Query 头数)
num_key_value_heads    = 2   (K/V 头数 -- 这就是图里的 num_kv_heads)
query_groups           = 7   (每 7 个 Query 头共享 1 组 K/V)

如果没有 GQA：每 token KV Cache = 86016 bytes
实际（GQA）：每 token KV Cache = 12288 bytes
GQA 省了 85.7% 的 KV Cache

context_len=  2048: 24.00 MB / 条序列
context_len=  8192: 96.00 MB / 条序列
context_len= 32768: 384.00 MB / 条序列

不用 KV Cache：is_growing = True   (每步重算整个序列，越来越慢)
用 KV Cache：  is_growing = False  (每步只算 1 个新 token，基本持平)

query_states: predicted=(1, 10, 896)  actual=(1, 10, 896)  [match]
key_states:   predicted=(1, 10, 128)  actual=(1, 10, 128)  [match]
value_states: predicted=(1, 10, 128)  actual=(1, 10, 128)  [match]
```

空间账（KV Cache 多大）和时间账（每步多久）合在一起，就是后面样板一（PagedAttention）、
样板二（Batching）为什么值得做的具体理由：KV Cache 单条序列占用越小、Decode 每步越稳定，
同样一块 GPU 显存能同时服务的并发请求就越多。

## 换个模型看看 GQA 有没有、差多少

```bash
python3 explore.py --model Qwen/Qwen2.5-7B-Instruct --skip-kv-growth-demo --skip-timing-demo --skip-walkthrough-demo
python3 explore.py --model gpt2 --skip-kv-growth-demo --skip-timing-demo --skip-walkthrough-demo   # 老模型没有 GQA，num_kv_heads == num_attention_heads
```

用 `gpt2` 对比一下：`uses GQA` 会显示 `False`，GQA 节省比例会是 0%——这能帮学员直观看到"不是所有模型都有这个优化"。**注意**：换成 `gpt2` 时一定要加 `--skip-walkthrough-demo`——架构对照表和逐层核对（`transformer_walkthrough.py`）是写死对比 Qwen2.5 家族的，模块路径（`model.layers.0.self_attn.q_proj` 这种）对 GPT-2 checkpoint（模块名是 `transformer.h.0.attn.c_attn` 这种合并了 QKV 的写法）不成立，会全部显示"跳过"，不会报错但也没有意义。

## 单元测试

```bash
python3 -m unittest test_kv_cache_math.py test_timing_stats.py test_transformer_walkthrough.py test_explore.py
```
