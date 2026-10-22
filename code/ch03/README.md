# Chapter 3 Demo：Transformer 生成机制报告

这个 Demo 用纯 Python 展示三件事：

1. 根据模型配置推导 Token、Hidden State、Q/K/V 和 Logits 的形状。
2. 把 Logits 经过 Temperature 与 Top-k 转成概率并采样。
3. 生成一条 Prefill 加多步 Decode 的事件记录，观察 KV Cache 长度变化。

它不加载真实模型，不测量性能，也不输出优化结论。报告中的 Logits 和 token ID 都是教学数据。

Demo 的 `temperature` 必须大于零。部分推理 API 用 `temperature=0` 表示 Greedy Decoding，但这里的 `softmax()` 保持数学定义，不接受除零；Greedy 的概念由正文单独解释。

## 运行

从 Git 仓库根目录运行：

```bash
python3 code/ch03/mechanics.py \
  --prompt-tokens 8 \
  --decode-steps 4 \
  --temperature 1.0 \
  --top-k 3 \
  --seed 7
```

保存 JSON：

```bash
python3 code/ch03/mechanics.py --output mechanics-report.json
```

## 阅读输出

- shapes 展示各阶段张量形状，Q 有 14 个头，K/V 有 2 个头，用来说明 GQA。
- sampling 展示候选 token 的概率与最终选中的 token ID。
- execution_trace 的第 0 步是 Prefill，后续步骤是 Decode。
- Prefill 一次写入全部 Prompt 的 K/V；每个普通 Decode step 把 Cache 长度增加 1。

## 测试

```bash
python3 -m unittest discover -s code/ch03 -p 'test_*.py'
```

## chat_template_probe.py：那 30 个 token 由什么组成

3.2 说第 1 章那次请求只发了一句话，服务端却报了 30 个 `prompt_tokens`。多出来的部分有两个可能的来源：模板套上去的控制标记，以及某些模型在没有 system 消息时自动插的一句默认系统提示。两者的量级差很多，猜不得。

服务起着的时候（第 1.2 节那条命令），走它的 `/tokenize`：

```bash
python3 code/ch03/chat_template_probe.py \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --output chat-template-probe.json
```

本机装了 transformers 的话，也可以不启动服务：

```bash
python3 code/ch03/chat_template_probe.py --local
```

输出里要看三样：`rendered` 是渲染出来的完整文本，`has_default_system` 说模板有没有自己插一句，`segments` 把总数拆成“用户这句话”和“模板加进去的”。`reading` 那一行直接写明 3.2 该怎么措辞。

这个脚本只做核对，不进正文的算例。
