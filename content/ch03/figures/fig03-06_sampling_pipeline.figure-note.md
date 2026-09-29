# 图 3-6 制作说明：Sampling

- 来源段落：第 3 章“3.7 Sampling：从 Logits 选择 token”。
- 阅读顺序：从 Vocabulary Logits 依次经过 Temperature、Softmax、候选过滤和选择策略。
- 关键结论：Logits 只是分数，解码策略决定最终选择哪个 token。
- 边界：不讨论回答质量评测或 Sampling 的性能开销。
