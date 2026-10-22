# 图 3-1 制作说明：从文本到下一个 token

- 来源段落：第 3 章“3.1 从文本到下一个 token”。
- 阅读顺序：从 Text 向右经过 Tokenizer、模型计算和 Sampling 到 Next Token。
- 关键结论：模型先计算词表分数，Sampling 才决定下一个 token。
- 边界：不出现 Serving 组件、GPU 指标或优化技术。
