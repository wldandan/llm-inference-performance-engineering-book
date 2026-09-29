# 课程 Demo 代码

所有章节 Demo 统一放在本目录中，并使用两位章节编号命名。课程侧的 Demo 映射与实验编排在 [Course 仓库](https://github.com/wldandan/llm-inference-performance-engineering-course) 中维护：

```text
code/
├── ch01/
├── ch02/
├── ...
└── ch30/
```

当前只为已有实现的章节创建目录。待建设章节先在下表登记，避免使用空目录冒充可交付代码。

## Demo 索引

| 章节 | 主题 | 代码 | 状态 |
|---|---|---|---|
| Ch01 | 第一个 LLM 服务 | [code/ch01](ch01/README.md) | 已在 GX10 实跑；待补录 vLLM 版本 |
| Ch02 | 真实请求生命周期 | [code/ch02](ch02/README.md) | 真实采集器与离线分析器已实现；待 GX10 生成真实证据报告 |
| Ch03 | Transformer 生成机制 | [code/ch03](ch03/README.md) | 已迁移并通过测试 |
| Ch04 | LLM Serving 架构 | [code/ch04](ch04/README.md) | 已迁移；支持单实例与 Scale-out profile |
| Ch05 | 性能指标与延迟预算 | [code/ch05](ch05/README.md) | 已迁移；包含 SLO-aware Goodput 与预算计算 |
| Ch06 | LLM 工作负载建模 | — | 待建设 |
| Ch07 | Benchmark Design | — | 待建设 |
| Ch08 | 请求级可观测性 | — | 待建设 |
| Ch09 | Profiling Toolchain | — | 待建设 |
| Ch10 | Root Cause Analysis Lab | — | 待建设 |
| Ch11 | Prefill 工作机制与性能模型 | — | 待建设 |
| Ch12 | 长上下文与 RAG 上下文成本 | — | 待建设 |
| Ch13 | Prefill 优化方法 | — | 待建设 |
| Ch14 | Prefill 优化实验 | — | 待建设 |
| Ch15 | Decode 工作机制与性能模型 | — | 待建设 |
| Ch16 | KV Cache 管理与容量 | — | 待建设 |
| Ch17 | 量化与内存优化 | — | 待建设 |
| Ch18 | 生成与 Runtime 优化 | — | 待建设 |
| Ch19 | Decode 优化实验 | — | 待建设 |
| Ch20 | Scheduler 与 Continuous Batching | — | 待建设 |
| Ch21 | 流量治理与可靠性 | — | 待建设 |
| Ch22 | Serving 架构选择与模型路由 | — | 待建设 |
| Ch23 | RAG 性能工程 | — | 待建设 |
| Ch24 | Agent 性能工程 | — | 待建设 |
| Ch25 | Serving 与 Agent 综合实验 | — | 待建设 |
| Ch26 | 容量、显存与成本模型 | — | 待建设 |
| Ch27 | 多副本、路由与 Autoscaling | — | 待建设 |
| Ch28 | 性能回归与发布门禁 | — | 待迁移旧生产工程素材 |
| Ch29 | Performance Review 与上线检查 | — | 待迁移旧生产工程素材 |
| Ch30 | End-to-End Performance Engineering Project | — | 待建设 |

## 使用约定

- 从 Git 仓库根目录运行时，路径统一写成 `code/chapterNN/...`。
- 每个已实现目录必须有独立 `README.md`，说明环境、命令、输出和边界。
- 单元测试与对应实现放在同一个章节目录，测试不依赖当前工作目录。
- Workshop 继续保留在 `content/workshops/`，不与章节 Demo 混放。
- 新增或迁移 Demo 时，同时更新本索引和 `strategy/course-design/30章-Demo映射-v0.2.md`。

运行当前所有章节 Demo 单元测试：

```bash
for chapter in code/chapter*; do
  python3 -m unittest discover -s "$chapter" -p 'test_*.py'
done
```
