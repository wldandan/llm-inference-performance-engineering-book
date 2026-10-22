# Chapter 17 Demo：量化收益估算与质量闸

`quant_tradeoff.py` 分两个子命令，因为量化有两半，不能混着算。

```text
estimate   只做算术，不需要 GPU。按 17.2 的分工把权重侧和 KV 侧分开算
evaluate   比对两个服务在同一批输入上的质量，需要实测数据
```

只依赖 Python 标准库。

## 1. 收益那一半

```bash
python3 code/ch17/quant_tradeoff.py estimate \
  --config code/ch15/model-7b-generic.json \
  --avg-context 2300 \
  --weight-dtype fp16,int8,int4 \
  --kv-dtype fp16,int8 \
  --measured-tpot-ms 17
```

输出把六个精度组合排成一张表。两条分工由代码算出来，不靠记：

```text
权重 INT8   单步下限 -50%   并发 +14%    → 主要改善延迟
KV   INT8   单步下限  -0%   并发 +100%   → 主要改善容量
```

FP16 必须在两个精度列表里，因为所有相对变化都以它为基线，脚本会拒绝缺了它的调用。

## 2. `realised_tpot_saving` 是这半边的重点

`delta_tpot_floor` 是**下限**的变化，不是你会拿到的变化。17.8 案例一那个服务把权重减半只省了 8%，因为它的实测 TPOT 是下限的 6.25 倍。

给了 `--measured-tpot-ms`，这一列按 `下限降幅 ÷ 实测倍数` 折算：

```text
实测是下限的 1.2 倍   权重减半省 42%
实测是下限的 6.25 倍  权重减半省  8%
```

不给，它只报上界并写明为什么不能当预期值用。实测倍数超过 2 时还会追加一条警告，指回 15.6 那个拆分。**实测低于下限会被拒绝**，因为下限已经假设带宽满载，比它快说明这段时间的边界定义有问题。

## 3. 质量那一半

```bash
python3 code/ch17/quant_tradeoff.py evaluate \
  --evalset content/ch17/evidence/quant-eval-sample.jsonl \
  --results content/ch17/evidence/quant-eval-results.json \
  --threshold 0.01
```

三条硬性要求，每一条都对应一种“评估悄悄失去意义”的方式：

- **评测集必须有 `long_answer` 和 `structured_output` 两类样本。** 只有短问答的评测集测不出 17.4 说的那两类退化，缺任一类直接拒绝。
- **阈值必须带写入时间。** 事后看着结果定标准，和第 14 章说的事后补写预期是同一个毛病。
- **逐维度都要过线。** 任一维度越界就判不通过，哪怕总分漂亮。

## 4. 那份合成样例演示的是第三条

`quant-eval-results.json` 是**合成样例，不是真机结果**，`synthetic` 字段和 `_note` 都写明了。它刻意做成这样：

```text
20 条样本   10 条短问答 / 4 条长回答 / 3 条结构化 / 3 条专业难例
总分下降    0.68 个百分点   →  1 个百分点的底线轻松通过
结构化输出  掉 3.9 个百分点  →  越界
```

这就是 17.8 案例二的机理，而且比正文那一版更进一步：**评测集里已经放了结构化样本，总分照样能通过**，因为短问答样本多，把那一维的退化在平均值里稀释掉了。所以底线要逐维度各设一条，不能只对总分设一条。0.998 → 0.959 换成错误率就是 0.2% → 4.1%，二十倍。

## 5. 测试

```bash
python3 -m unittest discover -s code/ch17 -p 'test_*.py'
```

49 项测试。17.2 的三档权重与 1/2/4 FLOP/byte、59 GiB 与 210 条、425984 与 851968 与 370；17.3 的 256 格与 log₂3 ≈ 1.6 位；17.8 案例一的 8% 与 42%；以及那份合成样例的每一个数，包括“总分通过而结构化输出越界”这个刻意的安排。

质量结果是合成的。用在自己的服务上时，跑一次 FP16 与 INT8 的对照，用实测 TPOT 校准 `realised_tpot_saving`，并把质量结果换成自己的评测集上的结果。
