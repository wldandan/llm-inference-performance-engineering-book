# 图 3-2 制作说明：Decoder-only Transformer Block

- 来源段落：第 3 章“3.3 Decoder-only Transformer Block”。
- 阅读顺序：沿主线从 Input x 到两组 RMSNorm、子层和 Residual Add。
- 关键结论：一个 Block 用两次“归一化—子层—残差”逐步更新 hidden state。
- 边界：不比较不同 Block、激活函数或 Kernel 的性能。
