# 附录 B CUDA、Kernel 与 Nsight

> 状态：占位，正文未写。本文件只登记正文已经做过的承诺，以及写作时必须回答的问题。
> 引用它的位置：第 18.5 节（Kernel 级分析）、第 30.5 节（Nsight 与自定义算子）、Part 4 开篇（“不写 kernel，那在附录”）。

## 这份附录要回答什么

1. 一个 Kernel 从提交到执行经过哪几步，`cudaLaunchKernel`、Stream、Event 分别在哪一步。
2. Nsight Systems 与 Nsight Compute 各自回答哪一类问题，什么时候用哪一个，什么时候两个都不用。
3. 一条 Decode step 的 Timeline 长什么样：哪些是 kernel，哪些是空隙，空隙来自 launch 还是来自 CPU 侧准备。
4. 怎样读一份 Nsight Compute 报告里的 Memory Throughput、Compute Throughput 和 Occupancy，以及为什么 Occupancy 高不等于快。
5. 自定义算子要满足什么条件才值得写，以及怎样在不改框架的前提下先验证它有没有收益。

## 与正文的接口

- 第 9 章给出的是“先问问题再挑工具”的选择流程，附录 B 只补 Nsight 这一支的操作细节，不重复那条流程。
- 第 18 章讲 CUDA Graph 时只用到“每步固定提交开销”这一个结论，推导和实测方法放在这里。
- 附录 A 的“Kernel Launch Overhead”一节给的是量级和判据，附录 B 给的是怎么在 Timeline 上把它看出来。

## 写作边界

- 不教 CUDA 编程语法。读者要写 kernel 时应去看 NVIDIA 的官方文档，这里只讲性能分析。
- 不给任何具体显卡的 kernel 耗时数字，除非它来自本书自己采集的报告并写明机型与日期。
