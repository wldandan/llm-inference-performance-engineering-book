# Chapter 8 Demo：把一条请求的痕迹串起来

`trace_one_request.py` 发送一条带自定义 Request ID 的请求，然后把这条请求在各处留下的痕迹收集成一张证据卡片。

**需要一个真实的 vLLM 服务，而且要开两个默认关闭的开关。** 单元测试不需要，它直接测卡片的组装逻辑。

## 1. 运行

服务端：

```bash
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --enable-request-id-headers \
  --enable-per-request-metrics
```

不开 `--enable-request-id-headers`，响应头里没有 `X-Request-Id`，`correlation` 只能是 `unknown`；不开 `--enable-per-request-metrics`，流里没有请求级指标，`server` 块全是 `null`，`gaps` 算不出来。两个参数名和默认值都是版本相关的，以 `content/reference/environment.md` 为准。

客户端：

```bash
python3 code/ch08/trace_one_request.py \
  --base-url http://127.0.0.1:8000/v1 \
  --request-id req-demo-001 \
  --output trace-req-demo-001.json
```

不给 `--request-id` 时脚本自己生成一个。ID 通过 `X-Request-Id` 请求头带给服务端。

## 2. 卡片五块

```text
identity      request_id、模型、采集时刻
client        请求发出、首个分片、结束、重试次数、错误
server        引擎返回的请求级记录（Queue / Scheduled-to-First-Token / Generation）与终态
correlation   客户端 ID 与服务端 ID 是否一致
gaps          客户端总时长与服务端总时长的差值，以及它拆成了什么
```

## 3. correlation 是本章的核心检查

它有三种结果，**不会把后两种默默当成第一种**：

```text
ok       两边 ID 一致
unknown  服务端没有回带 ID，这个关联无法验证
broken   两边 ID 不一致，证据链在这里断了，后面所有关联分析都不成立
```

`broken` 时脚本会打印警告并以非零状态退出。

## 4. gaps 不给差值起名字

差值先拆：被取消的重试尝试、客户端退避等待，这两项有记录的部分先扣掉，剩下的进 `unattributed_ms`。

**剩下那部分不叫“网络耗时”。** 它包含网络往返和客户端自身处理，而在没有观测到它的边界之前，第 2 章那条规矩仍然适用：没有观测到的边界，就不要给它起名字。

传入 `attempts` 可以把重试的账也拆进来，8.8 案例一那次操作拆完正好一分不剩。

## 5. 一条不要做的事

不要把 `request_id` 做成指标标签。第 8.2 节算过这笔账：指标的序列数是各标签取值数的乘积，加一个每条请求都不同的字段，监控系统会被打垮。请求级的时间数据走日志或 Trace，不走指标。

上面的输出都来自仓库里的样例。在自己的服务上跑一次时，把结果脱敏后和环境指纹一起归档。

## 6. 测试

```bash
python3 -m unittest discover -s code/ch08 -p 'test_*.py'
```

10 项测试覆盖三种 correlation 结果、8.8 案例一那次 9.48 秒操作的差值拆解（拆完为零）、剩余部分不被命名、缺服务端总时长时不硬算差值，以及卡片五块齐全。
