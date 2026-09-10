# LLM Performance Engineering 课程模板（Course Templates）

> V0.2：所有章节采用分层交付。Core 内容服务后端 / Agent 工程师；Advanced 内容服务平台 / 基础设施工程师，不要求 Core 学员完成 Advanced Labs。

> **文档职责：规定不同类型章节应该如何开发。**

为了保证课程结构统一，同时避免所有章节机械套用同一种结构，课程采用三类章节模板：

- Template A：基础理论与分析章节
- Template B：技术专题章节或技术专题小节
- Template C：综合实践章节

## 0. V0.2 分层章节结构

每章在选择 Template A / B / C 后，还需要明确以下层级：

### Core

- 目标用户：后端工程师、Agent 工程师、AI 应用工程师
- 目标：理解原理、完成基线、定位瓶颈、运行核心 Demo
- 结果：能够将方法迁移到 RAG、Agent 或普通 LLM 服务

### Advanced

- 目标用户：平台工程师、基础设施工程师、推理引擎工程师
- 目标：深入 GPU Runtime、多 GPU、通信、分布式缓存和容量规划
- 结果：能够设计和分析大规模推理基础设施

### 每章通用的交付字段

1. 学习目标：三个问题（见 2.2 第 1 项）；
2. 章节边界：本章不做什么，留给哪一章；
3. Demo、示例或可验证证据；
4. 运行环境、版本和适用条件；
5. 预期现象与结果解读；
6. 学习检查清单；
7. Advanced 深入方向（仅在确有必要时提供）。

如果章节主 Demo 要求真实服务或真实 GPU，课堂主案例必须复用该 Demo 的真实报告。真机数据尚未取得时，正文保留“待实测”和字段模板，不得用合成时间戳、示例性能数字或离线报告代替。合成数据只用于公式、状态机和异常边界的单元测试，并且不能进入性能结论。

Baseline、优化后结果和 Trade-off 不再强制出现在每一章。它们是优化专题（Template B）和综合实践（Template C）的必备项。Part 1 的机制与架构章节只需把“概念—证据—边界”讲清楚，避免为了套模板制造虚假的优化对照。

课程统一性能工程方法见 `01_Course_Design.md`；具体 Part / Chapter 以 `02_Course_Outline_v0.2.md` 为准。

---

## 1. 模板选择原则

### 1.1 Template A 用于建立概念和分析能力

适用于架构、生命周期、指标、性能模型、Benchmark、Profiling、工作机制和性能分析等章节。

### 1.2 Template B 用于展开单项优化技术

适用于 FlashAttention、KV Cache、Continuous Batching、Speculative Decoding 等技术专题。

当 Outline 中一个“优化方法”章节包含多项技术时，Template B 应用于**章内每个技术专题小节**，而不是要求整章只套用一次。

### 1.3 Template C 用于完整调优闭环

适用于 Prefill、Decode、Serving、Scalability 的实战验证，以及 Final Project。

### 1.4 不要求所有栏目等长

模板规定的是必须回答的问题，不是固定页数。章节可根据难度调整篇幅，但不能省略影响理解和验证的关键环节。

### 1.5 插图数量服从教学任务

每张图只回答一个关键问题，但每章不强制使用相同数量的图片。入门操作章可以用 3～5 张图完成运行路径、观察点和章节边界；机制或架构章可以根据概念密度增加图片。最终数量以已确认的 Storyboard 为准，校验脚本不得为了凑数要求无教学价值的插图。

---

## 2. Template A：基础理论与分析章节（Foundation / Analysis Chapter）

### 2.1 适用章节

典型适用范围：

- 真实请求生命周期
- Transformer 生成机制
- LLM Serving 架构
- 性能指标与延迟预算
- LLM 工作负载建模
- Benchmark Design
- 请求级可观测性
- Profiling Toolchain
- Root Cause Analysis
- Prefill / Decode / Serving 的工作机制与性能分析章节
- 容量、显存与成本模型
- 性能回归与发布门禁
- Performance Review

### 2.2 模板结构

#### 1. 学习目标（Learning Objectives）

章首只留这一节，内容写成**三个问题**：

```markdown
## 学习目标

读完这一章，你应该能回答三个问题：

1. …
2. …
3. …

跟着做完，你会得到……
```

引导句"你应该能回答三个问题"把目标（陈述句）和内容（问句）接上；末尾补一句本章产出物，这是问题给不了的信息。

不再单设「核心问题」小节。两节并存时，读者拿到的是同一批内容的两种句式，连着读六条反而抓不住重点。压不到三条通常不是内容太多，而是几条在讲同一个维度的不同实例，先合并维度。

这三个问题决定正文怎么分节，并由「本章总结」逐条回答。完整写法与判断方法见 `strategy/editorial/writing-rules.md` 规则 3。

#### 2. 核心内容（Core Concepts）

根据章节性质组织：

- 理论与核心概念
- 系统架构或工作机制
- 方法与分析流程
- 关键指标、数据结构或工具
- 与前后章节的关系

#### 3. Demo / 实验

教师演示或简单实验，至少明确：

- 实验目的
- 环境与输入
- 操作步骤
- 观察指标
- 预期现象

#### 4. 本章总结（Summary）

以「回到开头的三个问题」组织，逐条给出答案，让读者读完能自己对答案。之后接：

- 一份本章 Checklist，写可逐项打勾的动作（总结偏理解，Checklist 偏操作，两者不重复措辞）
- 与下一章的衔接

某个问题在总结里找不到对应的回答段落，说明要么正文没真的解决它，要么它本来就不该列在章首。

### 2.3 完成标准

Template A 章节完成时，应保证学员能够：

- 回答章首列出的三个问题
- 解释本章内容在推理系统中的位置
- 通过一个 Demo 或示例观察关键现象
- 使用 Checklist 逐项自查是否真的做到了

---

## 3. Template B：技术专题章节（Technology Chapter / Section）

### 3.1 适用技术

典型适用范围：

- FlashAttention
- FlashInfer
- CUDA Graph
- Kernel Fusion
- Persistent Kernel
- KV Cache 管理与容量
- PagedAttention
- KV Quantization
- Prefix Cache
- Dynamic Batching
- Continuous Batching
- Chunked Prefill
- Admission Control
- Speculative Decoding
- MTP
- Medusa
- EAGLE
- Quantization
- Replica
- Load Balance
- Autoscaling
- Advanced Appendices 中的 Tensor Parallel、Pipeline Parallel、Expert Parallel 和 PD Disaggregation

### 3.2 模板结构

#### 1. 为什么需要（Problem）

- 它解决什么性能问题？
- 在什么工作负载或系统条件下出现该问题？
- 为什么已有机制不足？

#### 2. 工作机制（How it Works）

- 执行流程
- 数据流
- 生命周期
- 对原有执行路径做了什么改变

#### 3. 性能模型（Performance Model）

- 为什么该技术可能有效？
- 改善哪些指标？
- 影响 Compute、Memory、Scheduling 或 Capacity 中的哪些资源？
- 收益依赖哪些条件？

#### 4. Profiling 与瓶颈分析

- 如何识别适用场景？
- 优化前有哪些 Profiling 特征？
- 哪些数据可以证明 Root Cause？
- 如何排除其他瓶颈？

#### 5. 优化实现（Optimization）

- 实现方式
- 参数配置
- 推理框架支持
- 启用、关闭或切换方式
- 与其他优化技术的组合关系

#### 6. Benchmark

- Baseline
- Workload 配置
- 优化后结果
- 核心指标对比
- 收益分析和可重复性

#### 7. Trade-off

- 优势
- 局限
- 副作用
- 对其他指标的影响
- 不适用场景

#### 8. Best Practice

- 推荐配置
- 适用场景
- 工程经验
- 上线前检查项

### 3.3 完成标准

Template B 技术专题完成时，应回答：

1. 为什么需要这项技术？
2. 它改变了哪一段执行机制？
3. 如何用 Profiling 判断是否适用？
4. Benchmark 是否证明了收益？
5. 收益的边界和 Trade-off 是什么？

---

## 4. Template C：综合实践章节（Case Study Chapter）

### 4.1 适用章节

- Prefill 优化实验
- Decode 优化实验
- Serving 与 Agent 综合实验
- Root Cause Analysis Lab
- Final Project

### 4.2 模板结构

#### 1. 实验目标

定义本次调优要解决的问题，以及目标指标和约束条件。

#### 2. Baseline

记录初始配置和指标：

- TTFT
- TPOT
- TPS
- GPU Utilization
- GPU Memory
- Concurrency / Cost（根据场景选用）

#### 3. Profiling

采集性能数据：

- Timeline
- GPU
- Memory
- Kernel
- Queue / Scheduler / Worker（根据场景选用）

#### 4. Root Cause

- 区分症状与根因
- 列出证据
- 排除非主要瓶颈
- 形成明确诊断结论

#### 5. Optimization Plan

制定优化方案：

- 优化目标
- 候选技术
- 实施顺序
- 预期收益
- 风险与 Trade-off

#### 6. 实施优化

逐步完成优化，每次只改变可控变量，并记录配置变化。

#### 7. Benchmark Verification

- 使用与 Baseline 一致的 Workload
- 对比核心指标
- 检查 P50 / P95 / P99 和稳定性
- 检查是否出现性能转移或副作用

#### 8. Performance Report

形成完整调优报告，至少包括：

- 问题描述
- 实验环境
- Baseline
- Profiling 证据
- Root Cause
- 优化方案
- Benchmark 结果
- Trade-off 与结论

#### 9. Lessons Learned

- 哪些假设被验证或否定？
- 哪些优化有效，哪些无效？
- 结论能否迁移到其他模型、框架或负载？
- 后续还应进行哪些实验？

### 4.3 完成标准

Template C 章节必须形成完整闭环：

```text
Baseline
    ↓
Profiling
    ↓
Root Cause
    ↓
Optimization Plan
    ↓
Implementation
    ↓
Benchmark Verification
    ↓
Performance Report
```

---

## 5. 三类模板与课程大纲的对应关系

| 课程章节 | 推荐模板 |
|---|---|
| Chapter 1～9 | Template A |
| Chapter 10 | Template C |
| Chapter 11～12 | Template A |
| Chapter 13 中的各项 Prefill 技术专题 | Template B |
| Chapter 14 | Template C |
| Chapter 15～17 | Template A / B，按章内专题选择 |
| Chapter 18 中的生成与 Runtime 技术专题 | Template B |
| Chapter 19 | Template C |
| Chapter 20～24 | Template A / B，按章内专题选择 |
| Chapter 25 | Template C |
| Chapter 26～29 | Template A |
| Chapter 30 | Template C |
| Advanced Appendices / Labs | Template B / C |

---

## 6. 课程开发原则

- **课程结构：** 分别使用单请求路径、应用关键路径和系统扩展路径，不把 Serving 当成 Decode 之后的阶段。
- **统一方法：** 各模块遵循“Workload & SLO → 理解系统 → 定位瓶颈 → 优化方案 → 同流量验证 → Regression Guard”。
- **模板选择：** 根据章节性质选择 Template A / B / C，不机械套用单一模板。
- **教学目标：** 建立 Performance Engineering 思维，而不是孤立学习优化技术。
- **实验要求：** 技术收益必须有 Baseline、Profiling 和 Benchmark 支撑。
- **工程要求：** 必须说明适用场景、限制条件和 Trade-off。
