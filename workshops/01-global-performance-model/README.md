# Workshop 01：用 Critical Path 定位全局性能问题

> 对应书稿：Chapter 7「Global Performance Model」  
> 实验类型：Level 1 / CPU / 合成依赖图  
> 结论边界：本实验验证分析算法与报告契约，不产生真实 LLM 服务或 GPU 性能结论。

## 目标

完成后，学员应能：

- 把 LLM、RAG 或 Agent 任务表示为有向无环依赖图；
- 区分节点总时长、Critical Path 和并行重叠时间；
- 把关键路径上的慢阶段写成“待验证假设”，而不是 Root Cause；
- 修改工作负载后重算关键路径，并解释为什么结果变化。

## 前置知识

- 知道 Queue、Prefill、Decode、RAG retrieval 和 Agent tool call 分别是什么；
- 能在命令行运行 Python 3；
- 了解 JSON 的数组、对象和字段。

不要求 GPU、vLLM、PyTorch 或外部网络。

## 准备时间与授课时间

| 环节 | 建议时长 |
|---|---:|
| 讲师课前准备 | 10 分钟 |
| 学员环境检查 | 5 分钟 |
| 原理与手算 | 10 分钟 |
| 基线运行 | 10 分钟 |
| 修改与重跑 | 15 分钟 |
| 对比、练习与讨论 | 10 分钟 |

## 材料与映射

| 材料 | 用途 |
|---|---|
| `code/chapter07/performance_model.py` | 校验 DAG，计算 Critical Path，生成待验证假设 |
| `code/chapter07/sample_llm_request.json` | 串行 LLM 基线 |
| `code/chapter07/sample_rag.json` | 并行检索基线 |
| `code/chapter07/sample_agent.json` | 并行工具调用基线 |
| `code/chapter07/test_performance_model.py` | 算法、边界条件与报告语义的自动验收 |

以下命令都从仓库根目录运行。

## 步骤 1：检查环境与基线

```bash
python3 --version
python3 -m unittest discover -s code/chapter07 -p 'test_*.py' -v
```

预期输出：8 项测试全部通过。如果测试失败，停在这一步，不继续解读报告数字。

## 步骤 2：运行三类基线

```bash
python3 code/chapter07/performance_model.py code/chapter07/sample_llm_request.json
python3 code/chapter07/performance_model.py code/chapter07/sample_rag.json
python3 code/chapter07/performance_model.py code/chapter07/sample_agent.json
```

记录三个字段：`critical_path_ms`、`all_node_time_ms`、`parallel_overlap_ms`。

| 样例 | 已验证的预期输出 | 应如何解释 |
|---|---|---|
| LLM | 854 / 854 / 0 ms | 样例是串行链，没有并行重叠 |
| RAG | 1020 / 1140 / 120 ms | 并行检索分支不能全部相加 |
| Agent | 1170 / 1470 / 300 ms | 较慢的必经工具分支进入 Critical Path |

表中数字的顺序是 `critical_path_ms / all_node_time_ms / parallel_overlap_ms`。它们是对仓库样例的算法输出，不是真实 Benchmark。

## 步骤 3：手算并更改一个变量

1. 先画出 `sample_agent.json` 的依赖图，手算当前 Critical Path。
2. 复制该样例到临时文件，不改原始 sample。
3. 只改一个工具节点的 `duration_ms`，使另一分支成为 Critical Path。
4. 写下修改前的预测：新路径、新总时长、哪个假设应该被优先验证。

这一步的“优化”只是改变合成工作负载，不代表已优化真实系统。

## 步骤 4：用同一分析器重跑

```bash
python3 code/chapter07/performance_model.py /path/to/modified-agent.json \
  --output /tmp/modified-agent-report.json
```

预期输出：

- `critical_path` 转移到你制造的较慢分支；
- 关键路径节点的 `on_critical_path` 和 `critical_path_share` 重新计算；
- 候选项仍保持 `status: needs_evidence`，不出现 `root_cause` 字段。

## 步骤 5：对比与结果分析

填写下表：

| 项目 | 修改前 | 修改后 | 证据等级 |
|---|---:|---:|---|
| Critical Path |  |  | 合成实验·已验证 |
| Critical Path 时长 |  |  | 合成实验·已验证 |
| 并行重叠 |  |  | 合成实验·已验证 |
| 优先候选假设 |  |  | 待验证 |
| 下一项最低成本证据 |  |  | 待采集 |

结果分析必须回答：

1. 为什么节点总时长与 Critical Path 不同？
2. 哪个局部节点变化改变了用户 E2E？
3. 现有报告能确认什么，不能确认什么？
4. 真实系统中还需哪一条 Trace、指标或对照实验？

## 练习

### 基础

为 `sample_rag.json` 标出并行分支、汇合点和 Critical Path，然后用程序核对手算结果。

### 进阶

新建一份含“超时 → 重试→ 备用工具”的 Agent DAG，比较有无重试时的 Critical Path。

### 证据思维

选一个关键路径节点，写出：候选根因、支持它的证据、可以推翻它的证据、质量或成本护栏。

## 排错提示

| 现象 | 原因 | 处理 |
|---|---|---|
| `can't open file` | 不在仓库根目录，或路径错误 | 回到包含 `code/` 与 `content/` 的目录后重跑 |
| `unknown dependency` | `depends_on` 引用了不存在的 ID | 检查拼写，并确认被依赖节点已定义 |
| `cycle` | 依赖图存在环 | 把“重复执行”展开为新节点，不要画回原节点 |
| 结果与手算不同 | 忽略了节点依赖或并行汇合 | 按拓扑顺序逐节点计算最早完成时间 |
| 报告只有假设没有 Root Cause | 这是有意设计 | 根因需真实 Trace、指标和对照实验，不应从合成时长自动生成 |

## 完成标准

- [ ] 8 项单测通过。
- [ ] 三份基线报告都已生成。
- [ ] 学员手算结果与程序一致。
- [ ] 修改只改一个变量，并完成重跑。
- [ ] 结果表区分“已验证输出”与“待验证根因”。
- [ ] 提交一份修改后的 JSON 和一份分析报告。

