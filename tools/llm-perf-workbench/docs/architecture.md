# V0.1 架构与边界

状态：2026-09-21，独立审查者 Maxwell 的 /arch 与 /ui 均批准。两项原阻断（完成/时间语义、预算/准入语义）补充后复审通过。实现已完成，核心修复独立复审通过；最终发布验收见 validation.md。

## 决策

- 独立 Python 3.12 项目；FastAPI 本地网页 + argparse CLI；无需 CDN 或额外前端构建服务。
- EvalScope 1.12.0 作为真实发压器，通过公开 run_perf_benchmark 与注册 API 插件扩展。固定版本来自 spike 的契约验证，而不是未经验证地追随 latest。
- 插件继承 OpenAI 插件，复用其 HTTP/SSE 处理，在安全 JSON 中保存逐请求内容、usage、结束原因、时间、ID。绝不从结果 pickle 恢复对象。
- 每个实验独立子进程；父进程拥有状态、全程时限、取消、监测与结果归档。支持受控顺序扫描和重复实验。
- 运行快照与 JSONL 原始记录保存在私有本地数据目录，配置和数据集版本不可被后续编辑覆盖。
- Prometheus 明文指标只在实验期间采集；使用可配置名称、标签、单位与聚合方式匹配引擎/Ascend/NVIDIA exporter。没有真机验证就不能宣称某硬件组合已验证。
- 环境预检仅 GET 模型列表和有限的生成请求；无 SSH、部署、重启或生产配置修改。

## 正确性

- 非流式不提供 TTFT/TPOT。流式 TTFT 明确是首个可观测内容（可能包含 reasoning）；TPOT 为基于 usage 的均摊估计；逐分片间隔不是逐 token ITL。
- 吞吐窗口从首条测量请求开始到最后终态，包含失败长尾；预热、预检分别统计。
- 客户端单调时钟计算请求时延，UTC 标记用于观测关联，不用跨机器时钟相减计算阶段时延。
- 质量状态 pass/fail/unknown；比较时未知质量不能获胜；数据集/提示/生成/负载变化必须显式展示。
- 根因输出为有证据的候选解释，建议必须包含复测条件。KV 使用率高本身不构成问题。
- 上游 HTTP 200 不直接等于成功：非流式必须为有效 choices/message，流式必须有合法的 choice 结束原因；流中断且没有完成证据标为 incomplete，非法 JSON/结构标为 protocol_error。length/content_filter 是已结束但质量不通过的输出。插件独立捕获所有成功/失败的请求结束单调时间，不能沿用上游最后一块时间作为总窗口终点。
- 逐请求 ID 在 build_request 建立，并通过受控 X-Workbench-Request-ID 头与内存映射传入 process_request；不等待上游在插件返回后才填写 request_id。phase/category/sample_id 仅在本地映射中保存。

## 安全

- 网页仅监听 loopback，Host 白名单、同源检查及写请求专用 header；无任意命令执行、任意路径下载或在线安装功能。
- API Key 只从环境变量读取，在发送时注入；不进入命令行、快照、输出报告。
- 预检和实验共用工作区排他锁；worker 监测父进程存活。小数秒超时由适配层严格执行，上游只接收其支持的整数超时字段。
- 缺失或非法 usage 在 canonical JSON 中始终保持 null。仅在返回 EvalScope 内部累计器前兼容为零；这些上游内部汇总不用于工作台指标、比较或导出。
- 限制输入、数据集、记录及网络响应大小；路径只由生成的安全 ID 定位。
- 时长/请求/并发/输出 token 上限均在发压前校验并在执行时检查。中止后未完成任务不能计为成功。
- 分享报告默认不含请求与响应原文、端点凭据和错误回显；HTML 必须转义。
- 预算按一次用户批准的实验计划计，包括所有扫描点、重复和预热；启动前按每条请求的 max_tokens 计算最坏输出总额。运行时发出请求前，在同一事件循环中无 await 地原子预留请求数和 max_tokens，未知消耗/中断不退还预留；超额禁止发送。复测是新计划，必须重新显式启动并使用新的预算，不自动继承无限授权。
- 服务预检为单独显式动作：最多两次生成（同步/流式各一次，每次最多 8 输出 tokens），清楚显示独立消耗；实验运行禁用 EvalScope 自动连接测试和重试，避免隐式额外生成。
- 到达速率模式不延迟重放被限流的到达事件：配置有限的 max_concurrency，饱和时记录 client_rejected，明确区分目标到达、实际发送和完成数量，不能当成模型服务错误。禁用重定向，不发额外跳转请求；不自动重试。

## UI 方案

浅暖灰工程实验记录风格，深青色强调；左侧导航：实验概览、新建实验、结果比较。
新建实验提供常用字段与 JSON 高级配置；输入和异常就地说明。运行中可停止；结果按性能、质量、资源、建议组织。
数字附单位、口径和样本量；未知状态显式可见。图表有表格替代；键盘可操作，窄屏可滚动。

## 非目标

不做生产监控、自动模型部署、调度器、全自动服务参数修改、完整业务工作流、实时卡数容量承诺。

## 来源

- 本仓库 .spike/llm-performance-tool/NOTES.md：本地契约验证与已知口径陷阱。
- https://evalscope.readthedocs.io/zh-cn/latest/user_guides/stress_test/custom.html
- https://evalscope.readthedocs.io/zh-cn/latest/user_guides/stress_test/parameters.html
- https://docs.vllm.ai/projects/ascend/en/latest/developer_guide/evaluation/using_evalscope.html
