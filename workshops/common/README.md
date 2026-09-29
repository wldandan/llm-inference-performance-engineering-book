# 统一 Benchmark 框架

`bench_client.py` 向 OpenAI-compatible 流式服务发送固定 workload，生成可由
`compare.py` 直接对比的 JSON 报告。脚本只使用 Python 标准库，不依赖特定推理框架。

## 最小用法

在任一 Workshop 目录中，服务启动后运行：

```bash
MODEL=Qwen/Qwen2.5-7B-Instruct \
LABEL=baseline \
CONFIG_NOTE="prefix cache disabled" \
REQUESTS_FILE=requests.jsonl \
bash ../common/bench.sh
```

固定 batch 的引擎可额外设置 `BATCH_SIZE=8`。Continuous/dynamic batching 的实际
batch size 无法从 OpenAI-compatible 接口观测，应留空，报告会明确记录该限制；
不要用客户端并发数冒充引擎 batch size。

对比时第一个文件必须是 baseline：

```bash
python3 ../common/compare.py baseline.json optimized.json
```

## 报告契约（schema 1.0）

每份报告统一保留：

- `model.id`：模型标识。
- `hardware.gpus`：GPU 型号、利用率、已用/总显存；无 NVIDIA GPU 时为空列表。
- `environment`：操作系统、Python 和 vLLM/PyTorch/Transformers 版本。
- `workload`：请求数、客户端并发数、引擎 batch size，以及实际输入/输出 token
  的 min/p50/p95/max/total。
- `metrics.latency`：TTFT、ITL 和端到端延迟。
- `metrics.throughput`：基于整段 benchmark 墙钟时间的 RPS、输入 TPS 和输出 TPS。
- `metrics.gpu_memory_used_mb`：benchmark 前后快照中的最大已用显存。

`summary.tokens_per_second_sum` 只为兼容旧 Workshop 保留。它把每个并发请求的速率相加，
不是服务整体吞吐，新实验必须使用 `output_throughput_tokens_per_second`。

## 可比性保护

`compare.py` 会对模型、客户端并发数、输入 token 分布和 GPU 型号做一致性检查。
任一项不一致都会在对比表后输出 `WARNING`，该结果不应用来得出优化结论。

## 已知限制

- token 长度依赖服务在流式响应中返回 usage；不返回时相关字段为 `null`。
- 显存目前是 benchmark 前后快照，不是高频峰值采样，短暂的 KV Cache 峰值可能被漏掉。
- 指标是客户端观测值，不替代服务端 tracing 或 profiler 证据。
- 首次模型下载、编译和预热会影响结果；正式实验应在相同环境多次重复。

