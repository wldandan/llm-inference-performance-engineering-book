请根据上传的资料，为「模块二：KV Cache深度解析与优化」生成一套完整的演讲幻灯片内容。

要求：
- 共5讲，每讲生成5-8页幻灯片
- 每页包含：标题、3-5个要点（bullet points）、一句话核心结论
- 每讲第一页必须包含一个直观类比，让没有技术背景的人也能理解
- 最后一讲之后加一页「模块总结」

---

第1讲：KV Cache基础与内存分析
类比：做题时的草稿纸——写过的计算就不重新算，但草稿纸越用越多
核心内容：KV Cache产生原因（避免重复计算注意力）、内存占用计算公式（2×num_layers×num_heads×d_head×seq_len×batch×dtype字节）、以LLaMA-2-7B为例计算不同场景下的内存消耗、为什么KV Cache是推理服务最主要的内存瓶颈

第2讲：PagedAttention
类比：虚拟内存分页——操作系统早就解决过这个问题
核心内容：原始KV Cache的内存碎片化问题（提前分配max_seq_len导致浪费）、PagedAttention设计：虚拟KV页→物理KV块的映射、动态内存分配消除碎片、copy-on-write支持Beam Search、实测效果：GPU利用率40%→75%、vLLM源码架构简述

第3讲：Prefix Caching与Radix Attention
类比：老师批改同班同学相同开头的作文——公共部分只改一次
核心内容：哪些场景有大量公共前缀（System Prompt、RAG检索结果、Few-shot示例）、Prefix Caching基本原理：哈希前缀匹配复用KV Cache、SGLang的Radix Tree实现：用前缀树自动管理所有前缀、Cache Hit Rate的计算与优化、LRU驱逐策略

第4讲：KV Cache压缩与稀疏化
类比：草稿纸上用缩写——信息量损失一点但省很多空间
核心内容：KV Cache量化（FP16→INT8/INT4）的可行性分析、注意力稀疏性：不是所有Token都同等重要、H2O（Heavy Hitter Oracle）：保留注意力分数高的Token、SnapKV：Prompt阶段压缩KV、StreamingLLM：滑动窗口保留最近Token、各方案对长文本理解能力的影响

第5讲：KV Cache分层存储与卸载
类比：把不常用的书从桌面移到书架再移到仓库——容量换速度
核心内容：GPU HBM→CPU DRAM→NVMe三层存储层级（带宽：3TB/s→50GB/s→7GB/s）、异步Prefetch：在计算时提前搬运下一批KV Cache、Mooncake（字节）：全局分布式KV Cache池设计、跨节点KV Cache共享在PD分离架构中的作用、工程实践：何时值得用CPU卸载，何时不值得

模块总结：
请列出5个核心结论（每讲一个），以及一张「KV Cache优化全景图」，展示从单机内存管理到分布式存储的完整优化链路。
