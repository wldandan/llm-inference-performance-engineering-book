# V0.1 最终验收记录

日期：2026-09-21。范围：`tools/llm-perf-workbench` 的 F01—F14。

结论：本机开发与交付验证通过，可通过网页和 CLI 主动运行实验、分析结果、导出报告和记录复测。
验收使用真实 EvalScope 1.12.0 和本地协议端点，**没有加载真实模型，没有连接 GX10 或 Ascend 集群**。
本文不构成模型质量、硬件兼容性、容量或提速证明。

## 最终测试快照

下列三个互不重叠的选择器覆盖本次全部 486 个用例，均通过，无跳过或 xfail。

| 测试选择器 | 通过 / 未选中 | 耗时 | 全生产包 statement coverage |
| --- | --- | --- | --- |
| `not integration and not e2e` | 448 / 38 | 9.04 秒 | 89%：2,238 statements，247 missed |
| `integration` | 30 / 456 | 72.82 秒 | 79%：2,238 statements，480 missed |
| `e2e and not integration` | 8 / 478 | 18.59 秒 | 不单独作为覆盖率门槛 |

集成组包含 2 个 Chrome + 真实管理器/EvalScope 的端到端用例；另外 8 个浏览器用例使用受控 API 数据，合计 10 个 Chrome 用例，不能重复计数。
覆盖率分母包含整个 `perfworkbench` 包，没有排除业务模块，也没有把单元用例改标为集成用例以提高比例。
单元 >80%、集成 >60% 的发布门槛均通过。

各组保留了两条第三方弃用警告，涉及 Starlette TestClient 的 HTTPX/AnyIO 接口；没有隐藏警告。
其他验证文档中的较早失败、用例数和覆盖率属于开发快照，最终结果以本页为准。

## F01—F14 证据映射

| Feature | 主要实现 | 主要测试 / 验收证据 |
| --- | --- | --- |
| F01 目标和约束 | `config.py`、`analysis.py`、网页实验表单 | `test_config.py`、`test_analysis.py`、`test_dashboard.py`：在线/离线约束、缺指标 unknown |
| F02 服务与模型 | `runner.py`、`evalscope_worker.py`、环境快照 | `test_integration.py`、`test_core_regressions.py`：模型列表、同步/流式预检、独立预算、执行互斥 |
| F03 数据集 | `dataset.py`、CLI/profile 与网页导入 | `test_dataset.py`、`test_workflow_integration.py`：JSONL、指纹、类别、长度、非法数据；未配 tokenizer 时 token 数未知 |
| F04 流量模型 | `config.py`、`dataset.py`、`evalscope_worker.py` | 配置/数据/集成测试：并发、到达速率、固定种子、类别混合、实际发出与客户端拒绝 |
| F05 基线与记录 | `store.py`、`runner.py`、worker 原始 JSONL | `test_store.py`、`test_runner.py`、集成测试：状态、预热、重复、快照、取消和中断记录 |
| F06 扫描 | `runner.py`、`sweep.py`、网页扫描视图 | `test_sweep.py`、工作流/浏览器测试：逐点结果、重复聚合、已测范围、fixture 不推荐容量 |
| F07 性能指标 | `analysis.py`、worker 时序和 usage | `test_analysis.py`、`test_worker_edges.py`：窗口、单位、分位数、分组、缺 usage、同步 TTFT 不可用 |
| F08 资源观测 | `telemetry.py`、实验采集生命周期 | `test_telemetry.py`、工作流测试：Prometheus、标签、缩放、重置、缺失与采集错误、结束停止采集 |
| F09 质量门槛 | `analysis.py`、人工标签导入 | 分析/工作流/浏览器测试：规则、截断、未知覆盖率、标签持久化、拒绝外来 request ID |
| F10 公平比较 | `analysis.py`、网页/CLI 比较入口 | 分析/工作流/浏览器测试：条件对齐、差异、质量门槛、fixture 与不兼容实验不排名 |
| F11 诊断 | `analysis.py` 的规则与证据输出 | `test_analysis.py`、结果页测试：证据、适用条件、缺失信息、不单凭 KV 或 TTFT 断言根因 |
| F12 建议与复测 | `analysis.py`、CLI/网页复测、存储关联 | 分析/CLI/工作流测试：声明单变量、判定条件、统一持久化结构、未知质量不宣称有效 |
| F13 导出 | `report.py`、CLI/网页下载 | `test_report.py`、工作流/浏览器测试：JSON/Markdown/HTML、单位、可追溯性、原文/密钥脱敏 |
| F14 运行保护 | 配置预算、runner、worker、web | 配置/核心回归/worker/web/集成测试：请求与输出预算、精确超时、取消、看护、同源/Host、响应上限 |

具体验收行为见 [Sprint 清单](sprints/v0.1.md)。各测试文件位于 `tests/`，浏览器文件位于 `tests/e2e/`。

## 测试先行与审查

- 配置/数据、存储/worker、管理器、CLI、扫描分别经过测试失败后实现；核心回归在修复前复现。
- Worker 边界测试发现畸形响应、缺 usage 累计、非法时序、读取额度绕过等失败，见 [Worker 边界记录](worker-edge-validation.md)。
- 独立核心审查指出的阻断问题已修复并复审通过；主任务补充日志脱敏、增量进度、锁清理、CLI 复测结构和 TPOT 单位回归。见 [代码审查](review.md)。
- 独立工作流集成验证使用真实应用、管理器、存储、EvalScope 与 CLI；仅外部模型/exporter 由本地端点代替，见 [工作流验证](workflow-integration-validation.md)。
- 网页经过桌面/移动端渲染检查与交互测试，详见 [网页验收](ui-validation.md)。截图中的固定数值仅用于检查界面，不作为性能数据。

## 构建与独立安装

以下操作实际执行成功：

1. 使用锁文件安装开发环境，固定 EvalScope 1.12.0。
2. Ruff 检查通过，31 个 Python 文件格式检查通过；前端 JavaScript 语法检查通过。
3. `uv build` 生成 wheel 和源码包，包含网页静态资源。
4. 在项目外新建 Python 3.12 虚拟环境，从 wheel 安装，并应用锁文件导出的生产依赖约束。
5. 独立环境从已安装包导入（不是源码目录），完成服务预检和真实 EvalScope 的 2 次本地协议请求，实验状态为 completed。
6. 独立环境的首页、JavaScript、CSS、实验列表路由均返回成功；HTML 报告生成且包含正确的 `ms/token` 单位。
7. 开发环境与独立环境分别检查 135、126 个已安装包，依赖兼容性检查通过。

首次独立安装的离线尝试因依赖缓存不完整失败；随后正常联网安装成功。**不宣称首轮安装支持完全离线**。
安装过程下载 Python 依赖，不下载模型。
独立 smoke 的数据始终标记 `protocol_fixture: true`，不会获得模型排名、容量或调优有效结论。

## 复现命令

在工具目录执行；需要允许本地回环端口以及可用的 Chrome/Playwright Chromium。

```sh
uv sync --locked --extra dev --python 3.12
uv run --locked pytest -m 'not integration and not e2e' --cov=perfworkbench --cov-report=term-missing -q
uv run --locked pytest -m integration --cov=perfworkbench --cov-report=term-missing -q
uv run --locked pytest -m 'e2e and not integration' -q
uv run --locked ruff check --no-cache perfworkbench tests
uv run --locked ruff format --no-cache --check perfworkbench tests
node --check perfworkbench/static/app.js
uv build
```

覆盖率命令分别执行，不使用 `--cov-append` 混合两类结果。单元与集成报告应分开保存。
运行入口、示例与真实服务接入方式见 [README](../README.md)。

## 尚未验证的外部条件

- Qwen3.5-122B、16 张 Ascend 910B1、真实 vLLM/Ascend 版本和实际 exporter 的运行兼容性与性能。
- 6 小时处理 6,000 份报告的业务容量；请求吞吐不能直接换算完整报告吞吐。
- 真实业务语料上的摘要事实正确性与优化收益；结构/关键词规则不替代人工质量校准。
- 大规模长期运行、海量实验的网页分页/磁盘配额；公开部署或多租户安全；第三方依赖漏洞数据库审计。

首次真机验收应另行授权，使用小数据集、有限请求预算和已确认的质量门槛，先建立真实基线。
本次不修改远程服务，不推送远程 Git，也不改动教材已有未提交内容。
