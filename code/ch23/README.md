# Chapter 23 Demo：RAG 链路时间分解

`rag_trace.py` 三个子命令，只有第一个需要真实链路：

```text
collect   采集逐段耗时，第一遍标冷、后面标热
analyze   逐段占比、关键路径、冷热对照、缓存状态
whatif    按给定的参数变化重新估算，用来在动手之前排优先级
```

## 1. 先分解

```bash
python3 code/ch23/rag_trace.py analyze \
  --trace content/ch23/evidence/rag-trace-sample.json
```

```text
热查询各段
  rewrite       180.0 ms   4.9%
  embed          25.0 ms   0.7%
  retrieve       95.0 ms   2.6%
  rerank        210.0 ms   5.7%
  assemble        4.0 ms   0.1%
  ttft         1400.0 ms   37.7%
  generate     1800.0 ms   48.5%
生成两段占比      86.2%
生成之前占比      13.8%
```

最后两行是这一章存在的理由：生成那两段第 12 章和第 15 章已经讲过，这一章关注的是它之前那 13.8%。

冷热对照那一行值得单看：

```text
冷查询总时长是热查询的 1.066 倍，差距集中在 retrieve（3.579 倍）
```

**检索冷起来慢 3.6 倍，端到端只慢 6.6%。** 这就是占比小的那一段能造成的全部影响，也是为什么分解要放在优化之前。

## 2. whatif 给的是顺序，不是结果

```bash
python3 code/ch23/rag_trace.py whatif \
  --trace content/ch23/evidence/rag-trace-sample.json \
  --final-k 5 --skip-rewrite --rerank-candidates 50
```

```text
估算节省          1236.6 ms（33.3%）
上下文            9000 → 4000 token
  skip-rewrite        省 180.0 ms
  rerank-candidates   省 157.5 ms
  final-k             省 899.1 ms
优先级            final-k 省 899 ms，skip-rewrite 省 180 ms，rerank-candidates 省 158 ms
```

899 和 180 就是 23.7 那句话里的“省 900 ms”和“省 180 ms”。输出里每一次都带上一句“这个模式只给估算，不替代实测”，因为把估算值写进性能报告是这类工具最常见的误用。

## 3. TTFT 的重估来自第 11 章，不是线性折算

`rag_trace.py` 直接 import `code/ch11/prefill_model.py`，用它的 `relative_cost` 折算 TTFT。理由就是 23.3 那一节：

```text
上下文 9000 → 4000 token
token 是 0.444 倍，而 Prefill 计算量是 0.358 倍
Attention 占比从 35.1% 降到 19.4%
```

**这两个比例不相等，正是 23.3 的重点。** 测试里有一组专门核对这件事：可缓存的固定部分为 0、每段 600 token 时，3000 token 的 600 ms 代进模型给出 9000 token 的 2349.9 ms，四舍五入正是正文那个 2350；反过来 2350 代回去给 600.0。两个数是同一个模型的两端，不是各自写上去的。

Attention 占比那个函数也一样：`S / (crossover + S)`，在 3000 上是 15%，在 9000 上是 35%，和 23.3 引的两个数一致。

## 4. 四处拒绝，全部来自 23.6 那套 Baseline 纪律

```text
缺 knowledge_base.version        拒。知识库是环境的一部分，它一变 TTFT 就变
冷热没标                          拒。23.2 说差几倍，混在一起的平均值没有参考价值
缺 cache_status，或开着不记命中率  拒。三层缓存，这件事最容易搞错
whatif --parallelize 主链上的段    拒。23.4 说那条链是 RAG 的结构决定的严格串行
```

最后一条是这个脚本最该守的一条。改写 → 检索 → 重排 → 生成并行不掉，一份把它并行掉的估算是在卖一份不存在的时间。支线（多路检索、多数据源）可以并行，脚本不拦。

还有一处对齐检查：`context_composition` 的 `fixed_tokens + final_k × tokens_per_chunk` 和 `context_tokens` 必须对得上，差超过 2% 就拒。在错的基数上估算，省出来的毫秒数全是错的。

## 5. 测试

```bash
python3 -m unittest discover -s code/ch23 -p 'test_*.py'
```

44 项。钉住正文数字的那一组：交叉点 16640、Attention 占比 15% 与 35%、9000 对 3000 的计算量比 3.9165、2350 与 600 的双向互推、`2350 − 600 = 1750` 以及扣掉重排代价后的 1450 到 1700、样例上 final_k 的 899 ms 和 skip-rewrite 的 180 ms。

`rag-trace-sample.json` 是**合成设定，不是真机采集**，三个查询各跑三遍，第一遍冷。

在自己的服务上做一次链路实测：接一条完整 RAG 链路，用 `collect --cold-start` 跑出冷热两组分解数据，然后按 `whatif` 排出的顺序逐项改，用实测值验证估算的准确度。
