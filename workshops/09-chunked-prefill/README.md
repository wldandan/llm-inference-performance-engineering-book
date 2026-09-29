# Workshop 09：Chunked Prefill

对应 `workshops/README.md` 样板九。`requests.jsonl` 第一行是一个约 900 字符的长 prompt（模拟审阅长文档），后面 6 行是几乎瞬间能完成的短问答——这是能触发"长 Prefill 阻塞短请求"现象的最小可信设计。

**验证过的 flag**（2026-09，vLLM 官方文档）：`--enable-chunked-prefill` / `--no-enable-chunked-prefill`。

**这个实验的核心指标不是聚合 p95**，而是"短请求"这一类单独的尾延迟——把长请求混进同一个聚合统计里会把信号稀释掉，所以多了一个 `analyze_short_vs_long.py`，专门把长/短请求分开算百分位。

## Step 1-2：baseline（关闭 chunked prefill）

```bash
bash serve_baseline.sh        # 终端 1
bash bench_baseline.sh        # 终端 2
python3 analyze_short_vs_long.py baseline.json
```

预期现象：`short requests` 那组的 `p95_total_latency_ms` / `p99_total_latency_ms` 明显偏高——短请求本身应该几十毫秒内完成，如果 p95 被拖到几百毫秒甚至更高，说明它们在排队等长请求的 Prefill。

## Step 3-4：开启 chunked prefill，重跑

```bash
bash serve_optimized.sh       # 终端 1，先 Ctrl+C 停掉 baseline
bash bench_optimized.sh       # 终端 2
python3 analyze_short_vs_long.py optimized.json
```

## Step 5：对比

```bash
python3 ../common/compare.py baseline.json optimized.json
python3 analyze_short_vs_long.py baseline.json
python3 analyze_short_vs_long.py optimized.json
```

对比两次 `analyze_short_vs_long.py` 的输出：`short requests` 组的尾延迟应该明显收窄；`long request` 组自身的总延迟可能略微变长（这是 Chunked Prefill 的代价——长请求被切成多块和别的请求交替执行，自己变慢了一点，换短请求不被拖累）。

## 单元测试

```bash
(cd ../common && python3 -m unittest test_bench_client.py test_compare.py)
python3 -m unittest test_analyze_short_vs_long.py
```
