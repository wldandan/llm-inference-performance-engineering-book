# 进阶附录

正文把 CUDA、多 GPU、MoE 和 PD 分离这四类内容移到这里，为的是让核心三十章不依赖 GPU 编程和分布式通信背景。正文引用附录时，一律只引用它的标题和小节标题，不引用小节编号，因此附录内部的编号可以独立调整。

附录的编号与体例：文件名 `appendix-<字母>-<主题>.md`，标题写成 `# 附录 X 标题`，小节编号 `X.1`、`X.2`，图号 `图X-N`，配图目录与附录同级。附录不使用“第 N 章”“本章”这类措辞，用“附录”和“本附录”。

## 当前状态

| 附录 | 主题 | 文件 | Demo | 状态 |
|---|---|---|---|---|
| 附录 A | GPU 性能心智模型 | [appendix-a-gpu-architecture/appendix-a.md](appendix-a-gpu-architecture/appendix-a.md) | `code/advanced/gpu-architecture` | 已完成，11 节 8 图 |
| 附录 B | CUDA、Kernel 与 Nsight | [appendix-b-cuda-kernel/appendix-b.md](appendix-b-cuda-kernel/appendix-b.md) | — | 只有占位，未写 |
| 附录 C | 多 GPU 与分布式推理 | [appendix-c-multi-gpu/appendix-c.md](appendix-c-multi-gpu/appendix-c.md) | — | 只有占位，未写 |
| 附录 D | MoE 模型的显存与计算 | [appendix-d-moe/appendix-d.md](appendix-d-moe/appendix-d.md) | — | 只有占位，未写 |
| 附录 E | PD 分离架构 | [appendix-e-pd-disaggregation/appendix-e.md](appendix-e-pd-disaggregation/appendix-e.md) | — | 只有占位，未写 |

未写的四个附录已经被正文引用。每个占位文件写清了引用它的具体位置、它必须回答的问题，以及正文对它做过的承诺，这样写的时候不必回头重新检索，读者点进来也不会以为自己找错了地方。

## 正文对附录的引用

| 引用位置 | 引用的是 | 承诺的内容 |
|---|---|---|
| 第 5.6 节 | 附录 A | 容量、带宽、算力、提交开销四类约束 |
| 第 11.4 节 | 附录 A | 分界点怎么从硬件规格算出来，Roofline 推导 |
| 第 15.2 节 | 附录 A | Roofline 与 Ridge Point 的完整推导，有效值的取法 |
| 第 16.2 节 | 附录 A | KV Cache 按层数头数位宽展开的算式，为什么必须留余量 |
| 第 17.2 节 | 附录 A | 实际有效带宽怎么从 Profiling 数据里读出来 |
| 第 20.7 节 | 附录 A | 四条硬件分支怎么当诊断起点 |
| Part 3 开篇 | 附录 A | 算术强度的完整推导与 Roofline |
| 第 30.5 节 | 附录 B | Nsight 与自定义算子 |
| Part 4 开篇 | 附录 B | 不写 kernel 的那部分内容 |
| 第 27.3 节、Part 6 开篇、第 30.5 节 | 附录 C | 多卡并行的实现细节，张量并行扩展效率的实测方法 |
| 第 0.2 节、第 30.5 节 | 附录 D | MoE 的总参数与激活参数怎样脱钩，显存按哪个算 |
| 第 13.5 节、第 30.5 节 | 附录 E | Prefill 与 Decode 独立资源池；第 13.5 节给了定义，第 30 章的扩展验收暂不要求这一项 |
