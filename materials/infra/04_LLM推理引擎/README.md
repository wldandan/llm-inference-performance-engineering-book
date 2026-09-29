# 模块四：LLM推理引擎

**状态**：内容开发中

**学时**：8学时理论 + 2学时实验 = 10学时

**讲次规划**：
- 讲1：推理全流程与内存分析（Prefill/Decode/TTFT/TPOT/KV Cache公式）
- 讲2：KV Cache管理（PagedAttention/Radix Attention/分层存储）
- 讲3：批处理与请求调度（Continuous Batching/Chunked Prefill/混合流量）
- 讲4：推理框架选型（vLLM vs SGLang 架构对比）
- 实验：推理服务搭建与基准测试（部署vLLM+SGLang，测TTFT/TPOT/吞吐量）

**注**：本模块与v1课程中模块一（推理引擎核心技术）和模块二（KV Cache）内容重叠较大，
可参考 _v1_推理优化课程/ 目录中的现有slides和notebooks。
