# Chapter 14 Demo：优化实验报告

`prefill_experiment.py` 把一次对照实验组织成结构化报告，并检查这份报告**是否具备被推翻的可能**。

需要真实 vLLM 服务采集数据。报告构建器和检查器不需要服务，可以直接拿仓库里那份合成样例跑一遍。

## 1. 检查一份报告

```bash
python3 code/ch14/prefill_experiment.py \
  --report content/ch14/evidence/prefill-experiment-sample.json \
  --model-config code/ch11/model-qwen25-05b.json
```

`prefill-experiment-sample.json` 是 14.4 那四轮的完整版。**它是合成数据，不是真机结果**，`synthetic` 字段和 `_note` 里都写明了。它证明的是这套结构能走通、成品长什么样，不能当作任何真实系统的结论。

## 2. 报告七块

```text
expectation   实验前写下的预期：方向、幅度、不变项、无效判据，加写入时间
fixed         本次固定的 workload、protocol、environment 三组
changed       本次唯一改动项及其取值
results       主指标名，Baseline 与 variant 各轮原始数据
guardrails    护栏指标的变化
verdict       与预期对照的结论
boundary      模型、负载、硬件、配置四项边界
```

`boundary.model` 由 `--model-config` 自动填，内容包含**交叉点**。这样 14.6 那条“报告要带上交叉点”的要求就不靠人记：别人拿到报告能自己判断能不能套用，不需要重跑一遍才发现结论不适用。

## 3. verdict 有四种，第四种最重要

```text
符合预期
低于预期
高于预期
在波动内不可分辨        ← 刻意保留
```

第四种不是失败，是一个准确的描述。检查器会拒绝一份既标了“在波动内不可分辨”、又在别处写着“有小幅提升”的报告，因为那是在用噪声支撑结论。

判据用的是**可识别线（t × √(2/n) × 变异系数，三轮对三轮约 2.3 倍）**，不是极差，直接复用第 7 章 `run_baseline.py` 的 `line_factor`。同一条线用两次（14.5）：先看改善有没有越过它，越过了再看“改善 − 预期”有没有越过它，线内为符合，线外按符号判低于或高于。中心值用均值，标准差按样本口径（除以 n−1），报告里也写明。

## 4. 检查器拒绝什么

- `expectation` 缺 `written_at`（事后补写的预期不被接受）；
- `expectation.magnitude` 里某一项没写 `basis`（**幅度的每个数都要有出处，不能是感觉**）；
- 缺 `null_criterion`（少了它这次实验就没有被推翻的可能）；
- `changed` 出现两项或以上（同时改两项，结果好了也不知道是谁的功劳）；
- `protocol.temperature` 不为 0；
- `protocol.prefix_cache` 不是 `off` 或 `on-and-recorded`（不能一次开一次关）；
- `protocol` 缺 `percentile_algorithm` 或 `stdev_convention`（两轮用不同算法，两个数字只是长得像）；
- `environment` 缺 `model_revision` / `framework_version` / `gpu` / `driver`；
- 任一轮少于三轮数据；
- `guardrails` 为空（只报主指标是不诚实的）；
- `boundary` 缺模型、负载、硬件、配置里的任何一项；
- `verdict` 标了“在波动内不可分辨”却又写着“小幅有效”“略有改善”。

## 5. 样例里四轮各演示一种结论

这不是凑巧，是刻意安排的：

```text
第 1 轮  Top-K 10 → 6            TTFT P50 改善 33.2%，预期 33.3%    符合预期
第 2 轮  启用 Prefix Cache        TTFT P50 改善 15.7%，预期 8%       高于预期
第 3 轮  确认 Attention 实现      变化 −0.4%，可识别线 2.5%          在波动内不可分辨
第 4 轮  启用 Chunked Prefill     短请求 ITL 改善 29.9%，预期 50%    低于预期
```

三个细节值得注意：

**第 1 轮预期的 33.3% 有出处。** `basis` 里写的是“2630 → 1830 token，按第 11 章模型 S×(16640+S) 算得 33.3%”，可以用 `code/ch11/prefill_model.py` 复算。主指标是 TTFT P50，因为这笔账算的是 P50 那条请求；负载率约 0.3，排队只占小头（14.1）。

**第 2 轮高于预期，原因在预期的依据。** 预期按四成命中率算，单副本加全体共享的 system prompt 实际命中了 0.82（13.3 的路由项接近 1）。护栏里并发从 40 掉到 36，TTFT 降了但并发掉了，这是一次交换而不是纯收益，报告必须两个都写。

**第 4 轮的主指标是短请求的 ITL，不是长请求的 TTFT**，而长请求 TTFT 变差 19% 记在护栏里。这一轮如果把主指标写成 TTFT，结论会反。

## 6. 测试

```bash
python3 -m unittest discover -s code/ch14 -p 'test_*.py'
```

40 项测试。大部分是拒绝测试，因为这份报告的价值在于它拒绝接受什么：每一条拒绝都对应一种实验悄悄失去结论能力的方式。另有一组针对样例文件本身：四轮的改动项、三轮共用同一个 Baseline、workload 与 protocol 逐字相同、四种结论都出现过、第 4 轮的主指标不是 TTFT。

样例是合成的。在真实服务上跑完四轮后，用真实报告替换它，检查器的规则不变。
