# 图 3-5 制作说明：Prefill

- 来源段落：第 3 章“3.6 Prefill：一次处理整段 Prompt”。
- 阅读顺序：从 S Prompt Tokens 进入完整序列前向计算；向右得到首个输出 token，向下写入 KV Cache。
- 关键结论：Prefill 写入完整 Prompt 的 K/V，并为首个输出 token 产生 Logits。
- 边界：不讨论 TTFT、计算瓶颈或 Prefill 优化。
