# 模块一：硬件基础与性能分析

## 模块定位

> **为什么所有优化都从硬件开始？**

优化 = 找到瓶颈 + 消除瓶颈。在AI Infra领域，瓶颈几乎总是藏在硬件特性里——Tensor Core的利用率、HBM的带宽上限、NVLink的拓扑结构。不理解这些，调参数就是在黑箱里瞎摸。

本模块建立三个核心认知框架：
1. **计算边界**：GPU能"算"多快？峰值在哪里？
2. **带宽边界**：数据"搬"多快？瓶颈在哪里？
3. **Roofline心智模型**：给定任意算子，能在图上指出"你在哪里、能优化多少"

这三件事理解透，后续所有模块（量化/蒸馏/推理引擎/分布式）都变得直觉化。

---

## 理论内容概述（3讲 × 2学时 = 6学时）

| 讲次 | 主题 | 核心问题 | 关键概念 |
|------|------|----------|----------|
| 讲1 | GPU架构深度解析 | GPU为什么比CPU快1000倍？ | SM / Warp / Tensor Core / HBM / SRAM / MFU / MBU |
| 讲2 | 存储与互联系统 | 数据搬运的代价是什么？ | NVLink / NVSwitch / InfiniBand / RoCE / 带宽层次 |
| 讲3 | 模型架构对Infra的影响 | 选什么模型，买什么卡？ | Dense vs MoE / GQA / MLA / 算力-带宽需求分析 |

### 讲1：GPU架构深度解析

- **SM（Streaming Multiprocessor）**：GPU的基本计算单元，H100共132个SM
- **Warp**：32个线程的调度单元，SIMT执行模型
- **Tensor Core**：矩阵专用计算单元，FP16 GEMM加速4-8倍
- **内存层次**：Register → L1/Shared SRAM → L2 → HBM
- **MFU（Model FLOP Utilization）**：实际FLOP利用率，衡量计算效率
- **MBU（Memory Bandwidth Utilization）**：内存带宽利用率，衡量搬运效率
- **A100 vs H100**：SXM5架构演进，Transformer Engine，FP8支持

### 讲2：存储与互联系统

- **GPU内存层次带宽**：L1~SRAM(19TB/s) → L2(4TB/s) → HBM(3.35TB/s) → PCIe(64GB/s)
- **节点内互联**：NVLink 4.0（900GB/s双向）vs PCIe 5.0（128GB/s）
- **NVSwitch**：全互联交换芯片，DGX H100全连接带宽 3.6TB/s
- **节点间互联**：InfiniBand HDR/NDR（400Gbps） vs RoCE v2
- **带宽与延迟的权衡**：RDMA、GPUDirect、collective通信原语

### 讲3：模型架构对Infra的影响

- **Dense vs MoE**：全参数激活 vs 稀疏激活，显存和计算特性完全不同
- **Transformer各层分析**：Attention（memory-bound, small batch） → FFN（compute-bound, large batch）
- **GQA（Grouped Query Attention）**：减少KV head数量，显著降低KV Cache带宽压力
- **MLA（Multi-head Latent Attention）**：DeepSeek创新，KV压缩+低秩分解
- **架构-硬件适配**：70B Dense → 8×A100；671B MoE → 16×H100+高带宽互联

---

## 实验：GPU性能分析实战（2学时）

### 实验目标

| 目标 | 技能 | 工具 |
|------|------|------|
| 分析推理热点 | 找到真实瓶颈op | PyTorch Profiler |
| 计算算术强度 | 理解compute/memory比值 | 手动计算 + Python |
| 定位Roofline位置 | 判断优化空间 | Matplotlib可视化 |

### 环境要求

```
Python >= 3.9
PyTorch >= 2.0
CUDA >= 11.8（可选，无GPU时CPU模拟）
matplotlib >= 3.5
jupyter >= 1.0
```

> 无GPU环境：notebook提供CPU fallback，所有计算逻辑均可运行，仅性能数字用模拟值替代。

### 预期输出

1. **Profiler火焰图** - 看到哪个op占用了最多时间
2. **算术强度表格** - Linear / Attention / FFN 三种算子的AI值对比
3. **Roofline图** - 标注典型操作点，直观判断compute-bound vs memory-bound

---

## 核心直觉类比

| 技术概念 | 生活类比 | 一句话解释 |
|----------|----------|------------|
| GPU的SM | 工厂的流水线 | H100有132条流水线同时运转，每条独立处理一批工件 |
| Warp调度 | 餐厅同桌点餐 | 32人同桌必须点同一道菜，一人"换菜"全桌等待 |
| Tensor Core | 专职速算员 | 只会做矩阵乘法，但做得极快，是通用乘法器的16倍 |
| SRAM vs HBM | 草稿纸 vs 书架 | 草稿纸（SRAM）很快但很小，书架（HBM）很大但要走几步才能取 |
| NVLink vs PCIe | 高速公路 vs 普通公路 | GPU间对话走NVLink（900GB/s），走PCIe（64GB/s）就像堵车 |
| 算术强度 | 每次出门办多少事 | 取一次数据能算多少次？取一次就算一次=浪费带宽 |
| Roofline模型 | 员工绩效图 | 横轴是每次出门办的事（AI），纵轴是总完成量，屋顶是上限 |
| MFU | 工厂产能利用率 | GPT-3训练MFU约45%，即峰值算力的45%被有效利用 |
| MoE专家路由 | 咨询公司分配专家 | 每个问题只派最合适的2位专家，而非全员上阵 |
| GQA | 多人共用一份笔记 | 8个Query head共享1个KV head，减少8倍KV Cache显存 |

---

## 推荐阅读

### NVIDIA官方文档

| 文档 | 说明 |
|------|------|
| [H100 Tensor Core GPU Architecture](https://resources.nvidia.com/en-us-tensor-core) | H100白皮书，SM架构、Transformer Engine、NVLink 4.0详细规格 |
| [CUDA C Programming Guide - Memory Hierarchy](https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#memory-hierarchy) | CUDA内存模型官方指南 |
| [DGX H100 System Architecture](https://resources.nvidia.com/en-us-dgx-systems/nvidia-dgx-h100-system-architecture-white-paper) | 节点内NVSwitch全互联拓扑 |
| [NVLink and NVSwitch](https://www.nvidia.com/en-us/data-center/nvlink/) | NVLink/NVSwitch技术规格 |

### 核心论文

| 论文 | 关键贡献 | 为什么读 |
|------|----------|----------|
| **Roofline: An Insightful Visual Performance Model** (Williams et al., 2009) | 提出Roofline模型 | 本模块核心工具，必读 |
| **FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness** (Dao et al., 2022) | IO感知算法设计 | 理解带宽优化的最佳案例 |
| **DeepSeek-V2: A Strong, Economical, and Efficient Mixture-of-Experts Language Model** (DeepSeek, 2024) | MLA + MoE架构 | 模块3（MoE/MLA）的直接对象 |
| **Efficiently Scaling Transformer Inference** (Pope et al., 2022) | 推理时的算力/带宽分析框架 | 将Roofline应用于LLM推理 |

### 扩展阅读

- Horace He, *Making Deep Learning Go Brrrr From First Principles* (blog, 2022)
- Tim Dettmers, *The Case for 4-bit Precision* (blog, 2022)  
- Lilian Weng, *Large Transformer Model Inference Optimization* (blog, 2023)
