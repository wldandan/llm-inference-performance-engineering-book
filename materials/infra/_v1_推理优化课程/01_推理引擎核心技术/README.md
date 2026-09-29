# 模块一：推理引擎核心技术

**学时**：12学时（6讲 × 2学时）  
**定位**：建立LLM推理的完整心智模型

---

## 本模块教什么

本模块回答一个问题：**ChatGPT回复你一条消息，GPU里发生了什么？为什么有时候快，有时候慢？**

从六个角度系统拆解：

| 讲次 | 主题 | 核心问题 | 关键结论 |
|------|------|---------|---------|
| 讲1 | LLM推理全流程 | Prefill和Decode有什么本质区别？ | Decode是Memory-Bound，是主要瓶颈 |
| 讲2 | 注意力机制演进 | 为什么要从MHA改到GQA、MLA？ | KV Cache内存压力 → 减少KV头数 |
| 讲3 | 量化技术全栈 | FP16压缩到INT4，损失了什么？ | 4x模型压缩，质量损失可控（AWQ最优）|
| 讲4 | 投机采样 | 为什么不需要更多计算就能更快？ | 验证比生成便宜，小模型草稿大模型验证 |
| 讲5 | 批处理策略 | Continuous Batching为什么能提升GPU利用率？ | 动态插入新请求，消除GPU等待 |
| 讲6 | 算子融合 | 减少什么让GPU更快？ | 减少HBM读写次数，不是增加算力 |

---

## 核心直觉（直觉类比总结）

| 技术 | 类比 | 本质 |
|------|------|------|
| Prefill/Decode | 读题 vs 写答案 | 并行 vs 串行 |
| Memory Bandwidth瓶颈 | 法拉利跟自行车队 | 算力闲置，等数据 |
| Flash Attention | 不写黑板，用草稿纸 | 减少HBM I/O |
| GQA/MLA | 共享笔记而非人人复制 | KV头共享 |
| 量化 | 评分用整数代替小数 | 精度换速度/空间 |
| 投机采样 | 小助手猜答案，老师批改 | 验证远比生成便宜 |
| Continuous Batching | 现代快餐，吃完就让位 | 消除GPU空转 |
| 算子融合 | 合并购物清单 | 减少GPU HBM往返 |

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `module01_overview.ipynb` | Jupyter Notebook：可运行代码 + 内嵌AI提示词 |
| `module01_notebooklm_prompts.md` | Google NotebookLM 专用提示词集 |

---

## 两种提示词的使用方式

### ① Jupyter Notebook 内嵌提示词
**文件**：`module01_overview.ipynb`  
**用法**：在 Notebook 中找到标有 `🤖 AI扩展提示词` 的 Markdown 单元格，复制提示词粘贴给 Claude / ChatGPT，获取该讲的深度技术扩展内容（含代码实现）。

每讲包含：
- 💡 **直觉类比** — 用生活场景讲清楚技术直觉
- 📐 **核心概念** — 数学/工程原理说明
- 📊 **可运行演示** — Python + matplotlib 可视化
- 🤖 **AI扩展提示词** — 用于向 Claude/ChatGPT 深挖技术细节

```bash
# 运行环境
pip install matplotlib numpy jupyter
pip install vllm torch transformers  # 可选，用于真实实验
```

### ② Google NotebookLM 提示词
**文件**：`module01_notebooklm_prompts.md`  
**用法**：
1. 将对应论文（FlashAttention、PagedAttention、AWQ、EAGLE-2 等）上传到 [NotebookLM](https://notebooklm.google.com)
2. 也可上传本模块 Notebook 的 PDF 导出版作为背景资料
3. 将提示词粘贴到 NotebookLM 对话框，基于上传资料获得定制化解读

NotebookLM 提示词覆盖范围：

| 分类 | 提示词数量 | 内容 |
|------|-----------|------|
| 讲1：推理全流程 | 2个 | 两阶段本质 + Roofline深挖 |
| 讲2：注意力机制 | 2个 | MHA→MLA演进 + Flash Attention原理 |
| 讲3：量化技术 | 2个 | 方案选型 + 实践指南 |
| 讲4：投机采样 | 2个 | 原理推导 + EAGLE-2解析 |
| 讲5：批处理策略 | 2个 | Continuous Batching + Chunked Prefill |
| 讲6：算子融合 | 2个 | Kernel Fusion原理 + Triton入门 |
| 综合 | 4个 | 性能决策树、选型指南、面试题、教学案例 |
| 论文阅读 | 2个 | 快速理解 + 深度解读通用模板 |

---

## 推荐阅读顺序

```
必读论文 → 课程Notebook → AI扩展提示词深挖 → 框架源码
```

**必读论文（按优先级）**
1. FlashAttention-2 (Dao, 2023) — Flash Attention原理
2. PagedAttention (Kwon et al., SOSP 2023) — vLLM基础
3. Speculative Decoding (Leviathan et al., ICML 2023) — 投机采样
4. EAGLE-2 (Li et al., 2024) — 最新投机采样
5. AWQ (Lin et al., 2023) — 量化最佳实践
