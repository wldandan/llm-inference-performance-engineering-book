# Chapter 1 Demo：第一个 LLM 服务

本 Demo 是全书的起点，只完成两个动作：

1. 使用 vLLM 启动一个 OpenAI-compatible 服务。
2. 使用客户端脚本访问这个服务，观察请求、首个内容 chunk、后续 chunks 和结束信号。

模型下载、模型选择和环境准备由读者或实验环境提前完成。本章不提供下载模型脚本。

## 1. 运行前提

本章默认使用 Linux + NVIDIA GPU 环境。按照 vLLM 官方文档准备独立 Python 环境并安装 vLLM；不同 CUDA、ROCm、CPU 或 Apple Silicon 环境应使用对应的安装方式。

开始前记录环境信息，后续性能实验需要把这些版本写入报告：

```bash
python3 --version
vllm --version
nvidia-smi
```

vLLM 官方文档：

- [安装说明](https://docs.vllm.ai/en/stable/getting_started/installation/)
- [vLLM CLI](https://docs.vllm.ai/en/stable/cli/index.html)

## 2. 启动 vLLM 服务

本章默认模型名：

```text
Qwen/Qwen2.5-0.5B-Instruct
```

如果模型已经在 Hugging Face cache 中，或当前环境可以直接解析该模型 id：

```bash
python3 code/ch01/start_vllm.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --served-model-name Qwen/Qwen2.5-0.5B-Instruct \
  --host 0.0.0.0 \
  --port 8000
```

如果模型已经在本地目录，例如 GX10 上的 `/home/admin/models/Qwen2.5-0.5B-Instruct`：

```bash
python3 code/ch01/start_vllm.py \
  --model /home/admin/models/Qwen2.5-0.5B-Instruct \
  --served-model-name Qwen/Qwen2.5-0.5B-Instruct \
  --host 0.0.0.0 \
  --port 8000
```

也可以不用封装脚本，直接使用官方 CLI：

```bash
vllm serve /home/admin/models/Qwen2.5-0.5B-Instruct \
  --served-model-name Qwen/Qwen2.5-0.5B-Instruct \
  --host 0.0.0.0 \
  --port 8000
```

如果只想确认封装脚本生成的命令，不启动服务：

```bash
python3 code/ch01/start_vllm.py --dry-run
```

## 3. 确认服务可访问

```bash
curl http://127.0.0.1:8000/v1/models
```

如果是远程机器，先确认网络或 SSH 隧道已经打通。

## 4. 使用脚本访问服务

从 Git 仓库根目录运行：

```bash
python3 code/ch01/streaming_client.py \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --prompt "请用三句话介绍 LLM 在线推理。" \
  --max-tokens 256 \
  --requests 1 \
  --concurrency 1
```

脚本会输出 JSON，记录客户端观察到的：

- 请求是否成功。
- `prompt`：实际发送给 vLLM 的原始输入。
- 首个流式 chunk 等待时间。
- 后续 chunk 间隔。
- 总请求耗时和 `request_output_rate_tokens_per_second`；后者包含首包等待，不是纯 Decode token 速率。
- token usage，如果服务端返回。
- GPU 快照，如果脚本运行机器本身支持 `nvidia-smi`。

第 1 章只要求读者把这些字段对应到客户端观察事件，不把观察值直接归因到服务端阶段，也不评价性能数值。第 5 章定义指标，第 7 章再讨论可信的 Benchmark。

正常情况下，终端会输出一份 JSON 报告。`summary.successes` 应为 `1`，`results[0].time_to_first_content_chunk_ms`、`total_latency_ms` 和 `stream_chunks` 应有值。服务未启动、模型名不匹配、SSE 返回错误或连接在 `[DONE]` 前中断时，脚本会返回非零状态并输出错误原因。

## 5. GX10 验收记录

本书已在 GX10 的 `/home/admin/code/llm-inference-performance-engineering/code/ch01` 完成真实运行，使用 NVIDIA GB10 和 `Qwen/Qwen2.5-0.5B-Instruct`。脱敏报告保存在 [GX10 客户端流式报告](../../content/ch01/evidence/gx10-streaming-client-report.json)：1 次请求成功，收到 256 个输出 token，SSE 正常结束。旧记录中的 `vllm_version` 缺失，因此它可以证明链路跑通，但还不是完整的可复现实验记录；下次 GX10 复跑必须补录版本。

这份报告用于验收端到端链路，不是 Benchmark。它只有一个请求、一个并发，没有 Warmup、重复实验或负载分布控制。

## 6. 单元测试

单元测试只验证命令构造、请求构造和客户端计算逻辑，不需要启动 vLLM：

```bash
python3 -m unittest discover -s code/ch01 -p 'test_*.py'
```

## 补两份记录里缺的字段

`streaming_client.py` 现在还会记三样 1.9 和 1.11 点过名的东西，不必再手工补：

```text
validation_environment  主机名、Python 版本、GPU、驱动，以及从服务 /version 问来的 vLLM 版本
finish_reason           这次是自然结束（stop）还是被 max_tokens 截断（length）
raw_content_events      引擎发出的分片总数；stream_chunks 只数正文非空的那些
empty_content_events    两者之差，正文为空的分片个数
```

最后两项解释的是 1.9 那个“254 个分片对 256 个 token”：**`stream_chunks` 的口径是正文非空的分片**，脚本遇到 `delta.content` 为空串时直接跳过。有的 token 解不出完整字符，引擎就会发出一个正文为空的分片，它不计数。跑一次就能看到 `raw_content_events − stream_chunks` 正好是差额，不用去抓包。

拿到新报告之后，把 `content/reference/environment.md` 第一节里那两处“待填”补上。
