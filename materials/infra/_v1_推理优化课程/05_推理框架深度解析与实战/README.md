# 模块五：推理框架深度解析与实战

**学时**：4学时（2讲 × 2学时）  
**定位**：深入理解主流推理框架的内部架构，掌握框架选型依据

---

## 本模块教什么

本模块回答一个问题：**同样是推理框架，vLLM、SGLang、TensorRT-LLM、LMDeploy各有什么不同？什么场景用哪个？**

从两个主流框架深度拆解：

| 讲次 | 主题 | 核心框架 | 关键结论 |
|------|------|---------|---------|
| 讲1 | vLLM深度解析 | vLLM | LLMEngine/Scheduler/Worker三层架构 + PagedAttention + Continuous Batching |
| 讲2 | SGLang深度解析 | SGLang + 框架选型 | RadixAttention + FlashInfer + Overlap调度 + 四框架选型矩阵 |

---

## 核心直觉（直觉类比总结）

| 技术/框架 | 类比 | 核心特性 |
|----------|------|---------|
| vLLM | 精密机器的各个零件 | PagedAttention + Continuous Batching，工业级稳定 |
| SGLang | vLLM的更聪明版本 | RadixAttention前缀树 + FlashInfer高性能Kernel |
| TensorRT-LLM | 专为NVIDIA调教的赛车 | NVIDIA硬件极致优化，部署复杂 |
| LMDeploy | 轻量级快速部署工具 | 简单易用，适合中小规模 |

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `module05_notebooklm_slide_prompt.md` | Google NotebookLM 专用幻灯片生成提示词 |
| `module05_slides.html` | 可翻页暗黑主题 HTML 演示文稿（约16页） |

---

## 框架选型速查

```
推理框架选型决策树：
├── 需要极致 NVIDIA 性能？
│   └── TensorRT-LLM（H100最佳选择，但部署复杂）
├── 需要 Prefix Cache 最优？
│   └── SGLang（RadixAttention命中率更高）
├── 需要生态最广/最稳定？
│   └── vLLM（社区最活跃，插件最多）
├── 需要快速验证/中小规模？
│   └── LMDeploy（配置简单，上手快）
└── Apple Silicon / 边缘端？
    └── llama.cpp / MLX（见模块三讲5）
```

---

## 推荐阅读顺序

```
vLLM源码 → SGLang论文 → 框架Benchmark对比 → 生产部署实践
```

**必读资料（按优先级）**
1. vLLM 论文 (Kwon et al., SOSP 2023) — PagedAttention 基础
2. SGLang 论文 (Zheng et al., NeurIPS 2024) — RadixAttention + 结构化输出
3. FlashInfer 论文 (2024) — GPU Kernel 加速
4. vLLM GitHub (github.com/vllm-project/vllm) — 源码架构
5. SGLang GitHub (github.com/sgl-project/sglang) — 源码架构
6. TensorRT-LLM 官方文档 — NVIDIA 专项优化
