# Chapter 30 Demo：项目脚手架与验收

这是一套脚手架，不是单个脚本。七个目录对应 30.2 的七个阶段，`verify.py` 是它们的总验收器。

```text
project/
  workload/        阶段二：workload 描述模板与生成器
  baseline/        阶段二：Baseline 采集与对比
  observe/         阶段三：请求级追踪与指标采集
  experiment/      阶段四到六：实验记录与报告生成
  capacity/        阶段七：容量与成本模型
  gate/            阶段七：门禁与断言
  report/          贯穿全程：报告契约模板与渲染
  verify.py        总验收脚本
  samples/         两份样例项目，一份通过、一份差一点
```

每个目录下的 `README.md` 写了这一阶段要产出什么、`verify.py` 读哪个文件、以及复用前面哪一章的 Demo。**脚手架本身不产生数据**，数据来自前二十九章那些脚本。

## 1. 验收

```bash
python3 code/ch30/project/verify.py \
  --project-dir code/ch30/project/samples/sample-pass --level base
```

```text
五项交付物        全部 ok
九块报告契约      齐全 9/9　缺 无　空 无
八条自查          八条全绿
五处接缝          五处一致
结论              pass
```

它检查四件事，任何一件不过关就是 `incomplete`：

```text
deliverables      30.1 那五项交付物的存在性
report_contract   30.3 那九块的齐全度，缺一块不算，写成空的也不算；第 7、8 块里
                  来自 Part 6 的那几项（扩缩容触发指标、冷启动、回路滞后、回滚
                  预案、观察窗口、负责人）缺了同样不算
self_check        30.4 那八条，逐条出结论
cross_check       第 29 章那五处接缝，直接 import code/ch29/release_check.py
```

## 2. 八条自查里哪几条能自动判

`SELF_CHECKS` 把八条分成两类，`kind` 字段标明：

```text
结构判定（4 条，不过关直接失败）
  5. 护栏指标每轮都记了         某轮 guardrails 为空
  6. 没有一轮改了多项           某轮 changed 多于一项
  7. 质量是否决项               动了精度而 quality 为空
  8. 边界五项写齐了             boundary 少于五项

启发式判定（4 条，不过关报告警并注明需人工确认）
  1. 不可用没有被写成 0         拿 unavailable_stages 去报告里搜对应的 0
  2. 没有把客户端观测当成服务端事实   搜“网络耗时”“分片数即 token 数”这类说法
  3. 每个性能数字都有对应的条件   某轮 conditions 里没有批量或上下文
  4. 留了“测不出来”这个结论的位置   三轮以上全是明确结论时告警
```

**四条结构判定都在 30.4 末尾点名的那五条里**，它们查的是同一件事：这次改动换走了什么，所以它们是失败而不是告警。五条里剩下的那条（每个数字都带条件）只能靠关键词猜，归在告警里。

后四条只能靠关键词和缺失来猜，所以它们报告警，并且在文案里直接说“需人工确认”。**把启发式判定伪装成确定性判定，比不判更糟**：读的人会以为绿灯代表查过了。

## 3. 两份样例的用法

```bash
python3 code/ch30/project/verify.py \
  --project-dir code/ch30/project/samples/sample-incomplete
```

`sample-incomplete` 是 `sample-pass` 的“差一点”版本，两份只在 `workload`、`gate`、`experiment`、`report` 四个文件上不同，`baseline`、`capacity`、`observe` 逐字相同。它一次踩中八条自查的全部八条：

```text
[告警] 1  报告里把 client_queue 和 tokenizer_internal 写成了 0
[告警] 2  根因结论里写了“网络耗时 560 ms”
[告警] 3  r1 的 conditions 里只有环境和时间，没有批量或上下文
[告警] 4  四轮全是明确结论，没有一轮不可分辨
[失败] 5  r2 没有护栏
[失败] 6  r1 同时改了两项
[失败] 7  r3 动了精度却没有质量数据
[失败] 8  边界缺 chain_structure
[缺项]    有门禁：assertions 为空
[不一致]  容量模型上下文 1800 对 workload 实际 2400，2 张卡实际要 3 张
```

最后那一行由第 29 章那份脚本算出来。样例的 `capacity.json` 写明了显存先满，所以能直接换算成卡数；吞吐先满时脚本不换算，要求用第 26 章的模型重算。**把接缝换算成卡数，是让“对不上”变成一个容量问题而不是格式问题的那一步。**

## 4. 扩展验收

`--level extended` 额外要求一项换了部署形态的对照数据：张量并行扩展效率、MoE 激活参数或 Kernel 分析。PD 分离的对照数据给了也计入，但暂不要求：本书只在第 13 章给了它的定义，做法所在的附录 E 还没写。**报告契约完全不变**，这是 30.5 的意思：形态可以换，方法不换。

通过基本验收的样例跑 `--level extended` 会以 `incomplete` 结束，测试核对这一点。

## 5. 测试

```bash
python3 -m unittest discover -s code/ch30/project -p 'test_*.py'
```

55 项。主体是 `TestIncompleteSample`：八条自查逐条验证，每条都核对报出来的那个 id 是对的。另外钉住的：五项交付物和九块契约的顺序、四条结构判定正好是第 5 到第 8 条、五处接缝来自 `code/ch29/release_check.py` 而不是这里重写的、以及两份样例只在四个文件上不同；还有第 7、8 块那两项 Part 6 物证（P1-2）与余量和卡数对得上（P2-2）。

两份样例都是**合成设定**。

用在自己的项目上时，按七个阶段走完一遍，把七个目录填上真实数据，用 `verify.py` 通过基本验收，并且让门禁真的拦住一次人为制造的回归。这三件事做完，样例里那些合成数字就都换成了你自己的。
