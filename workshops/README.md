# Workshop 实验通用模板 + 全部 13 个样板

> 新增的 [Workshop 01：用 Critical Path 定位全局性能问题](01-global-performance-model/README.md) 已按“目标、前置知识、准备时间、步骤、预期输出、练习、排错、完成标准”补齐。它是 Chapter 7 的 Level 1 分析 Lab，不计入下方 13 个优化技术样板。

> 本目录是章节内容之外的第二条学习路径：每章的"优化方法"讲完机制和证据后，配一个可动手复现的实验。13 个技术点的讲义（本文件）已全部铺开（2026-09-03），顺序跟随 `02_Course_Outline.md` 的章节顺序：Ch12 Prefill 优化方法 → Ch16 Decode 优化方法（5 个）→ Ch20 Serving 优化方法（2 个）→ Ch24 Scalability 优化方法（3 个）。
>
> **`00-model-internals/` 是额外加的第 0 个入口**，不是五步瓶颈实验，而是"先看懂模型结构参数，再看这些参数怎么决定了后面所有优化技术"的起点（从 Qwen2.5-0.5B 的 GQA `num_kv_heads` 算到 KV Cache 大小，再连到 PagedAttention/Continuous Batching）。建议排在样板一之前、Chapter 1-3 前后使用。
>
> **哪些已经是能跑的代码，不只是文档**：`00-model-internals/`、`02-batching-tiers/`、`04-kv-quantization/`、`05-prefix-cache/`、`07-kernel-level-cuda-graph/`、`08-speculative-decoding/`、`09-chunked-prefill/` 这 7 个目录有实际的脚本/单元测试，可以直接跑（需要真实 GPU 环境，本仓库这边没有 GPU 无法帮你实际跑通，但脚本本身经过语法检查，Python 部分的纯函数逻辑有单元测试覆盖）。其余 6 个（一、三、六、十、十一、十二、十三——样板一 PagedAttention 也还没有代码）目前只有下面的文字讲义，还没有对应代码目录。共享的压测客户端在 `common/`（`bench_client.py` + `compare.py`，都有单元测试）。
>
> **样板二的实际实现和下面文字描述不完全一样**：原计划 Static/Dynamic/Continuous 三档对比，动手做的时候发现 Dynamic Batching 那一档找不到能直接跑的最小参照实现（vLLM 没有这个模式，需要 Triton 或自建调度器）；后来在参考资料（O'Reilly《Hands-On LLM Serving and Optimization》配套代码）里找到一个纯 `transformers` 写的服务，同时实现了 Static 和 Continuous 两种调度，于是改成了"naive Static → naive Continuous → vLLM Continuous"三档，细节和口径提醒见 `02-batching-tiers/README.md`。这不代表下面样板二的文字讲义作废——那段文字仍然是讲课时用来解释三层调度粒度差异的正确讲法，只是"用什么代码演示"换了个更容易搭建的方案。

> 每个优化点 = 一节课 = 一个自包含实验，五步结构（用户确认版，2026-09-02）：
> **环境搭建（单机/多机）→ 性能脚本加压制造瓶颈 → 执行优化措施 → 重跑相同脚本验证 → 对比总结**
> 对应 course-04 方法论（01_Course_Design.md）里"验证收益"环节的操作化落地，
> 不是另起一套教学法。可复现性要求（warmup、多次重复取统计量）内建在"性能脚本"
> 本身的设计里，不单列步骤。
>
> 三条设计决定（2026-09-02 用户拍板）：
> 1. **压测工具按技术点各选合适的**，不强制全课程统一一个工具。
> 2. **环境搭建是每个实验显式的第一步**，必须写清楚单机单卡 / 单机多卡 / 多机多节点。
> 3. **不引入额外的故障注入工具**——"瓶颈"就是用性能脚本加压 + 配置降级来复现，
>    压力本身就是注入方式，除非某个技术点确实无法用这种方式复现，否则不加新工具。
>
> **具体 CLI 参数名以你实际使用的框架版本文档为准**——vLLM / SGLang 的 flag 命名会随版本演进（例如 `--attention-backend`、`--kv-cache-dtype`、`--speculative-model` 这类参数在不同版本里的写法可能不同），下文给出的是当前主流写法作为教学起点，正式制作实验讲义前建议对照当时的官方文档核对一遍。

## 通用模板结构

```
实验：<优化技术名> —— 对应章节 <ChXX>
瓶颈类型：Compute-bound / Memory-bound / Scheduling-bound / Capacity-bound
学习目标：完成本实验后应能说明 —— 问题现象、根因、优化原理、trade-off、何时不该用

Step 1 环境搭建
  - 单机单卡 / 单机多卡 / 多机多节点（明确标注，这决定了教学环境的复杂度和成本）
  - 模型 / GPU 数量与型号 / 框架版本（锁定版本，避免学员基线对不上讲师基线）
  - 本实验选用的压测工具（按技术点选择，说明为什么选它而不是别的）

Step 2 性能脚本加压，制造瓶颈
  - 命令（未优化配置）
  - 预期现象（如何判断"瓶颈确实出现了" —— 具体指标阈值或失败模式）

Step 3 执行优化措施
  - 命令/配置改动（只改这一项，其余不变，保证对比干净）

Step 4 重跑相同性能脚本
  - 完全相同的命令，仅配置项不同

Step 5 对比与总结
  - 指标对比表（优化前 / 优化后 / 变化幅度）
  - 讨论：为什么会变化？引入了什么代价？什么场景下这个优化不该用/收益有限？
```

---

## 样板一：PagedAttention（Memory-bound，对应 Ch16 Decode 优化方法）

**瓶颈类型：** Memory-bound / 显存碎片

**学习目标：** 说明 KV Cache 显存碎片如何限制并发上限；解释 PagedAttention 用分页管理
消除碎片的机制；量化对最大并发数和吞吐的影响。

**Step 1 环境搭建：** 单机单卡即可。固定模型（如 Llama-3.1-8B-Instruct）、固定 GPU 型号、
固定 vLLM 版本。压测工具选 `vllm bench serve`（vLLM 原生，天然贴合 vLLM 的
`--block-size` 配置项，不需要额外适配）；脚本内建 warmup 若干轮 + 多次重复取 p50/p95，
避免 GPU 抖动把配置差异误判成随机噪音。

**Step 2 制造瓶颈**：用较小/不合理的 `--block-size` 或关闭分页管理的基线配置启动服务，
用 `vllm bench serve` 逐步提高并发请求数加压。预期现象：显存碎片导致有效可用 KV Cache
远小于理论显存容量，达到某个并发数前就开始 OOM / 请求被拒绝，最大并发数明显低于预期。

**Step 3 优化措施**：切换为标准 PagedAttention 分页配置（如 `--block-size 16`）。

**Step 4 重跑**：完全相同的 `vllm bench serve` 命令和加压曲线。

**Step 5 对比总结**：对比表列 —— 最大可支撑并发数 / 显存利用率 / OOM次数 / 吞吐(tokens/s)。
总结：分页消除外部碎片，代价是分页间接寻址的小额开销（通常可忽略，收益远大于成本）；
但如果显存本身就很宽裕、并发压力很低，这项优化的收益不明显——这就是"什么场景不该用"的讨论点。

---

## 样板二：从 Static 到 Dynamic 到 Continuous Batching（Scheduling-bound，对应 Ch20 Serving 优化方法）

**瓶颈类型：** Scheduling-bound / GPU 空闲

**学习目标：** 区分三档调度粒度——Static Batching（固定 batch size，等整批算完才开始下一批）、
Dynamic Batching（在一个时间窗口内动态攒批，但仍要等这一批算完）、Continuous Batching（新请求
可以在任意一步随时加入/退出正在跑的 batch）；说明每往前一档，GPU 空闲和尾延迟分别改善多少；
理解为什么"能不能动态攒批"和"能不能随时插入正在执行的 batch"是两个不同层次的问题，不能混为一谈。

**Step 1 环境搭建：** 单机单卡即可。模型/GPU 版本锁定。**这三档没法在同一个框架里靠一个开关切换**
——现代主流推理框架（如 vLLM）本身就是 continuous batching 原生设计，不提供退回 static/dynamic
的开关，这一点要对学员讲清楚，不能假装是"改一个参数"的事。实验环境需要两套工具：
- Static / Dynamic 两档用一个可控的最小化参照实现（例如 Triton Inference Server 的 dynamic
  batcher，或者一个自己写的、按时间窗口攒批的最小调度器包一层同一个模型）——Static 版本把窗口
  设成"必须等一个完整 batch 凑满"，Dynamic 版本改成"时间窗口到了就出批，不强求凑满"。
- Continuous 这一档用 `vllm bench serve` 打同一个模型。
- 压测请求分布**要长短混合**（模拟真实流量），这样"等最长请求"的问题才会暴露出来，仅调高并发数不够。
- **对比口径的限制**：跨工具对比会引入框架本身的实现差异（不完全是纯粹的调度算法差异），这一点
  要在最终报告里明确写出来，不能把"框架A比框架B快"直接等同于"batching策略A比策略B好"。

**Step 2 制造瓶颈（Static）**：用 Static Batching 参照实现（固定 batch size，等整批凑满/算完
才开始下一批），跑长度分布不均的混合请求。预期现象：短请求要等同批次里的长请求结束才能返回，
GPU 利用率曲线出现明显空闲区间（等凑批的间隙），p95/p99 延迟远高于 p50。

**Step 3 第一次优化（升级到 Dynamic）**：切到 Dynamic Batching 参照实现（时间窗口到了就出批，
不强求凑满），重跑相同请求分布。预期现象：等凑批的空闲有所缓解（不用死等固定数量的请求到齐），
但同批次内"短请求等长请求算完"的问题依然存在——这一档解决的是"攒批要不要死等"，不是"批内调度"。

**Step 4 第二次优化（升级到 Continuous）**：切到 vLLM，开启 continuous batching，重跑相同请求
分布。预期现象：短请求不再被同批次的长请求拖住，GPU 利用率曲线的空闲区间基本消失。

**Step 5 对比总结**：三档对比表列 —— GPU 利用率 / 吞吐(TPS) / p50 vs p95/p99 延迟 / 队列等待时间，
Static / Dynamic / Continuous 各一行。总结：Dynamic 相对 Static 改善的是"攒批延迟"，Continuous
相对 Dynamic 改善的是"批内调度粒度"，两次提升的根因不同，不能笼统地说"batching 优化了"就完事；
讨论点：请求长度越均匀，Continuous 相对 Dynamic 的边际收益越小（因为"等长请求"这个问题本来就不
明显）——这是判断"什么场景收益有限"的具体依据。

---

## 样板三：FlashAttention / FlashInfer（Compute-bound，对应 Ch12 Prefill 优化方法）

**瓶颈类型：** Compute-bound / attention 访存效率

**学习目标：** 说明 attention 计算如果把中间的 attention score 矩阵完整物化（materialize）到 HBM，会带来大量非必要的显存读写；解释 FlashAttention / FlashInfer 用分块计算 + 在线 softmax 避免物化中间矩阵的机制；量化对长 prompt TTFT 和 Tensor Core 利用率的影响。

**Step 1 环境搭建：** 单机单卡即可。固定模型（如 Llama-3.1-8B-Instruct）、固定 GPU 型号、固定 vLLM 版本。压测工具选 `vllm bench serve` 控制 prompt 长度分布（需要能拉出 4K-8K token 级别的长 prompt）；辅助用 Nsight Compute 采集一次 attention kernel 的 Tensor Core 利用率和 HBM 带宽占用，作为"计算效率"而非只看端到端延迟的独立证据（呼应 Chapter 1 GPU 架构基础、Chapter 7 Profiling Toolchain）。

**Step 2 制造瓶颈**：把 attention backend 降级为不做分块优化的实现（如显式指定 xformers / naive attention backend，而不是 vLLM 默认的 FlashAttention/FlashInfer），用长 prompt（4K-8K tokens）请求加压。预期现象：TTFT 随 prompt 长度增长的斜率明显变陡；Nsight Compute 显示 HBM 带宽占用高但 Tensor Core 利用率不高，说明大量时间花在读写中间矩阵而不是纯矩阵乘法计算。

**Step 3 优化措施**：切回 FlashAttention / FlashInfer backend（vLLM 较新版本通常默认已是这个配置，所以"未优化"状态本身就需要显式降级才能构造出来）。

**Step 4 重跑**：完全相同的长 prompt 请求集合和长度分布。

**Step 5 对比总结**：对比表列 —— TTFT / Tensor Core 利用率 / HBM 带宽占用 / attention kernel 耗时占端到端 Prefill 的比例。总结：FlashAttention 的收益随 prompt 变长而增大；短 prompt（几百 token 量级）场景下，分块本身的调度开销可能让收益不明显甚至打平——这是"何时不该用/收益有限"的具体依据，不是所有 Prefill 请求都值得为这项优化专门调优。

---

## 样板四：KV Quantization（Memory-bound，对应 Ch16 Decode 优化方法）

**瓶颈类型：** Memory-bound / 显存容量限制并发上限

**学习目标：** 说明 KV Cache 显存占用如何随并发数和上下文长度线性增长、进而限制最大并发；解释 KV Cache 量化（如 FP8）如何在可控的质量损失下压缩显存占用；量化对最大并发和吞吐的影响，并说明这是**有损**优化，验证环节必须包含质量检查，不能只看性能指标。

**Step 1 环境搭建：** 单机单卡即可。构造长上下文场景（如 4K-8K token 的多轮对话或长文档问答），这样 KV Cache 占用才会成为主要显存压力来源。压测工具选 `vllm bench serve` 控制并发梯度；**额外需要一个质量抽检脚本**（例如用 lm-eval 跑一个小规模任务，或对固定一批 prompt 做人工/自动化的输出对比），这是本实验区别于其他样板的地方——KV 量化和 PagedAttention 不同，PagedAttention 是无损优化，KV 量化不是。

**Step 2 制造瓶颈**：不开 KV Cache 量化（FP16/BF16 KV Cache），逐步提高并发直到接近显存上限，记录最大可支撑并发数。预期现象：并发到某个点后开始 OOM 或请求被拒绝，而此时 GPU 计算并未打满，瓶颈明显是显存容量而不是算力。

**Step 3 优化措施**：开启 KV Cache 量化（如 `--kv-cache-dtype fp8`）。

**Step 4 重跑**：完全相同的并发梯度和上下文长度设置，**同时跑一遍质量抽检脚本**。

**Step 5 对比总结**：对比表列 —— 最大可支撑并发数 / 显存占用 / 吞吐 / 质量抽检结果（不能省略这一列）。总结：量化收益在长上下文、高并发场景最明显；短上下文/低并发场景本身显存压力就不大，量化收益有限，而精度损失的风险始终存在——这是判断"什么场景不该用"时必须把质量因素放进权衡的具体例子。

---

## 样板五：Prefix Cache（单节点前缀复用，Memory-bound，对应 Ch16 Decode 优化方法）

**瓶颈类型：** Memory-bound / 重复计算

**学习目标：** 说明多轮对话、共享 system prompt 等场景下，如果不复用前缀，每个请求都要重新完整 Prefill 相同的前缀部分；解释 Prefix Cache 如何复用已经计算过的 KV Cache 避免重复 Prefill；量化对 TTFT 和实际 Prefill token 处理量的影响。

**Step 1 环境搭建：** 单机单卡即可。构造有大量共享前缀的请求集合（例如固定的长 system prompt 或检索增强的固定上下文 + 不同的用户提问，模拟企业问答服务的典型形态）。压测工具用 `vllm bench serve` 或自定义脚本按顺序发送这批共享前缀的请求。

**Step 2 制造瓶颈**：关闭 prefix caching，发送共享前缀请求序列。预期现象：每个请求的 TTFT 都要付出完整 system prompt 的 Prefill 开销，即使前缀和上一个请求完全相同；Prefill token 处理总量随请求数线性增长，没有任何复用。

**Step 3 优化措施**：开启 prefix caching（如 `--enable-prefix-caching`；注意较新版本的 vLLM 可能默认开启，所以 Step 2 的"关闭"需要显式验证，不能想当然认为默认就是关的）。

**Step 4 重跑**：完全相同的共享前缀请求序列。

**Step 5 对比总结**：对比表列 —— 平均 TTFT / 前缀命中率 / 实际 Prefill token 处理量。总结：收益直接取决于请求之间的前缀重复率；如果 workload 里每个请求的 prompt 都互不相同（没有共享前缀），Prefix Cache 拿不到收益，反而多了一点缓存管理和淘汰策略的开销——这是"何时不该用"的判断依据。

---

## 样板六：跨副本缓存感知路由（Cache-Aware Routing，Ch16 Decode 优化方法）

**瓶颈类型：** Memory-bound（跨机场景）/ 路由策略导致缓存失效

**学习目标：** 说明多副本部署下，如果路由是轮询或随机的，即使每个副本单独都开了 Prefix Cache，前缀命中率也会被打散（请求可能被发到从未处理过该前缀的副本）；解释缓存感知路由（按前缀树/一致性哈希路由到"曾经处理过这个前缀"的副本）如何在多副本场景下恢复前缀复用的收益。

**Step 1 环境搭建：** 多机多节点（教学演示可以退化为同机多卡、每张卡各自绑定一个独立 vLLM 副本来模拟"多副本"，但要明确标注这是简化，真实生产场景是跨机部署）。需要一个支持缓存感知路由的路由层（如 SGLang 的 RadixAttention 路由器，或自建的一致性哈希路由脚本）。压测工具用自定义脚本发送前缀密集的请求序列，并记录每个请求实际被路由到了哪个副本。

**Step 2 制造瓶颈**：用随机/轮询路由 + 多副本，发送前缀密集的请求序列。预期现象：即使每个副本单独开了 Prefix Cache，整体前缀命中率仍然很低（接近"没开 cache"的水平），因为请求被打散到了不同副本。

**Step 3 优化措施**：切换为缓存感知路由（按前缀一致性哈希路由）。

**Step 4 重跑**：完全相同的请求序列和请求分布。

**Step 5 对比总结**：对比表列 —— 整体前缀命中率 / 平均 TTFT / 吞吐。总结：收益高度依赖前缀密集度和副本数量——副本数很少（如只有 2 个）或前缀重复率本身就低时，收益有限；同时要讨论这项优化的副作用：按前缀路由可能导致某些副本负载明显高于其他副本（负载倾斜），是"引入了什么代价"的具体例子。

---

## 样板七：Kernel-Level Optimization（CUDA Graph / Kernel Fusion / Persistent Kernel，Scheduling-bound，Ch16 Decode 优化方法）

**瓶颈类型：** Scheduling-bound / CPU 端 kernel launch 开销

**学习目标：** 说明 Decode 阶段逐 token 生成时，每一步 batch 通常较小但要发起一长串小 kernel，CPU 端逐个发起这些 kernel 的启动和同步开销会占到总耗时的显著比例；解释 CUDA Graph 通过捕获并重放固定执行图消除重复启动开销的机制；量化对 TPOT 和 CPU-GPU timeline 空隙的影响。

**Step 1 环境搭建：** 单机单卡即可。压测工具用 `vllm bench serve` 关注 TPOT，配合 Nsight Systems 采集一段 Decode 过程的 CPU-GPU timeline，直接观察 kernel 之间的空隙（呼应 Chapter 1 硬件基础、Chapter 15 CPU Dispatch / Kernel Launch Overhead 的根因分析）。

**Step 2 制造瓶颈**：关闭 CUDA Graph（如 `--enforce-eager`），跑 Decode 密集场景（较高并发、较短单步 batch）。预期现象：Nsight Systems timeline 上能看到明显的 GPU 空闲间隙（在等 CPU 发起下一个 kernel），TPOT 高于按显存带宽粗算的理论值。

**Step 3 优化措施**：开启 CUDA Graph（移除 `--enforce-eager`，多数框架默认就是开启状态，所以 Step 2 的"关闭"是刻意构造的对照组）。

**Step 4 重跑**：完全相同的 Decode 密集压测脚本。

**Step 5 对比总结**：对比表列 —— TPOT / GPU 空闲间隙占比 / 每步 kernel launch 次数。总结：CUDA Graph 要求执行图的 shape 相对固定，遇到高度动态的 batch 组成（每步请求数和 KV Cache 布局都在变）时收益会打折扣，甚至可能因为频繁重新 capture 而得不偿失；graph capture 本身也有一次性开销和额外显存占用，低频/极小规模请求场景不一定划算——这是"何时不该用"的具体判断依据。

---

## 样板八：投机解码 Speculative Decoding / MTP / Medusa / EAGLE（Ch16 Decode 优化方法）

**瓶颈类型：** Memory-bound（间接）/ 逐 token 串行生成的次数太多

**学习目标：** 说明标准 autoregressive decode 本质上是串行的，每生成一个 token 都要完整走一次模型前向；解释投机解码用小模型/draft head"一次猜多步、模型验一步"来减少昂贵前向次数的机制；量化**接受率（acceptance rate）**如何决定这项技术是否真的省时间——这是本实验最核心的变量。

**Step 1 环境搭建：** 单机单卡（如果 draft 模型足够小可以和目标模型共享显存；如果 draft 模型需要独立资源，视具体框架要求可能需要单机多卡）。需要目标模型 + draft 模型，或者已经内置 MTP / EAGLE head 的模型 checkpoint。压测工具用 `vllm bench serve` 关注 TPOT，同时记录框架输出的投机解码接受率指标。

**Step 2 制造瓶颈**：先关闭投机解码，跑标准 decode，记录 baseline TPOT，**同时准备两类 prompt**：一类可预测性高（如代码续写、模板化回复），一类可预测性低（如开放式创意写作）——这一步的"加压"不是加并发，而是准备好后续对比所需的两类 workload。

**Step 3 优化措施**：开启投机解码（如配置 `--speculative-model` 等参数，具体写法以框架版本文档为准）。

**Step 4 重跑**：分别用"可预测性高"和"可预测性低"两类 prompt 各跑一遍，完全相同的其余配置。

**Step 5 对比总结**：对比表列 —— TPOT / 接受率 / 端到端吞吐，按两类 prompt 分别列。总结：接受率是决定成败的关键——可预测文本接受率高，投机解码收益明显；开放式创意生成接受率低，draft 和验证的额外开销可能抵消甚至超过收益。这是"何时不该用"最核心也最容易被忽视的一条：这项技术不是无脑开启就有收益的开关，必须先了解自己的 workload 属于哪一类。

---

## 样板九：Chunked Prefill（Scheduling-bound，Ch20 Serving 优化方法）

**瓶颈类型：** Scheduling-bound / 长 Prefill 阻塞其他请求的 Decode

**学习目标：** 说明一次性执行的长 prompt Prefill 会独占 GPU 较长时间，阻塞同批次里正在等待 Decode 的其他请求，拖慢它们的 TPOT；解释 Chunked Prefill 把长 Prefill 拆成多个小块、与其他请求的 Decode 交替执行的机制；量化对混合负载下 P95/P99 TPOT 的影响。

**Step 1 环境搭建：** 单机单卡即可。构造混合负载：少量长 prompt 请求（如 8K tokens 量级）+ 大量短交互式请求同时并发（这里的"长短混合"和样板二 Continuous Batching 的加压方式类似，但样板二关注的是输出长度混合，这里关注的是**输入长度**混合，两者根因不同，实验不能混为一谈）。压测工具用 `vllm bench serve` 控制并发下的 prompt 长度分布。

**Step 2 制造瓶颈**：关闭 chunked prefill，用上述混合负载加压。预期现象：短请求的 Decode 会被长请求的 Prefill 打断，短请求的 P95/P99 TPOT 出现明显尖峰，即使整体 GPU 利用率已经很高。

**Step 3 优化措施**：开启 chunked prefill（如 `--enable-chunked-prefill`；较新版本的 vLLM 可能默认开启，同样需要显式验证 baseline 状态）。

**Step 4 重跑**：完全相同的混合负载。

**Step 5 对比总结**：对比表列 —— 短请求 P50/P95/P99 TPOT / 整体吞吐 / 长请求自身 TTFT（用来说明代价）。总结：Chunked Prefill 用略微拉长长请求自身的 TTFT，换取短请求 TPOT 的稳定性；如果 workload 里全是长 prompt 或全是短 prompt（没有长短混合的场景），这项优化的收益就不明显。**补充讨论（Admission Control）**：Chunked Prefill 解决的是"已经进入执行的请求之间如何不互相拖累"，Admission Control 解决的是更前一层的问题——"要不要让这个请求现在就进来"，两者是互补而非替代关系，可以在本实验的讨论环节延伸对比：如果连准入控制都没有，Chunked Prefill 也救不了一个已经全面过载的系统。

---

## 样板十：Prefill-Decode 分离（PD Disaggregation，Capacity-bound，Ch20 Serving 优化方法，多机）

**瓶颈类型：** Capacity-bound / Prefill 和 Decode 在同一组 GPU 上争抢资源

**学习目标：** 说明 Prefill（计算密集）和 Decode（显存带宽密集）混跑在同一组 GPU 上时会互相干扰——即使有 Chunked Prefill 缓解，长 Prefill 仍然会挤占 Decode 的执行窗口；解释 PD 分离把两个阶段拆到独立 GPU 池、通过 KV Cache 跨机传输衔接的架构；量化对 **goodput**（同时满足 TTFT 和 TPOT SLO 的有效吞吐，而不是单纯吞吐）的影响。

**Step 1 环境搭建：** 多机多节点——这是 13 个样板里教学成本最高的一个，需要至少两组独立 GPU 池（一组做 Prefill worker，一组做 Decode worker）和高速网络（理想情况下是 RDMA）传输 KV Cache，具体依赖 vLLM 的 disaggregated serving 支持或 NVIDIA Dynamo 等编排层，版本和可用性以实际环境为准。压测工具需要专门统计 goodput 口径（同时统计 TTFT SLO 达成率和 TPOT SLO 达成率，而不是只看平均延迟），可以用 genai-perf 或框架自带的 disagg benchmark 脚本。

**Step 2 制造瓶颈**：用传统混合部署（Prefill 和 Decode 在同一组 GPU 上跑，配合 Chunked Prefill 已经是能做到的最优配置），压测高并发的长短混合负载。预期现象：GPU 利用率已经很高，但仍有相当比例的请求违反 TTFT 或 TPOT 的 SLO，goodput 明显低于原始吞吐数字给人的印象。

**Step 3 优化措施**：切换为 PD 分离部署（独立 Prefill 池 + Decode 池 + KV Cache 跨机传输）。

**Step 4 重跑**：完全相同的负载曲线和 SLO 定义。

**Step 5 对比总结**：对比表列 —— Goodput / TTFT SLO 达成率 / TPOT SLO 达成率 / 总 GPU 数量下的资源利用效率。总结：PD 分离的代价是 KV Cache 跨机传输的网络开销、更复杂的资源池管理，以及两组资源池各自的容量规划问题；小规模部署（如单机 8 卡以内、请求量不足以撑起两个独立资源池）收益可能不如混合部署简单直接——这是"何时不该用"的关键点，也是为什么本样板被放在课程后期或作为选修实验的原因。

---

## 样板十一：Tensor Parallel / Pipeline Parallel（Capacity-bound，Ch24 Scalability 优化方法 · Scale-up，多卡）

**瓶颈类型：** Capacity-bound / 单卡装不下模型或单卡算力不够

**学习目标：** 说明当模型显存需求超过单卡容量、或单卡算力无法达到目标吞吐时，如何用 Tensor Parallel（层内切分）和 Pipeline Parallel（层间切分）把计算分摊到多卡；量化通信开销（All-Reduce / 流水线气泡）对吞吐的影响，理解"卡数翻倍不等于吞吐翻倍"的原因。

**Step 1 环境搭建：** 单机多卡（至少 2 卡，理想情况下能对比 TP=2 和 TP=4）。选一个单卡装不下、或选一张较小显存的卡型号来人为制造"装不下"场景的模型（这样才能观察到从"根本跑不起来"到"能跑但要看 scaling 效率"的完整过程）。压测工具用 `vllm bench serve`，额外用 `nvidia-smi` 或 NCCL 相关工具观察卡间通信占用。

**Step 2 制造瓶颈**：从最小可行并行度开始（如果模型装不下单卡，最小可行并行度本身就是"瓶颈"的一部分——先让学员看到不切分根本跑不起来）。

**Step 3 优化措施**：逐步提高 TP / PP 并行度，对比不同配置。

**Step 4 重跑**：完全相同的压测脚本，只改并行度配置。

**Step 5 对比总结**：对比表列 —— 卡数 / 吞吐 / 相对理论线性 scaling 的效率百分比 / 通信开销占比。总结：Tensor Parallel 适合层内并行度高、卡间带宽好（如 NVLink）的场景；Pipeline Parallel 适合跨机场景（单次通信量小但有流水线气泡）；如果模型单卡本来就装得下、吞吐也够用，盲目上多卡并行反而会因为通信开销让效率不升反降——这是"何时不该用"的判断依据。

---

## 样板十二：MoE Expert Parallel（Capacity-bound + Scheduling-bound，Ch24 Scalability 优化方法 · Scale-up，多卡）

**瓶颈类型：** Capacity-bound（激活参数与总参数的显存模型）+ Scheduling-bound（All-to-All 通信与专家负载不均）

**学习目标：** 说明 MoE 模型"按激活参数而非总参数"计算显存和成本的特性；解释 Expert Parallel 如何把不同专家分布到不同 GPU；量化 All-to-All 通信开销和专家负载不均（routing skew）对吞吐的影响。

**Step 1 环境搭建：** 多机多卡（MoE 模型通常参数量较大，需要多卡；专家并行实验还需要能构造出会触发负载不均的输入分布）。选一个开源 MoE 模型（如 DeepSeek 系列或 Mixtral 系列）。压测工具用 `vllm bench serve` 加一份专家路由分布统计——**这是本样板和其他样板最大的不同**：多数框架不一定直接暴露"每个专家被调用了多少次"这个指标，可能需要自行插桩或读取框架日志，实验设计时要如实标注这一步的额外工程量。

**Step 2 制造瓶颈**：先用均匀/多样化的输入分布跑一遍，记录 baseline 吞吐和各专家调用分布（通常相对均衡）；再构造倾斜输入分布（比如让大量同类型 query 系统性地路由到少数专家），观察吞吐下降和 All-to-All 通信占比上升。

**Step 3 优化措施**：对比"无负载均衡策略"与"开启专家负载均衡/路由策略"两种配置。

**Step 4 重跑**：用相同的倾斜输入分布，分别在两种配置下跑。

**Step 5 对比总结**：对比表列 —— 吞吐 / 专家调用分布的不均衡系数（如最大值/平均值）/ All-to-All 通信耗时占比。总结：这是 13 个技术点里复现难度最高的一个——负载不均需要构造特定的输入分布才能稳定复现，不是简单调一个开关。**降级方案**：如果学员环境没有 MoE 模型或多卡资源，可以把这个实验降级为"读一份真实生产环境的专家负载分布日志，做案例分析"，而不强求亲手复现，这个降级选项需要在课程设计时明确标注，不能假装每个人都能跑起完整实验。

---

## 样板十三：Scale-out（Capacity-bound，Ch24 Scalability 优化方法 · Scale-out，多机）

**瓶颈类型：** Capacity-bound / 单实例容量到顶

**学习目标：** 说明单实例容量到顶后，横向扩容（加副本）如何提升总吞吐；解释负载均衡策略选择（轮询 vs 最少连接 vs 缓存感知，呼应样板六的跨副本路由）如何影响扩容效果；理解 autoscaling 的触发指标选择（QPS / GPU 利用率 / 队列长度）各自的滞后性和误判风险。

**Step 1 环境搭建：** 多机多节点（至少 2 个独立实例，可选配一个 autoscaler，如 K8s HPA 或一个简化的自定义扩缩容脚本）。压测工具用一个**逐步爬升的负载生成器**（而不是固定并发），模拟真实流量增长曲线，这样才能观察到"扩容触发"和"扩容生效"之间的时间差。

**Step 2 制造瓶颈**：固定单实例，用爬升负载压测直到打满容量。预期现象：超过容量后请求排队时间陡增，P99 延迟失控，即使还没到物理意义上的 OOM。

**Step 3 优化措施**：开启多副本 + 负载均衡 +（可选）autoscaling。

**Step 4 重跑**：完全相同的爬升负载曲线。

**Step 5 对比总结**：对比表列 —— 单实例 vs 多实例的容量上限 / 扩容生效延迟（从触发到新实例可用的时间）/ 扩容期间的请求失败率或延迟毛刺。总结：autoscaling 有固有的滞后性（新实例启动 + 模型加载需要时间，不是秒级生效）；指标选择不当（比如只看 CPU 利用率而不看 GPU/队列长度）会导致扩容触发太晚——这是"证明扩容方案真的有效"环节里最容易被忽视的坑，也是负载均衡策略（样板六提到的缓存感知路由）为什么要和扩容策略一起设计的原因：新扩出来的实例没有历史缓存，如果路由策略只按缓存命中率分配流量，新实例可能长期吃不到流量，扩容等于白扩。

---

## 已解决的设计问题（不再是待定项）

- 压测工具：按技术点各选，多数样板复用 `vllm bench serve`（vLLM 原生、天然贴合 vLLM 配置项）；MoE 专家负载分布统计、PD 分离的 goodput 口径、Scale-out 的扩容生效延迟，这三类指标框架不一定直接暴露，需要额外插桩或换用 genai-perf 等专门工具，已在对应样板里单独说明。样板二（Static/Dynamic/Continuous Batching 三档对比）是唯一需要**跨工具对比**的样板——vLLM 只原生支持 continuous batching，static/dynamic 两档要用 Triton dynamic batcher 或自建的最小调度器，报告里必须注明这个限制，不能把框架实现差异当成纯粹的调度策略差异。
- 环境复杂度：每个实验 Step 1 都显式声明了单机单卡 / 单机多卡 / 多机多节点，13 个样板里 PD 分离、Tensor/Pipeline Parallel、MoE Expert Parallel、Scale-out、跨副本缓存感知路由这 5 个需要多卡或多机，教学成本最高的是 PD 分离（多机 + 高速网络 + 编排层）。
- 故障注入工具：确认不引入额外工具，"用性能脚本加压 + 配置降级"这个方式对全部 13 个技术点都够用；MoE 的负载不均需要构造特定输入分布才能稳定复现，但仍然是"用输入构造压力"，没有引入新的注入框架。

## 剩余待做

- MoE 专家并行样板给出了"读日志做案例分析"的降级方案，但降级版的具体案例素材（一份真实生产专家负载分布日志）还没有落实来源。
- PD 分离样板依赖的具体框架能力（vLLM disaggregated serving / NVIDIA Dynamo 等）版本可用性需要在正式制作讲义前重新核实一遍，本文档写作时（2026-09）的说法可能会过时。
- 每个样板目前只有"预期现象"的定性描述，还没有配套具体的指标阈值（比如"P99 TPOT 超过多少毫秒算触发瓶颈"），正式制作讲义时需要在真实硬件上先跑一遍拿到具体数字。
- 样板二 Static/Dynamic Batching 这两档具体用哪个参照实现（Triton dynamic batcher，还是自建的最小时间窗口调度器）还没有定，两个选项的教学成本和可控性不一样（Triton 是现成工具但要单独学它的配置；自建调度器可控性高但要维护一份教学专用代码），需要在正式制作讲义前拍板。
