请根据上传的资料，为「模块八：前沿专题」生成一套完整的演讲幻灯片内容。

要求：
- 每讲2-3张幻灯片，包含标题页、核心技术页、趋势展望页
- 每讲第一张以直觉类比开场，帮助学生建立感性认识
- 内容前沿但不失严谨，引用最新论文和技术报告（2024-2025年）
- 技术深度适合已学完前六模块的工程师受众
- 包含具体的数据、指标和论文引用
- 展望部分要区分"已落地"和"研究方向"

第1讲：Reasoning模型Infra挑战（类比：解题过程越写越长的试卷）
- 类比引入：CoT推理链越长越准确，但显存（试卷纸）有限——当Thinking Token数量达到32K+，KV Cache占用超过模型权重本身
- Reasoning模型的特殊性：o1/R1系列 vs 普通LLM的KV Cache模式对比；长推理链对显存的非线性增长影响；Prefill/Decode比例失衡
- KV Cache爆炸与应对：长序列KV压缩技术（SnapKV、StreamingLLM、H2O）；Thinking Token Budget限制（DeepSeek-R1 max_thinking_tokens参数）；动态KV淘汰策略
- 早停与自适应推理：置信度检测早停（答案已收敛停止继续推理）；Speculative Thinking（草稿模式）；推理预算感知调度（Budget-Aware Scheduling）
- DeepSeek-R1 Infra优化实践：PD分离对长推理的意义、显存管理策略、实测数据对比

第2讲：下一代AI Infra趋势（2025-2026展望）
- 硬件变革：GB200 NVL72（72卡直连，5.5 PetaFLOPS，NVLink 1.8TB/s带宽）；Groq LPU（确定性延迟，无调度抖动，TTFT <100ms）；华为Ascend 910C（国产替代路线）
- 算法前沿：Flash Attention 3（利用 Hopper 异步特性，较 FA2 提升 1.5-2×）；MLA（Multi-head Latent Attention，DeepSeek-V3的KV压缩核心）；Speculative Decoding 2.0（Draft模型自适应生成）
- 系统架构趋势：Test-Time Compute Scaling（更多计算换更好输出质量，o1/R1系列验证）；全局KV Cache Pool（跨请求/跨用户共享）；存算一体芯片（PIM/CIM，从根本解决内存带宽墙）
- 2025-2026研究展望：长上下文推理（1M token window）；多模态统一推理架构；推理成本持续降低路线图（MoE + 量化 + 硬件协同）

模块总结要求：
- 一张"AI Infra技术雷达"幻灯片（分为落地/试验/研究三圈层）
- 一张"课程知识图谱"幻灯片，将8个模块知识点串联成完整的AI Infra工程师成长路径
- 结束语：AI Infra是当前AI发展速度最快的工程领域，今天的前沿是明年的标配——持续学习是核心竞争力
