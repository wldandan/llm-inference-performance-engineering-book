请根据上传的资料，为「模块五：推理框架深度解析与实战」生成一套完整的演讲幻灯片内容。

要求：
- 共2讲，每讲生成7-10页幻灯片
- 每页包含：标题、3-5个要点（bullet points）、一句话核心结论
- 每讲第一页必须包含一个生活化类比，让没有技术背景的人也能理解
- 最后一讲之后加一页「模块总结」

---

第1讲：vLLM深度解析
类比：精密机器的各个零件——vLLM就像一台精密的工业机器，LLMEngine是控制中心，Scheduler是调度大脑，Worker是执行手臂，KV Cache Manager是内存管家，每个零件各司其职，精密配合
核心内容：
- vLLM整体架构三层设计（LLMEngine/AsyncLLMEngine + Scheduler + Worker/ModelRunner）
- Scheduler核心逻辑（Waiting/Running/Swapped三种队列，FCFS+抢占调度，preemption触发条件）
- PagedAttention与KV Cache Manager（Block Table映射、物理块分配、Copy-on-Write for Beam Search）
- Continuous Batching实现细节（如何在一个Forward Pass中混合不同进度的请求）
- vLLM Plugin生态（OpenAI兼容API、多模态支持、LoRA热加载、Speculative Decoding集成）
- vLLM性能调优关键参数（--gpu-memory-utilization、--max-num-seqs、--enforce-eager vs CUDA Graph）

第2讲：SGLang深度解析与框架选型
类比：更聪明的版本——如果vLLM是一台精密机器，SGLang是同类机器但加装了AI大脑：RadixAttention让它记住所有用过的前缀不重复计算，Overlap Scheduler让它同时思考下一批而不是空等，FlashInfer让它的每个动作都更高效
核心内容：
- SGLang核心创新：RadixAttention前缀树（把所有历史请求的KV Cache组织成Radix Tree，新请求自动匹配最长前缀）
- FlashInfer集成（统一的GPU Kernel库，比vLLM内置的attention快10-20%）
- Overlap Scheduler设计（CPU调度与GPU计算完全重叠，消除CPU成为瓶颈的问题）
- Structured Output加速（直接在采样阶段mask非法Token，比后处理验证快5-10x）
- 四大框架选型矩阵：vLLM vs SGLang vs TensorRT-LLM vs LMDeploy（从场景/性能/易用性/生态四个维度对比）
- 生产部署最佳实践（容器化部署、健康检查、指标采集、版本管理）

模块总结：
请列出2个核心结论（每讲一个），以及一张「推理框架全景选型指南」，从研究/快速验证/中等规模生产/大规模生产/NVIDIA极致优化五个场景给出推荐框架和关键配置。
