# Chapter 20 Demo：调度状态观测

`scheduler_watch.py` 把 20.7 那三个信号采下来，然后回答 20.6 和 20.7 各自留下的一个问题：饱和到排队之间有多少预警时间，以及当前是谁在限制。

三个子命令，只有第一个需要真实服务：

```text
collect      按固定间隔抓 /metrics，输出时间序列
analyze      从 trace 读出三个 onset、lead_time 和判断
queue-model  20.6 那张 ρ/(1−ρ) 表、波动修正、P99、多服务台对照、突发消化，以及和实测排队时间的对照
```

## 1. 运行

离线部分可以直接拿仓库里那份合成 trace 跑：

```bash
python3 code/ch20/scheduler_watch.py analyze \
  --trace content/ch20/evidence/scheduler-trace-sample.json \
  --slo-itl 80
```

```text
saturation_onset  15.0
queue_onset       25.0
preemption_onset  40.0
lead_time         10.0
verdict           KV 不足
```

采数据需要真实 vLLM 服务。**注意 `--max-num-seqs`：**

```bash
python3 code/ch20/scheduler_watch.py collect \
  --url http://localhost:8000 \
  --interval 0.5 --duration 120 \
  --max-num-seqs 64 \
  --output scheduler-trace.json
```

`running_ratio` 是 Running 相对上限的占比，即 20.7 的槽位占用率，而 `/metrics` 只给分子。不传这个参数，采出来的 trace 里 `running_ratio` 全是空，`analyze` 会直接拒绝，因为 20.7 说那是最早动的那个信号。

## 2. lead_time 是这个脚本最有用的输出

它量化了“饱和”到“开始排队”之间有多少预警时间，直接决定告警该配在哪个指标上。三种情形，三种结论：

```text
lead_time > 0     告警配在 running_ratio 上来得及
lead_time ≤ 0     排队不晚于饱和，说明 max_num_seqs 不是当前的约束，
                  把告警配在 running_ratio 上会完全失灵
无 saturation     整段未持续饱和，这段 trace 不能用来定参数
```

第二种是 20.7 那个顺序被打破的情形。**顺序被打破本身就是结论**，不是数据有问题。

## 3. 两个刻意的设计

**onset 需要连续 `--sustain` 个样本，默认 3。** 单个样本越线是噪声，而一份满是单样本 onset 的 trace 比没有 trace 更糟：它会让你把告警配在抖动上。返回的是这一串的**第一个**样本的时刻，不是最后一个，否则每个 lead_time 都会偏短一个确认窗口。

**`analyze` 宁可拒绝也不猜。** 缺 `running_limit` 就没有 `running_ratio`，20.7 那条推理断在第一步；缺 `preemption_total` 就少了三个信号里最严重的那个，此时给出的判断在最要命的那种情形下必然是错的。两种都直接报错。

## 4. 四种判断

```text
KV 不足            窗口内有抢占，或 KV 使用率峰值 ≥ 0.9
                   → 按第 16 章降 max_model_len 或提 gpu_memory_utilization
token 预算不足     请求数没到上限，而单步 token 触到 max_num_batched_tokens
                   → 这是 token 预算在限制，不是 max_num_seqs
                   只在按步采的 trace 上判：collect 按时间间隔采样，
                   batched_tokens 是一个间隔里所有步的 prompt token 之和，
                   和每步的预算不是一回事（trace 里 tokens_per_step 记 False）
请求数上限约束     running_ratio 到顶并开始排队，KV 和 token 预算都没触顶
                   → 按第 19 章那条 Goodput 曲线找 max_num_seqs 的峰值
未饱和             整段没有持续排队，这段 trace 不能用来定参数
```

判断顺序就是 20.7 的严重度顺序，抢占排在最前，因为它是唯一会自我加强的那一个。

## 5. queue-model 的正确用法

```bash
python3 code/ch20/scheduler_watch.py queue-model \
  --capacity-qps 12 --arrival-qps 10.8 \
  --service-cv 1.5 --slots 64 --burst-factor 3 \
  --measured-queue-ms 900
```

ρ 和 S 按 20.6 的定义算：ρ = 到达速率 ÷ 满载吞吐，S = 1 ÷ 满载吞吐。上面这组参数给出 ρ = 0.9、S ≈ 83 ms。满载吞吐从第 19 章的批量扫描读：token/s 除以平均输出长度。

输出按 20.6 的顺序排：

```text
ρ/(1−ρ) 表          0.5 / 0.8 / 0.9 / 0.95 → 1 / 4 / 9 / 19
波动修正            (Ca² + Cs²)/2，--arrival-cv 与 --service-cv 默认都是 1
P99 排队            S × ln(100ρ)/(1−ρ) 乘波动修正；ρ = 0.9 时约 45 个 S
多服务台对照        --slots 个槽位按 Erlang C；64 槽位、ρ = 0.9 时约 3.1 个 S
突发消化            --burst-factor 倍到达持续 --burst-seconds 秒的积压与消化时间
```

按服务台个数，单服务台那一行是上界，Erlang C 那一行是下界，真实的连续批处理落在两者之间；服务时长的波动和抢占又把真实排队往上推。

**对照的意义在于对不上的时候。** 实测超过预测 3 倍以上，脚本会说瓶颈不在排队本身：先确认 `--service-cv` 填的是实测的服务时长波动，再去看显存和抢占；实测远低于预测，要么是多服务台效应在起作用，要么是等待藏进了 Running——批量越过分界点后，多出来的负载表现为单步变长、ITL 变差，Waiting 仍是空的，正是 20.7 案例一那种误判，对照同期的 `running_ratio` 和 ITL 再下结论。三条边界每次都随输出一起打印，因为“把这个毫秒数写进报告”正是这条式子最常见的误用。

到达速率不低于满载吞吐时，脚本报错而不是给一个数：那时队列每秒净增“到达减满载”那么多条，等待随压测时长线性增长，平均值没有意义。

没有满载吞吐时可以给 `--trace`，用 `running_ratio`（槽位占用率）的时间平均当 ρ 的粗略代理。它通常偏低，因为小批量下请求停留得短，同样的到达占的槽位更少。样例 trace 的时间平均是 0.869。时间平均到了 1 时脚本同样报错，不会悄悄改成 0.99。

## 6. 测试

```bash
python3 -m unittest discover -s code/ch20 -p 'test_*.py'
```

58 项。其中一组专门钉住正文的数字：`ρ/(1−ρ)` 在 0.5 / 0.8 / 0.9 / 0.95 上必须正好是 1 / 4 / 9 / 19；12 QPS 满载时 S 约 83 ms；0.7 → 0.735 排队涨约 19%，0.9 → 0.945 约 17 个 S；P99 在 0.9 时约 45 个 S；64 槽位的 Erlang C 在 0.9 时约 3.1 个 S；一分钟三倍突发在 0.9 和 0.7 时分别要约 17 和 3.7 分钟消化。样例 trace 的三个 onset 必须是 15.0 / 25.0 / 40.0 且严格按 20.7 的顺序，lead_time 必须是 10.0。

`scheduler-trace-sample.json` 是**合成设定，不是真机采集**，`synthetic` 字段和 `_note` 都写明了。它是阶梯式增压四档：余量充足、Running 打满但未排队、开始排队、KV 见底开始抢占。

在自己的服务上做一次真机观测：用阶梯式增压跑一轮，记录三个 onset 时刻和对应的 QPS，画出饱和曲线；从最高一档读出满载吞吐，用 `queue-model` 把各档的预测排队和实测排队对一遍，再用你的 trace 替换样例。
