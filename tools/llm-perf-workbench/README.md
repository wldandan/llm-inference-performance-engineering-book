# LLM 推理性能优化工作台 · V0.1

用自己的数据和流量做实验，比较模型/配置，查看指标与质量，再验证优化建议。

本工具独立于教材和章节 Demo。EvalScope 是实际发压器；工作台负责实验、口径、质量、资源指标、诊断与复测。只在你主动运行实验时请求模型，不部署模型、不通过 SSH 修改服务，也不自动调整生产参数。

## 启动网页

需要 macOS 或 Linux、Python 3.12；Windows 原生暂不支持进程组/文件锁，建议使用 Linux 环境。

```sh
cd "/Users/leiw/Projects/tutorials/leiw/Courses/cn/04 LLM 推理性能工程实战/tools/llm-perf-workbench"
uv sync --locked --extra dev --python 3.12
uv run --locked perfworkbench serve
```

打开 **http://127.0.0.1:8800**。默认仅本机访问，实验文件位于当前目录的 `.workbench/`；不要把该目录或上游原始日志当成脱敏报告分享。

如果已在此目录安装好依赖，也可直接运行 `.venv/bin/perfworkbench serve`。网页没有 CDN、在线字体或外部前端服务依赖。

## 没有模型时，先验证工具能跑通

另开终端，在同一目录启动显式的本地协议端点：

```sh
uv run --locked perfworkbench demo
```

再生成配置并执行一次实验：

```sh
uv run --locked perfworkbench init --output local-protocol.json
uv run --locked perfworkbench run local-protocol.json
```

输出包含实验 ID。用它查看或导出结果：

```sh
uv run --locked perfworkbench list
uv run --locked perfworkbench report 实验ID --format html --output report.html
```

**协议端点返回固定文本和固定 usage，不加载模型。它只能验证软件流程，不能用于模型选型、硬件容量或提速结论。** 协议示例不会获得“优化有效”的判定。20/50/100/200/400 只是示例标签，不代表真的提供了相应数量文章。

## 接入自己的模型服务

“新建实验”默认使用本地 Ollama 地址 `http://127.0.0.1:11434/v1`。填入已安装的真实模型 ID，即可用内置 5 条示例问题做一次小规模试跑；也可以选择 vLLM 或编辑其他 OpenAI-compatible 地址。页面不会自动下载模型、预检或发出生成请求。

- **快速试跑**：5 次测量、并发 1、无预热，默认每请求最大输出 256 tokens。第一次可能包含模型加载时间，不用于稳态容量结论。
- **基线测量**：50 次测量 + 1 次预热、并发 1。示例只有 5 条，会重复使用；真实基线应换为自己的代表性数据。
- **导入 JSONL 数据集**：替换请求数据，保留其他配置和原有安全预算。样本自己的 `max_tokens` 优先于全局设置。
- **导入实验配置**：右上角直接选择完整 `.json`（例如已准备的 `smoke.json`），无需手工粘贴；导入后保留原模型、负载、生成、质量与预算，显示为自定义配置。
- **高级设置**：连接信息、流量/生成、质量目标、安全/观测按组展开。完整 JSON 也可直接展开粘贴，不再要求先填完表单。

选择快捷预设会显式设置负载、默认输出上限和对应请求/并发/输出预算；**导入或手动改参数不会自动扩大预算**。开始前检查底部的实际请求量、输出预留和安全上限。默认质量需人工评价，GPU/KV 观测未配置时显示未知。流式用于采集客户端 TTFT/TPOT，不代表业务必须流式。

服务地址通常是 `http://主机:端口/v1`，模型 ID 使用该服务 `/v1/models` 的真实值。切换模型后，仍需主动点击“启动实验计划”才会开始调用。

也可编辑 `examples/real-service.json`。其中地址、模型、硬件版本和数据必须换成你的实际配置，再执行：

```sh
uv run --locked perfworkbench validate examples/real-service.json
uv run --locked perfworkbench preflight examples/real-service.json
uv run --locked perfworkbench run examples/real-service.json
```

预检是单独的主动操作：获取模型列表、最多两次生成（同步/流式各一次，每次上限 8 个输出 token）。预检消耗单列，不混入实验指标。正式实验禁用 EvalScope 隐式连接测试和重试。

如果需要认证，在启动工作台的终端环境里设置密钥，用 `endpoint.api_key_env` 填环境变量名（如 `LLM_API_KEY`），**不要填写密钥值**。数据集、配置和报告都不应该手工包含密钥。连接远端服务优先使用 HTTPS。

## 数据集与负载

每行一个独立业务请求，JSONL 示例：

```json
{"id":"classify-001","category":"classify-small","messages":[{"role":"user","content":"待分类的真实文章摘要……"}],"max_tokens":128}
{"id":"summarize-001","category":"summary-large","messages":[{"role":"user","content":"某技术主题下的真实摘要……"}],"max_tokens":512}
```

- `id` 必须唯一；同一条样本可重复发出，但每次调用有独立 request ID。
- `category` 用于混合比例、分组指标，不会把多份报告拼成一个请求。
- 支持文本 Chat Completions；工具调用、多模态、完整业务工作流不属于首版。
- 默认展示字符画像；只有指定本地 tokenizer 并应用 chat template，才展示预估输入 token。运行后 usage 用于实际逻辑 token 吞吐。
- `load.mode=concurrency` 表示固定并发；`rate` 表示到达速率。`load.mix` 定义类别权重，按最大余数法分配后用固定种子打散。实际组成始终可检查。
- 输出长度是 max_tokens 上限，不是强制生成长度；实际输出分布要看真实返回。

```sh
uv run --locked perfworkbench profile examples/dataset.jsonl
```

## 扫描与复测

在配置里设置 `load.scan`（例如固定并发模式的 `[1,2,4]`）及 `load.repeats`，启动一个计划。扫描改变一个负载变量，每点独立留档，预算覆盖所有点、重复和预热。

```sh
uv run --locked perfworkbench sweep experiment.json
uv run --locked perfworkbench compare 基线ID 候选ID
uv run --locked perfworkbench retest 基线ID 复测ID --allow-change load.concurrency --min-change 0.10
```

模型/配置对比要求同数据、生成参数、质量门槛和负载；不同并发的结果不能当成公平模型排名。并发/速率调优复测须显式声明唯一改变的变量。界面扫描视图展示已测点与达标点，不插值承诺未测容量。复测判定是本次观测，不代替重复实验或统计显著性验证。

更改服务端配置由你在外部完成；工作台保存其环境声明，但不核实未暴露的 TP/精度/驱动参数。对比时必须如实记录变化。

## 指标怎么看

| 指标 | 口径 |
| --- | --- |
| requests/s | 成功的测量请求数 ÷ 完整测量窗口；不是 Reports/hour |
| input/output tokens/s | 成功请求已知 usage 的逻辑 token 数 ÷ 同一完整窗口；输入包含缓存部分，不是实际计算 TPS |
| E2E | 客户端完整请求时延 |
| TTFT | 流式首个可观测输出片段时延，可能先收到 reasoning；不是纯 Prefill 时间 |
| TPOT | 基于 usage 的均摊估计 `(E2E−TTFT)/(输出token数−1)`；不等于逐 token ITL |
| 分片间隔 | 客户端 SSE 内容片段之间的间隔，不能当 token 间隔 |
| goodput | 同时通过质量和已配置逐请求延迟约束的请求吞吐 |
| KV Cache | 诊断信号，需要结合队列、抢占等证据，不以越高越好为目标 |

窗口保留失败请求的长尾，预热不计入测量；非流式 TTFT/TPOT、缺 usage 的 token 吞吐显示未知。P50/P95/P99 附样本量。极少样本的高分位数不足以支持稳定性结论。

质量支持 JSON/字段/关键词/最小长度规则和人工标签；这些规则不能证明摘要事实正确，重要业务应使用人工校准标准。`quality.mode=manual` 时可导入 `{request_id: "pass|fail|unknown"}`。未评价不会计为通过，截断输出不能靠人工 pass 绕过硬失败规则。

```sh
uv run --locked perfworkbench label 实验ID labels.json
```

## 资源指标采集

### 本机 Ollama 与系统内存

在“安全预算与资源观测”中勾选“采集本机 Ollama 与内存”，然后主动启动实验。
默认关闭；不用安装 Prometheus。该选项确认模型实际运行在工作台后端所在主机，
不适用于端口转发到远程机器的服务。只接受 loopback 的根路径或 `/v1` 地址。

- 后端仅定时 GET 同源 `/api/ps`，按模型名称精确匹配，读取 `size_vram` 和 `context_length`；
  不额外生成、加载或下载模型。密钥继续从配置的环境变量读取。
- 系统总/可用内存与 Swap 来自工作台主机。`size_vram` 是 Ollama 报告的模型 GPU 侧内存，
  不是整卡已用显存或 KV 占用；Apple Silicon 使用统一内存。上下文值是配置容量，不是已用 token 数。
- 观测随实验启停并写入该实验的 `telemetry.jsonl`，结果页可看最新状态和采样记录。
  采集期间可能包含预热；默认间隔 1 秒，每轮串行采集后等待，不保证精确周期。
- 未加载、超时、权限/协议错误保留缺失原因，不填零、不沿用上次成功值。取消允许当前在途采样完成，
  采集器停止返回后不再采样；单次网络超时不是严格的整体停止时限。
- 本轮不启动 `sudo` 或 GPU 特权采样；本地来源不提供 GPU 活跃度和 KV 占用率。
  已配置的外部 GPU/KV exporter 可以同时采集，不受影响。

高级 JSON 配置：`"telemetry": {"interval_s": 1, "local": {"enabled": true}, "sources": []}`。
旧配置缺少 `local` 时默认关闭。资源缺失不影响模型请求本身，不能据此声称完成 GPU/KV 瓶颈诊断。

### 已有 Prometheus 格式 exporter

在 `telemetry.sources` 配置 Prometheus exposition 地址。默认尝试已知 vLLM 指标别名；设备指标需要按实际 exporter 配置 metric、labels、scale、aggregation，见 [资源指标接入](docs/telemetry.md)。

对 Ascend 910B1，API 调用与指标协议可以在本机验证，但 **Qwen3.5-122B、16 张 910B1 的真实性能和具体 exporter 版本仍需真机验证**。没有采集的 NPU/KV 指标显示缺失原因，不生成数值，不宣称已定位通信或算子瓶颈。

## 停止与隐私

- 网页“停止”或 `perfworkbench cancel 实验ID` 停止整个计划，包括尚未执行的扫描点。
- 在途连接会被关闭并保留中断记录；这不保证远端服务立即释放已经接收请求的所有计算资源。
- 最大请求数、输出 token 预留、并发和计划时长在发压前校验。到达速率过高触发客户端准入拒绝时单独记录，不冒充服务端失败。
- 缓存条件是使用者声明；工作台不会主动清空远端缓存，也不会假设预热后必然命中。
- 原始内容保存在本地私有实验目录。分享请用 report 导出，默认去掉原文、URL、密钥、原始错误和自由文本标签。
- 这是单用户本地工具，不是可暴露到公网的多租户平台。

## 功能与验收

F01—F14 的逐项验收标准在 [Sprint 清单](docs/sprints/v0.1.md)，整体状态在 [SPRINT-STATUS.md](SPRINT-STATUS.md)。架构、边界和数据契约在 `docs/`。运行过程中生成的测试证据不应解释为真实模型性能。

初版验收：486 项测试通过（含 10 项浏览器测试），单元覆盖率 89%、集成 79%；独立 wheel 安装及本地协议实验通过。详见 [最终验收记录](docs/validation.md) 和 [代码审查](docs/review.md)。

2026-09-26 简化界面回归：498 项测试通过（含 22 项浏览器测试），合并 Python statement coverage 95%，离线构建通过。见 [简化界面验收](docs/sprints/simple-editor.md)。真实 Ollama 生成及 Ascend 性能不属于这轮本地协议测试结论。

```sh
uv run --locked --extra dev pytest -m "not e2e" -q
uv run --locked --extra dev pytest tests/e2e -q
uv run --locked --extra dev ruff check --no-cache perfworkbench tests
uv build
```

浏览器测试需要本机 Chrome 或 Playwright Chromium。测试只请求自己创建的回环端点，不连接实验室集群。
