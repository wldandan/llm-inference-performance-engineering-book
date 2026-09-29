# Workshop 08：投机解码（n-gram / prompt-lookup）

对应 `workshops/README.md` 样板八。用 n-gram（prompt-lookup）方法而不是 EAGLE/Medusa，因为它不需要单独的 draft 模型 checkpoint，最容易实际搭起来。

**验证过的 flag**（2026-09，vLLM 官方文档 + 《Hands-On LLM Serving and Optimization》配套 `ch07/SpecDecode.ipynb` 交叉核对过参数量级）：

```
--speculative-config '{"method": "ngram", "num_speculative_tokens": 4, "prompt_lookup_min": 2, "prompt_lookup_max": 5}'
```

两组 prompt：`requests_predictable.jsonl`（代码补全、JSON 重排、校对、CSV 转表格——这类任务输出会大量复用输入里已经出现过的文本，是 n-gram 方法真正能受益的场景）和 `requests_creative.jsonl`（开放式创意写作，几乎不会复用输入文本）。

## Step 1-2：baseline

```bash
bash serve_baseline.sh        # 终端 1
LABEL=baseline_predictable REQUESTS_FILE=requests_predictable.jsonl bash bench.sh   # 终端 2
LABEL=baseline_creative REQUESTS_FILE=requests_creative.jsonl bash bench.sh
```

## Step 3-4：开启投机解码

```bash
bash serve_optimized.sh       # 终端 1，先 Ctrl+C 停掉 baseline
LABEL=optimized_predictable REQUESTS_FILE=requests_predictable.jsonl bash bench.sh   # 终端 2
LABEL=optimized_creative REQUESTS_FILE=requests_creative.jsonl bash bench.sh
```

## Step 5：对比

```bash
python3 ../common/compare.py baseline_predictable.json optimized_predictable.json --metrics itl_avg_ms tokens_per_second_sum
python3 ../common/compare.py baseline_creative.json optimized_creative.json --metrics itl_avg_ms tokens_per_second_sum
```

预期：`predictable` 组的 `itl_avg_ms`（约等于 TPOT）明显下降；`creative` 组几乎不变甚至可能因为验证开销略微变差。如果两组差异不明显，先确认 vLLM 日志/metrics 里有没有暴露接受率（acceptance rate）相关字段——不同版本暴露方式不一样，这个脚本本身没有单独采集接受率，只看端到端 TPOT。

## 单元测试

```bash
(cd ../common && python3 -m unittest test_bench_client.py test_compare.py)
```
