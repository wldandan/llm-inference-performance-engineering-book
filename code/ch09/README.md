# Chapter 9 Demo：建立问题到工具的对照

`profiling_planner.py` 不采集任何数据。它帮你在花几小时采集之前想清楚三件事：手上这个现象该用哪一层的工具、需要什么前置证据、预期开销多大。

只依赖 Python 标准库，不需要 GPU。

## 1. 运行

```bash
python3 code/ch09/profiling_planner.py \
  --symptom "TTFT 高但 Queue 正常" \
  --evidence-have request_metrics \
  --output plan-ttft.json
```

`--evidence-have` 可以给多个，取值范围：`request_metrics`、`trace`、`logs`、`cpu_profile`、`engine_trace`、`kernel_profile`。

## 2. 计划七块

```text
symptom          现象描述
already_known    已有哪些证据，它们排除了什么
next_layer       建议采集的下一层
rationale        为什么是这一层，上一层为什么不够
expected_cost    预期开销与对系统的影响
window           建议的采集窗口与触发方式
must_record      这次采集必须记录的元数据
```

## 3. 两类警告

**跳级。** 请求级证据还没看就要抓 kernel，脚本会把 `next_layer` 拉回 `request` 并给出警告。上一层能解释清楚的现象不需要下一层的数据，而请求级几乎不花钱。

**目标不清。** 现象描述里既没有量值也没有指明哪一段，比如只写了“服务慢”。这种描述任何一层都答不了，要先按 10.1 补上量值、范围、时间和对照。

## 4. expected_cost 里的判据

`comparable_to_baseline` 回答“开着这一层的采集测出来的数字，能不能直接和未采集的 Baseline 比”，`comparison_rule` 说不能时该怎么办：

```text
请求级          yes                    开销可以忽略，直接比
采样 profiler   same_conditions_only   改前改后都开着同样的采样，或先测出开销再扣掉
框架 trace      same_conditions_only   延迟数字只在两边条件相同时可比，调度结论仍可用
kernel profiler never                  另一个系统，任何延迟数字都不要拿去比
```

**采集开销是每一轮都有的固定偏差，不是随机波动。** 它多跑几轮平均不掉，所以不拿它和第 7.3 节的可识别线比大小（第 9.5 节）。

## 5. 这个 Demo 的用处

不在于输出多聪明，在于**它强迫你在花几小时采集之前，先把“我要回答什么问题”写下来**。第 10 章的根因报告会直接用到这份计划里的 `expected_cost` 和 `must_record`。

## 6. 测试

```bash
python3 -m unittest discover -s code/ch09 -p 'test_*.py'
```

15 项测试覆盖可证伪判定、跳级警告与它的解除条件、三类现象各自路由到哪一层、七块字段齐全、开销按偏差处理而不和可识别线比，以及四层的排序。
