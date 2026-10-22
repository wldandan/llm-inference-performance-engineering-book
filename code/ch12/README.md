# Chapter 12 Demo：上下文成本清单

`context_cost.py` 把一个 prompt 按来源拆开，逐段算出 token 数、占比、延迟贡献，以及“再多取一段要多花多少”。

12.1 那句话是这个 Demo 的全部理由：**做这个决定的人通常看不到这笔账。** 这份清单就是那笔账。

**它不评估回答质量。** 成本那一边可以算，质量那一边要靠你自己的评测集，两边都有才能画出 12.4 那条曲线。所以检查器会拒绝带 `quality`、`accuracy`、`recall` 这类字段的输入描述。

只依赖 Python 标准库，不需要 GPU。

## 1. 运行

```bash
python3 code/ch12/context_cost.py \
  --prompt-spec code/ch12/rag-prompt.json \
  --model-config code/ch11/model-qwen25-05b.json \
  --output context-cost-rag.json
```

`--model-config` 读第 11 章那份共享配置，计算量的形状和第 11 章同源。TTFT 的绝对值按 `baseline` 那个实测锚点标定（1230 token、320 ms，折合约 3 TFLOP/s），和 11.1 那个 2.4 秒是同一个实测尺度，不是 11.5 用 30 TFLOP/s 算的估计。

## 2. prompt 描述文件

`rag-prompt.json` 就是 12.2 那张分段表写成文件。**段的顺序就是拼进 prompt 的顺序**，这一点后面有用：

```text
system prompt   fixed       200 token
few-shot 示例   fixed       400 token
检索片段        retrieval   200 × K
对话历史        history     260 × 轮数
用户问题        user         30 token
```

四种 `source` 的区别在于**谁决定它的长度**：`fixed` 写在代码里、`retrieval` 由 Top-K 决定、`history` 由保留几轮决定、`user` 才是用户行为。12.2 的三个反直觉结论都是从这个分类来的。

`baseline` 那一块是实测锚点（Top-K=3 时 320 ms）。**没有它脚本不会给出绝对毫秒数**，只给相对计算量，并写明原因。绝对时间只能来自实测。

## 3. 可缓存前缀，不是固定内容总和

`cacheable` 这一项容易被算错，脚本刻意只认前缀：

```text
不随请求变化    system 200 + few-shot 400 + 用户问题 30 = 630 token
可缓存前缀      system 200 + few-shot 400              = 600 token
```

用户问题虽然每次都是那一段模板加一句话，却排在整个 prompt 的**最后**，它前面的检索片段一变，前缀匹配早就断了。所以 Prefix Cache 的天花板是 600 而不是 630。

再往下还有一层折扣：`prefill_saving_if_fully_hit` 比 token 占比更低，因为被缓存的恰好是**最便宜的那一段**（靠前的位置要注意的位置更少）。两档的数字是：

```text
Top-K = 3    前缀占 49% 的 token   全命中省 47% 的 Prefill 计算
Top-K = 10   前缀占 23% 的 token   全命中省 20% 的 Prefill 计算
```

脚本还会检查固定段有没有被排到变化内容后面。排错了 `prefix_tokens` 直接算成 0 并给警告，这正是 13.8 案例二那个“可缓存比例 55%、命中率 3%”的成因。

## 4. sensitivity 是给做决定的人看的

```text
items   input_tokens   estimated_ttft_ms
  3          1230            320.0
  5          1630            433.6
 10          2630            737.8
 20          4630           1433.7
```

再加上 `one_more_item`：当前档位再多取一段要多花多少 token、多少毫秒。**调 Top-K 之前看一眼这一档，比上线后查投诉便宜。**

注意每多一段的边际延迟成本是递增的（第 4 段和第 20 段不一样贵），这是 Attention 平方项的直接后果，也是 12.4 那条曲线为什么会有拐点。

## 5. 检查器拒绝什么

- `source` 不在 fixed / retrieval / history / user 之内；
- 一个段同时给了 `tokens` 和 `tokens_per_item`，或者两个都没给；
- 用了 `tokens_per_item` 却不给 `items`（取几段是代码里的常数，必须写出来）；
- 描述里出现 `quality`、`accuracy`、`recall`、`ttft_ms`、`results` 这类字段；
- 段名重复；
- `baseline` 只给了 tokens 或只给了 ttft_ms。

## 6. 测试

```bash
python3 -m unittest discover -s code/ch12 -p 'test_*.py'
```

28 项测试。其中一组把 12.1 的 2.31 倍、12.2 的两档占比、12.4 那张表的四行全部钉在代码上；另一组确认“省下的计算一定低于 token 占比”这条性质在所有档位上都成立，以及固定段排错位置时会报警。
