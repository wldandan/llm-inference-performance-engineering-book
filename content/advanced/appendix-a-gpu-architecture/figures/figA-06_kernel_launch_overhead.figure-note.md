# 图 A-6 制作说明：Kernel Launch Overhead

- 来源段落：附录 A“A.6 Kernel Launch Overhead”。
- 阅读顺序：先看上方长 Kernel，再看下方短 Kernel Timeline 中橙色 Gap 的相对占比。
- 关键结论：Kernel 越短、数量越多，固定提交与调度开销越值得检查。
- 边界：不展开 CUDA Graph、Kernel Fusion 或 Runtime 调优步骤。
