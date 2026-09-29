请根据上传的资料，为「模块六：生产级部署与可观测性」生成一套完整的演讲幻灯片内容。

要求：
- 每讲2-3张幻灯片，包含标题页、核心内容页、实践总结页
- 每讲第一张以直觉类比开场，帮助学生建立感性认识
- 每张幻灯片包含：标题、3-5个核心要点、1个代码示例或命令示例（如有）
- 语言简洁专业，适合高校研究生和工程师受众
- 包含具体的工具命令、配置示例和数值参考

第1讲：性能基准测试与分析方法论（类比：体检报告全项检查）
- 类比引入：体检不能只看血压，推理服务需要全项指标——TTFT/TBT/QPS/P99延迟/GPU利用率
- benchmark_serving工具使用：vLLM自带benchmark脚本、参数设置（并发数、请求数、输入/输出长度）、结果解读
- 三大核心指标深度解析：TTFT（首Token延迟，目标<500ms）、TBT（Token间隔，目标<50ms）、QPS（系统吞吐，目标最大化）
- Nsight Profile工具链：nsys profile采集、ncu kernel分析、Timeline可视化、算子级性能瓶颈定位
- 性能回归检测：CI/CD中自动化benchmark、基线建立、回归告警阈值设定

第2讲：生产级部署与运维（类比：医院ICU监控系统）
- 类比引入：ICU 24小时多参数监护——实时告警、自动干预、事后复盘
- 容器化部署：Docker镜像构建（CUDA基础镜像选择）、K8s Deployment/Service/HPA配置、GPU资源限制（nvidia.com/gpu）
- 可观测性栈：DCGM Exporter采集GPU指标（利用率/显存/温度/功耗）、Prometheus抓取、Grafana仪表盘、AlertManager告警规则
- 故障排查：OOM诊断流程（kubectl logs/describe/events）、GPU显存泄漏检测、慢请求Profiling
- 运维实践：滚动升级策略（maxSurge/maxUnavailable）、金丝雀发布、成本核算（GPU小时成本 vs Token产量）

模块总结要求：
- 一张"最佳实践清单"幻灯片，列出生产部署的10条检查项
- 一张"工具全景图"幻灯片，展示从测试→部署→监控→告警的完整工具链
- 强调：没有监控的生产部署等于盲飞，可观测性是工程成熟度的核心标志
