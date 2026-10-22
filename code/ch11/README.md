# Chapter 11 Demo：Prefill 计算量与显存估算器

`prefill_model.py` 读入模型配置和输入长度，算出这一次 Prefill 大概该花多少、要写多少 KV Cache，并把结果和你带来的实测值放在一起解读。

**它不测量任何东西。** `--measured-ms` 是你从真实 Baseline 拿来的数字；不给它，报告就只有理论一侧，并且会写明“没有测就是没有测”。

只依赖 Python 标准库，不需要 GPU。

## 1. 共享配置

`model-qwen25-05b.json` 是**全书共享的参考模型一的配置**（Part 3 开篇那张表）。第 12、13、14 章的 Demo 都读它，正文里所有与这个模型有关的数字都出自它：

```text
交叉点             16640 token       = 2×896 + 2×128 + 3×4864
非嵌入参数量       3.58 亿           进入 2 × 参数量 × S 的就是它
词表嵌入           1.36 亿           查表，不是 GEMM，不该算进去
```

换模型只改这一份文件。**不要在四章正文里各改一遍**，那正是 2026-09-22 那轮审阅查出的六处数字不一致的来源。

## 2. 运行

```bash
python3 code/ch11/prefill_model.py \
  --config code/ch11/model-qwen25-05b.json \
  --input-tokens 8000 \
  --peak-tflops 153 \
  --effective-tflops 30 \
  --measured-ms 2400 \
  --reference-tokens 400 \
  --reference-ms 80 \
  --output prefill-estimate-8k.json
```

输出六组：

```text
config               层数、hidden、KV 头数、head_dim、KV 维度
compute              GEMM、Attention、两者占比、交叉点、长度翻倍的倍数
memory               KV Cache 写入量、按并发放大、若换成 MHA 会是多少、注意力矩阵大小
arithmetic_intensity 只算权重与算上激活读写两种 Prefill 强度，以及 Decode 的 FLOP/byte
comparison           下限（峰值算）、估计（有效值算）、实测、折合有效算力，以及绝对值检验的解读
ratio_check          两个长度的估算倍数与实测倍数，以及比值检验的解读
```

`compute` 把 GEMM 和 Attention **分开列出**是刻意的：改变 `--input-tokens` 再跑一次，能看到占比怎么随长度移动，比记住“长了之后 Attention 变重要”直观得多。

## 3. 几个刻意的设计

**`doubling_factor` 这一项。** 它回答“输入翻倍，时间涨几倍”，而答案永远小于 4：交叉点上正好 3.000，往长了去趋近 4 但取不到。11.7 案例一就是拿它把“翻倍就是四倍”排除掉的。

**`relative_cost` 只有一个式子：`S × (交叉点 + S)`。** 它是把 GEMM 和 Attention 相加后除掉公共系数的结果，所以两个长度的相对计算量之比，就等于它们的 FLOPs 之比。第 12、13、14 章比较两个长度时用的都是它。

**显存一律用二进制单位。** 与框架日志和显存分配器同口径；第 16 章要接着算容量，口径在这里定下来。

**`arithmetic_intensity` 给两种算法。** 只算权重读取时，参数量约掉，Prefill 的强度约等于输入 token 数。把每个投影读入、写出的激活也算进分母，强度是 `1 ÷ (1/S + 1/k + 1/n)`，S 长到和矩阵宽度相当时封顶：这个模型 512、2048、8000 token 时约 287、494、602。Decode 每步约等于 1。

## 4. 解读那一行

`comparison.reading` 按 11.5 那张表分四档：

```text
实测 < 下限             不可能是算出来的   先查 Prefix Cache 命中，或这段时间的边界定义
下限 ≤ 实测 < 估计      实现比假设高效     正常，不能据此断定缓存命中
实测 ≤ 3 × 估计         同一量级内         Prefill 本身没有明显异常
实测 > 3 × 估计         高出数倍           有额外开销：kernel 效率、多轮调度，或混着别的东西
```

**下限用峰值算，估计用有效值算，两者不能混。** 下限已经假设硬件满载，比它快说明某段计算没有发生；只比估计快，说明的是实现效率比假设的高。

`ratio_check` 是 11.2 那个检验：给出较短那次测量（`--reference-tokens`、`--reference-ms`），它比较估算的增长倍数和实测的增长倍数。比值检验约掉了所有常数因子，所以它可以通过、而绝对值检验同时不通过，11.1 那个 2.4 秒就是这样。

## 5. 测试

```bash
python3 -m unittest discover -s code/ch11 -p 'test_*.py'
```

34 项测试。除了常规的配置校验，它们**把正文里的每个数字都钉在了代码上**：11.2 那张表的五行、11.3 的 93.75 MiB / 4.58 GiB / 656 MiB、11.4 的 287 / 494 / 602、11.5 的 8.48 TFLOPs、55 ms 下限与 283 ms 估计、2.4 秒的两个检验、11.7 案例一的 2.215 倍与案例二的低于下限、13.4 要用的 10 MiB 与 1710 MiB。正文改了而代码没改，或者反过来，测试会失败。
