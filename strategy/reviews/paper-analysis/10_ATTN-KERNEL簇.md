# ATTN-KERNEL 簇解析结果（51 篇，实际独立 49 篇）

> 解析 agent：paper-attn-kernel2，2026-09-17 完成
> 重复文件：MInference.pdf = MInference 1.0.pdf；Sparse FlashAttention.pdf = QK-SparseDropping Attention.pdf
> 帮助类型：A-深化正文 / B-正文证据 / C-扩展视野 / D-低相关

## 逐篇结果

| # | 文件 | 核心贡献 | 关键数字 | 章节映射 | 类型 | 建议 |
|---|---|---|---|---|---|---|
| 1 | ACTIVATION SPARSITY.pdf (TEAL, ICLR'25) | 训练免幅度激活稀疏，全模型40-50%稀疏度下跳过权重通道显存搬运 | 解码加速1.53x/1.8x（40%/50%），兼容权重量化 | Ch15, Ch18 | C | Ch15讲带宽受限时作"量化之外的另一条路：激活稀疏"深入阅读 |
| 2 | Blockwise Attention.pdf (BPT) | 块级计算自注意力并融合FFN，两重嵌套分块循环 | 训练序列为vanilla 32x、比FA长2-4x | Ch13, 附录A | C | 讲FA分块循环时引用为"分块思想可扩展到FFN" |
| 3 | CRITIPREFILL.pdf | 相邻query关注相似KV子集的局部性，段级关键度估计剪枝prefill注意力 | 128K时prefill占总推理时间95.6%；Llama3-8B 2.7x、Yi-9B 3.0x（A100） | Ch11, Ch12, Ch13 | B+C | "95.6%"是长输入prefill主导的绝佳证据标签；Ch13裁剪路可提名 |
| 4 | ChunkAttention.pdf | 前缀树KV cache + 两阶段划分内核，多租户共享系统提示词 | 共享prompt 1K-4K时注意力内核3.2-4.8x | Ch13, Ch3 | B | Ch13 Prefix Cache一节直接证据：共享前缀既省显存又加速内核 |
| 5 | Eigen Attention.pdf | SVD低秩投影在低维空间做注意力，后训练免微调 | KV cache减40%、注意力延迟减60% | Ch12 | C-弱 | 仅当Ch12列"KV压缩流派谱系"时收录，否则放弃 |
| 6 | FASTDECODE.pdf | KV cache访问卸载到多节点CPU聚合带宽，GPU专注计算 | 同GPU吞吐为vLLM的1.88-5.04x | Ch15, Ch12 | C | Ch15"decode受KV带宽限制"的极端解法案例 |
| 7 | FLASH-ATTENTION RNG.pdf | GEMM重叠隐藏FA中dropout的RNG延迟 | 1.26x vs 顺序、1.22x vs 融合 | 附录A | D | dropout是训练场景，推理书不适用，放弃 |
| 8 | FREE.pdf | 浅-深双出口早退+同步并行解码 | — | Ch18外围 | D | 早退路线已被投机解码实质取代，放弃 |
| 9 | FastAttention.pdf | FA移植到昇腾NPU与Volta GPU（两级tiling） | NPU上10.7x vs 标准注意力；V100 1.43x vs xformers | Ch13, 附录A | C | 说明FA tiling思想可跨架构迁移 |
| 10 | Flash-Decoding++.pdf | 统一最大值异步softmax（免同步）+flat GEMM双缓冲 | vs HF 4.86x/3.93x；vs SOTA引擎1.37x；同步softmax占注意力18.8% | Ch15, Ch13, Ch18 | A+B | Ch15 decode注意力并行核心参考；"18.8%同步开销"证据标签 |
| 11 | FlashAttention-2.pdf | 重构工作划分：减非matmul FLOPs、序列维并行、warp间减通信 | vs FA1约2x；A100前向达理论峰值50-73% | Ch13, 附录A | A | 必收：Ch13主线文献 |
| 12 | FlashAttention-3.pdf | Hopper异步：warp特化生产者-消费者、softmax与WGMMA交错、FP8块量化 | H100 1.5-2.0x；FP16 740 TFLOPs/s（75%）；FP8近1.2 PFLOPs/s | Ch13, 附录A | A | 必收：附录A讲Tensor Core异步/TMA最佳实例 |
| 13 | FlashAttention.pdf | IO感知精确注意力：tiling+online softmax避免N×N矩阵读写HBM | 注意力7.6x（GPT-2）、GPT-2训练3x、显存O(N)；SRAM 19TB/s vs HBM 1.5TB/s | Ch13, Ch3, 附录A | A | 必收：Ch13基石；显存层级带宽对比是附录A证据标签 |
| 14 | FlashLLM.pdf (Apple) | 参数存NAND闪存按需加载：窗口化复用+行列捆绑 | 跑2x DRAM容量模型；GPU加速20x | Ch12 | C-弱 | 端侧offloading偏离本书GPU数据中心视角 |
| 15 | Flex Attention.pdf | 编译器驱动注意力编程模型：score_mod/mask_mod数行PyTorch生成优化内核 | 性能媲美手写内核，可组合多种变体 | Ch13, Ch3 | C | Ch13工程生态深入阅读 |
| 16 | HADACORE.pdf | FEM张量积的Tensor Core加速 | 双精度8 TFLOPS（45%理论值） | 附录A | D | 领域偏（有限元HPC），放弃 |
| 17 | Hash Attention.pdf (Reformer, ICLR'20) | LSH哈希注意力O(L²)→O(L log L)+可逆层 | 64K序列enwik8 | Ch3, Ch13 | C | 稀疏注意力历史起点，Ch13稀疏路开篇溯源 |
| 18 | HyperAttention.pdf | LSH找大项+重要性采样近线性注意力，支持因果掩码 | ChatGLM2 32k快50%；131k单层5x | Ch13, Ch12 | C | 近线性注意力理论-工程折中案例 |
| 19 | I-LLM.pdf | 全整数PTQ：FSBR平滑+DI-MatMul+位操作softmax/RMSNorm | W4A4精度损失可忽略 | 量化章 | D | 移交量化簇 |
| 20 | INT-FLASHATTENTION.pdf | 首个与FA前向流程兼容的INT8量化注意力 | vs FA-FP16快72%；量化误差较FP8小82% | Ch13, 量化章 | C | Ch13与量化章交叉点：量化注意力内核代表 |
| 21 | InfiniGen.pdf | 用上层输入推测下层注意力模式，仅预取关键KV | 卸载系统3.00x加速、精度+32.6pp | Ch12, Ch15 | C | Ch12长上下文KV管理深入阅读 |
| 22 | LITE.pdf | 指令微调加中间层损失，置信度早退 | 7B/13B FLOPs省37.86%/46.35% | Ch18外围 | D | 早退训练主题，省FLOPs非墙钟，放弃 |
| 23 | LUT TENSOR CORE.pdf | LUT式mpGEMM软硬协同 | 计算密度较SOTA LUT加速器1.44x | 附录A, 量化章 | C-弱 | 硬件研究向，一句话参考 |
| 24 | MInference 1.0.pdf | 长上下文prefill动态稀疏：离线确定每头模式+在线建稀疏索引 | 1M prefill加速10x；注意力稀疏度96.8%；8B模型1M需30min、300K需6min（A100） | Ch11, Ch12, Ch13 | A+B | 必收：Ch13"上下文裁剪"路线代表；"300K→6min"是Ch11证据标签 |
| 25 | MInference.pdf | 与 1.0 重复 | — | — | 重复 | 保留一份 |
| 26 | MMInference.pdf | 长上下文VLM模态感知稀疏注意力 | 1M token prefill 8.3x | Ch12, Ch13 | C | MInference多模态续作，仅作深入阅读 |
| 27 | Microbenchmark.pdf | Turing/Ampere Tensor Core微基准：mma/mma.sp/ldmatrix吞吐延迟 | 首个基于新mma接口的系统测量 | 附录A | A | 必收：附录A Tensor Core指令级实测数据来源 |
| 28 | Online Softmax.pdf | online softmax原始论文：单遍计算max+归一化项 | softmax 1.3x、softmax+topk融合5x | Ch3, Ch13 | A | 必收：Ch3七步管线与Ch13机制推导直接引用的源头短文 |
| 29 | QK-SparseDropping Attention.pdf (SCFA) | 扩展FA支持动态Q/K丢弃与哈希稀疏（Triton内核） | 8k/16k训练加速2.0x/3.3x不损ppl | Ch13 | C | 与44重复；稀疏化与FA内核结合代表 |
| 30 | QUICK.pdf | 离线交错重排量化权重布局，消除bank conflict | vs AutoAWQ内核1.91x（大batch）、吞吐1.94x | 附录A, Ch18, 量化章 | B+C | 附录A"bank conflict"概念最佳实战案例 |
| 31 | REFORM.pdf | 超长上下文两阶段：增量压缩KV+早退出 | 1M上下文RULER/BABILong +52%/+34%；推理时间-30%、峰值显存-5% | Ch12 | C | Ch12长上下文深入阅读 |
| 32 | S3D.pdf | 自投机解码：中间层跳过+同时多token预测，零额外VRAM | vs 8bit量化EAGLE最高3.9x（A10G） | Ch18 | C | 归投机解码簇 |
| 33 | SCCA.pdf | 移位跨块注意力+移位空洞注意力 | LLaMA2-7B 4k→8k（单V100），需LoRA+PI微调 | Ch12外围 | D | 需微调的学术方法，工程落地弱，放弃 |
| 34 | STAND.pdf | 无模型N-gram投机草稿+随机草稿+Gumbel-TopK | AIME/GPQA/LiveCodeBench延迟-60~65% | Ch18 | C | 归投机解码簇 |
| 35 | SageAttention-2.pdf | INT4 QK+FP8 PV（两级累加） | OPS vs FA2/xformers约3x/4.5x；Hopper上匹敌FA3-FP8且精度更高 | Ch13, 附录A | A+B | 必收：量化注意力系列当前主力 |
| 36 | SageAttention-3.pdf | Blackwell FP4微缩放量化注意力 | RTX5090上1038 TOPS、vs 最快FA 5x；视频生成490s→164s | Ch13, 附录A | A+B | 必收："新精度→新内核"代际节奏最新案例 |
| 37 | SageAttention.pdf | 系列开篇：INT8 QK+FP8 PV，K通道离群值平滑 | OPS vs FA2/xformers 2.1x/2.7x | Ch13, 附录A | A | 必收：机制基础，与2/3构成完整故事线 |
| 38 | SeerAttention.pdf | MoE式可学习门控预测块级注意力稀疏度 | 长上下文prefill更低延迟且精度更优 | Ch13 | C | "学习型稀疏"路线代表，与MInference对照 |
| 39 | Skip Attention.pdf | 推理时跳过深层attention/MLP子层的层剪枝实证 | 13B去掉33%注意力层仅掉1.8% | Ch18外围 | D | 结构剪枝偏题，放弃 |
| 40 | Slim attention.pdf | 用W_KV从K在线算V，数学等价只存K cache | MHA上下文显存减半；T5-11B 32x | Ch12, Ch3 | C | 有趣的等价变换边栏素材，作深入阅读 |
| 41 | SpMM.pdf (SMaT) | 非结构化SpMM映射到Tensor Core（BCSR块+行重排） | vs cuSPARSE最高125x（平均2.6x） | 附录A, Ch13 | C | 附录A"Tensor Core为何偏爱块稀疏"佐证 |
| 42 | SparQ.pdf | decode时只取top-r查询对应V行+均值近似 | 注意力数据传输最多省8x，免训练即插即用 | Ch15, Ch12 | B+C | Ch15带宽受限直接利用者："decode不必每次搬全量KV"证据标签 |
| 43 | SpargeAttention.pdf | 通用免训练两段在线过滤稀疏注意力，集成SageAttention | vs 稠密/稀疏基线2.5-5x；Mochi视频端到端1.83x | Ch13, Ch15 | B+C | 稀疏+量化集大成实现，Ch13进阶深入阅读 |
| 44 | Sparse FlashAttention.pdf | 与29重复（SCFA） | — | — | 重复 | 保留一份 |
| 45 | Sparse Frontier.pdf | 最大规模训练免稀疏注意力实证：6方法×128K×9任务 | "更大稀疏模型胜过等成本更小稠密模型"；"prefill细粒度估计不实际、decode的token-to-page可行" | Ch12, Ch13 | B | 必收级：Ch13稀疏路线选型指南，直接支撑正文主张 |
| 46 | SparseInfer.pdf | 符号位XOR预测ReLU化LLM激活稀疏 | vs SOTA快约21%（Jetson Orin） | Ch15 | D | 边缘场景+前置条件多，被TEAL覆盖，放弃 |
| 47 | Streaming Attention.pdf | 单遍流式亚线性空间近似注意力的理论算法 | 纯理论界保证 | Ch12外围 | D | 纯理论，工程书不适用，放弃 |
| 48 | Tensor Core.pdf | V100 Tensor Core可编程性/性能/精度系统研究 | 混合精度实测83 TFLOPs/s（FP32的7x） | 附录A | A | 必收：附录A Tensor Core经典文献 |
| 49 | Tensor Cores.pdf | bipolar-INT格式+位级分解实现任意精度MatMul全用Tensor Core | MatMul vs CUTLASS 2.4x、LLM推理6.7x | 附录A, 量化章 | C | 低比特任意精度GEMM位操作技巧 |
| 50 | TurboAttention.pdf | FlashQ头级KV量化执行+SAS稀疏softmax近似 | 注意力1.2-1.8x、KV cache省4.4x+ | Ch13, Ch15, 量化章 | C | 量化+稀疏+Flash三合一综合方案 |
| 51 | Understanding LLMs.pdf | 从训练到推理的LLM全景综述 | — | — | D | survey簇覆盖，无增量价值，放弃 |

## 本簇三档结论

**必收（12篇）**：FlashAttention / FA-2 / FA-3（Ch13 完整演化链 + 附录A）、Online Softmax（Ch3/13 源头短文）、MInference 1.0（Ch13 裁剪路代表 + Ch11 证据）、Flash-Decoding++（Ch15）、SageAttention 三部曲（量化注意力线）、Microbenchmark + Tensor Core（附录A 配对）、Sparse Frontier（Ch13 选型实证）、ChunkAttention（Ch13 Prefix Cache 证据）。QUICK 接近必收（附录A bank conflict 案例）。

**深入阅读（约18篇）**：Flex Attention、SparQ、SpargeAttention、SeerAttention、CritiPrefill、HyperAttention、INT-FLASHATTENTION、TurboAttention、InfiniGen、FASTDECODE、FastAttention、Blockwise Attention、Reformer、MMInference、REFORM、SpMM、Tensor Cores、Slim attention、TEAL；S3D/STAND 移交投机解码簇。

**放弃（约11篇）**：FLASH-ATTENTION RNG、FREE、LITE、Skip Attention、SCCA、Streaming Attention、Understanding LLMs、SparseInfer、Eigen Attention、HADACORE；FlashLLM 一句话提及或放弃。

## 给正文的横向观察（Ch13 行文骨架）

本簇呈现三条演化主线：
1. **精确内核线**：online softmax → FA1 → FA2（工作划分）→ FA3（异步+FP8）→ FlexAttention（可编程性）
2. **量化内核线**：SageAttention 1→2→3（INT8→INT4/FP4，跟随 Tensor Core 精度代际）
3. **稀疏线**：Reformer（LSH起源）→ MInference（免训练模式识别）→ SeerAttention（学习型门控）→ SpargeAttention（稀疏+量化融合），选型依据见 Sparse Frontier
