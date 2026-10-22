---
layout: page
title: LLM 推理性能工程实战
description: 面向推理系统的性能优化实战——看懂推理系统、定位真实瓶颈、选对优化手段、用数据验证收益
---
<div class="landing">
    <main>
    <header class="hero">
      <div class="wrap">
        <div class="eyebrow"><span class="sep"></span>LLM Inference Performance</div>
        <h1>LLM Performance Engineering</h1>
        <p class="lede">面向推理系统的性能优化实战。不背一份优化技巧清单，而是学会像系统工程师一样思考：看懂推理系统、定位真实瓶颈、选对优化手段、用数据验证收益。</p>
        <div class="cta-row">
          <a class="btn primary" href="preface.html">开始阅读 · 前言</a>
          <a class="btn ghost" href="part01.html">跳到 Part 1</a>
          <a class="btn ghost" href="reference/glossary.html">术语表</a>
        </div>
        <div class="stats">
          <div class="stat"><div class="n">7</div><div class="l">课程模块 Part</div></div>
          <div class="stat"><div class="n">30</div><div class="l">章节 Chapter，另有开篇</div></div>
          <div class="stat"><div class="n">13+</div><div class="l">动手实验，逐项验证</div></div>
        </div>
      </div>
    </header>
    <section id="method">
      <div class="wrap">
        <div class="section-head">
          <div class="kicker">课程方法论</div>
          <h2>先系统，后技术；先分析，后优化</h2>
          <p>不按 FlashAttention、PagedAttention、Speculative Decoding 这样的技术清单组织，也不按 TTFT、TPOT 这样的单一指标组织，而是以"推理系统"本身为主线——建立一套可迁移的思维方式，面对任何模型、框架和硬件都能用。</p>
        </div>
        <div class="method-flow">
          <span class="step">理解系统</span><span class="arrow">→</span>
          <span class="step">理解瓶颈</span><span class="arrow">→</span>
          <span class="step">定位瓶颈</span><span class="arrow">→</span>
          <span class="step">优化方案</span><span class="arrow">→</span>
          <span class="step">验证收益</span>
        </div>
        <div class="principle-grid">
          <div class="principle"><div class="idx">01</div><h4>先系统，后技术</h4><p>先建立推理系统和请求生命周期的整体认知，再进入具体技术专题，技术点不会和系统位置脱节。</p></div>
          <div class="principle"><div class="idx">02</div><h4>先分析，后优化</h4><p>不从"有哪些优化技术"出发，而从"当前系统的瓶颈是什么"出发——完成 Benchmark、Profiling 和根因分析后，才选择优化方案。</p></div>
          <div class="principle"><div class="idx">03</div><h4>指标必谈 Trade-off</h4><p>TTFT、TPOT、TPS、显存、成本并非相互独立，不把某项技术简单归到单一指标，而是分析它对多个指标的共同影响。</p></div>
          <div class="principle"><div class="idx">04</div><h4>优化必须验证</h4><p>每项优化都要通过可重复 Benchmark 验证，不能仅凭原理或单次运行结果判断收益。</p></div>
        </div>
      </div>
    </section>
    <section id="story">
      <div class="wrap">
        <div class="section-head">
          <div class="kicker">先睹为快</div>
          <h2>一次请求，到底经历了什么</h2>
          <p>在拆开每一个技术点之前，先用一个真实场景把整条链路走一遍。</p>
        </div>
        <div class="story">
          <div class="scenario">场景：一个基于 vLLM 部署的 Llama-3.1-8B-Instruct 聊天服务，用户输入 "帮我写一段快速排序的 Python 代码，并解释一下时间复杂度。"</div>
          <ol>
            <li><span class="step-n">01</span><span class="step-t">请求到达服务入口，如果系统正忙，会先排一小会儿队 —— 这就是 <b>Queue</b>。</span></li>
            <li><span class="step-n">02</span><span class="step-t">系统把这句话整段"读"一遍，这个阶段叫 <b>Prefill</b>，读完后用户看到第一个字冒出来。</span></li>
            <li><span class="step-n">03</span><span class="step-t">模型进入逐字生成，叫 <b>Decode</b>——为避免重复计算前文，中间结果被缓存为 <b>KV Cache</b>，显存不够时会成为重要瓶颈。</span></li>
            <li><span class="step-n">04</span><span class="step-t">文字一个接一个蹦出来，而不是等全部写完再显示——这叫<b>流式输出</b>。</span></li>
            <li><span class="step-n">05</span><span class="step-t">代码和解释生成完毕，模型输出停止信号，请求结束。</span></li>
          </ol>
          <div class="tier-label">但这只是一个用户 —— 需求继续往上走</div>
          <ol>
            <li class="tier-up"><span class="step-n">06</span><span class="step-t">同一时间，成百上千个像这样的用户一起在问问题呢？——请求要排队、要打包成批次处理，GPU 要一直保持忙碌、不能让谁被落下，这是 <b>Serving 优化</b>要回答的问题。</span></li>
            <li class="tier-up"><span class="step-n">07</span><span class="step-t">这个服务要在生产环境里长期扛住这样的流量，还要压低每一次回答的成本呢？——要决定用多少张卡、怎么分摊负载、什么时候该加机器，这是 <b>Scalability 优化</b>要回答的问题。</span></li>
          </ol>
          <div class="payoff">"等多久看到第一个字""字与字蹦出来快不快""这台机器同时能服务多少用户""一千个并发要花多少钱"——这些问题背后，分别对应具体的性能指标和具体的软硬件瓶颈。整门课，就是把从单个请求到生产集群的每一层需求拆开，讲清楚原理、讲清楚怎么测、讲清楚怎么优化。</div>
        </div>
      </div>
    </section>
    <section id="curriculum">
      <div class="wrap">
        <div class="section-head">
          <div class="kicker">课程内容</div>
          <h2>7 个模块，沿着推理系统的生命周期展开</h2>
          <p>从一个请求建立系统认知，先把测量、观测和根因分析的方法立住，再依次进入 Prefill、Decode、Serving 与应用链路、容量与生产工程，最后用一个综合项目把前面的内容用在一件事上。</p>
        </div>
        <details class="part-card" id="part0">
          <summary>
            <span class="pn">开篇</span>
            <span class="pt"><h3>推理性能的三条规律</h3><div class="pq">不启动服务、不写代码：从价目表上的三个差价讲起，推荐先读，跳过也不影响后面各章</div></span>
            <span class="pc">Ch 0</span>
            <span class="chev">▸</span>
          </summary>
          <div class="chapters">
            <a class="ch-row" href="ch00/ch00.html"><span class="cn">00</span><span class="ct">延迟、成本和质量为什么总在互相拉扯<span class="desc">写比读贵，算过的不必重算；批量摊薄搬运，满载拉长等待；只有有用的产出才算数</span></span></a>
          </div>
        </details>
        <details class="part-card" id="part1" open>
          <summary>
            <span class="pn">Part 1</span>
            <span class="pt"><h3>从一个请求理解推理系统</h3><div class="pq">读完交付：一次真实调用的完整记录与统一的指标口径</div></span>
            <span class="pc">Ch 1–5</span>
            <span class="chev">▸</span>
          </summary>
          <div class="chapters">
            <a class="ch-row" href="ch01/ch01.html"><span class="cn">01</span><span class="ct">第一个 LLM 服务<span class="desc">启动最小 vLLM 服务，跑通同步与流式调用，留下第一份运行记录</span></span></a>
            <a class="ch-row" href="ch02/ch02.html"><span class="cn">02</span><span class="ct">真实请求生命周期<span class="desc">请求在系统里如何流动</span></span></a>
            <a class="ch-row" href="ch03/ch03.html"><span class="cn">03</span><span class="ct">Transformer 生成机制<span class="desc">模型怎样生成下一个 token</span></span></a>
            <a class="ch-row" href="ch04/ch04.html"><span class="cn">04</span><span class="ct">LLM Serving 架构<span class="desc">谁负责请求链路的哪一段</span></span></a>
            <a class="ch-row" href="ch05/ch05.html"><span class="cn">05</span><span class="ct">性能指标与延迟预算<span class="desc">先统一口径，再比较数字</span></span></a>
          </div>
        </details>
        <details class="part-card" id="part2">
          <summary>
            <span class="pn">Part 2</span>
            <span class="pt"><h3>测量、观测与根因分析</h3><div class="pq">读完交付：一份可复现的 Baseline 和一份根因报告</div></span>
            <span class="pc">Ch 6–10</span>
            <span class="chev">▸</span>
          </summary>
          <div class="chapters">
            <a class="ch-row" href="ch06/ch06.html"><span class="cn">06</span><span class="ct">LLM 工作负载建模<span class="desc">先说清楚“负载”是什么</span></span></a>
            <a class="ch-row" href="ch07/ch07.html"><span class="cn">07</span><span class="ct">Benchmark Design<span class="desc">让一个数字可以被复现</span></span></a>
            <a class="ch-row" href="ch08/ch08.html"><span class="cn">08</span><span class="ct">请求级可观测性<span class="desc">把一条请求的痕迹找齐</span></span></a>
            <a class="ch-row" href="ch09/ch09.html"><span class="cn">09</span><span class="ct">Profiling Toolchain<span class="desc">先问问题，再挑工具</span></span></a>
            <a class="ch-row" href="ch10/ch10.html"><span class="cn">10</span><span class="ct">Root Cause Analysis Lab<span class="desc">把现象收敛成可证伪的结论</span></span></a>
          </div>
        </details>
        <details class="part-card" id="part3">
          <summary>
            <span class="pn">Part 3</span>
            <span class="pt"><h3>Prefill 与上下文优化</h3><div class="pq">读完交付：长 Prompt 场景下的 TTFT 优化与同流量验证</div></span>
            <span class="pc">Ch 11–14</span>
            <span class="chev">▸</span>
          </summary>
          <div class="chapters">
            <a class="ch-row" href="ch11/ch11.html"><span class="cn">11</span><span class="ct">Prefill 工作机制与性能模型<span class="desc">首 token 之前发生了什么</span></span></a>
            <a class="ch-row" href="ch12/ch12.html"><span class="cn">12</span><span class="ct">长上下文与 RAG 上下文成本<span class="desc">塞进去的每一段都要付钱</span></span></a>
            <a class="ch-row" href="ch13/ch13.html"><span class="cn">13</span><span class="ct">Prefill 优化方法<span class="desc">四条路各自通向哪里</span></span></a>
            <a class="ch-row" href="ch14/ch14.html"><span class="cn">14</span><span class="ct">Prefill 优化实验<span class="desc">把预期拿去撞真实数据</span></span></a>
          </div>
        </details>
        <details class="part-card" id="part4">
          <summary>
            <span class="pn">Part 4</span>
            <span class="pt"><h3>Decode、KV Cache 与生成优化</h3><div class="pq">读完交付：TPOT、显存与质量的联合权衡结论</div></span>
            <span class="pc">Ch 15–19</span>
            <span class="chev">▸</span>
          </summary>
          <div class="chapters">
            <a class="ch-row" href="ch15/ch15.html"><span class="cn">15</span><span class="ct">Decode 工作机制与性能模型<span class="desc">为什么一次只算一个 token 反而更亏</span></span></a>
            <a class="ch-row" href="ch16/ch16.html"><span class="cn">16</span><span class="ct">KV Cache 管理与容量<span class="desc">显存决定你能同时服务多少人</span></span></a>
            <a class="ch-row" href="ch17/ch17.html"><span class="cn">17</span><span class="ct">量化与内存优化<span class="desc">用精度换容量和速度</span></span></a>
            <a class="ch-row" href="ch18/ch18.html"><span class="cn">18</span><span class="ct">生成与 Runtime 优化<span class="desc">不动精度的另外两条路</span></span></a>
            <a class="ch-row" href="ch19/ch19.html"><span class="cn">19</span><span class="ct">Decode 优化实验<span class="desc">五个指标要一起看</span></span></a>
          </div>
        </details>
        <details class="part-card" id="part5">
          <summary>
            <span class="pn">Part 5</span>
            <span class="pt"><h3>Serving、RAG 与 Agent 性能工程</h3><div class="pq">读完交付：一条真实应用链路的关键路径优化</div></span>
            <span class="pc">Ch 20–25</span>
            <span class="chev">▸</span>
          </summary>
          <div class="chapters">
            <a class="ch-row" href="ch20/ch20.html"><span class="cn">20</span><span class="ct">Scheduler 与 Continuous Batching<span class="desc">请求在进 GPU 之前发生了什么</span></span></a>
            <a class="ch-row" href="ch21/ch21.html"><span class="cn">21</span><span class="ct">流量治理与可靠性<span class="desc">顶不住的时候该怎么垮</span></span></a>
            <a class="ch-row" href="ch22/ch22.html"><span class="cn">22</span><span class="ct">Serving 架构选择与模型路由<span class="desc">这套东西到底该不该自己部署</span></span></a>
            <a class="ch-row" href="ch23/ch23.html"><span class="cn">23</span><span class="ct">RAG 性能工程<span class="desc">模型之外的那一半时间</span></span></a>
            <a class="ch-row" href="ch24/ch24.html"><span class="cn">24</span><span class="ct">Agent 性能工程<span class="desc">一次任务，几十次调用</span></span></a>
            <a class="ch-row" href="ch25/ch25.html"><span class="cn">25</span><span class="ct">Serving 与 Agent 综合实验<span class="desc">在一条真实链路上守住 SLO</span></span></a>
          </div>
        </details>
        <details class="part-card" id="part6">
          <summary>
            <span class="pn">Part 6</span>
            <span class="pt"><h3>容量、成本与生产工程</h3><div class="pq">读完交付：容量模型、回归门禁与上线检查清单</div></span>
            <span class="pc">Ch 26–29</span>
            <span class="chev">▸</span>
          </summary>
          <div class="chapters">
            <a class="ch-row" href="ch26/ch26.html"><span class="cn">26</span><span class="ct">容量、显存与成本模型<span class="desc">这套系统该配多少，花多少钱</span></span></a>
            <a class="ch-row" href="ch27/ch27.html"><span class="cn">27</span><span class="ct">多副本、路由与 Autoscaling<span class="desc">弹性为什么救不了突发</span></span></a>
            <a class="ch-row" href="ch28/ch28.html"><span class="cn">28</span><span class="ct">性能回归与发布门禁<span class="desc">让变慢在上线前就被拦住</span></span></a>
            <a class="ch-row" href="ch29/ch29.html"><span class="cn">29</span><span class="ct">Performance Review 与上线检查<span class="desc">上不上，谁来拍板</span></span></a>
          </div>
        </details>
        <details class="part-card" id="part7">
          <summary>
            <span class="pn">Part 7</span>
            <span class="pt"><h3>综合项目</h3><div class="pq">读完交付：一套可运行、可观测、可解释的完整服务</div></span>
            <span class="pc">Ch 30</span>
            <span class="chev">▸</span>
          </summary>
          <div class="chapters">
            <a class="ch-row" href="ch30/ch30.html"><span class="cn">30</span><span class="ct">端到端性能工程项目<span class="desc">把二十九章用在一件事上</span></span></a>
          </div>
        </details>
        <details class="part-card" id="appendix">
          <summary>
            <span class="pn">附录</span>
            <span class="pt"><h3>深入硬件与速查</h3><div class="pq">GPU 架构、CUDA、多 GPU、MoE、PD 分离，以及公式与术语速查</div></span>
            <span class="pc">A–F</span>
            <span class="chev">▸</span>
          </summary>
          <div class="chapters">
            <a class="ch-row" href="advanced/appendix-a-gpu-architecture/appendix-a.html"><span class="cn">A</span><span class="ct">GPU 性能心智模型<span class="desc">先看四类约束</span></span></a>
            <a class="ch-row" href="advanced/appendix-b-cuda-kernel/appendix-b.html"><span class="cn">B</span><span class="ct">CUDA、Kernel 与 Nsight<span class="desc">提纲登记中</span></span></a>
            <a class="ch-row" href="advanced/appendix-c-multi-gpu/appendix-c.html"><span class="cn">C</span><span class="ct">多 GPU 与分布式推理<span class="desc">提纲登记中</span></span></a>
            <a class="ch-row" href="advanced/appendix-d-moe/appendix-d.html"><span class="cn">D</span><span class="ct">MoE 模型的显存与计算<span class="desc">提纲登记中</span></span></a>
            <a class="ch-row" href="advanced/appendix-e-pd-disaggregation/appendix-e.html"><span class="cn">E</span><span class="ct">PD 分离架构<span class="desc">提纲登记中</span></span></a>
            <a class="ch-row" href="reference/appendix-f.html"><span class="cn">F</span><span class="ct">公式、前提与失效点速查<span class="desc">动笔之前先核对前提</span></span></a>
            <a class="ch-row" href="reference/glossary.html"><span class="cn">词</span><span class="ct">术语表<span class="desc">按全书出场顺序排列</span></span></a>
            <a class="ch-row" href="reference/environment.html"><span class="cn">环</span><span class="ct">实验环境与版本<span class="desc">所有“默认”说法的版本基准</span></span></a>
          </div>
        </details>
      </div>
    </section>
    <section id="workshop">
      <div class="wrap">
        <div class="section-head">
          <div class="kicker">动手实验</div>
          <h2>每个优化点，都是一次真刀真枪的实验</h2>
          <p>不是听完原理就翻页，而是先亲手制造瓶颈，再亲手解决它——用同一份性能脚本，跑两遍，看数字说话。</p>
        </div>
        <div class="lab-flow">
          <div class="lab-step"><div class="num">01</div><div class="t">环境搭建<br/>单机 / 多机</div></div>
          <div class="lab-step"><div class="num">02</div><div class="t">加压<br/>制造瓶颈</div></div>
          <div class="lab-step"><div class="num">03</div><div class="t">执行<br/>优化措施</div></div>
          <div class="lab-step"><div class="num">04</div><div class="t">重跑<br/>相同脚本</div></div>
          <div class="lab-step"><div class="num">05</div><div class="t">对比<br/>与总结</div></div>
        </div>
        <div class="lab-example">
          <span class="tag">示例实验 · Chapter 16</span>
          <h4>PagedAttention：显存碎片如何限制并发上限</h4>
          <div class="row"><span class="lbl">制造瓶颈</span><span class="val">用不合理的 block-size 启动服务，逐步加压，观察显存碎片导致的 OOM 与并发上限</span></div>
          <div class="row"><span class="lbl">优化措施</span><span class="val">切换为标准 PagedAttention 分页配置</span></div>
          <div class="row"><span class="lbl">对比指标</span><span class="val">最大并发数 · 显存利用率 · OOM 次数 · 吞吐（tokens/s）</span></div>
        </div>
      </div>
    </section>
    <section id="audience">
      <div class="wrap">
        <div class="section-head">
          <div class="kicker">适合谁学</div>
          <h2>面向想把系统真正跑快的人</h2>
        </div>
        <div class="audience-grid">
          <div>
            <ul class="out-list">
              <li>独立完成一次完整的 LLM 推理性能优化：从 Benchmark、Profiling 到根因定位、方案选择和收益验证</li>
              <li>看懂从 GPU 硬件、KV Cache 到推理引擎、Serving 编排的完整链路，而不是只会调框架参数</li>
              <li>面对新模型、新框架、新硬件，也能用同一套分析方法找到瓶颈，而不是死记一份优化清单</li>
              <li>理解 Prefill-Decode 分离、MoE 专家并行等 2026 年生产级架构背后的系统原理</li>
              <li>产出一份优化前后的对比报告，讲清楚收益、代价和适用边界</li>
            </ul>
          </div>
          <div class="prereq-box">
            <h4>先修要求</h4>
            <ul>
              <li>Python 与 Linux 基础操作</li>
              <li>理解 Transformer 的基本结构（Attention、自回归生成）</li>
              <li>具备基础的软件工程能力</li>
            </ul>
          </div>
        </div>
      </div>
    </section>
    <footer>
      <div class="wrap">
        <p>LLM Performance Engineering · <a href="https://github.com/wldandan/llm-inference-performance-handbook">GitHub</a></p>
        <p>理解推理系统 → 分析性能问题 → 优化系统 → 工程实践</p>
      </div>
    </footer>
  </main>
</div>