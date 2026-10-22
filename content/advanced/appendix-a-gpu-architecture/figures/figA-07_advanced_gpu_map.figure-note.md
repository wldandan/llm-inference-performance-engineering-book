# 图 A-7 制作说明：进阶硬件地图

- 来源段落：附录 A“A.8 再往下一层”。
- 阅读顺序：从 GPU 进入一个 SM，再沿 Warp Scheduler、Active Warps 和执行单元读取；底部是片上资源与 Occupancy。
- 关键结论：做服务调优只需知道这些指标回答什么，Kernel 级分析时再深入。
- 边界：不进入 CUDA 代码、Bank Conflict 或指令流水线细节。
