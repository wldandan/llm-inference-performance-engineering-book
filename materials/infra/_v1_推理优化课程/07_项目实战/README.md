# 模块七：项目实战

## 模块概述

| 项目 | 内容 |
|------|------|
| 学时 | 6学时（3讲 × 2学时） |
| 前置模块 | 模块一至六全部内容 |
| 核心目标 | 综合运用课程全部知识，独立完成推理优化全流程项目，培养工程化思维 |

---

## 教学内容

| 讲次 | 主题 | 核心任务 | 学时 |
|------|------|---------|------|
| 第1讲 | 实战一：推理性能基准建立 | 选定Qwen2.5-7B，建立完整benchmark，Profile分析瓶颈，提出优化假设并验证ROI | 2学时 |
| 第2讲 | 实战二：生产推理服务搭建 | 基于vLLM/SGLang实现，启用Prefix Caching，量化对比实验，PD分离验证 | 2学时 |
| 第3讲 | 实战三：项目路演与答辩 | 展示优化全流程：问题定义→根因分析→方案实施→效果量化，答辩评审 | 2学时 |

---

## 核心直觉类比

| 概念 | 直觉类比 | 说明 |
|------|---------|------|
| 性能基准建立 | 新员工入职体能测试 | 摸清底数才能制定提升计划 |
| Profile分析 | X光/CT精准定位 | 不靠猜测，用工具精准找到瓶颈所在 |
| 优化假设 | 医生开处方 | 基于诊断提出治疗方案，而非随机尝试 |
| ROI验证 | 用药效果追踪 | 每个优化都要量化效果，计算投入产出比 |
| Prefix Caching | 试卷填写已知题目答案 | 重复前缀直接复用，节省大量计算 |
| 量化对比 | 减重效果测量 | 量化前后精确对比，不靠感觉 |
| 项目路演 | 临床病例汇报 | 结构化展示：问题→诊断→治疗→疗效 |

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `README.md` | 本文件，模块概述与教学设计 |
| `module07_notebooklm_slide_prompt.md` | NotebookLM生成幻灯片的提示词 |
| `module07_slides.html` | 可翻页暗黑主题HTML演示文稿 |

---

## 项目评分标准

| 评分维度 | 权重 | 评分要点 |
|---------|------|---------|
| 问题定义 | 20% | 指标选取合理、基线完整 |
| 根因分析 | 25% | Profile工具使用正确、瓶颈定位准确 |
| 方案实施 | 30% | 至少2种优化方案实施 |
| 效果量化 | 15% | 数据完整、对比公平 |
| 工程质量 | 10% | 代码规范、实验可复现 |

---

## 推荐阅读

- [vLLM Examples & Notebooks](https://github.com/vllm-project/vllm/tree/main/examples)
- [SGLang Tutorial](https://sgl-project.github.io/tutorials)
- [Qwen2.5 Model Card](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)
- [LLM Benchmarking Best Practices](https://huggingface.co/blog/open-llm-leaderboard)
- [MLCommons MLPerf Inference](https://mlcommons.org/benchmarks/inference-datacenter/)
