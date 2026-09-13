# 《LLM 推理性能工程实战》V0.2 课程大纲

> 副标题：从模型原理、性能分析到 Serving 与 Agent 优化

## 课程定位

面向后端工程师、Agent 工程师、AI 应用工程师和 MLOps / 平台工程师。课程聚焦纯文本 Decoder-only LLM 的在线推理，用一套持续演进的真实服务，帮助学员完成“运行、理解、测量、诊断、优化、验证、上线守护”的性能工程主线。

标签说明：`Core` 为主线必修；`Bridge` 为 Core 掌握概念、Advanced 深入实现；高级 GPU 和分布式内容放在 Advanced Appendices / Labs。

## 学习主线

```text
真实服务与请求
  → 模型执行与 Serving 架构
  → Workload、指标、Benchmark 与诊断
  → Prefill / Decode / Serving 优化
  → RAG / Agent 关键路径优化
  → 容量、成本、回归门禁与综合项目
```

V0.2 保留现有 7 Part、30 章结构。两本参考书用于补强方法，不用于扩张目录：

- 《AI Systems Performance Engineering》补强 SLO-aware Goodput、假设驱动诊断、最小侵入优化和持续性能回归；
- 《Inference Engineering》补强生产代表性 Benchmark、Serving 选型、客户端开销和上线检查；
- 应用选型、客户端、容器化、冷启动、Shadow 和 Canary 作为现有章节中的必要小节，不新增独立章节；
- GPU/CUDA、多 GPU、MoE、Expert Parallel 和 PD Disaggregation 仍放在 Advanced。

## Part 1：从一个请求理解推理系统

| 章节 | 标题 | 定位 | 核心问题 |
|---|---|---|---|
| Ch1 | 第一个 LLM 服务 | Core | 如何启动 vLLM，并用一次同步请求完成最小生成闭环？ |
| Ch2 | 真实请求生命周期 | Core | 同步调用为什么不够，如何用流式事件和服务端证据还原 Queue、Prefill、Decode 与终态？ |
| Ch3 | Transformer 生成机制 | Core | Attention、自回归、Sampling、Prefill、Decode 和 KV Cache 如何协作？ |
| Ch4 | LLM Serving 架构 | Core | API、Gateway、Scheduler、Worker、Runtime 和 GPU 如何协作？ |
| Ch5 | 性能指标与延迟预算 | Core | 如何定义 TTFT、TPOT、TPS、P99、SLO-aware Goodput、质量和成本预算？ |

章节边界：Ch1 用同步请求验证最小服务链路，并让观察缺口自然出现；Ch2 再引入流式响应，关联真实生命周期证据；Ch3 解释模型内部；Ch4 解释系统组件；Ch5 才正式定义和评价性能。

## Part 2：测量、观测与根因分析

| 章节 | 标题 | 定位 | 核心问题 |
|---|---|---|---|
| Ch6 | LLM 工作负载建模 | Core | Chat、RAG、Agent 的输入输出、到达模式、并发和 SLO 应如何描述？ |
| Ch7 | Benchmark Design | Core | 如何用生产代表性的长度、到达模式、参数和请求内容建立可重复 Baseline？ |
| Ch8 | 请求级可观测性 | Core | 如何用 Request ID 关联客户端时间、日志、指标和 Trace？ |
| Ch9 | Profiling Toolchain | Bridge | API、CPU、Scheduler、GPU Timeline 和 Kernel 工具分别回答什么问题？ |
| Ch10 | Root Cause Analysis Lab | Core | 如何把性能现象收敛成可证伪根因，并从最小侵入方案开始优化？ |

本篇输出一份诊断报告，而不是一组互相孤立的工具截图。

## Part 3：Prefill 与上下文优化

| 章节 | 标题 | 定位 | 核心问题 |
|---|---|---|---|
| Ch11 | Prefill 工作机制与性能模型 | Core | Prompt 如何经过 Attention、GEMM 并创建 KV Cache？ |
| Ch12 | 长上下文与 RAG 上下文成本 | Core | 上下文长度、有效信息密度和 Prompt 结构如何放大 TTFT 与 token 成本？ |
| Ch13 | Prefill 优化方法 | Bridge | FlashAttention、上下文裁剪、Prefix Cache 和 Chunked Prefill 何时有效？ |
| Ch14 | Prefill 优化实验 | Core | 如何用相同长 Prompt 工作负载验证 TTFT、吞吐和显存变化？ |

FlashInfer 按具体 Kernel/Runtime 能力介绍，不把框架名称当成单一优化算法。

长上下文同时压 Prefill 计算量和 KV Cache 占用，本篇只负责前一半：Ch12 讲上下文长度如何放大 TTFT 与 token 成本，显存占用、并发上限和抢占交给 Ch16。Ch12 正文要显式写出这个交接，让读者知道这笔账只算了一半。

## Part 4：Decode、KV Cache 与生成优化

| 章节 | 标题 | 定位 | 核心问题 |
|---|---|---|---|
| Ch15 | Decode 工作机制与性能模型 | Core | 为什么逐 Token Decode 容易受显存带宽和调度开销限制？ |
| Ch16 | KV Cache 管理与容量 | Core | 如何估算 KV Cache、理解增长与碎片，并使用 PagedAttention？ |
| Ch17 | 量化与内存优化 | Core + Bridge | 权重量化和 KV Quantization 如何改变容量、速度与质量？ |
| Ch18 | 生成与 Runtime 优化 | Bridge | Speculative Decoding、CUDA Graph 和 Kernel 优化分别解决什么瓶颈？ |
| Ch19 | Decode 优化实验 | Core | 如何联合验证 TPOT、TPS、显存、接受率和质量边界？ |

Dynamic/Continuous Batching 不放在本篇，统一归入 Serving Scheduler。

## Part 5：Serving、RAG 与 Agent 性能工程

| 章节 | 标题 | 定位 | 核心问题 |
|---|---|---|---|
| Ch20 | Scheduler 与 Continuous Batching | Core | Waiting/Running、Token Budget 和 Continuous Batching 如何影响利用率与尾延迟？ |
| Ch21 | 流量治理与可靠性 | Core | 如何联合设计连接复用、异步/流式调用、Admission、Timeout、Cancel、Retry 和 Backpressure？ |
| Ch22 | Serving 架构选择与模型路由 | Core | 如何比较共享 API、专用部署与自托管，并设计模型/引擎选择和缓存感知路由？ |
| Ch23 | RAG 性能工程 | Core | Retrieval、Rerank、Context 和 Generation 中谁决定关键路径与成本？ |
| Ch24 | Agent 性能工程 | Core | 多步 LLM、工具调用、串并行、重试和上下文增长为何放大延迟？ |
| Ch25 | Serving 与 Agent 综合实验 | Core | 如何优化一条真实 RAG/Agent 服务链路并守住 SLO？ |

Ch21 的客户端内容只解释端到端性能必需的连接、协议和并发控制，不扩成客户端开发课程。Ch22 只建立选择方法，不做模型榜单或框架功能大全；课程主 Demo 默认以 vLLM 为基线。

## Part 6：容量、成本与生产工程

| 章节 | 标题 | 定位 | 核心问题 |
|---|---|---|---|
| Ch26 | 容量、显存与成本模型 | Core | 如何估算模型、KV Cache、并发上限和单位 Token 成本？ |
| Ch27 | 多副本、路由与 Autoscaling | Core | 如何通过 Scale-out、负载均衡和弹性扩缩容满足 SLO？ |
| Ch28 | 性能回归与发布门禁 | Core | 如何用自动 Benchmark、Shadow/Canary 和阈值识别回归并阻止问题版本上线？ |
| Ch29 | Performance Review 与上线检查 | Core | 如何把 Dashboard、容量、成本、模型加载/冷启动和回滚计划纳入上线决策？ |

生产可观测性贯穿 Ch8、Ch27-Ch29；容器化、Readiness 和冷启动只作为上线检查项，不单独扩成部署运维 Part。

## Part 7：综合项目

| 章节 | 标题 | 定位 | 核心问题 |
|---|---|---|---|
| Ch30 | End-to-End Performance Engineering Project | Core + Advanced | 如何交付一套可运行、可观测、可解释、可优化且有回归门禁的 LLM 服务？ |

Core 项目使用单 GPU 构建可观测 RAG/Agent 服务；Advanced 学员可以替换为多 GPU 或分离式架构，但沿用同一份 Workload、SLO 和验证报告。

## Advanced Appendices / Labs

Advanced 内容不占用 30 章 Core 主线编号：

| 附录 | 主题 | 实验重点 |
|---|---|---|
| A | GPU Architecture 与 Roofline | SM、Tensor Core、HBM、Occupancy、硬件计数器 |
| B | CUDA 与高级 Kernel Profiling | CUDA Graph、Kernel Fusion、Nsight Compute |
| C | Multi-GPU Inference | Tensor Parallel、Pipeline Parallel、NCCL、Scaling Efficiency |
| D | MoE、Expert Parallel 与 All-to-All | 专家路由、负载倾斜、通信开销 |
| E | PD Disaggregation 与 KV Transfer | Prefill/Decode 资源池、KV 传输、独立扩缩容 |

Core 正文只解释这些能力解决什么问题、何时值得使用以及如何阅读结果；实现细节和多卡实验留在附录。

## Demo 交付要求

正式验收采用 8 个递进实验，而不是强制每章构造一个孤立性能实验：

1. 第一个真实服务；
2. 真实请求生命周期；
3. Workload、Benchmark 与请求级可观测性；
4. Prefill 与长上下文优化；
5. Decode、KV Cache 与量化优化；
6. Scheduler、Batching 与流量治理；
7. RAG / Agent 关键路径优化；
8. 容量、回归门禁与端到端项目。

每个正式实验必须记录环境、Workload、Baseline、证据、优化配置、同流量重跑、指标对比和 Trade-off。
