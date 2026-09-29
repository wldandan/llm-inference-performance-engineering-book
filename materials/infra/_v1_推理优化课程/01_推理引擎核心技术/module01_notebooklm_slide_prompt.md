请根据上传的资料，为「模块一：推理引擎核心技术」生成一套完整的演讲幻灯片内容。

要求：
- 共6讲，每讲生成5-8页幻灯片
- 每页包含：标题、3-5个要点（bullet points）、一句话核心结论
- 每讲第一页必须包含一个生活化类比，让没有技术背景的人也能理解
- 最后一讲之后加一页「模块总结」

---

第1讲：LLM推理全流程
类比：打字预言机——手机输入法每次预测下一个字
核心内容：Prefill阶段（并行处理输入）vs Decode阶段（逐字生成）、TTFT/TBT/吞吐量三个指标、为什么Decode是Memory-Bound（内存带宽瓶颈）、Roofline模型直觉

第2讲：注意力机制演进与优化
类比：班级握手问题——每人和所有人握手，人数翻倍握手次数翻四倍
核心内容：MHA→MQA→GQA→MLA的演进逻辑、KV Cache内存压力、Flash Attention通过分块计算避免写大矩阵到显存、FA1/FA2/FA3三代核心改进

第3讲：量化技术全栈解析
类比：电影评分精度——8.734分 vs 9分，省空间但精度降低
核心内容：PTQ vs QAT、FP16→INT8→FP8→INT4各格式特点、GPTQ/AWQ/GGUF三大方案对比、量化对模型大小/速度/质量的三角权衡

第4讲：投机采样与加速解码
类比：小助手猜答案老师批改——小模型先猜5个词，大模型一次验证
核心内容：Draft-Verify范式、为什么验证比生成便宜、草稿接受率与加速比的关系、Medusa/Eagle/EAGLE-2方案对比

第5讲：批处理策略演进
类比：餐厅服务演进——从团餐等人到快餐随到随服务
核心内容：Static Batching（等最慢的人）→ Dynamic Batching → Continuous Batching（vLLM核心，GPU利用率40%→75%）→ Chunked Prefill（防止长请求拖累短请求）

第6讲：算子融合与内核优化
类比：合并购物清单——一次去超市买完所有东西
核心内容：GPU HBM vs SRAM速度差距、算子融合减少HBM读写次数、常见融合场景（Fused Attention/MLP/LayerNorm）、Triton自定义Kernel vs torch.compile

模块总结：
请列出6个核心结论（每讲一个），以及一张「优化方向全景图」，展示六个技术点如何共同作用于LLM推理加速。
