# Workshop 05：Prefix Cache（单节点前缀复用）

对应 `workshops/README.md` 样板五。`requests.jsonl` 里 5 条请求共享同一段约 700 字符的 system context（模拟企业内部客服场景的固定提示词），只有最后的用户问题不同——这是能触发前缀复用的最小可信设计。

**验证过的 flag**（2026-09，vLLM 官方文档）：`--enable-prefix-caching` / `--no-enable-prefix-caching`。不同版本的默认值可能不一样，所以 baseline 显式传 `--no-enable-prefix-caching`，不依赖默认值。
当前公开 CLI 参考：[vLLM Serve CLI](https://docs.vllm.ai/en/latest/cli/serve/)。

## 一条命令跑完完整实验

```bash
bash run_experiment.sh
```

该入口会依次启动 baseline、运行固定 workload、停止服务、启动 optimized、
重跑同一 workload，最后生成对比表。每次结果写入独立时间戳目录
`results/<UTC run id>/`，不覆盖上一次实验。

先检查计划，不启动模型：

```bash
bash run_experiment.sh --dry-run
```

## Step 1-2：baseline（关闭前缀复用）

```bash
bash serve_baseline.sh        # 终端 1
bash bench_baseline.sh        # 终端 2，服务起来之后再跑
```

预期现象：每个请求的 TTFT 都要为完整的 ~700 字符 system context 重新做 Prefill，即使 5 个请求的前缀完全相同。

## Step 3-4：开启前缀复用，重跑

```bash
bash serve_optimized.sh       # 终端 1，先 Ctrl+C 停掉 baseline
bash bench_optimized.sh       # 终端 2
```

## Step 5：对比

```bash
python3 ../common/compare.py baseline.json optimized.json --metrics ttft_avg_ms ttft_p95_ms output_throughput_tokens_per_second
```

看 `ttft_avg_ms` 的下降幅度。如果几乎没有变化，先确认：(1) baseline 服务是不是真的传了 `--no-enable-prefix-caching`（用 `curl http://127.0.0.1:8000/v1/models` 之外没法直接确认配置，建议看服务启动日志里打印的 engine args）；(2) `CONCURRENCY` 是不是设得太高，把前缀命中的收益淹没在排队时间里——先用默认的 `CONCURRENCY=4` 跑通，再自己加压。

## 单元测试

```bash
(cd ../common && python3 -m unittest test_bench_client.py test_compare.py test_convert_sharegpt.py)
python3 -m unittest test_run_experiment.py
```

## 已知限制

- 需要 NVIDIA GPU、可用的 `vllm` CLI 和能下载模型的环境。
- Prefix Cache 改善的主要是共享前缀的 Prefill/TTFT，不保证输出 TPS 一定提升。
- 默认并发为 4。高并发下的排队时间可能淹没缓存命中收益，应先用默认值建立 baseline。
- 本实验的 engine batch size 是动态的，报告中保留为 `null`；`client_concurrency=4`
  不等于 batch size。
