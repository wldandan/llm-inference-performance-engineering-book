# Chapter 13 Demo：四条路的适用条件自检

`prefill_optimization_check.py` 读入第 6 章的 workload 描述和第 12 章的上下文账单，对四条路各给一个判断：适用 / 有限 / 不适用，以及依据、预期、代价、前提、风险。

**它不替你做决定。** 四条路同时标为“适用”时，仍然要一次只试一条。

只依赖 Python 标准库，不需要 GPU。

## 1. 完整流水线

这个 Demo 的输入是前面两章的输出，三步连起来跑：

```bash
# 1. 第 6 章：写一份负载描述
python3 code/ch06/workload_builder.py \
  --profile rag --arrival poisson --rate 8 --duration 120 \
  --name prefill-long-context \
  --output workload-rag.json

# 2. 第 12 章：算一份上下文账单
python3 code/ch12/context_cost.py \
  --prompt-spec code/ch12/rag-prompt.json \
  --model-config code/ch11/model-qwen25-05b.json \
  --output context-cost-rag.json

# 3. 第 13 章：判断四条路
python3 code/ch13/prefill_optimization_check.py \
  --workload workload-rag.json \
  --context-cost context-cost-rag.json \
  --model-config code/ch11/model-qwen25-05b.json \
  --output prefill-options.json
```

**第 3 步拒绝手写的输入。** 缺 `cacheable` 或缺长度分布就直接报错，因为那两项正是判断的依据。这样做的用意是：想知道该开哪个开关，得先有一份负载描述和一份成本账单，顺序不能跳。

## 2. 每条路输出什么

```text
applicable              适用 / 有限 / 不适用
reason                  判断依据，带上具体数字
expected                预期改善什么，以及**改善的是谁的指标**
improves_whose_metric   本条请求 / 其他请求
cost                    代价落在哪里
prerequisite            启用前必须先确认的事
risk                    风险等级与回滚方式
evidence_field          这个判断读的是输入里哪个字段
```

`improves_whose_metric` 单独列一项，是因为 13.5 那件事最容易被忽略：**Chunked Prefill 改善的是别人的指标。** 报告里只看长请求 TTFT，会得出“这项技术有害”的错误结论。

## 3. 硬写进去的门槛

```text
CACHEABLE_FLOOR       0.30    可缓存前缀低于三成 → Prefix Cache 标为“有限”
FLASH_SHORT_PROMPT    1000    P50 低于千 token → FlashAttention 标为“有限”
MIXED_LENGTH_RATIO    3.0     P99/P50 低于 3 → Chunked Prefill 标为“不适用”
TRIM_FRACTION         0.40    裁剪 40% 时算出的收益，用来报预期
```

这四个数都是正文里写过的，放在代码顶部是为了让两边不会各说各的。改门槛就改这里，正文跟着改。

还有一条不带数字的规则：**没有提供质量评测配置时，上下文裁剪一定带警告。** 这条路的代价是质量，没有评测集就无法判断是否划算，那样的“优化”是在赌。

## 4. 多副本那一刀

`deployment` 里三个字段决定路由项：`replicas`（副本数 N）、`prefix_scope`（`shared` 表示全体请求共享的前缀，`session` 表示只被同一会话或同一文档复用的前缀，默认 `session`）、`prefix_reuse`（会话前缀被复用的次数 k）。这就是 13.3 那个算式的最后一项：

```text
命中率 ≈ 可缓存占比 × 局部性系数 × 未被淘汰的比例 × 路由项
路由项 ≈ 1 − N × (1 − (1 − 1/N)^k) ÷ k        会话前缀、随机路由
```

全体共享的前缀每个副本各存一份照样命中，路由项按 1 算；会话前缀按 k 和 N 算，N = 4、k = 2 时约 12.5%。没写 `prefix_reuse` 时按复用两次这种最保守的情形取 1/(2N)，并给出警告（1/N 不是最坏情况，路由项随 k 单调上升，k = 2 时只有 1/(2N)）。单实例或开了 `cache_aware_routing` 时路由不再打散，但每个前缀第一次出现时总要写一次，所以路由项取 1 − 1/k（复用两次是 50%），不是 1；第 22 章讲缓存感知路由收回的是打散那一刀。

## 5. 测试

```bash
python3 -m unittest discover -s code/ch13 -p 'test_*.py'
```

28 项测试，分四组：13.7 那三条硬规则各一条；13.8 那三个案例各一条（600 token 上 FlashAttention 有限、检索片段拼在 system 前面时缓存失效、清一色长请求低并发时 Chunked Prefill 不适用）；多副本路由折算（路由项的表、共享前缀不挨这一刀、会话前缀按复用次数算）；以及报告结构本身（四条路都在、判断只有三种取值、每条都说清改善谁的指标、顺序与 13.6 一致、纪律那句话里有“一次只试一条”）。

**正文案例各配一条测试是刻意的。** 案例的数字如果和工具判断不一致，读者会发现书里自相矛盾，而这类错误比正文出错更伤，因为案例是被当模板用的。
