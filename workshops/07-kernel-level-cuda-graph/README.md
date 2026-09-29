# Workshop 07：Kernel-Level Optimization（CUDA Graph）

对应 `workshops/README.md` 样板七。`requests.jsonl` 是短 prompt + 400 token 生成长度，刻意做成 Decode 密集型负载（Prefill 占比小），这样才能把 CUDA Graph 消除的 kernel launch 开销体现在 `itl_avg_ms`（约等于 TPOT）上。

**验证过的 flag**（2026-09，vLLM 官方文档）：`--enforce-eager`，默认 `False`。文档原文："If True, we will disable CUDA graph and always execute the model in eager mode."——所以 baseline 是显式加上这个 flag，optimized 是**不加**（用 vLLM 默认行为），和其他样板"baseline 不加 flag、optimized 加 flag"的方向刚好相反，写讲义时要提醒学员这一点，容易搞反。

## Step 1-2：baseline（`--enforce-eager`，CUDA Graph 关闭）

```bash
bash serve_baseline.sh        # 终端 1
bash bench_baseline.sh        # 终端 2
```

## Step 3-4：optimized（默认配置，CUDA Graph 开启）

```bash
bash serve_optimized.sh       # 终端 1，先 Ctrl+C 停掉 baseline
bash bench_optimized.sh       # 终端 2
```

## Step 5：对比

```bash
python3 ../common/compare.py baseline.json optimized.json --metrics itl_avg_ms itl_p95_ms tokens_per_second_sum
```

重点看 `itl_avg_ms`（等价于 TPOT）的下降幅度。如果想要更直接的证据而不只是端到端延迟，配合 Nsight Systems 抓一段 trace，对比两次运行里 GPU 执行间隙（CPU 在等着发起下一个 kernel）的占比——这是 `workshops/README.md` 样板七里提到的"独立证据"，本脚本本身不采集 Nsight 数据。

## 单元测试

```bash
(cd ../common && python3 -m unittest test_bench_client.py test_compare.py)
```
