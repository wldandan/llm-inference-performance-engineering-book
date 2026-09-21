# Worker 边界验证记录

范围：仅 `tests/test_worker_edges.py` 和本文档；生产 worker/runner 由主任务修改。
采用 TDD 技能和语言 resolver（Python 无覆盖层标准，使用通用最佳实践）。
保留真实生产逻辑与 EvalScope 解析器，仅在外部 HTTP/调度边界提供可控输入。
已有 `test_worker.py` 和 `test_integration.py` 已阅读；本文件补充边界契约，不重写主流程测试。

## 初次基线

Worker SHA-256：`f4922ff0eb7dfe3bc77c14c41c686792ea6851e0e8186c56d1aaa8d0812730e8`。
单元选择器 `not integration and not e2e`：296 passed、6 failed、17 deselected；
总体 77%（1872 statements / 432 missed），worker 35%（220 / 143 missed）。
6 个原有失败均因当时 `perfworkbench.sweep` 尚未存在，不属于本次新增测试。

## 首批 red：33 passed / 9 failed

以下失败已立即报告给主任务，未改生产代码，未加 xfail/skip 掩盖：

| 行为 | 用例 | 实际证据 |
| --- | --- | --- |
| 非流式 message 为 null/字符串/数字/数组时不能成功 | `test_nonstream_finish_reason_does_not_validate_a_malformed_message` ×4 | `success == True`，预期 protocol_error |
| finish_reason 为数组/对象时需安全失败 | `test_invalid_finish_reason_is_a_safe_failure` ×2 | `TypeError: unhashable type`，位于原 worker 第 31 行 |
| TTFT 不能为负或超过完整请求时长 | `test_invalid_first_chunk_latency_does_not_create_impossible_timing` ×2 | -0.1 → -100 ms，1.5 → 1500 ms（请求总时长 1000 ms） |
| 超限后 JSON→text fallback 不得重新获得读取额度 | `test_body_limit_failure_cannot_be_bypassed_by_parser_fallback_read` | 第二次读取未抛 `response_size_limit` |

已通过的初批测试包含非法 choices、合法终止原因、非法 token usage、部分时序过滤、
UTF-8 分片、按字节累计响应限制、JSON 解析失败、上下文清理与禁止跳转。

## EvalScope 累计器边界新增 6 个失败

用例：`test_unknown_usage_cannot_crash_or_pollute_evalscope_accumulation`。
调用链保留真实 `WorkbenchPlugin → OpenaiPlugin → MetricsAccumulator.update → BenchmarkData.finalize`。
HTTP 响应由内存 session 提供，不 mock 解析、归一化、记录或累计器。

| usage | 实际结果 |
| --- | --- |
| 缺失 | `ValueError: Unable to retrieve usage information`；没有 tokenizer 时继承的 parse_responses 抛异常 |
| completion_tokens 为字符串 | finalize 中与整数比较产生 TypeError |
| completion_tokens 为 true | 上游累计 token 数变成 1 |
| completion_tokens 为 -1 | 上游累计 token 数变成 -1 |
| completion_tokens 为 3.5 | 上游累计 token 数变成 3.5 |
| completion_tokens 为 Infinity | 上游累计 token 数变成 Infinity |

这些场景的本地 records 已正确保存 `output_tokens: null`，但返回的 EvalScope 对象仍保留不安全 usage。
测试要求真实累计步骤不崩溃、不引入非法 token 数，同时保留本地记录的 unknown/null 语义。

## 主任务恢复前的验证结果

- 新文件：81 个 unit 参数化用例，其中 66 passed、15 failed；另有 4 个明确标记 integration 的真实 HTTP 用例，全部 passed。
- 真实 HTTP 覆盖累计响应大小上限、非法 JSON、307 不跳转，以及 UTF-8 JSON 完整输出与身份记录。
- 项目级 `not integration and not e2e`：417 passed、15 failed、23 deselected，2 条原有第三方 deprecation warnings。
- 项目整体 statement coverage：87%（2143 statements / 270 missed）；worker：100%（220 / 0 missed）。
  未更改覆盖率选择或排除规则。其他任务同时增加了测试/模块，整体变化不全部归因于本任务。
- worker SHA-256 仍与初始一致；原有 sweep 的 6 个失败已随主任务实现消失。
- Ruff check / format check 通过。

核心通过行为：请求 build 字段保留，phase/sample/request ID 关联，发出请求前持久化 starts，
环境凭据注入和内容脱敏，取消/超时/请求预算/token 预算/并发拒绝记录，失败不退还 token，
完成后恢复并发额度，独立完成时间修正，API 调度参数与 JSONL 输入，预检的两个有限请求、
context 来源和模型列表失败降级，错误包版本/缺包/benchmark 异常的安全 worker-error 文件。

## 主任务恢复后的补充约束

主任务确认正在修复缺 usage、伪成功、preflight 锁、sticky cap、字典键脱敏、浮点超时和中断计时。
本次 QA 继续只修改自己的两个文件；preflight 锁和中断恢复属于 runner，交由主任务验证。
补充 `_scrub` 嵌套字典键测试；超时需保留用户的浮点时限语义。
最初检查参数向上取整，随后要求向 EvalScope 直接传浮点数，这两者都过度绑定实现。
主任务在实际请求外增加 `asyncio.timeout`，允许 EvalScope 参数兼容性取整，同时按原浮点值限制请求。
因此测试改为验证实际行为：0.03/0.12 秒时限可中止一直等待的外部 I/O，生成失败记录，
恢复并发额度且不退还 token 预算。另保留 0.05/1.2 秒、两种负载模式的 worker 调用契约测试。

主任务首轮修复后 SHA-256：`332fe741bd04d44acfafea197a654cb500356a530744715881b339fb65978101`。
当时 worker 测试 92 passed / 4 failed；四个失败均来自“必须直接转发浮点数”的实现约束，
已以更合适的实际超时行为测试替代，不能将其报告为仍然存在的生产超时缺陷。
原来的 15 个 worker/累计器失败与字典键脱敏失败在该轮已通过。

本记录保留 red 证据，不声明主任务尚未完成的生产修复已通过。

## 复现

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_worker_edges.py \
  -m 'not integration' -q -p no:cacheprovider --tb=short
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_worker_edges.py \
  -m integration -q -p no:cacheprovider --tb=short
PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE=/private/tmp/worker-edge-project \
  .venv/bin/python -m pytest tests -m 'not integration and not e2e' -q \
  -p no:cacheprovider --cov=perfworkbench --cov-report=term-missing --tb=short
```

integration 需要 loopback socket 权限；新 unit 用例不启动网络监听、不下载 tokenizer/模型，
只读取已安装 EvalScope 1.12.0。包失败测试在进程内运行真实 worker 入口并验证 SystemExit(1)
与安全文件；不把预期异常写成 xfail/skip。所有测试产物与 coverage 数据保存在临时目录。
