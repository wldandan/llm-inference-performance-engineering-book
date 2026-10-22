# Chapter 5 Demo：性能指标与延迟预算报告

这个 Demo 读取一组 JSONL 请求记录，计算客户端口径的：

- TTFT、E2E、TPOT 和 ITL 分布；
- 运行窗口提交速率、成功请求率、成功/已观测输出速率，以及满足质量、TTFT 和 E2E SLO 的 Goodput；
- 每百万输出 token 成本、每个成功请求成本，以及每个 good request 成本（分母与 Goodput 同一套条件）。
- 从 TTFT/E2E SLO 反推的阶段延迟预算，以及整条请求共用的那一份未分配余量。

余量输出成三个字段：`unallocated_total_ms`、`unallocated_before_first_token_ms` 和 `unallocated_after_first_token_ms`。前者等于后两者之和，**六项已分配阶段加上 `unallocated_total_ms` 正好等于 E2E SLO**。报告里没有并列的“TTFT 余量”和“E2E 余量”字段，因为把它们当成两行相加会得出超过 SLO 的总额。`unmeasured_segments` 列出预算里没有对应事件对的那些段，当前只有 `first_token -> first_chunk_received` 一条。

失败、超时或取消的记录可以保留已经观察到的部分输出。报告分别列出成功请求 token、失败请求部分 token 和全部已观察 token，并使用完整字段名区分成功输出速率与已观测输出速率。

从 Git 仓库根目录运行：

```bash
python3 code/ch05/metrics_report.py
```

保存报告：

```bash
python3 code/ch05/metrics_report.py \
  code/ch05/sample.jsonl \
  --output metrics-report.json
```

输入中的 `token_times_ms` 是客户端观察到的 token 时间点。真实流式接口有时按 chunk 返回，不能把 chunk 时间直接冒充严格 token 时间；接入真实服务时，应先固定 tokenizer 计数、流式聚合和时钟口径。

每条输入必须提供 `quality_pass`、质量指标、分数、阈值、评估器名称和版本。脚本会复核布尔标签是否与分数和阈值一致，并拒绝在同一报告中混用不同质量合同。报告固定使用 nearest-rank 分位数，记录共享墙钟窗口、成本分母和质量门槛。样例是合成数据，只用于验证公式与预算合同，不是 Benchmark。

## 测试

```bash
python3 -m unittest discover -s code/ch05 -p 'test_*.py'
```
