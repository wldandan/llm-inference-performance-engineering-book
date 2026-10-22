# Chapter 7 Demo：跑一次可复现的 Baseline

`run_baseline.py` 读入第 6 章生成的 workload 描述，按描述发送请求，输出一份四块齐全的 Baseline 报告。

**这个 Demo 需要一个真实的 vLLM 服务在 GPU 上运行。** 单元测试用一个假的 transport 替代服务，因此不需要 GPU，但它测的是报告契约，不是性能。

## 1. 运行

```bash
python3 code/ch07/run_baseline.py \
  --workload workload-chat.json \
  --base-url http://127.0.0.1:8000/v1 \
  --warmup 20 \
  --runs 3 \
  --requests-per-run 200 \
  --prefix-cache off \
  --vllm-version 0.9.1 \
  --model-revision a1b2c3d \
  --gpu-name "NVIDIA GB10" \
  --driver-version 550.54.15 \
  --launch-command "vllm serve ... --max-num-seqs 64" \
  --output baseline-chat.json
```

环境指纹那五个参数和 `--prefix-cache` 不是可选的。**缺任何一项脚本直接退出，不生成报告。** 这不是苛刻：一份没有环境的 Baseline 半年后没人能用。

## 2. 工作顺序

1. 读 workload 描述，调用第 6 章的检查器校验它自洽；
2. 采集环境指纹，缺项报错退出；
3. 发送 Warmup 请求，不计入统计；
4. 由 workload 的种子生成请求序列：长度，以及开环模式的计划发送时刻（泊松间隔取指数分布）；
5. 按计划时刻并发发送，延迟从计划时刻起算（协调遗漏的修正，第 6.3 节）；闭环模式固定在途条数，延迟从实际发送时刻起算；
6. 等待在途请求全部返回并计入（`drained`）；
7. 每轮重放同一串请求，prompt 文本按轮次和序号加前缀、互不为前缀（第 7.5 节），共 N 轮后输出报告。

突发（`burst`）和阶梯（`ramp`）两种到达模式没有实现，脚本直接拒绝。

## 3. 报告四块

```text
workload     第 6 章那份描述（含随机种子），原样嵌入
protocol     Warmup 数量与是否排除、轮次、每轮请求数、到达模式、延迟起点、
             Prefix Cache 状态、窗口两端事件、在途处理、分位数算法、标准差口径
environment  Python / vLLM 版本、模型名与 revision、GPU、驱动、完整启动命令
results      每轮原始记录 + 跨轮统计（均值、极差、CV、可识别线及其算法）
```

两处口径写在 `protocol` 里，不留给读者猜：分位数用 nearest-rank（和第 5 章一致），标准差用样本口径（除以 n−1）。第 7.3 节解释了为什么这两项必须写明。

## 4. 它拒绝什么

- workload 描述不自洽；
- 环境指纹缺项；
- 轮次少于三轮（一轮只是分布里的一个采样点）。

## 5. 怎么读这份报告

先看 `results.ttft_p95_ms.detectable_difference`，也就是可识别线，算法是 `t × √(2/n) × CV`（三轮对三轮约 2.3 × CV），写在 `detectable_difference_rule` 里。后面任何优化的收益如果小于它，只能写“在波动内不可分辨”。线超过 20% 时 `verdict` 会标成 `too noisy`，这时先回 7.3 找波动源，不要用这份 Baseline 去比较。`warnings` 非空说明每轮请求太少，单轮 P95 本身就不稳。

每条原始记录都有 `send_lag_ms`，是实际发送比计划晚了多少。它普遍偏大，说明发压端跟不上计划，先加大 `--max-in-flight` 或换一台发压机。

## 6. 测试

```bash
python3 -m unittest discover -s code/ch07 -p 'test_*.py'
```

25 项测试覆盖 nearest-rank 与第 5 章一致、可识别线系数（3 轮 2.27、12 轮 0.85）、7.3 与 7.8 案例一的数字、泊松计划时刻的指数间隔与可复现、开环并发发送、闭环在途上限、延迟从计划时刻起算、prompt 互不为前缀、每轮重放同一串长度、环境指纹与 Prefix Cache 状态的缺项拒绝、报告四块齐全、原始记录保留、尾部样本不足的警告，以及三轮下限。
