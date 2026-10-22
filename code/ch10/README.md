# Chapter 10 Demo：产出一份根因报告

`rca_report.py` 不采集数据。它把调查过程组织成结构化报告，并检查这份报告是否自洽。

只依赖 Python 标准库，不需要 GPU。

## 1. 运行

```bash
python3 code/ch10/rca_report.py \
  --input content/ch10/evidence/rca-report-sample.json \
  --output rca-report.json
```

仓库里那份 `rca-report-sample.json` 就是正文 10.6 那次调查的完整版，可以直接拿它跑一遍看它为什么通过。**它是合成数据，不是真机诊断。** 它证明的是流程能走通、结构长什么样，不能当作任何真实系统的结论。

## 2. 报告七块

```text
problem       现象、范围、时间、对照 Baseline
hypotheses    候选假设，每条含预期证据、所需层次、判定门槛、结论
evidence      实际采到的证据，标明来源、层次、采集条件
ruled_out     已排除项及其依据
conclusion    结论、置信度、支撑证据引用
unknowns      残留不确定性及其影响
next_step     最小侵入改动、改动层级、验证方式
```

## 3. 检查器拒绝什么

- `problem` 缺范围或对照；
- 某条假设没写预期证据（即无法被证伪），或者没写判定门槛（“高”是多高仍由人说了算）；
- `conclusion` 引用的证据编号在 `evidence` 里不存在；
- `evidence` 里有条目没写采集条件（第 9 章的要求）；
- 只有一条假设，且 `ruled_out` 为空；
- 某条假设标了 `unconfirmed`，却没出现在 `unknowns` 里（未查完的线索必须写下来）；
- `next_step.verification` 没有写明同流量重跑；
- `next_step.tier` 不在 config / parameter / code / architecture 之内。

**倒数第四条是刻意设的。** 只提出一个假设、什么都没排除的调查，通常是先有结论再找证据。检查器不判断你的结论对不对，它只检查这个调查过程是否具备被推翻的可能。

## 4. conclusion 里的两个字段

样例报告的 `conclusion` 有 `resolved` 和 `not_resolved` 两项，对应 10.6 那句话：改动后 P99 回到 620 ms 而不是 400 ms，差 55%，远超可识别线。**这两项要分开写。** 只写“已恢复”，那 220 ms 的缺口就消失了，而它恰恰是下一次同类故障的起点，也是第 28 章门禁阈值该定在哪里的依据。

样例报告是合成数据。真正的交付，是在自己的服务上走完一次完整流程，产出一份能通过这个检查器的报告。

## 5. 测试

```bash
python3 -m unittest discover -s code/ch10 -p 'test_*.py'
```

17 项测试分两组：一组确认 10.6 那份样例报告能通过自己的检查器，且摘要与正文叙述一致；另一组逐条触发上面每一类拒绝。
