# 模块二：分布式训练

## 模块定位

**为什么训练基础设施是 AI Infra 的核心？**

GPT-3（175B 参数）在单张 A100（80GB）上无法存放——仅模型权重就需要 350GB（FP16）。训练一次 GPT-3 需要 3.14×10²³ FLOP，单卡 A100 峰值 312 TFLOPS，理论上需要跑 **32,000 年**。现实中，OpenAI 用了约 1,000 张 A100 跑了 34 天。

从单卡到千卡集群，中间每一层技术决策——数据如何切分、模型如何切割、显存如何节省、通信如何隐藏——都直接决定训练效率和成本。这就是分布式训练基础设施的价值所在。

本模块系统讲授从 DDP 到 Megatron-LM 的完整技术栈，使学员能够：
1. 理解并评估各类并行策略的适用场景
2. 诊断和优化大规模训练的显存与通信瓶颈
3. 在实际项目中选型并配置分布式训练框架

---

## 内容概览

| 讲次 | 主题 | 核心技术 | 学时 |
|------|------|----------|------|
| 讲1 | 数据并行与梯度同步 | DDP Ring-AllReduce / ZeRO-1/2/3 / 通信计算重叠 | 2学时 |
| 讲2 | 模型并行：TP 与 PP | Tensor Parallelism / Pipeline Parallelism / 3D并行 | 2学时 |
| 讲3 | 训练内存优化 | 混合精度BF16 / 梯度检查点 / Flash Attention / ZeRO-3 | 2学时 |
| 讲4 | 大规模训练工程实践 | Checkpoint策略 / Loss Spike诊断 / Megatron vs DeepSpeed | 2学时 |
| 实验 | 分布式训练对比实验 | 单卡 / DDP / FSDP(ZeRO-2) 吞吐量与显存对比 | 2学时 |

**总计：10学时（8学时理论 + 2学时实验）**

---

## 实验说明

### 实验目标

跑 GPT-2 风格模型，量化对比三种训练配置的性能指标：

| 指标 | 说明 |
|------|------|
| 吞吐量 (tokens/s) | 每秒处理的 token 数，越高越好 |
| 显存峰值 (GB) | 训练过程中 GPU 显存最大占用 |
| 每步耗时 (ms) | 单个 batch 的前向+反向+更新时间 |
| 通信开销占比 (%) | 通信时间 / 总时间，越低说明通信隐藏越好 |

### 环境要求

**理想配置（推荐）：**
- 2张 GPU（任意 VRAM ≥ 8GB，如 RTX 3080 / A10）
- CUDA 11.8+ / PyTorch 2.1+
- 支持 NCCL 通信后端

**最低配置（单卡模拟）：**
- 1张 GPU（VRAM ≥ 6GB）
- DDP 部分用单机多进程模拟
- FSDP 以单卡模式展示概念

**无 GPU（CPU 模式）：**
- 自动缩小规模：batch_size=2, seq_len=64, 4层模型
- 可完成所有实验并观察相对差异

### 预期输出

运行 `module02_lab.ipynb` 后，你将得到：
1. 对比柱状图：各配置吞吐量（tokens/s）
2. 对比柱状图：各配置显存峰值（GB）
3. Trade-off 散点图：吞吐量 vs 显存
4. 关键数字（参考值，实际因硬件不同）：
   - BF16 vs FP32：速度提升 ~1.5–2x，显存节省 ~40%
   - 梯度检查点：显存节省 ~30–40%，速度损失 ~20%
   - FSDP ZeRO-2：多卡时显存减半，吞吐量接近 DDP

---

## 核心直觉类比

理解分布式训练最好先建立直觉，然后再看公式。

| 技术 | 类比 | 直觉解释 |
|------|------|----------|
| **DDP（数据并行）** | 工厂多条生产线 | 每条生产线（GPU）独立处理一批零件（数据），最后把各线的质检报告（梯度）汇总求平均，所有线同步更新工艺参数（权重） |
| **Ring-AllReduce** | 圆桌传菜 | N个人围坐一圈，每人把自己的菜往右传、接左边的菜，经过 2(N-1) 轮，每人桌上都有所有人的菜——通信量与人数成正比而非平方 |
| **ZeRO 分片** | 团队共用工具柜 | ZeRO-1：各人用自己的优化器，但共享工具柜；ZeRO-2：连梯度也分摊存放；ZeRO-3：连模型参数也拆分，用时临时借阅 |
| **Tensor Parallelism** | 矩阵乘法分工 | 一个大型矩阵乘法，把矩阵"竖着切"分给两个人算，各算各的列，最后拼合结果——两人同时工作，速度翻倍 |
| **Pipeline Parallelism** | 汽车装配流水线 | 4个工段（GPU）串行：底盘→车身→内饰→涂装，每个工段独立工作。但换批次时会有空档（气泡），优化目标是减少空档率 |
| **混合精度 BF16** | 草稿用粗笔，定稿用细笔 | 前向/反向用 BF16（粗笔，省纸省时间），梯度累加用 FP32（细笔，保精度），最终权重更新用 FP32 |
| **梯度检查点** | 边走边扔掉路标，迷路了重走 | 不保存所有中间激活值（省内存），反向传播时重新计算需要的激活值（多花约33%时间），典型的以时间换空间 |

---

## 关键公式速查

```
# Pipeline 气泡率
bubble_rate = (p - 1) / (m + p - 1)
# p = 流水线阶段数, m = micro-batch 数
# p=4, m=8 时: (4-1)/(8+4-1) = 3/11 ≈ 27.3%

# ZeRO 显存节省（Ψ = 参数量，单位 亿）
ZeRO-1: 优化器状态分片, 节省 4Ψ bytes (每GPU)
ZeRO-2: +梯度分片,       节省 8Ψ bytes (每GPU)
ZeRO-3: +参数分片,       节省 16Ψ bytes (每GPU)

# AllReduce 通信量（Ring）
数据量 = 2 × (N-1)/N × 参数量 ≈ 2 × 参数量（N大时）
```

---

## 推荐阅读

### 论文（必读）

| 论文 | 重点 | 链接 |
|------|------|------|
| ZeRO: Memory Optimizations Toward Training Trillion Parameter Models | ZeRO-1/2/3 核心思想 | [arXiv 1910.02054](https://arxiv.org/abs/1910.02054) |
| Megatron-LM: Training Multi-Billion Parameter Language Models | Tensor & Pipeline 并行 | [arXiv 1909.08053](https://arxiv.org/abs/1909.08053) |
| Efficient Large Scale Language Modeling with Mixtures of Experts | 3D并行实践 | [arXiv 2006.16668](https://arxiv.org/abs/2006.16668) |
| FlashAttention: Fast and Memory-Efficient Exact Attention | Flash Attention 训练加速 | [arXiv 2205.14135](https://arxiv.org/abs/2205.14135) |
| GPipe: Efficient Training of Giant Neural Networks | Pipeline 并行原理 | [arXiv 1811.06965](https://arxiv.org/abs/1811.06965) |

### 博客/文档（推荐）

- [Hugging Face: Model Parallelism](https://huggingface.co/docs/transformers/perf_train_gpu_many) - 工程实践视角
- [DeepSpeed ZeRO Tutorial](https://www.deepspeed.ai/tutorials/zero/) - 官方配置指南
- [PyTorch FSDP Tutorial](https://pytorch.org/tutorials/intermediate/FSDP_tutorial.html) - FSDP 完整用法
- [Lilian Weng: Large Language Model Training](https://lilianweng.github.io/posts/2023-01-10-inference-optimization/) - 系统综述

---

## 文件结构

```
02_分布式训练/
├── README.md                              # 本文件：模块导引
├── module02_slides.html                   # 演讲幻灯片（24页，暗黑主题）
├── module02_lab.ipynb                     # 实验 Notebook（可运行）
└── module02_notebooklm_slide_prompt.md   # NotebookLM 提示词
```
