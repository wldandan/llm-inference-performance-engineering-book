# Chapter 2 Demo：真实请求生命周期证据

第 1 章和第 2 章都会访问真实 vLLM，但交付物不同：

| | 第 1 章 | 第 2 章 |
|---|---|---|
| 目标 | 证明服务能够启动并完成流式调用 | 解释一条请求的生命周期由哪些证据支持 |
| 主要输入 | 一条真实流式请求 | 同一请求、请求级 timing metrics、`/metrics` 前后快照 |
| 主要输出 | 客户端调用报告 | 带证据等级的生命周期报告 |
| 不做 | 服务端阶段归因 | Benchmark、调优和根因结论 |

本章主程序是 `capture_lifecycle.py`。它在 GPU 上运行的真实 vLLM 服务中发送一条流式请求，并把结果分成：

- **直接观测**：客户端事件、vLLM 返回的请求 ID、usage、请求级 timing metrics，以及 Prometheus 聚合指标增量；
- **计算得到**：客户端首个内容 chunk 等待和流式端到端时间；
- **推断**：API 没有暴露精确时间戳的阶段；
- **不可得**：当前证据不足，不能写成 `0 ms`，也不能强行归因。

## 1. 运行环境

- Linux + NVIDIA GPU；
- Python 3.10 或更高版本；
- 已安装支持 OpenAI-compatible API 的 vLLM；
- 推荐启用 vLLM 的 per-request metrics。

先记录版本：

```bash
python3 --version
vllm --version
nvidia-smi
```

## 2. 启动真实 vLLM 服务

GX10 示例：

```bash
vllm serve /home/admin/models/Qwen2.5-0.5B-Instruct \
  --served-model-name Qwen/Qwen2.5-0.5B-Instruct \
  --enable-per-request-metrics \
  --host 0.0.0.0 \
  --port 8000
```

如果当前 vLLM 版本不支持 `--enable-per-request-metrics`，脚本仍可采集客户端事件和 `/metrics` 聚合增量，但会把 Queue、scheduled-to-first-token 和 Decode 的单请求时长标为 `unavailable`，不会用零值补齐。

## 3. 采集生命周期证据

从仓库根目录运行：

```bash
python3 code/ch02/capture_lifecycle.py \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --prompt "请解释一次 LLM 请求的生命周期。" \
  --max-tokens 128 \
  --model-revision local-snapshot \
  --server-command "vllm serve ... --enable-per-request-metrics" \
  --require-server-metrics \
  --require-complete-evidence \
  --output content/ch02/evidence/gx10-real-lifecycle-report.json
```

`--require-server-metrics` 检查 Queue、TTFT 和 Generation 三个请求级时长，失败时返回状态码 `2`。`--require-complete-evidence` 还检查 request ID、usage、Python/vLLM/GPU、模型 revision 和服务启动命令，失败时返回状态码 `3`。任一项缺失，报告中的 `acceptance.status` 都会是 `incomplete`。

## 4. 如何阅读报告

报告包含四部分：

| 字段 | 含义 |
|---|---|
| `direct_observations.client_events_ms` | 客户端单调时钟上的请求、响应头、内容 chunk 与结束事件 |
| `direct_observations.server_per_request_metrics_ms` | vLLM 直接返回的单请求 Queue、TTFT、Generation 等时长 |
| `direct_observations.server_prometheus_delta` | 请求前后服务端聚合指标变化 |
| `phase_evidence` | 每个生命周期阶段的证据等级与边界说明 |

需要特别注意：

- `time_to_first_content_chunk` 是客户端看到首段文本的时间，不等于纯 Prefill；
- `time_to_first_token_ms` 按当前 vLLM 的请求级指标合同表示从调度到首个输出 token，脚本使用 `scheduled_to_first_token` 保存，不擅自改名；
- Prometheus delta 是直接观测到的**服务端聚合证据**。有其他并发流量时，它不能归属于当前请求；
- GPU 快照或 GPU Utilization 不能证明某个阶段的根因，本章不做这种推断。

## 5. 离线分析器

`lifecycle_trace.py` 与 `sample-events.jsonl` 是辅助练习，用于验证正常、取消、失败和非法状态跳转：

```bash
python3 code/ch02/lifecycle_trace.py \
  --input code/ch02/sample-events.jsonl
```

样例数据是合成事件，不使用 GPU，不代表真实 vLLM 的阶段耗时。[离线合成验收报告](../../content/ch02/evidence/offline-synthetic-lifecycle-report.json)只证明分析器可运行，不能替代本章新的真实采集结果。

## 6. 测试

```bash
python3 -m unittest discover -s code/ch02 -p 'test_*.py'
```

测试覆盖 SSE payload、客户端/服务端证据分层、缺失服务端指标、Prometheus 解析与增量、正常/取消/失败状态，以及 CLI 输出。单元测试不需要 GPU；课程主 Demo 的验收仍必须连接真实 GPU 上的 vLLM。

## 7. 参考文档

本章字段名与阶段边界的出处：

- [vLLM RequestStatus](https://docs.vllm.ai/en/stable/api/vllm/v1/request/)：2.2 节归一化状态的对照来源。
- [vLLM Per-Request Metrics](https://docs.vllm.ai/en/latest/features/per_request_metrics/)：`time_to_first_token_ms` 起点的依据，2.10 节的版本注意事项来自这里。
- [vLLM Production Metrics](https://docs.vllm.ai/en/latest/usage/metrics/)：Prometheus 指标名与类型，采集 delta 时对照。
- [vLLM Benchmark CLI：Latency Metrics](https://docs.vllm.ai/en/stable/benchmarking/cli/)：官方压测工具的指标口径，第 7 章建立 Baseline 时对照。

链接会随 vLLM 版本变化。核对字段之前先确认文档版本与 `environment.vllm_version` 一致。
