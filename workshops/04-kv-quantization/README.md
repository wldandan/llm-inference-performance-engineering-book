# Workshop 04：KV Cache Quantization

对应 `workshops/README.md` 里的样板四。完整讲义/学习目标见那里；本文件只给能直接跑的命令。

**验证过的 flag**（2026-09，来自 vLLM 官方 `docs.vllm.ai/en/stable/configuration/engine_args/`）：`--kv-cache-dtype`，可选 `auto` / `fp8` 等，默认 `auto`（跟随模型原始 dtype）。这是**有损**优化，必须跑 `quality_check.py`，不能只看性能数字。

## 环境

单机单卡。默认模型 `Qwen/Qwen2.5-7B-Instruct`，可用 `MODEL=...` 环境变量覆盖。`requests.jsonl` 里是 4 条较长的输入（模拟事故复盘、会议纪要总结这类企业场景），配合较高并发把 KV Cache 显存压力压出来。

## Step 1-2：起 baseline 服务，制造瓶颈

终端 1：

```bash
bash serve_baseline.sh
```

终端 2（等服务起来、`curl http://127.0.0.1:8000/v1/models` 有响应之后）：

```bash
bash bench_baseline.sh
python3 quality_check.py --model "${MODEL:-Qwen/Qwen2.5-7B-Instruct}" --label baseline --output baseline_quality.txt
```

`bench_baseline.sh` 默认 64 个请求、并发 16（可用 `CONCURRENCY=` / `REQUESTS=` 覆盖），跑完写出 `baseline.json`。如果这一步在你的显卡上没有观察到显存压力/OOM，调大 `CONCURRENCY` 或者把 `serve_baseline.sh` 里的 `--max-model-len` 调大，直到出现瓶颈。

## Step 3-4：切到优化配置，重跑

终端 1：先 `Ctrl+C` 停掉 baseline 服务，再起优化版：

```bash
bash serve_optimized.sh
```

终端 2：

```bash
bash bench_optimized.sh
python3 quality_check.py --model "${MODEL:-Qwen/Qwen2.5-7B-Instruct}" --label optimized --output optimized_quality.txt
```

## Step 5：对比

```bash
python3 ../common/compare.py baseline.json optimized.json
diff baseline_quality.txt optimized_quality.txt
```

`compare.py` 输出吞吐/延迟的百分比变化；`diff` 是质量检查——如果 `optimized_quality.txt` 的答案（尤其是那道乘法题）开始出现明显错误或前后不一致，说明这次量化在你测的模型/精度组合上代价过高，不该无脑用。

## 单元测试

```bash
(cd ../common && python3 -m unittest test_bench_client.py test_compare.py)
python3 -m unittest test_quality_check.py
```
