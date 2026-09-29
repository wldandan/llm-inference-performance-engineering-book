# 统一课程材料索引：12模块

课程：《LLM 推理系统与性能工程实战》。30章教材是主干，`infra/`收纳原02的完整材料树。按下面的映射在同一目录继续建设，不另维护一份系统主课。

以下是文件级初步归属，不是逐章教学验收。**已有文件、代码可运行、真机证据齐备是不同状态。** 旧系统课件与Notebook本轮未预跑；新版模型压缩、引擎、分布式推理、前沿和路演目录只有占位规划。旧资料中的模拟和历史性能数字需重新核验。

| 模块 | 当前主题 | 主干教材与代码 | 系统补充/历史材料 | 后续缺口与边界 |
|---|---|---|---|---|
| 1 | 模型服务搭建与系统全景 | [Ch1–5导读](../content/part01.md)、[Ch1代码](../code/ch01/README.md)、[Ch4架构代码](../code/ch04/README.md) | [v1引擎课件](infra/_v1_推理优化课程/01_推理引擎核心技术/module01_slides.html)、[框架部署课件](infra/_v1_推理优化课程/05_推理框架深度解析与实战/module05_slides.html) | 补齐统一版本、部署记录和运行手册；API接入不替代部署 |
| 2 | 硬件执行栈与资源估算 | [GPU架构附录](../content/advanced/appendix-a-gpu-architecture/chapter05.md)、[已有附录代码](../code/advanced/gpu-architecture/README.md) | [硬件导引](infra/01_硬件基础与性能分析/README.md)、[硬件Notebook](infra/01_硬件基础与性能分析/module01_lab.ipynb) | 区分估算、模拟与硬件实测；整理执行栈和兼容性解释 |
| 3 | 请求指标与可信基线 | [请求与指标](../content/part01.md)、[测量篇](../content/part02.md)、[Ch2采集](../code/ch02/README.md)、[Ch5指标](../code/ch05/README.md) | [场景优化课件](infra/_v1_推理优化课程/03_不同场景下的性能优化策略/module03_slides.html) | Ch6–7实验代码待建设，保留开环/闭环、冷热、预热与重复条件 |
| 4 | 分层观测、Profiling与根因诊断 | [Ch8–10所在测量篇](../content/part02.md) | [硬件课件](infra/01_硬件基础与性能分析/module01_slides.html)、[生产观测课件](infra/_v1_推理优化课程/06_生产级部署与可观测性/module06_slides.html) | 后端/GPU采集需权限；诊断实验和证据包待建设 |
| 5 | Prefill与上下文优化 | [Ch11–14](../content/part03.md) | [v1引擎课件](infra/_v1_推理优化课程/01_推理引擎核心技术/module01_slides.html)、[KV课件](infra/_v1_推理优化课程/02_KV_Cache深度解析与优化/module02_slides.html) | 逐项验证长度、缓存和调度的收益，不能直接复用历史加速数字 |
| 6 | Decode、KV Cache与内存优化 | [Ch15–17所在Decode篇](../content/part04.md) | [KV课件](infra/_v1_推理优化课程/02_KV_Cache深度解析与优化/module02_slides.html) | 容量、访存、并发与质量的对照实验待建设 |
| 7 | 模型表示与运行时优化实验 | [Ch18–19所在Decode篇](../content/part04.md) | [模型压缩规划](infra/03_模型压缩与高效架构/README.md)仅占位、[v1框架课件](infra/_v1_推理优化课程/05_推理框架深度解析与实战/module05_slides.html) | 补精度/格式/引擎兼容记录、投机与编译对照；蒸馏剪枝深入实现为选修 |
| 8 | Serving调度、治理与路由 | [Ch20–22](../content/part05.md) | [v1引擎课件](infra/_v1_推理优化课程/01_推理引擎核心技术/module01_slides.html)、[生产课件](infra/_v1_推理优化课程/06_生产级部署与可观测性/module06_slides.html) | 补负载扫描、准入、取消、重试、背压及SLO验证 |
| 9 | RAG与Agent端到端性能 | [Ch23–25](../content/part05.md) | 不额外铺一套Agent架构课 | 保留正在写的原稿；后续补真实应用链路、任务质量与成本证据 |
| 10 | 分布式推理与扩展取舍 | [Ch26–27容量篇](../content/part06.md)、[Ch4架构代码](../code/ch04/README.md) | [v1分布式课件](infra/_v1_推理优化课程/04_分布式推理架构/module04_slides.html)、[新版分布式规划](infra/05_本地与分布式推理/README.md)仅占位 | 主干做副本/并行取舍；复杂多机、MoE、P/D按需进阶，不以训练实验替代推理实验 |
| 11 | 容量、成本与生产运行 | [Ch26–29](../content/part06.md) | [生产部署课件](infra/_v1_推理优化课程/06_生产级部署与可观测性/module06_slides.html) | 补版本、权限、健康检查、配额、恢复与容量成本实测 |
| 12 | 性能回归与综合工程交付 | [Ch28–29](../content/part06.md)、[Ch30](../content/part07.md) | [v1项目课件](infra/_v1_推理优化课程/07_项目实战/module07_slides.html)、[原路演规划](infra/结课_综合路演/README.md)仅占位 | 交付服务、运行手册、基线、优化与回归证据；API项目明确未完成的后端验证 |

## 选修与历史来源

- [训练系统独立选修](training-elective.md)：材料在同一仓库，训练不是推理主干前置。
- [原Infra材料入口](infra/README.md)：课件、Notebook、历史设计及其状态。
- [原v2课程设计](infra/课程设计_v2_2026-06-08.md)：仅作为材料来源，旧58学时不自动成为新课时。
- [参考书目录](../ref/)：结合现有来源映射选读；参考PDF不纳入公开Git分发。

## 已知材料问题

- v1推理引擎的 `infra/_v1_推理优化课程/01_推理引擎核心技术/module01_overview.ipynb` 在第254行附近存在JSON字符串转义错误，当前不能正常解析。迁移前后文件哈希一致，属于既有问题；本轮原样保留，需修复格式并重新验证后再纳入实验。
- 另外两个硬件/训练Notebook通过JSON结构检查，但未执行；不能据此认定依赖、计算结果和教学耗时已经验证。
- 原写作策略提到的 `content/scripts/validate_part.py` 当前不存在；未发现现成的站点构建配置，本轮不宣称完成整书构建。

## 本轮完成与未完成

已完成物理归并、统一入口、12模块的初步材料归属和旧地址兼容。原教材、代码和课件未改写，实验尚未因“放到一起”而完成适配或验收。

下一步逐模块细化要保留的段落、待补机制、代码起点、硬件条件和运行证据。只使用API时先做客户端/应用链路测量；完整服务部署与GPU诊断仍需后端环境。历史占位目录不标为可直接授课。

[返回课程入口](../README.md) · [现有代码状态](../code/README.md)
