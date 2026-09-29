# 图 3-7 制作说明：Decode 与 KV Cache

- 来源段落：第 3 章“3.8 Decode：一次消费一个新 token”。
- 阅读顺序：从 Prefill 完成状态进入 Decode 主线；Sampling 得到的 token 沿下方虚线返回下一轮输入。
- 关键结论：普通 Decode 每步复用历史 K/V，只为当前 token 追加一份新状态。
- 边界：不讨论 PagedAttention、KV Cache 量化或 Decode 性能瓶颈。
