# 本书 Demo 代码

所有章节 Demo 统一放在 Git 仓库根目录的本目录中，并使用两位章节编号命名：

```text
code/
├── ch01/
├── ch02/
├── ...
├── ch30/
└── advanced/
    └── gpu-architecture/
```

第 1 至 30 章和附录 A 的 Demo 都已实现，每个目录带独立 README 和单元测试。附录 B 至 E 还没有代码，在下表里登记为待建设，不用空目录冒充可交付代码。

Demo 之间有复用关系：第 12、23 章的 TTFT 估算调第 11 章的代价模型，第 19、25 章的实验检查器复用第 14 章的四种结论，第 30 章的接缝检查直接 import 第 29 章的 `release_check.py`。改上游时下游的测试会跟着红。

## Demo 索引

| 章节 | 主题 | 代码 | 状态 |
|---|---|---|---|
| Ch01 | 第一个 LLM 服务 | [code/ch01](ch01/README.md) | 已在两台真机实跑（NVIDIA GB10 与 RTX 3080 Ti），脱敏报告在 content/ch01/evidence，环境与版本见 content/reference/environment.md |
| Ch02 | 真实请求生命周期 | [code/ch02](ch02/README.md) | 真实采集器与离线分析器已实现；附离线合成报告 |
| Ch03 | Transformer 生成机制 | [code/ch03](ch03/README.md) | 已迁移并通过测试 |
| Ch04 | LLM Serving 架构 | [code/ch04](ch04/README.md) | 已迁移；支持单实例与 Scale-out profile |
| Ch05 | 性能指标与延迟预算 | [code/ch05](ch05/README.md) | 已迁移；包含 SLO-aware Goodput 与预算计算 |
| Ch06 | LLM 工作负载建模 | [code/ch06](ch06/README.md) | 已实现；负载描述与自洽检查器，纯标准库 |
| Ch07 | Benchmark Design | [code/ch07](ch07/README.md) | 已实现；Baseline 要在自己的服务上生成 |
| Ch08 | 请求级可观测性 | [code/ch08](ch08/README.md) | 已实现；含样例 trace |
| Ch09 | Profiling Toolchain | [code/ch09](ch09/README.md) | 已实现；采集计划生成器，纯标准库 |
| Ch10 | Root Cause Analysis Lab | [code/ch10](ch10/README.md) | 已实现；含合成数据的完整根因报告 |
| Ch11 | Prefill 工作机制与性能模型 | [code/ch11](ch11/README.md) | 已实现；含全书共享的模型配置 `model-qwen25-05b.json` |
| Ch12 | 长上下文与 RAG 上下文成本 | [code/ch12](ch12/README.md) | 已实现；复用 ch11 的估算函数 |
| Ch13 | Prefill 优化方法 | [code/ch13](ch13/README.md) | 已实现；消费 ch06 与 ch12 的输出 |
| Ch14 | Prefill 优化实验 | [code/ch14](ch14/README.md) | 已实现；含合成数据的四轮实验报告 |
| Ch15 | Decode 工作机制与性能模型 | [code/ch15](ch15/README.md) | 已实现；含 Part 4 共享的模型配置 `model-7b-generic.json` |
| Ch16 | KV Cache 管理与容量 | [code/ch16](ch16/README.md) | 已实现；16.6 那张容量表的代码版，`--overhead` 要按实测校准 |
| Ch17 | 量化与内存优化 | [code/ch17](ch17/README.md) | 已实现；估算与质量闸两个子命令，含合成质量评测样例 |
| Ch18 | 生成与 Runtime 优化 | [code/ch18](ch18/README.md) | 已实现；含合成接受率样例，接受率要按实测替换 |
| Ch19 | Decode 优化实验 | [code/ch19](ch19/README.md) | 已实现；含合成数据的五轮五维记分卡，复用 ch14 的检查纪律 |
| Ch20 | Scheduler 与 Continuous Batching | [code/ch20](ch20/README.md) | 已实现；含合成调度 trace，三个 onset 与 ρ/(1−ρ) 表由测试钉住 |
| Ch21 | 流量治理与可靠性 | [code/ch21](ch21/README.md) | 已实现；含有无准入的一对合成演练，重试放大器可从演练曲线上读 |
| Ch22 | Serving 架构选择与模型路由 | [code/ch22](ch22/README.md) | 已实现；架构判据按 22.2 的优先级排，路由评估复现案例二那组数 |
| Ch23 | RAG 性能工程 | [code/ch23](ch23/README.md) | 已实现；TTFT 重估直接复用 ch11 的代价模型 |
| Ch24 | Agent 性能工程 | [code/ch24](ch24/README.md) | 已实现；含十个任务的合成追踪与三种浪费模式检测 |
| Ch25 | Serving 与 Agent 综合实验 | [code/ch25](ch25/README.md) | 已实现；拆预算在不可行时报错，复用 ch14 的四种结论 |
| Ch26 | 容量、显存与成本模型 | [code/ch26](ch26/README.md) | 已实现；`whatif` 在杠杆不通时报 +0.0% 而不编一个降幅 |
| Ch27 | 多副本、路由与 Autoscaling | [code/ch27](ch27/README.md) | 已实现；含合成流量轨迹，未满足需求按突发和趋势分开算 |
| Ch28 | 性能回归与发布门禁 | [code/ch28](ch28/README.md) | 已实现；含一份“每项都更好”却被拦住的合成运行 |
| Ch29 | Performance Review 与上线检查 | [code/ch29](ch29/README.md) | 已实现；九项全绿而接缝对不上时仍然不通过 |
| Ch30 | 端到端性能工程项目 | [code/ch30/project](ch30/project/README.md) | 已实现；七个阶段的脚手架与总验收，接缝检查复用 ch29 |

进阶附录的 Demo 不按章节编号，单独列出：

| 附录 | 主题 | 代码 | 状态 |
|---|---|---|---|
| 附录 A | GPU 性能心智模型 | [code/advanced/gpu-architecture](advanced/gpu-architecture/README.md) | 已实现；GPU 约束预算器，纯标准库 |
| 附录 B | CUDA、NCCL 与通信 | — | 待建设 |
| 附录 C | 多 GPU 与分布式推理 | — | 待建设 |
| 附录 D | MoE 模型的显存与计算 | — | 待建设 |
| 附录 E | PD Disaggregation | — | 待建设 |

## 使用约定

- 从 Git 仓库根目录运行时，章节 Demo 的路径统一写成 `code/chNN/...`，附录 Demo 写成 `code/advanced/<主题>/...`。
- 每个已实现目录必须有独立 `README.md`，说明环境、命令、输出和边界。
- 单元测试与对应实现放在同一个章节目录，测试不依赖当前工作目录。
- 插图的生成器与测试跟着正文走，放在 `content/chNN/figures/`，不放在这里。
- 新增或迁移 Demo 时同时更新本索引；正文里引用的命令和数字，由该章的测试钉住。

在仓库根目录运行全部单元测试，共 64 个目录、66 个测试文件（30 章 Demo、附录 A 的 Demo、31 份插图生成器、附录 F 与术语表的检查）：

```bash
find code content -name 'test_*.py' -exec dirname {} \; | sort -u | while read -r dir; do
  (cd "$dir" && python3 -m unittest discover -p 'test_*.py' -q) || echo "FAILED: $dir"
done
```

逐个目录进去跑，是因为有些 Demo 按模块名 import 同目录的兄弟文件（例如 `import rag_trace`）。只对 `code/chNN` 做 discover 会漏掉两类：第 30 章的测试在 `code/ch30/project/` 下，而 `code/ch30` 这一档会静默地跑出 0 个用例；`content/` 下那 33 个目录（31 份插图生成器、附录 A 的 Demo、附录 F 与术语表的检查）则完全不在范围内。
