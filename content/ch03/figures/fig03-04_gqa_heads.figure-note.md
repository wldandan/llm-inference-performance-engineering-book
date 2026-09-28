# 图 3-4 制作说明：MHA 与 GQA

- 来源段落：第 3 章“3.5 GQA：为什么 K/V 的头数比 Query 少”。
- 阅读顺序：先看上方 MHA 的 Head 对应，再看下方 GQA 的两组共享关系。
- 关键结论：GQA 减少的是 K/V Heads，不是 Query Heads。
- 边界：不写显存节省比例或性能收益。
