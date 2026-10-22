# Chapter 6 Demo：把负载写成一份可复现的描述

`workload_builder.py` 做两件事：把第 6 章那四组字段组装成一份 workload 描述文件，并检查这份描述是否自洽。

**它只描述负载，不发送请求，也不产生任何性能数字。** workload 描述是实验的输入，Benchmark 结果是实验的输出，两者不能混在同一个“报告”里。真正把请求发出去是第 7 章的事。检查器会主动拒绝带有 `results`、`ttft_ms`、`goodput` 这类字段的描述。

只依赖 Python 标准库，不需要 GPU。

## 1. 生成一份描述

从仓库根目录运行：

```bash
python3 code/ch06/workload_builder.py \
  --profile chat \
  --arrival poisson \
  --rate 10 \
  --duration 60 \
  --output workload-chat.json
```

闭环写法（注意它给的是并发数，不是速率）：

```bash
python3 code/ch06/workload_builder.py \
  --profile chat --arrival closed --concurrency 32 --duration 60 \
  --output workload-chat-closed.json
```

## 2. 四组字段

```text
identity     负载名称、类型（chat / rag / agent）、数据来源
length       prompt 与 output 各自的 P50 / P90 / P99 / max
arrival      模式、速率或并发数、持续时间、随机种子
slo          指标、分位数、阈值
```

`identity.type` 为 `agent` 时还要有 `steps`，含四个分位数和 `mean`。

内置的长度分位数只是起点，**必须换成你自己的数**。第 6.2 节说过，最可靠的来源是线上日志的 `usage` 字段；没有线上数据时用真实业务样本跑一遍 tokenizer，不要拍一个平均值。

## 3. 检查器拒绝什么

```bash
python3 code/ch06/workload_builder.py --validate workload-chat.json
```

它会拒绝这几类不自洽的描述：

- 长度分位数不单调（P50 大于 P90）；
- 到达模式是开环（`constant` / `poisson` / `burst` / `ramp`）却没给速率；
- 到达模式是 `closed` 却没给并发数，或者同时给了速率（闭环下速率是结果不是输入）；
- SLO 只给了阈值没给分位数；
- 类型是 `agent` 却没有步数分布；
- 缺随机种子；
- 描述里混进了性能数字。

## 4. Little's Law

`expected_concurrency(doc, mean_latency_s)` 实现 6.4 那条关系，用来判断压测配置是否自洽。它拒绝对闭环描述使用，因为闭环下并发是输入不是结果。

实测在途数远超预期时，不是这条式子失效了，是平均时长被排队拉长了：在途 55 条、到达率 10 req/s，反推平均时长就是 5.5 秒。

## 5. 测试

```bash
python3 -m unittest discover -s code/ch06 -p 'test_*.py'
```

17 项测试覆盖四组字段的生成、agent 步数分布、闭环与开环的差别、检查器的全部拒绝条件、Little's Law 的两种读法，以及命令行的生成与校验两条路径。
