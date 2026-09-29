# 模块八：前沿专题

## 模块概述

| 项目 | 内容 |
|------|------|
| 学时 | 4学时（2讲 × 2学时） |
| 前置模块 | 模块一至七全部内容 |
| 核心目标 | 了解AI Infra前沿研究方向，掌握Reasoning模型的推理特殊挑战，展望2025-2026技术趋势 |

---

## 教学内容

| 讲次 | 主题 | 核心知识点 | 学时 |
|------|------|-----------|------|
| 第1讲 | Reasoning模型Infra挑战 | 长推理链KV爆炸、Thinking Token压缩、DeepSeek-R1推理优化、早停策略、动态分配 | 2学时 |
| 第2讲 | 下一代AI Infra趋势 | GB200 NVLink72、Groq LPU、华为Ascend、Flash Attention 3、Test-Time Compute Scaling、存算一体、2025-2026展望 | 2学时 |

---

## 核心直觉类比

| 概念 | 直觉类比 | 说明 |
|------|---------|------|
| Reasoning模型长推理链 | 解题过程越写越长的试卷 | CoT越详细越好，但纸（显存）是有限的，用完就写不下了 |
| KV Cache爆炸 | 草稿纸写满了装不下 | Thinking Token越多，KV Cache越大，显存压力指数级增长 |
| Thinking Token压缩 | 草稿纸精简版 | 保留关键步骤，去掉冗余推理，减少显存占用 |
| 早停策略 | 答案已经明确就别继续算 | 检测到推理收敛就停止，避免无效Token生成 |
| GB200 NVLink72 | 72核心协处理器直连 | 超大规模互联，训练/推理全新范式 |
| Groq LPU | 专为顺序推理优化的芯片 | 重新设计硬件架构匹配推理计算模式 |
| Test-Time Compute Scaling | 考试时多想想，答案更准 | 推理时计算越多，输出质量越高 |
| 存算一体 | 就在数据旁边计算，不搬运 | 消除冯·诺依曼瓶颈，彻底解决内存带宽问题 |

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `README.md` | 本文件，模块概述与教学设计 |
| `module08_notebooklm_slide_prompt.md` | NotebookLM生成幻灯片的提示词 |
| `module08_slides.html` | 可翻页暗黑主题HTML演示文稿 |

---

## 推荐阅读

**Reasoning模型**
- [DeepSeek-R1: Incentivizing Reasoning Capability in LLMs](https://arxiv.org/abs/2501.12948)
- [Scaling LLM Test-Time Compute Optimally](https://arxiv.org/abs/2408.03314)
- [Think More, Hallucinate Less](https://arxiv.org/abs/2501.05634)

**硬件前沿**
- [NVIDIA GB200 NVL72 Architecture](https://www.nvidia.com/en-us/data-center/gb200-nvl72/)
- [Groq LPU Architecture Overview](https://groq.com/technology/)
- [Flash Attention 3: Fast and Accurate Attention](https://arxiv.org/abs/2407.08608)

**系统架构**
- [Mooncake: A KVCache-centric Disaggregated Architecture](https://arxiv.org/abs/2407.00079)
- [存算一体综述 (Processing-in-Memory)](https://arxiv.org/abs/2106.08902)
