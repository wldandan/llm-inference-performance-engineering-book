# 图 3-3 制作说明：Causal Self-Attention

- 来源段落：第 3 章“3.4 Causal Self-Attention”。
- 阅读顺序：X 分流成 Q/K/V；Q 与 K 计算权重，权重与 V 在输出节点汇合。
- 关键结论：Causal Attention 只汇总当前位置允许访问的历史信息。
- 边界：不出现 FlashAttention、Kernel Fusion 或性能数据。
