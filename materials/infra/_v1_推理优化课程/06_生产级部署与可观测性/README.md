# 模块六：生产级部署与可观测性

## 模块概述

| 项目 | 内容 |
|------|------|
| 学时 | 4学时（2讲 × 2学时） |
| 前置模块 | 模块五：推理框架深度解析与实战 |
| 核心目标 | 掌握AI推理服务的性能基准测试方法论与生产级部署运维体系 |

---

## 教学内容

| 讲次 | 主题 | 核心知识点 | 学时 |
|------|------|-----------|------|
| 第1讲 | 性能基准测试与分析方法论 | benchmark_serving工具、TTFT/TBT/QPS指标体系、Nsight Profile工具链、性能回归检测 | 2学时 |
| 第2讲 | 生产级部署与运维 | Docker/K8s容器化部署、DCGM GPU监控、Prometheus+Grafana可观测性栈、OOM排查、滚动升级、成本核算 | 2学时 |

---

## 核心直觉类比

| 概念 | 直觉类比 | 说明 |
|------|---------|------|
| 性能基准测试 | 体检报告全项检查 | 不能只看某一项指标，需要全面评估TTFT/TBT/QPS/P99延迟的综合状态 |
| TTFT（首Token延迟） | 医生接诊等待时间 | 衡量服务响应速度，决定用户第一印象 |
| TBT（Token间隔时间） | 输液滴速 | 决定流式输出的流畅度体验 |
| QPS（每秒请求数） | 医院日门诊量 | 系统吞吐量上限，决定服务规模 |
| 生产级部署 | 医院ICU监控系统 | 7×24小时实时监控、告警、自动恢复 |
| Prometheus+Grafana | ICU多参数监护仪 | 多维度指标采集、实时可视化、阈值报警 |
| GPU OOM | 手术室突然停电 | 需要提前预防、快速恢复，不允许业务中断 |
| 滚动升级 | 医院不停诊换设备 | 零停机升级，保证服务连续性 |

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `README.md` | 本文件，模块概述与教学设计 |
| `module06_notebooklm_slide_prompt.md` | NotebookLM生成幻灯片的提示词 |
| `module06_slides.html` | 可翻页暗黑主题HTML演示文稿 |

---

## 推荐阅读

- [vLLM Benchmarking Guide](https://docs.vllm.ai/en/latest/performance/benchmarks.html)
- [NVIDIA Nsight Systems User Guide](https://docs.nvidia.com/nsight-systems/)
- [DCGM Metrics Reference](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-user-guide/feature-overview.html)
- [Prometheus + Grafana for GPU Monitoring](https://github.com/NVIDIA/dcgm-exporter)
- [Kubernetes for ML Serving Best Practices](https://kubernetes.io/docs/concepts/workloads/)
- [MLOps: Continuous Delivery for Machine Learning](https://mlops.community/)
