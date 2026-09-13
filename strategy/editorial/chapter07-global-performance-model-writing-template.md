# Chapter 7「Global Performance Model」完整写作样板

> 用途：这是“一个主题如何从问题写到可运行证据”的编辑样板。正文仍以 [`ch07.md`](../../content/ch07/ch07.md) 为准，本文不复制或取代章节正文。

## 1. 主题合同

| 字段 | 内容 |
|---|---|
| 主题 | Global Performance Model（全局性能模型） |
| 大纲位置 | Part 1 / Chapter 7 / Core |
| 核心问题 | 性能瓶颈来自 Queue、Prefill、Decode 还是 RAG / Agent 的其他环节？ |
| 方法链位置 | 连接“理解系统”与“理解瓶颈”，并为后续 Benchmark / Profiling 生成待验证假设 |
| 本章做到 | 建立 Outcome → Workload → Stage → Resource → Evidence 模型；计算依赖图的 Critical Path |
| 本章不做 | 不宣称已找到 Root Cause；不给出量化、KV Cache、调度器或 Kernel 优化结论 |
| 权威输入 | `01_Course_Design.md`、`02_Course_Outline_v1.0.md`、`03_Course_Template.md` |
| 可运行证据 | `code/ch07/performance_model.py`、三份 sample JSON、`test_performance_model.py` |

## 2. 证据标签

书稿中的每个性能结论都应显式归入以下一类：

| 标签 | 可写内容 | 禁止的外推 |
|---|---|---|
| `[原理]` | 定义、公式、算法与边界条件 | 不得据此声称某配置必然提速 |
| `[合成实验·已验证]` | 仓库内样例的精确输入、算法输出和测试结果 | 不得当成真实 LLM / GPU Benchmark |
| `[真实测量·已验证]` | 锁定环境、工作负载、方法和原始产物后的实测数字 | 不得外推到未测模型、硬件或负载 |
| `[待验证]` | 候选瓶颈、预期现象、尚未实跑的收益 | 不得使用“提升了”“降低了”等完成时措辞 |

## 3. 九段式完整写作结构

### 3.1 问题场景

用一个用户可感知的 Outcome 开场，同时给出足以阻止“怪 GPU”的反常信号。本主题可用：企业问答 P95 task E2E 从 1.8 s 升到 4.9 s，但 LLM TTFT 只从 0.9 s 升到 1.0 s，GPU Utilization 为 45%。

完成标准：必须写明指标、分位数、负载和测量边界；如果数字是教学设定，标记“合成案例”。

### 3.2 原理

依次定义 Outcome、Workload、Stage、Resource、Evidence，再说明串行路径可做近似阶段加法，有并行分支时必须使用 DAG 与 Critical Path。

完成标准：公式后紧跟适用条件；“慢阶段”只生成假设，不直接生成 Root Cause。

### 3.3 直觉解释

把全局模型解释成“先找用户等待的最长必经路，再问为什么这条路慢”。并行的两个检索分支像两位同时准备材料的同事，汇合点等的是较晚完成的那一位，不是两人用时之和。

完成标准：直觉解释不替代定义，不创造与实现不一致的比喻。

### 3.4 代码

只引导读者阅读与本章观点直接相关的接口：

| 概念 | 代码位置 | 作用 |
|---|---|---|
| 输入校验 | `performance_model.py::_validate_nodes` | 拒绝重复 ID、未知依赖、负时长和非法图 |
| 关键路径 | `performance_model.py::analyze_critical_path` | 计算终点完成时间、路径与并行重叠 |
| 候选假设 | `performance_model.py::rank_hypotheses` | 为关键路径节点列出待采证据 |
| 报告契约 | `performance_model.py::build_report` | 输出 `synthetic_global_performance_model` 与 `needs_evidence` |

完成标准：正文中的命令能从仓库根目录直接运行；代码字段名与实际 API 一致。

### 3.5 实验

实验固定六个字段：目标、环境、输入、步骤、观测指标、可重复性边界。本主题先运行 8 项单测，再使用同一程序处理 LLM、RAG 和 Agent 三份合成依赖图。

### 3.6 结果分析

下表是 2026-09-08 在本仓库实际运行得到的合成实验结果：

| 样例 | Critical Path | 节点总时长 | 并行重叠 | 结论等级 |
|---|---:|---:|---:|---|
| LLM | 854 ms | 854 ms | 0 ms | `[合成实验·已验证]` |
| RAG | 1020 ms | 1140 ms | 120 ms | `[合成实验·已验证]` |
| Agent | 1170 ms | 1470 ms | 300 ms | `[合成实验·已验证]` |

可以得出：程序正确保留并行重叠，没有把节点时长无条件相加。不可以得出：RAG 一定比 LLM 慢 166 ms，或 Agent 在真实系统中一定需要 1170 ms。这些数字来自教学样例，非真实服务测量。

### 3.7 常见错误

1. 把最长阶段写成 Root Cause。
2. 把并行节点全部相加当作 E2E。
3. 不锁定 Workload 就比较前后结果。
4. 把 GPU Utilization 当作用户 Outcome。
5. 局部优化后不重算 Critical Path。
6. 只看 LLM Server，遗漏 RAG 检索、Agent 工具、超时与重试。

### 3.8 练习

练习要同时覆盖解释、计算、修改和证伪：

- 解释：区分 TTFT 路径与 E2E 路径。
- 计算：给定并行检索 DAG，手算 Critical Path。
- 修改：更改 Agent sample，使另一工具分支成为关键路径。
- 证伪：为“Queue 过长源于容量不足”列出一条支持证据和一条反证。

### 3.9 小结

小结只回收三件事：本章新建立的模型、实验已经证明的范围、仍需 Benchmark / Profiling 验证的范围。最后显式引向 Chapter 8 的 Benchmark Design。

## 4. 术语、符号与 API 一致性表

| 概念 | 统一写法 | 避免 |
|---|---|---|
| 首个可消费内容的时间 | TTFT | 未说明边界的“首 token 时间” |
| 端到端延迟 | E2E latency / task E2E | 在任务和单次 LLM 调用之间混用 E2E |
| 关键路径 | Critical Path | critical chain、最慢节点 |
| 根因前的判断 | 候选假设 / `needs_evidence` | Root Cause |
| 全局模型五层 | Outcome / Workload / Stage / Resource / Evidence | 改变顺序或临时换名 |
| 报告入口 | `build_report(scenario)` | 书稿中虚构不存在的 API |

## 5. 样板验收清单

- [ ] 问题场景有 Outcome、Workload 和测量边界。
- [ ] 原理与直觉解释互相支撑，但没有把比喻当作证据。
- [ ] 代码路径、函数名、输入字段和输出字段真实存在。
- [ ] 实验命令可运行，测试先通过。
- [ ] 每个数字能追溯到输入和原始报告。
- [ ] 合成结果不伪装为真实硬件 Benchmark。
- [ ] 未完成的采证与真实环境验收标记为“待验证”。
- [ ] 练习能让学员产出新报告，而不是复述正文。

