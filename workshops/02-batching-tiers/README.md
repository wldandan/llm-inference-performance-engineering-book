# Workshop 02：Static → Continuous Batching（3 档，非 vLLM + vLLM）

对应 `workshops/README.md` 样板二，但**跑起来之后按实际可搭建的口径做了调整**：原计划做 Static/Dynamic/Continuous 三档对比，Dynamic Batching（时间窗口攒批）需要 Triton dynamic batcher 或自建调度器，找不到能直接跑的最小参照实现；反而在《Hands-On LLM Serving and Optimization》(Chi Wang & Peiheng Hu, O'Reilly) 的配套代码里找到一个用纯 `transformers`（不用 vLLM）写的服务，同时实现了 Static 和 Continuous 两种调度——细节见 `../common/naive_baseline_server/NOTICE.md`。所以实际的三档变成：

| Tier | 引擎 | 调度方式 |
|---|---|---|
| Tier 1 | naive_baseline_server（纯 transformers） | Static：`/generate` 一次性提交整批 prompt，`model.generate()` 跑完整批才返回 |
| Tier 2 | naive_baseline_server（同一个服务，另一个端点） | Continuous：`/generate_stream`，每步都从队列里把新请求补进正在跑的 batch |
| Tier 3 | vLLM | Continuous（生产级），外加 PagedAttention、CUDA Graph 等 vLLM 的其他优化 |

`requests.jsonl` 不是手写的，是从书配套代码 `ch09/sharegpt_samples.json`（真实 ShareGPT 采样，带 `prompt_len`/`expected_output_len`）里用 `../common/convert_sharegpt.py` 选出的 6 条最短 + 4 条最长请求，长短混合是真实数据自带的，不是编出来的。

**重要口径提醒**：Tier1→Tier2 才是纯粹的"调度粒度"对比（同一个引擎，只换调度方式）；Tier2→Tier3 混进了 vLLM 的所有其他优化（PagedAttention、CUDA Graph、更高效的 attention kernel……），差距不能全部归因于"batching 更好"。这个提醒也打印在 `print_summary.py` 的输出里。另外 Tier1/2 用的这个 naive 服务在流式路径里完全不用 KV Cache（每一步都重新算全部历史），比"只是没有分页管理"还要慢得多，所以默认模型用了很小的 `facebook/opt-125m`，不要在这上面跑大模型。

## Step 1-2：Tier 1（Static）

```bash
bash serve_naive.sh              # 终端 1
bash bench_tier1_static.sh       # 终端 2
```

## Step 3-4：Tier 2（Continuous，同一个服务）

不用重启服务，直接换一个 bench 脚本打同一个服务：

```bash
bash bench_tier2_continuous_naive.sh   # 终端 2
```

## Step 5（部分）：Tier 3（vLLM，生产级 Continuous）

```bash
# 先 Ctrl+C 停掉终端 1 的 naive 服务
bash serve_vllm.sh               # 终端 1
bash bench_tier3_vllm.sh         # 终端 2
```

## 对比

```bash
python3 print_summary.py tier1_static.json tier2_continuous_naive.json tier3_continuous_vllm.json
```

## 单元测试

```bash
(cd ../common && python3 -m unittest test_bench_client.py test_compare.py test_convert_sharegpt.py)
(cd ../common/naive_baseline_server && python3 -m unittest test_bench_naive.py)
```
