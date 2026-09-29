请根据上传的资料，为「模块一：硬件基础与性能分析」生成一套完整的演讲幻灯片内容。

要求：
- 共3讲 + 1个实验模块，每讲生成5-7页幻灯片
- 每页包含：标题、3-5个要点（bullet points）、一句话核心结论
- 每讲第一页必须包含一个直观类比
- 实验模块生成3-4页操作指引幻灯片
- 最后加一页「模块总结」

---

第1讲：GPU架构深度解析
类比：工厂车间——CPU是几个技艺精湛的工匠，GPU是成千上万条流水线同时运作
核心内容：SM（流式多处理器）工作原理，每个SM包含多个Warp（32线程束）并行执行；Tensor Core专用矩阵乘法加速（一次完成4×4矩阵乘，比普通CUDA Core快16倍）；HBM（高带宽显存）vs SRAM（片上缓存）的容量与带宽差异；FP32/FP16/BF16/FP8/INT8各数据类型的计算吞吐量对比；A100 vs H100核心参数对比（算力/带宽/Tensor Core代际）；MFU（模型算力利用率）和MBU（内存带宽利用率）的含义

第2讲：存储与互联系统
类比：图书馆的多层存储——桌上的便签（SRAM，快但小）、书架（HBM，大但慢）、仓库（DRAM/NVMe，更大更慢）
核心内容：GPU内存层次带宽具体数字（SRAM约19TB/s，HBM约3.35TB/s，DRAM约50GB/s）；为什么内存带宽比算力更常成为瓶颈（Arithmetic Intensity决定）；NVLink vs PCIe节点内互联（带宽差距5-10倍）；NVSwitch：多GPU全互联的实现；InfiniBand vs RoCE节点间网络（400Gb/s vs latency差异）；带宽和延迟对分布式训练的影响

第3讲：模型架构对Infra的影响
类比：选汽车配道路——跑车配赛道，越野车配山路，模型架构决定硬件需求
核心内容：Dense模型 vs MoE模型的算力/内存需求差异（LLaMA-7B vs Mixtral-8x7B对比）；Transformer各层（Embedding/Attention/FFN/LMHead）的算力带宽需求分析；GQA（分组查询注意力）如何减少KV Cache内存需求（从MHA的32头到GQA的8头）；MLA（多头潜在注意力，DeepSeek创新）的KV压缩原理；架构选型与硬件适配决策树（什么模型适合什么硬件）

实验模块：GPU性能分析实战
核心内容：Roofline模型的构建（GPU峰值算力和带宽两条线）；如何计算矩阵乘法的Arithmetic Intensity（FLOPs/Bytes）；用PyTorch Profiler定位推理热点；在Roofline图上标注Linear层（Compute-Bound）和Attention（Memory-Bound）；实验操作步骤（含M1 Mac CPU运行的fallback方案）

模块总结：
请列出3个核心结论（每讲一个），一张「硬件选型决策图」展示不同场景下的最优硬件配置，以及一句话说明为什么硬件理解是所有优化技术的基础。
