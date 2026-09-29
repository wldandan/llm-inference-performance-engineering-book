# 模块二：KV Cache 深度解析与优化

**学时**：10学时（5讲 × 2学时）  
**定位**：LLM推理最核心的内存瓶颈，从原理到系统全链路

---

## 本模块教什么

**核心问题**：为什么大模型服务一台 A100（80GB）只能同时处理几十个请求？内存都去哪了？

| 讲次 | 主题 | 核心问题 | 关键结论 |
|------|------|---------|---------|
| 讲1 | KV Cache基础与内存分析 | KV Cache是什么，占多少内存？ | 序列越长、Batch越大，内存消耗呈线性增长 |
| 讲2 | PagedAttention | 为什么vLLM把GPU利用率从40%提到75%？ | 虚拟页→物理块，消除内存碎片 |
| 讲3 | Prefix Caching与Radix Attention | System Prompt重复计算，能省掉吗？ | 前缀匹配复用，SGLang核心技术 |
| 讲4 | KV Cache压缩与稀疏化 | KV Cache本身能压缩吗？ | 量化+稀疏，最多压缩10x |
| 讲5 | KV Cache分层存储与卸载 | GPU装不下时怎么办？ | HBM→DRAM→NVMe三层架构 |

---

## 核心直觉（类比总结）

| 技术 | 类比 | 本质 |
|------|------|------|
| KV Cache | 做题时的草稿纸——写过的就不重新算 | 空间换时间，避免重复计算 |
| 内存碎片 | 停车场里零散空位但大车进不去 | 逻辑连续但物理不连续 |
| PagedAttention | 虚拟内存分页——操作系统的经典方案 | 按需分配，消除碎片 |
| Prefix Caching | 老师批改同一份试卷开头的固定部分 | 公共前缀只算一次 |
| KV Cache量化 | 草稿纸上用缩写代替全称 | 精度降低换空间 |
| KV Cache卸载 | 把不常用的书从桌面移到书架 | 慢存储换容量 |

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `module02_overview.ipynb` | Jupyter Notebook：可运行代码 + 内嵌AI提示词 |
| `module02_notebooklm_slide_prompt.md` | Google NotebookLM 生成Slide提示词 |
| `module02_slides.html` | 可翻页 HTML 演示文稿 |

---

## 推荐阅读

**必读论文**
1. PagedAttention/vLLM (Kwon et al., SOSP 2023) — 本模块核心
2. RadixAttention/SGLang (Zheng et al., 2024) — Prefix Caching
3. H2O (Zhang et al., 2023) — KV Cache稀疏化
4. SnapKV (Li et al., 2024) — KV Cache压缩
5. Mooncake (Qin et al., 2024) — 分布式KV Cache
