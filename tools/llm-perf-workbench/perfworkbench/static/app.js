"use strict";

(() => {
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const form = $("#experiment-form");
  const MAX_BYTES = 2 * 1024 * 1024;
  const activeStatuses = new Set(["pending", "queued", "starting", "running", "cancelling", "stopping"]);
  const statuses = {
    pending: "待运行", queued: "排队中", starting: "启动中", running: "运行中", cancelling: "正在取消",
    stopping: "正在停止", completed: "已完成", failed: "失败", cancelled: "已取消", interrupted: "已中断", timed_out: "已超时",
    pass: "通过", fail: "未通过", unknown: "未知", effective: "有效", ineffective: "无效",
    insufficient_evidence: "证据不足", missing: "缺失", ok: "正常",
  };
  const jsonFields = new Set(["endpoint.environment", "load.mix", "quality.required_text", "telemetry.sources"]);
  const nullableFields = new Set(["endpoint.api_key_env", "endpoint.context_length", "tokenizer_path",
    "goals.min_requests_per_s", "goals.max_p95_e2e_ms", "goals.max_p95_ttft_ms", "goals.max_p95_tpot_ms"]);
  const state = {spec: null, runs: [], current: null, view: "overview", jsonDirty: false, polling: false, endpoint: null, sweepPlan: null,
    preset: "quick", datasetSource: "内置示例"};
  const pretty = (value) => JSON.stringify(value, null, 2);
  const valueText = (value) => value == null ? "未知" : typeof value === "object" ? pretty(value) : String(value);
  const statusText = (value) => statuses[value] || value || "未知";
  const number = (value, suffix = "") => typeof value === "number" && Number.isFinite(value)
    ? `${value.toLocaleString("zh-CN", {maximumFractionDigits: 3})}${suffix}` : "未知";
  const ratio = (value) => typeof value === "number" && Number.isFinite(value) ? number(value * 100, "%") : "未知";
  const get = (object, path) => path.split(".").reduce((value, key) => value?.[key], object);
  const set = (object, path, value) => {
    const parts = path.split(".");
    const key = parts.pop();
    const target = parts.reduce((parent, part) => parent[part] ??= {}, object);
    target[key] = value;
  };
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const parameterHelp = {
    "name": [
      "给本次实验起一个方便识别、查找和对比的名字。名称必填，最多 128 个字符，不会改变模型或运行参数。",
      "例如：baseline、qwen3-1.7b-并发1。叫 baseline 只是命名，不会自动把该实验设为对比基线。",
    ],
    "endpoint.api_key_env": [
      "访问需要鉴权的模型服务时，在这里填写保存密钥的环境变量名，例如 MODEL_API_KEY。不要填写密钥本身。工作台进程从自己的环境中读取对应值，用于请求模型服务。",
      "请在启动工作台前配置该变量；只填写变量名不会创建变量，变量不存在或值为空会报错。不需要鉴权的本地服务可以留空。",
    ],
    "endpoint.context_length": [
      "声明当前推理服务允许单次请求使用的上下文总长度，即输入 + 输出的 token 上限，不是文字字数，也不是每次必须用满的长度。",
      "例如：服务当前配置的上限是 32768 tokens，就填 32768。不确定可以留空，按未知处理；这里不会修改 Ollama 或 vLLM 的服务配置。",
      "已配置可用的本地 tokenizer 时，工作台会用最大输入 token 数加最大输出预留做保守检查；未配置时无法完成这项 token 级长度检查。",
    ],
    "endpoint.environment": [
      "记录本次实验实际使用的硬件、推理引擎、版本和并行策略，方便理解两次实验的性能差异。这里不是设置环境变量，不会修改模型服务配置。",
      '例如：{"engine": "ollama", "device": "Apple Silicon"}。请按实际环境填写；暂不记录时保留 {}，不要把文本框清空。',
      "使用单层 JSON 对象，值可以是字符串、数字或 null。不要写密钥、密码或其他敏感信息。",
    ],
    "notes": [
      "补充本次实验的目的、调整和观察点，方便以后回看；可以留空。备注不会作为提示词发给模型，也不会修改实验配置。",
      "例如：只把并发从 1 改为 2，其他条件不变，观察吞吐量和错误率。请勿记录密钥或敏感数据。",
    ],
    "load.mode": [
      "选择请求如何发给模型服务。固定并发：同时保持指定数量的请求在途，一个结束后再补一个，直到完成本轮请求。目标到达速率：按设定的平均速度发起新请求，不等待上一条完成。",
      "例如：并发 4 表示最多同时等待 4 个响应；到达速率 2 req/s 表示平均每秒发起 2 个新请求，不代表每秒能完成 2 个。",
    ],
    "load.concurrency": [
      "固定并发模式下，客户端最多同时进行的请求数。一个请求结束后，再补发后续请求；不是每秒请求数，也不是模型的 Batch Size 或显卡数量。",
      "例如：测量 10 次、并发 2，表示这 10 次请求最多同时跑 2 个，不是发送 20 次。到达速率模式的在途限制由安全设置中的“并发上限”控制。",
    ],
    "load.rate": [
      "仅用于“目标到达速率”模式，单位 req/s，表示平均每秒计划发起多少个新请求。固定并发模式下不生效。",
      "例如：2 表示平均每秒发起 2 个请求，不代表服务每秒完成 2 个。服务变慢时在途请求会增多；触及安全上限时，部分请求可能被客户端拒绝。",
    ],
    "load.count": [
      "“每点”就是每个测试档位，例如并发 1、2、4 是三个点。这里填写每个点、每轮正式测量的请求总数，不包含预热，也不再乘以并发数。",
      "例如：扫描 1、2、4，每点 10 次、重复 1 轮，共测量 30 次；不填扫描点就只测当前一个档位。数据集不足时会重复取样，10 次请求不一定是 10 条不同数据。",
    ],
    "load.warmup": [
      "每个测试档位在每轮正式测量前先发送的请求数，用来让服务进入运行状态。预热会消耗时间和 token，但不计入正式性能指标。",
      "例如：每点测量 10 次、预热 2 次，每点每轮实际发送 12 次。填 0 表示不预热；预热不等于保证 KV / 前缀缓存命中。",
    ],
    "load.repeats": [
      "每个测试档位完整运行多少轮，用来观察结果是否稳定。每轮都会重新执行该点的预热与正式测量，分别留下记录。",
      "例如：3 个扫描点，每点测量 10 次、预热 2 次，重复 2 轮，共发送 3 × (10 + 2) × 2 = 72 次，其中正式测量 60 次。",
    ],
    "load.scan": [
      "一次比较多个负载档位，用逗号分隔。固定并发模式扫描并发数，目标到达速率模式扫描 req/s；各点独立测量。填写后以扫描值代替对应的单一数值。",
      "例如：填 1, 2, 4，在固定并发模式下依次测并发 1、2、4；每点测量数和重复次数对每个档位都生效。留空则只测当前并发数或到达速率。",
    ],
    "load.mix": [
      "控制不同类别在请求数量中的比例。类别名必须对应数据集的 category 字段，数值是正的相对权重，不是 token 比例，也不是把多个任务合并为一次模型请求。",
      '例如：{"classify": 0.3, "summary": 0.7}，测量 100 次时分配 30 次分类、70 次总结；填 3 和 7 也表示同样比例，小样本会取整。类别内样本不足时会重复取样。',
      "保留 {}：不指定类别权重，按原数据顺序取样，不足时循环，再打乱顺序；并非各类别平均分配。这里也不会建立“先分类、再总结”的工作流依赖。",
    ],
    "generation.max_tokens": [
      "限制单次请求最多生成多少个 token，不包含输入，也不是要求模型必须生成这么多。token 是模型处理文本的单位，不等于汉字或单词数。",
      "例如：填 256，回答可以提前结束；达到上限时可能被截断。样本自己设置的 max_tokens 优先于这里的默认值。",
      "调大上限会增加计划的输出预算预留，但不代表实际一定消耗这么多。比较性能时应保持上限一致，并检查实际输出长度和结束原因。",
    ],
    "generation.temperature": [
      "控制生成答案时的采样随机性：较低时更偏向高概率的下一个 token，较高时选择更分散、回答更多样；它不是速度或准确率开关。",
      "当前默认 0，通常表示每一步选概率最高的 token，但不保证多次回答完全相同。具体支持范围和行为以模型服务为准。",
      "性能对比时保持该值一致；修改它可能改变答案内容、长度和质量，进而影响测量结果。",
    ],
    "generation.top_p": [
      "控制采样时的候选范围：将下一 token 的候选按概率从高到低排列，保留累计概率达到设定阈值的候选，再从中采样。",
      "例如：0.9 表示累计概率达到 90%，不是保留 90% 的词，也不是答案有 90% 的正确率。默认 1 表示不按此阈值缩小范围。",
      "数值越小，候选范围通常越窄。Temperature 为 0、使用贪心生成时，部分服务会忽略 Top P；性能对比时保持采样参数一致。",
    ],
    "cache_condition": [
      "记录本次实验的缓存前提，便于比较结果。这只是声明，不是 KV Cache 开关，也不是自动测得的缓存命中率。",
      "未知：未确认缓存状态。声明为冷缓存：已在服务侧准备无可复用缓存的条件。声明为热缓存：已准备预热或可复用前缀的条件。",
      "选择此项不会清空缓存、执行预热或保证命中。需要自行准备并验证，拿不准就保留“未知”；仅发送过预热请求不能证明后续请求会命中缓存。",
    ],
    "goals.mode": [
      "标记本次实验的业务目标：离线吞吐侧重单位时间完成多少任务；在线响应侧重用户等待多久、生成是否及时。",
      "这里只记录目标类型，不会自动改变负载模式、并发或其他阈值。下面填写的是验收目标，不是让模型自动达到这些性能的配置。",
    ],
    "goals.min_requests_per_s": [
      "希望正式测量达到的最低成功请求吞吐，单位 req/s。计算方式是成功请求数除以完整测量窗口，不包含预热。",
      "例如：填 2，表示希望平均每秒至少成功完成 2 次模型请求；不是每秒发送 2 次，也不是每秒完成 2 份多步骤报告。留空则不设此目标，不会自动调整发压速率。",
    ],
    "goals.max_p95_e2e_ms": [
      "成功测量请求的端到端耗时 P95 上限。E2E 从客户端发出请求算到完整响应结束，包含网络、排队和生成等耗时；单位毫秒。",
      "例如：填 2000，要求约 95% 的成功请求在 2 秒内完成。留空则不设此目标；它不是请求超时，超时限制在安全预算中设置。该阈值也用于逐请求的有效吞吐筛选。",
    ],
    "goals.max_p95_ttft_ms": [
      "成功测量请求的首个可观测输出片段耗时 P95 上限，单位毫秒。例如：填 500，要求约 95% 的成功请求在 0.5 秒内开始返回内容。",
      "本工具从流式响应观测 TTFT，首片段可能是思考内容，不等于纯 Prefill 时间。非流式或观测缺失时标为未知；留空不设此目标。该阈值也用于逐请求的有效吞吐筛选。",
    ],
    "goals.max_p95_tpot_ms": [
      "先为每个成功请求计算平均输出 token 耗时，再看这些数值的 P95。这里估算 TPOT = (E2E − TTFT) / (输出 token 数 − 1)，单位 ms/token，不是逐 token 间隔 ITL 的 P95。",
      "例如：填 50，要求约 95% 的成功请求平均每个后续 token 不超过 50ms。非流式、缺少 usage 或输出不足 2 个 token 时无法估算；留空不设此目标。该阈值也用于逐请求的有效吞吐筛选。",
    ],
    "goals.max_error_rate": [
      "允许的最高请求错误比例：正式测量中失败请求数除以实际已发送请求数。0 表示不允许失败，0.01 表示最多 1%，不是填 1 表示 1%。",
      "这里不是答案错误率；答案是否合格由质量评价判断。客户端未发出的拒绝请求单独记录，不算服务失败。此项用于结果验收，不会一超标就自动停止实验。",
    ],
    "quality.mode": [
      "选择如何判断回答合格：业务规则检查长度、指定文本及 JSON；人工标签使用你对每次请求标记的 pass / fail；不评估则将质量标为未知。",
      "默认人工标签，未标记不会算通过。业务规则只检查形式和指定内容，不能证明事实正确；请求失败、被过滤及启用的截断检查仍可判为失败。",
    ],
    "goals.min_quality_pass_rate": [
      "正式测量中，质量通过的请求数除以实际已发送请求数，需要达到的最低比例。1 表示 100%，0.95 表示 95%。",
      "未知或未人工评价的请求不会算通过，也不会从分母排除。这个值用于验收，不会自动评价答案或改变模型输出；没有有效测量请求时结果为未知。",
    ],
    "quality.min_chars": [
      "仅在业务规则模式下，要求回答文本至少包含多少个字符。这里按字符计数，不是 token 数；空格、标点也计入。",
      "例如：填 100，少于 100 个字符的回答不通过。它只检查返回内容，不会要求模型必须生成这么长，也不能说明答案正确。填 0 表示不设最低长度。",
    ],
    "quality.required_text": [
      '仅在业务规则模式下，要求回答包含数组中的每段文本。例如：["摘要", "关键词"] 表示两段都必须出现，不是任选一段。',
      "这里的 JSON 数组只是填写检查规则的格式，不要求模型回答 JSON；普通文本回答也可以检查。",
      "使用精确的文本包含检查，区分大小写，不做语义相似度判断。保留 [] 表示不检查；这些文本不会自动加入发给模型的提示词。",
    ],
    "quality.reject_truncated": [
      "勾选后，结束原因 finish_reason 为 length 的回答会判为质量不通过，常见原因是生成达到 token 上限，答案可能没有说完。",
      "此检查也适用于人工标签和不评估模式，人工 pass 不能覆盖它。取消勾选只是关闭这项判定，不会修复截断或自动让回答通过其他检查。",
    ],
    "safety.max_requests": [
      "整份实验计划允许的请求数量预算，包含所有扫描点、重复轮次、预热和正式测量。提交前会检查计划是否超出预算。",
      "例如：3 个扫描点，每点测量 10 次、预热 2 次、重复 1 轮，需要至少 3 × (10 + 2) = 36 次。它是上限，不是额外再发送这么多次；主动服务预检的请求单独计量。",
    ],
    "safety.max_concurrency": [
      "客户端允许同时在途的请求数上限，是安全限制，不是模型服务的 Batch Size 或全局并发限制。",
      "固定并发及扫描点不能超过它；目标到达速率模式下，如果新请求到来时在途数已满，客户端会拒绝该请求并记录，不会无限排队。调高该值不会自动增加固定并发。",
    ],
    "safety.max_duration_s": [
      "整份实验计划共用的最长运行时间，单位秒，包含预热、所有扫描点和重复轮次，不是每个点各有这么长时间。",
      "例如：900 表示 15 分钟。到期会停止本地压测执行并将未完成部分记录为超时；已发出的请求是否立即在模型服务端停止，取决于服务端处理。",
    ],
    "safety.request_timeout_s": [
      "客户端等待单次请求完成的最长时间，单位秒，覆盖请求发送到完整响应结束，而不只是等待首个 token。",
      "例如：180 表示单次请求最多等待 3 分钟，超过就中止等待并记录失败，不会自动重试。长输入或长输出任务需留足时间；整份计划仍受计划总时限约束。",
    ],
    "safety.max_output_tokens": [
      "整份计划的输出 token 预留预算，包含预热、扫描和重复，不包含输入 token，也不是每条请求的输出上限。",
      "提交前保守计算：计划总请求数 × 样本中最大的有效单请求输出上限。例如：5 次请求，每次上限 256，需要预留 1280 tokens；样本自己的 max_tokens 优先。实际生成较短不会让已超出预留预算的计划自动获准。",
    ],
    "safety.max_response_bytes": [
      "客户端接收单条响应体的最大字节数；流式响应按所有分片累计，不是每个分片各有这么大额度。用于防止异常大响应占用过多内存。",
      "例如：2097152 bytes = 2 MiB。响应体还包含 JSON / SSE 等协议内容，所以这不是字符数或 token 数。超出后会中止接收并记录失败，不会自动截取成合格答案。",
    ],
    "telemetry.interval_s": [
      "每轮资源指标采集完成后，等待多少秒再开始下一轮。只有启用本地采集或配置了观测源、并主动启动实验时才会采集；不是模型请求的发送间隔。",
      "默认 1 秒。采集本身也需要时间，因此实际两轮间隔可能更长；间隔越短观测越密，但采集开销也会增加。它不是 token 间隔，不能用来测 ITL。",
    ],
    "telemetry.local.enabled": [
      "采集的是运行工作台的后端主机，不一定是浏览器所在电脑。勾选即确认模型实际运行在同一主机；SSH 隧道、端口转发或远程服务不适用，即使地址显示 localhost。系统内存采集支持 macOS / Linux。",
      "默认关闭。启用后仅在主动启动的实验期间，读取系统内存并向同源 Ollama /api/ps 发出 GET 状态请求，不额外生成；实验结束或停止后停止采集。模型地址须为本机回环地址，路径为根路径或 /v1。",
      "不采集设备 GPU 或 KV 使用量。模型内存来自 size_vram，只是模型 GPU 侧报告，不等于设备或 KV 内存；配置上下文是容量配置，非使用量。已有 Prometheus / exporter 观测可继续使用。",
    ],
    "telemetry.sources": [
      "配置提供 Prometheus 文本指标的观测端点，例如模型服务或 GPU / NPU exporter 的 /metrics 地址；不是 Chat Completions 地址。保留 [] 表示未配置 exporter，不影响单独启用的本地采集。缺失数据按未知处理，不当作 0。",
      "每个来源填写 name、url、api_key_env 和 mappings。mappings 用实际指标名、单位换算、标签过滤及聚合方式映射到队列、KV Cache、设备利用率等指标；空映射尝试内置 vLLM 指标，硬件指标需按实际 exporter 配置。",
      "api_key_env 只填环境变量名，不填密钥。工作台不会替你安装 exporter，也不会因为填写 JSON 就立即访问端点；仅在实验运行期间采集。",
    ],
    "protocol_fixture": [
      "仅当实验连接的是测试协议用的替身服务时勾选。此类服务通常返回固定文本和 usage，用于检查工具流程，不执行真实模型推理。",
      "这是实验用途标记，不会自动切换服务地址或启动替身。勾选后结果不能作为真实模型性能、容量或优化有效的证据；连接真实模型时不要勾选。",
    ],
  };
  let activeHelp = null;
  function closeParameterHelp() {
    if (activeHelp) activeHelp.tip.hidden = true;
    activeHelp = null;
  }
  function showParameterHelp(entry) {
    if (activeHelp === entry) return;
    closeParameterHelp();
    entry.pinned = false;
    entry.tip.hidden = false;
    activeHelp = entry;
  }
  function uniqueId(base) {
    let id = base;
    for (let suffix = 2; document.getElementById(id); suffix += 1) id = `${base}-${suffix}`;
    return id;
  }
  function decorateParameterHelp() {
    for (const [name, paragraphs] of Object.entries(parameterHelp)) {
      const control = form.querySelector(`[name="${name}"]`);
      if (!control || control.closest(".help-field")) continue;
      const label = control.closest("label");
      if (!label) continue;
      const title = [...label.childNodes].filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => node.textContent).join("").trim();
      const children = [...label.children];
      const field = element("div", null, `${label.className} help-field`.trim());
      const row = element("div", null, "help-label-row");
      const button = element("button", null, "help-trigger");
      const icon = element("span", "?", "help-icon");
      icon.setAttribute("aria-hidden", "true");
      button.append(icon);
      const tip = element("div", null, "parameter-tip");
      const idBase = name.replaceAll(".", "-");
      if (!control.id) control.id = uniqueId(`field-${idBase}`);
      tip.id = uniqueId(`help-${idBase}`);
      tip.setAttribute("role", "tooltip");
      tip.hidden = true;
      tip.append(element("strong", title), ...paragraphs.map((text) => element("p", text)));
      button.type = "button";
      button.setAttribute("aria-label", `${title}说明`);
      button.setAttribute("aria-describedby", tip.id);
      control.setAttribute("aria-describedby", [control.getAttribute("aria-describedby"), tip.id].filter(Boolean).join(" "));
      label.replaceWith(field);
      label.className = "";
      label.htmlFor = control.id;
      label.replaceChildren(document.createTextNode(title));
      if (control.type === "checkbox") {
        field.classList.remove("check");
        row.classList.add("check");
        row.append(control, label, button, tip);
        field.append(row, ...children.filter((child) => child !== control));
      } else {
        row.append(label, button, tip);
        field.append(row, ...children);
      }
      const entry = {button, tip, field, pinned: false};
      button.addEventListener("pointerenter", (event) => {
        if (event.pointerType !== "touch") showParameterHelp(entry);
      });
      button.addEventListener("focus", () => showParameterHelp(entry));
      button.addEventListener("click", () => {
        // Focus precedes a first click/tap: pin that newly opened tip, rather than closing it.
        if (activeHelp === entry && entry.pinned) closeParameterHelp();
        else { showParameterHelp(entry); entry.pinned = true; }
      });
      button.addEventListener("blur", () => { if (activeHelp === entry) closeParameterHelp(); });
      field.addEventListener("pointerleave", () => {
        if (activeHelp === entry && !entry.pinned && document.activeElement !== button) closeParameterHelp();
      });
    }
  }
  decorateParameterHelp();
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeParameterHelp(); });
  document.addEventListener("pointerdown", (event) => {
    if (activeHelp && !activeHelp.button.contains(event.target) && !activeHelp.tip.contains(event.target)) closeParameterHelp();
  });
  form.addEventListener("toggle", (event) => {
    if (activeHelp && !event.target.open && event.target.contains(activeHelp.field)) closeParameterHelp();
  }, true);
  function syncArrivalRateVisibility() {
    const field = $("#arrival-rate-field");
    field.hidden = form.elements.namedItem("load.mode").value !== "rate";
    if (field.hidden && activeHelp && field.contains(activeHelp.field)) closeParameterHelp();
  }
  function showError(target, error) {
    const node = $(target);
    node.textContent = error ? (error.message || String(error)) : "";
    node.hidden = !error;
    if (error && target === "#editor-error") node.scrollIntoView({block: "nearest"});
  }
  function output(target, data) {
    const node = $(target);
    node.textContent = typeof data === "string" ? data : pretty(data);
    node.hidden = false;
  }
  function parseJSON(text, label) {
    try { return JSON.parse(text); }
    catch { throw new Error(`${label} JSON 解析失败：检查引号、逗号、括号和数字格式。请修正后重试。`); }
  }
  function bounded(text, label) {
    if (new TextEncoder().encode(text).byteLength > MAX_BYTES) throw new Error(`${label}超过 2 MiB，请缩小输入。`);
    return text;
  }
  async function api(path, data) {
    const options = {credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(data === undefined ? 20000 : 90000)};
    if (data !== undefined) {
      options.method = "POST";
      options.headers = {"Content-Type": "application/json", "X-Workbench-Action": "local"};
      options.body = bounded(JSON.stringify(data), "请求");
    }
    let response;
    try { response = await fetch(path, options); }
    catch (error) {
      throw new Error(error.name === "TimeoutError" ? "操作等待超时；请刷新实验列表确认状态后重试，避免重复提交。" : "无法连接本地服务，请确认工作台仍在运行后刷新。");
    }
    if (!response.ok) {
      const message = await response.text();
      throw new Error(`HTTP ${response.status} · ${message.slice(0, 2000) || "本地服务未能完成请求"}`);
    }
    try { return await response.json(); }
    catch { throw new Error("本地服务返回了无效 JSON，请刷新后重试。"); }
  }
  async function action(button, errorTarget, operation) {
    if (button?.disabled) return;
    if (button) { button.disabled = true; button.setAttribute("aria-busy", "true"); }
    showError(errorTarget, null);
    try { await operation(); }
    catch (error) {
      if (error.field && errorTarget === "#editor-error") {
        const guidance = revealField(error.field);
        if (guidance) error.message = guidance;
      }
      if (errorTarget === "#editor-error") invalidateEstimate(error.message);
      showError(errorTarget, error);
    }
    finally { if (button) { button.disabled = false; button.removeAttribute("aria-busy"); } }
  }
  function navigate(view) {
    closeParameterHelp();
    state.view = view;
    $$(".view").forEach((node) => { node.hidden = node.id !== `view-${view}`; });
    $$("nav [data-view]").forEach((button) => {
      if (button.dataset.view === view) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    if (view !== "detail") {
      $("#raw-opt-in").checked = false;
      $("#raw-responses").replaceChildren();
      $("#raw-responses").hidden = true;
    }
    if (view === "compare") renderCandidates();
    window.scrollTo({top: 0, behavior: "instant"});
  }
  $$('[data-view]').forEach((button) => button.addEventListener("click", () => navigate(button.dataset.view)));
  $(".brand").addEventListener("click", (event) => { event.preventDefault(); navigate("overview"); });

  function readJSONL(text, allowEmpty = false) {
    bounded(text, "数据集");
    const ids = new Set();
    const rows = [];
    text.split(/\r?\n/).forEach((line, index) => {
      if (!line.trim()) return;
      const row = parseJSON(line, `数据集第 ${index + 1} 行`);
      if (!row || typeof row !== "object" || Array.isArray(row) || typeof row.id !== "string" || !row.id.trim()
          || !Array.isArray(row.messages) || !row.messages.length) {
        throw new Error(`数据集第 ${index + 1} 行必须包含非空 id 和 messages 数组。`);
      }
      if (ids.has(row.id)) throw new Error(`数据集第 ${index + 1} 行的 id 重复，请使用唯一 ID。`);
      ids.add(row.id);
      rows.push(row);
    });
    if (!rows.length && !allowEmpty) throw new Error("请导入 JSONL 数据集，或填写至少一条样本。");
    return rows;
  }
  function baseSpec() {
    return {name: "", endpoint: {}, dataset: [], load: {}, generation: {extra: {}}, goals: {deadline_s: null, target_requests: null},
      quality: {require_json: false, json_fields: []}, safety: {}, telemetry: {local: {enabled: false}}, cache_condition: "unknown", tokenizer_path: null, notes: "", protocol_fixture: false};
  }
  function requireAppliedJSON() {
    if (state.jsonDirty) throw new Error("高级 JSON 尚未应用。请先点击“应用 JSON”，以保留本次编辑。");
  }
  function revealField(input) {
    const hiddenRate = input.name === "load.rate" && $("#arrival-rate-field").hidden;
    const target = hiddenRate ? form.elements.namedItem("load.mode") : input;
    for (let parent = target.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === "DETAILS") parent.open = true;
    }
    target.focus();
    return hiddenRate ? "到达速率无效，请切换到目标到达速率后修正。" : null;
  }
  function readForm(allowEmpty = false, replacementDataset = null) {
    requireAppliedJSON();
    const spec = structuredClone(state.spec || baseSpec());
    // JSON-only setting: preserve explicit seeds, including 0, and default only when absent.
    if (spec.load.seed === undefined) spec.load.seed = 42;
    for (const input of form.querySelectorAll("[name]")) {
      try {
      const key = input.name;
      let value;
      if (input.type === "checkbox") value = input.checked;
      else if (jsonFields.has(key)) value = parseJSON(input.value, key);
      else if (key === "load.scan") {
        value = input.value.trim() ? input.value.split(/[,，]/).map((point) => {
          if (!point.trim() || !Number.isFinite(Number(point)) || Number(point) <= 0) throw new Error("扫描点必须是逗号分隔的正数。");
          return Number(point);
        }) : [];
      } else if (nullableFields.has(key) && input.value.trim() === "") value = null;
      else if (input.type === "number") {
        value = Number(input.value);
        if (!input.value.trim() || !Number.isFinite(value)) throw new Error(`${key} 需要有效数字。`);
      } else value = input.value.trim();
      // Preserve the shape of older imported configurations; absence already means disabled.
      if (key === "telemetry.local.enabled" && !value && get(spec, key) === undefined) continue;
      set(spec, key, value);
      } catch (error) {
        error.field = input;
        throw error;
      }
    }
    try { spec.dataset = replacementDataset ?? readJSONL($("#dataset-jsonl").value, allowEmpty); }
    catch (error) { error.field = $("#dataset-jsonl"); throw error; }
    return spec;
  }
  function fillForm(spec, preset = null, source = "配置中的数据") {
    if (!spec || typeof spec !== "object" || Array.isArray(spec) || !Array.isArray(spec.dataset)) throw new Error("完整 JSON 需要 ExperimentSpec 对象及 dataset 数组。");
    for (const key of ["endpoint", "load", "generation", "goals", "quality", "safety", "telemetry"]) {
      if (!spec[key] || typeof spec[key] !== "object" || Array.isArray(spec[key])) throw new Error(`完整 JSON 缺少 ${key} 对象，请检查配置。`);
    }
    // Prepare every value before touching the current form or its unapplied draft.
    const json = bounded(pretty(spec), "配置");
    const rows = spec.dataset.map((row) => JSON.stringify(row)).join("\n");
    readJSONL(rows, true);
    if (!Array.isArray(spec.load.scan ?? [])) throw new Error("load.scan 必须是数组。");
    const values = [...form.querySelectorAll("[name]")].map((input) => {
      const value = get(spec, input.name);
      if (input.type === "checkbox") return [input, value === true];
      if (jsonFields.has(input.name)) return [input, pretty(value ?? (input.name.includes("sources") || input.name.includes("required_text") ? [] : {}))];
      if (input.name === "load.scan") return [input, (value || []).join(", ")];
      return [input, value ?? ""];
    });
    for (const [input, value] of values) {
      if (input.type === "checkbox") input.checked = value;
      else input.value = value;
    }
    state.spec = structuredClone(spec);
    state.jsonDirty = false;
    state.preset = preset;
    state.datasetSource = source;
    $("#dataset-jsonl").value = rows;
    $("#spec-json").value = json;
    $("#json-hint").textContent = "当前 JSON 与表单一致。编辑后先应用，再启动。";
    syncArrivalRateVisibility();
    updateEstimate(spec);
  }
  function invalidateEstimate(message) {
    $("#plan-estimate").textContent = "配置待确认 · 暂无有效预算预览";
    $("#budget-status").textContent = message;
    $("#run-settings-summary").textContent = "";
  }
  function updateEstimate(spec) {
    $("#dataset-summary").textContent = `${spec.dataset.length} 条 · ${state.datasetSource}`;
    $("#preset-status").textContent = state.preset === "quick" ? "快速试跑" : state.preset === "baseline" ? "基线测量" : "自定义配置";
    $$('[data-preset]').forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.preset === state.preset)));
    const service = spec.endpoint.base_url === "http://127.0.0.1:11434/v1" ? "ollama" : spec.endpoint.base_url === "http://127.0.0.1:8000/v1" ? "vllm" : "custom";
    $$('[data-service]').forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.service === service)));
    if ([...form.querySelectorAll('input[type="number"]')].some((input) => !input.validity.valid)) {
      invalidateEstimate("数值参数不完整或超出允许范围；请修正后再启动。");
      return;
    }
    const load = spec.load;
    const points = Math.max(1, load.scan?.length || 0) * load.repeats;
    const requests = (load.count + load.warmup) * points;
    const caps = spec.dataset.map((row) => row.max_tokens ?? spec.generation.max_tokens);
    if (!caps.length || ![points, requests, ...caps].every((value) => typeof value === "number" && Number.isFinite(value) && value > 0)) {
      invalidateEstimate("请补充有效数据与负载参数。");
      return;
    }
    const tokens = requests * Math.max(...caps);
    $("#plan-estimate").textContent = `${number(points)} 个实验点 · 最多 ${number(requests)} 次请求 · ${number(tokens)} 输出 tokens 预留`;
    const parallel = load.mode === "rate" ? `目标到达 ${load.scan?.length ? load.scan.join(" / ") : number(load.rate)} req/s · 在途上限 ${number(spec.safety.max_concurrency)}` : `并发 ${load.scan?.length ? load.scan.join(" / ") : load.concurrency}`;
    const quality = spec.quality.mode === "manual" ? "质量待人工评价" : spec.quality.mode === "none" ? "质量未知（未评估）" : "质量按业务规则判断";
    $("#run-settings-summary").textContent = `${parallel} · ${spec.generation.stream ? "流式（采集 TTFT / TPOT）" : "非流式（TTFT / TPOT 未知）"} · ${quality} · 本地采集：${spec.telemetry.local?.enabled === true ? "开启" : "关闭"} · ${spec.telemetry.sources?.length ? "已配置资源观测（exporter）" : "未配置 GPU / KV 观测"}${spec.protocol_fixture ? " · 协议替身，不代表模型性能" : ""}`;
    const exceeds = requests > spec.safety.max_requests || tokens > spec.safety.max_output_tokens ||
      Math.max(load.concurrency, ...(load.mode === "concurrency" ? load.scan || [] : [])) > spec.safety.max_concurrency;
    $("#budget-status").textContent = `安全上限：${number(spec.safety.max_requests)} 次 / ${number(spec.safety.max_output_tokens)} 输出 tokens / ${number(spec.safety.max_duration_s)} 秒。${exceeds ? "当前计划超出预算：请显式选择预设，或在高级设置中调整预算。" : ""}`;
  }
  form.addEventListener("input", (event) => {
    if (event.target.name === "load.mode") syncArrivalRateVisibility();
    if (event.target.id === "spec-json") {
      state.jsonDirty = true;
      invalidateEstimate("JSON 尚未应用；应用后重新显示本次预算。");
      return;
    }
    if (state.jsonDirty || event.target.type === "file") return;
    if (event.target.id === "dataset-jsonl") state.datasetSource = "自定义数据";
    if (/^(load|generation|safety)\./.test(event.target.name)) state.preset = null;
    try { const spec = readForm(true); updateEstimate(spec); $("#spec-json").value = pretty(spec); }
    catch (error) { invalidateEstimate(error.message); }
  });
  $("#load-example").addEventListener("click", () => action($("#load-example"), "#editor-error", async () => {
    requireAppliedJSON();
    const spec = await api("/api/example");
    requireAppliedJSON();
    fillForm(spec);
    $("#editor-feedback").textContent = "起始配置已载入。请确认模型地址与数据内容；尚未发出模型请求。";
  }));
  $("#toggle-json").addEventListener("click", () => action(null, "#editor-error", async () => {
    const opening = $("#advanced-panel").hidden;
    $("#advanced-panel").hidden = !opening;
    $("#toggle-json").setAttribute("aria-expanded", String(opening));
    $("#toggle-json").textContent = opening ? "收起高级 JSON" : "展开高级 JSON";
    if (opening && !state.jsonDirty) {
      try {
        $("#spec-json").value = pretty(readForm(true));
        $("#json-hint").textContent = "可直接粘贴完整实验配置，修改后点击应用。";
      } catch {
        $("#json-hint").textContent = "当前表单有未完成或非法字段；下面保留上一次有效 JSON，可直接替换为完整配置。";
      }
    }
  }));
  $("#apply-json").addEventListener("click", () => action($("#apply-json"), "#editor-error", async () => {
    fillForm(parseJSON(bounded($("#spec-json").value, "配置"), "完整实验"));
    $("#editor-feedback").textContent = "JSON 已应用到表单；服务端会在提交时验证完整契约与预算。";
  }));
  async function readFile(input) {
    const file = input.files[0];
    if (!file) return null;
    if (file.size > MAX_BYTES) throw new Error("文件超过 2 MiB，请缩小输入。");
    return file.text();
  }
  $("#config-file").addEventListener("change", () => action(null, "#editor-error", async () => {
    requireAppliedJSON();
    const text = await readFile($("#config-file"));
    if (text === null) return;
    requireAppliedJSON();
    fillForm(parseJSON(text, "实验配置"));
    $("#editor-feedback").textContent = "配置已导入；保留原始参数与预算。请确认服务地址、模型与数据后再启动。";
    $("#config-file").value = "";
  }));
  $$('[data-service]').forEach((button) => button.addEventListener("click", () => action(null, "#editor-error", async () => {
    requireAppliedJSON();
    const input = form.elements.namedItem("endpoint.base_url");
    if (button.dataset.service === "custom") { input.focus(); input.select(); return; }
    input.value = button.dataset.service === "ollama" ? "http://127.0.0.1:11434/v1" : "http://127.0.0.1:8000/v1";
    input.dispatchEvent(new Event("input", {bubbles: true}));
  })));
  $$('[data-preset]').forEach((button) => button.addEventListener("click", () => action(null, "#editor-error", async () => {
    const spec = readForm(true);
    const baseline = button.dataset.preset === "baseline";
    Object.assign(spec.load, {mode: "concurrency", count: baseline ? 50 : 5, warmup: baseline ? 1 : 0, concurrency: 1, repeats: 1, scan: []});
    spec.generation.max_tokens = 256;
    const requests = spec.load.count + spec.load.warmup;
    const caps = spec.dataset.length ? spec.dataset.map((row) => row.max_tokens ?? 256) : [256];
    if (!caps.every((value) => Number.isInteger(value) && value > 0)) throw new Error("样本 max_tokens 必须是正整数，未调整预算。");
    Object.assign(spec.safety, {max_requests: requests, max_concurrency: 1, max_output_tokens: requests * Math.max(...caps)});
    fillForm(spec, button.dataset.preset, state.datasetSource);
    $("#editor-feedback").textContent = "已应用负载、默认输出上限及请求/并发/输出预算。数据、质量、时限和其他配置保持不变。";
  })));
  $("#dataset-file").addEventListener("change", () => action(null, "#editor-error", async () => {
    requireAppliedJSON();
    const text = await readFile($("#dataset-file"));
    if (text === null) return;
    const rows = readJSONL(text);
    requireAppliedJSON();
    const spec = readForm(false, rows);
    fillForm(spec, state.preset, $("#dataset-file").files[0].name);
    $("#editor-feedback").textContent = `已导入 ${rows.length} 条样本。生成画像以查看长度、重复与类别。`;
    $("#dataset-file").value = "";
  }));
  $("#profile").addEventListener("click", () => action($("#profile"), "#editor-error", async () => {
    const spec = readForm();
    output("#profile-result", await api("/api/profile", {dataset: spec.dataset, tokenizer_path: spec.tokenizer_path}));
  }));
  $("#preflight").addEventListener("click", () => action(null, "#editor-error", async () => {
    if (state.jsonDirty) throw new Error("请先应用高级 JSON，再预检服务。");
    const endpoint = structuredClone(state.spec?.endpoint || {});
    for (const input of form.querySelectorAll('[name^="endpoint."]')) {
      const key = input.name.split(".")[1];
      endpoint[key] = jsonFields.has(input.name) ? parseJSON(input.value, input.name)
        : input.type === "number" ? (input.value ? Number(input.value) : null) : (input.value.trim() || null);
    }
    if (!endpoint.base_url || !endpoint.model) throw new Error("预检前请填写服务地址与模型名称。");
    state.endpoint = endpoint;
    $("#preflight-target").textContent = `${endpoint.base_url} · ${endpoint.model}`;
    $("#preflight-dialog").showModal();
  }));
  $("#confirm-preflight").addEventListener("click", () => action($("#preflight"), "#editor-error", async () => {
    $("#preflight-dialog").close();
    output("#preflight-result", await api("/api/preflight", state.endpoint));
  }));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    action($("#submit"), "#editor-error", async () => {
      requireAppliedJSON();
      const invalid = [...form.querySelectorAll("input, select, textarea")].find((input) => !input.validity.valid);
      if (invalid) {
        const error = new Error(`请检查 ${invalid.labels?.[0]?.textContent.trim() || invalid.name}：${invalid.validationMessage}`);
        error.field = invalid;
        throw error;
      }
      const spec = readForm();
      const plan = await api("/api/runs", spec);
      state.spec = spec;
      await refreshRuns();
      if (!plan.run_ids?.length) throw new Error("计划已接受但未返回实验 ID，请刷新实验列表确认状态。");
      await openRun(plan.run_ids[0]);
    });
  });

  const starterQuestions = ["用两句话解释什么是大语言模型。", "简要说明 HTTP 请求和响应的关系。", "什么是缓存？请举一个后端开发的例子。", "将这句话概括为一个标题：系统每天收集技术文章，分类后生成主题报告。", "列出检查一个 API 服务是否就绪的两个方法。"];
  $("#dataset-jsonl").value = starterQuestions.map((content, index) => JSON.stringify({id: `starter-${index + 1}`, category: "starter", messages: [{role: "user", content}]})).join("\n");
  fillForm(readForm(), "quick", "内置示例");

  function badge(status) {
    const node = element("span", statusText(status), "badge");
    node.dataset.status = status;
    return node;
  }
  function renderRuns() {
    $("#run-count").textContent = String(state.runs.length);
    $("#active-count").textContent = String(state.runs.filter((run) => activeStatuses.has(run.status)).length);
    const list = $("#run-list");
    list.replaceChildren();
    if (!state.runs.length) {
      const empty = element("div", null, "empty-state");
      empty.append(element("span", "[ + ]", "empty-mark"), element("h3", "还没有实验记录"),
        element("p", "配置一份工作负载，留下第一条可复现的基线。这里不会展示模拟性能数据。"));
      const button = element("button", "创建第一份实验");
      button.type = "button";
      button.addEventListener("click", () => navigate("editor"));
      empty.append(button);
      list.append(empty);
      return;
    }
    for (const run of state.runs) {
      const row = element("article", null, "run-row");
      const description = element("div");
      description.append(element("h3", run.spec?.name || run.id),
        element("p", `${run.spec?.endpoint?.model || "模型未知"} · ${String(run.created_at || "时间未知")} · ${run.id.slice(0, 8)}`));
      if (run.spec?.protocol_fixture) description.append(element("p", "协议替身 · 不代表模型性能"));
      const button = element("button", "查看实验");
      button.type = "button";
      button.addEventListener("click", () => action(button, "#global-error", () => openRun(run.id)));
      row.append(description, badge(run.status), button);
      list.append(row);
    }
  }
  async function refreshRuns() {
    const runs = await api("/api/runs");
    if (!Array.isArray(runs)) throw new Error("实验列表格式无效，请检查本地服务版本。");
    if (JSON.stringify(runs) !== JSON.stringify(state.runs) || !$("#run-list .empty-state, #run-list .run-row")) {
      state.runs = runs;
      renderRuns();
      if (state.view === "compare") renderCandidates();
    }
    $("#connection").textContent = "● 本地服务已连接";
  }
  async function openRun(id) {
    const run = await api(`/api/runs/${encodeURIComponent(id)}`);
    if (state.current?.id !== id) {
      $("#raw-opt-in").checked = false;
      $("#labels-feedback").textContent = "";
      $("#retest-result").replaceChildren();
      $("#sweep-result").hidden = true;
      $("#load-sweep").setAttribute("aria-expanded", "false");
      state.sweepPlan = null;
    }
    state.current = run;
    renderDetail(run);
    navigate("detail");
  }
  function metric(label, value, unit, explanation) {
    const node = element("div", null, "metric");
    node.append(element("span", label, "metric-label"), element("strong", number(value)), element("small", unit), element("small", explanation));
    return node;
  }
  const localSources = {
    local_system: {title: "系统内存", metrics: {
      host_memory_total_bytes: "主机总内存", host_memory_available_bytes: "主机可用内存",
      host_swap_used_bytes: "Swap 已用", host_swap_total_bytes: "Swap 总量",
    }},
    local_ollama: {title: "Ollama 模型", metrics: {
      model_memory_bytes: "模型内存（GPU 侧报告）", model_context_tokens: "配置上下文（非使用量）",
    }},
  };
  const localReasons = {
    model_not_loaded: "模型未加载", field_unavailable: "字段未提供", invalid_value: "数值无效",
    invalid_response: "响应无效", ambiguous_model: "模型匹配不唯一", http_401: "认证失败",
    http_404: "状态接口不存在", http_500: "服务端错误", missing_api_key: "密钥环境变量缺失",
    timeout: "采样超时", network_error: "网络错误", system_unavailable: "系统采样不可用",
    redirect_rejected: "已拒绝重定向", response_too_large: "响应超出大小限制", unsupported_encoding: "响应编码不支持",
  };
  function localValue(frame, key) {
    const sample = frame?.metrics?.[key];
    let reason = frame?.status === "error" ? frame.error || sample?.reason || "invalid_response" : sample?.reason;
    if (!reason && sample?.status === "available") {
      const value = sample.value;
      if (typeof value !== "number" || !Number.isFinite(value) || value < 0 ||
          (sample.unit === "tokens" && !Number.isInteger(value))) reason = "invalid_value";
      else if (sample.unit === "tokens") return {available: true, text: `${value.toLocaleString("zh-CN", {maximumFractionDigits: 0})} tokens`};
      else if (sample.unit === "bytes") {
        const gib = value >= 1024 ** 3;
        const scaled = value / (gib ? 1024 ** 3 : 1024 ** 2);
        return {available: true, text: `${scaled > 0 && scaled < 0.001 ? "< 0.001" : number(scaled)} ${gib ? "GiB" : "MiB"}`};
      }
    }
    reason ||= "field_unavailable";
    const explanation = Object.hasOwn(localReasons, reason) ? ` · ${localReasons[reason]}` : "";
    return {available: false, text: `null · ${reason}${explanation}`};
  }
  function sampleTime(timestamp) {
    const date = new Date(typeof timestamp === "number" ? timestamp * 1000 : NaN);
    if (!Number.isFinite(date.getTime())) return element("span", "采样时间未知", "muted");
    const time = element("time", date.toISOString());
    time.dateTime = date.toISOString();
    time.title = "采样时间（UTC）";
    return time;
  }
  function localAvailability(available, total) {
    return available === total ? "可用" : available > 0 ? "部分缺失" : "失败";
  }
  function renderTelemetry(run) {
    const telemetry = run.telemetry || [];
    const rows = Array.isArray(telemetry) ? telemetry : [];
    const isLocal = (frame) => Object.hasOwn(localSources, frame?.source_kind);
    // Match report semantics: the last appended whole frame wins, even if UTC goes backwards.
    const local = rows.filter(isLocal).reverse();
    const latest = new Map();
    for (const frame of local) if (!latest.has(frame.source_kind)) latest.set(frame.source_kind, frame);
    const enabled = run.spec?.telemetry?.local?.enabled === true;
    const sources = $("#local-telemetry-latest");
    sources.replaceChildren();
    let available = 0;
    let total = 0;
    if (enabled) for (const [kind, definition] of Object.entries(localSources)) {
      const frame = latest.get(kind);
      const section = element("section", null, "local-source");
      const values = Object.entries(definition.metrics).map(([key, title]) => ({title, ...localValue(frame, key)}));
      const count = values.filter((value) => value.available).length;
      available += count;
      total += values.length;
      const status = frame ? localAvailability(count, values.length) : "等待首样本";
      section.append(element("h4", `${definition.title} · ${status}`));
      if (frame) {
        const meta = element("p", `${frame.source || kind} · `, "local-source-meta");
        meta.append(sampleTime(frame.timestamp));
        section.append(meta);
        const list = element("dl");
        for (const value of values) list.append(element("dt", value.title),
          element("dd", value.text, value.available ? "local-value" : "local-missing"));
        section.append(list);
      } else section.append(element("p", "本次尚未收到该来源的采样。", "muted"));
      sources.append(section);
    }
    const lastStatus = local.length ? localAvailability(available, total) : "等待首样本";
    const stopped = !activeStatuses.has(run.status);
    const status = !enabled ? "未启用" : stopped ? "已停止" : lastStatus;
    const badge = $("#local-telemetry-status");
    badge.textContent = status + (enabled && stopped ? ` · ${local.length ? `最后样本：${lastStatus}` : "未收到样本"}` : "");
    badge.dataset.state = !enabled ? "disabled" : stopped ? "stopped" : lastStatus === "可用" ? "available" : lastStatus === "部分缺失" ? "partial" : lastStatus === "失败" ? "failed" : "waiting";

    const body = $("#local-telemetry-table tbody");
    const entries = [];
    let count = 0;
    // Historical display order is independent of the current per-source state.
    const history = [...local].sort((a, b) => b.timestamp - a.timestamp);
    for (const frame of history) for (const [key, title] of Object.entries(localSources[frame.source_kind].metrics)) {
      count += 1;
      if (entries.length >= 200) continue;
      const row = element("tr");
      const time = element("td");
      time.append(sampleTime(frame.timestamp));
      const name = element("td", title);
      name.append(element("small", key));
      const value = localValue(frame, key);
      row.append(time, element("td", frame.source || frame.source_kind), name,
        element("td", value.text, value.available ? "local-value" : "local-missing"));
      entries.push(row);
    }
    if (!entries.length) {
      const row = element("tr");
      const cell = element("td", "暂无本地采样记录。");
      cell.colSpan = 4;
      row.append(cell);
      entries.push(row);
    }
    body.replaceChildren(...entries);
    $("#local-telemetry-count").textContent = `显示最近 ${Math.min(count, 200)} 条指标记录，共 ${count} 条（最多 200 条，最新在前）。原始 JSON 保留本次返回的全部采样。`;
    const exporters = Array.isArray(telemetry) ? rows.filter((frame) => !isLocal(frame)) : telemetry;
    output("#exporter-telemetry", Object.keys(exporters).length ? exporters : "暂无 exporter 观测；本地采集不提供设备 GPU / KV 指标。");
    output("#telemetry-raw", telemetry);
  }
  function renderDetail(run) {
    const summary = run.summary || {};
    const metrics = summary.metrics || {};
    $("#detail-title").textContent = run.spec?.name || "实验详情";
    $("#detail-status").textContent = statusText(run.status);
    $("#detail-status").dataset.status = run.status;
    $("#detail-meta").textContent = `${run.id} · ${run.spec?.endpoint?.model || "未知模型"} · ${String(run.created_at || "时间未知")}`;
    $("#cancel").hidden = !activeStatuses.has(run.status);
    $("#sweep-panel").hidden = !run.parent_id;
    const progress = run.progress || {};
    const done = progress.completed ?? progress.finished ?? progress.done;
    const total = progress.total;
    if (typeof done === "number" && typeof total === "number" && total > 0) {
      $("#run-progress").max = total;
      $("#run-progress").value = done;
      $("#progress-text").textContent = `${done} / ${total} · ${statusText(run.status)}`;
    } else {
      $("#run-progress").removeAttribute("value");
      $("#progress-text").textContent = `${statusText(run.status)} · ${activeStatuses.has(run.status) ? "等待计数更新" : "进度计数未知"}`;
    }
    $("#run-progress").hidden = !activeStatuses.has(run.status) && !(typeof done === "number");
    if (Object.keys(progress).length) output("#progress-details", progress);
    else $("#progress-details").hidden = true;
    const warnings = [
      `测量样本数：${number(summary.sample_count)}。缺失指标保持未知；中断、低样本量与质量不足会限制结论。`,
      run.spec?.protocol_fixture ? "协议替身实验：仅验证协议与工作流，不代表真实模型性能，也不能证明优化有效。" : "结果仅适用于本次数据、环境与负载；请结合质量覆盖率判断可靠性。",
      ...(summary.warnings || []).map(valueText),
    ];
    $("#reliability").textContent = warnings.join("\n");
    if (run.error) showError("#detail-error", valueText(run.error));
    else showError("#detail-error", null);
    $("#metrics").replaceChildren(
      metric("请求吞吐", metrics.requests_per_s, "req/s", "完整测量窗口，包含失败长尾"),
      metric("有效吞吐 Goodput", metrics.goodput_per_s, "req/s", "受质量与目标约束"),
      metric("输出 token 吞吐", metrics.output_tokens_per_s, "tokens/s", "来自服务 usage；缺失不估填"),
      metric("端到端 E2E · P95", metrics.e2e_ms?.p95, "ms", `有效样本 ${number(metrics.e2e_ms?.count)}`),
      metric("首块 TTFT · P95", metrics.ttft_ms?.p95, "ms", `有效样本 ${number(metrics.ttft_ms?.count)}`),
      metric("均摊 TPOT · P95", metrics.tpot_ms?.p95, "ms/token · 估计值", `有效样本 ${number(metrics.tpot_ms?.count)}`),
    );
    const tbody = $("#category-table tbody");
    tbody.replaceChildren();
    const groups = summary.groups || {};
    if (!Object.keys(groups).length) { const tr = element("tr"); const td = element("td", "暂无类别测量证据"); td.colSpan = 5; tr.append(td); tbody.append(tr); }
    for (const [category, group] of Object.entries(groups)) {
      const g = group.metrics || group;
      const tr = element("tr");
      [category, number(g.sent), number(g.requests_per_s), number(g.e2e_ms?.p95), number(g.ttft_ms?.p95)].forEach((v) => tr.append(element("td", v)));
      tbody.append(tr);
    }
    output("#metric-details", {metrics, definitions: summary.definitions || "暂无口径定义"});
    const quality = summary.quality || {};
    $("#quality").replaceChildren(element("p", `通过 ${number(quality.pass)} · 不通过 ${number(quality.fail)} · 未知 ${number(quality.unknown)}`),
      element("p", `覆盖率 ${ratio(quality.coverage)} · 通过率 ${ratio(quality.pass_rate)} · 错误率 ${ratio(metrics.error_rate)}`),
      element("small", "未知质量不计为通过。分母口径见完整指标定义。"));
    output("#goals", summary.goals?.length ? summary.goals.map((goal) => ({...goal, status: statusText(goal.status)})) : "暂无目标判定；未知不代表达标。");
    renderTelemetry(run);
    renderRecommendations(run.diagnostics || []);
    const selected = $("#retest-candidate").value;
    $("#retest-candidate").replaceChildren(new Option("选择已记录的实验", ""));
    state.runs.filter((candidate) => candidate.id !== run.id).forEach((candidate) => $("#retest-candidate").add(new Option(`${candidate.spec?.name || candidate.id} · ${candidate.id.slice(0, 8)} · ${statusText(candidate.status)}`, candidate.id)));
    if (state.runs.some((candidate) => candidate.id === selected && candidate.id !== run.id)) $("#retest-candidate").value = selected;
    output("#snapshot", {spec: run.spec, profile: run.profile, parent_id: run.parent_id});
    if (run.retest) {
      $("#retest-result").replaceChildren(element("div", `已保存的复测关联 · ${statusText(run.retest.status)}`, "result-status"),
        element("pre", pretty(run.retest)));
    }
    output("#request-audit", (run.records || []).map(({output_text, messages, body, input_text, response, ...record}) => record));
    renderRaw();
    $("#exports").replaceChildren();
    for (const [format, title] of [["markdown", "Markdown"], ["json", "JSON"], ["html", "HTML"]]) {
      const link = element("a", `下载 ${title}`);
      link.href = `/api/runs/${encodeURIComponent(run.id)}/report?format=${format}`;
      link.download = `experiment-${run.id}.${format === "markdown" ? "md" : format}`;
      $("#exports").append(link);
    }
  }
  function renderRecommendations(diagnostics) {
    const target = $("#recommendations");
    target.replaceChildren();
    if (!diagnostics.length) { target.append(element("p", "证据不足：暂无可支持的调整建议。先检查请求记录、质量与资源观测。", "muted")); return; }
    for (const diagnostic of diagnostics) {
      const article = element("article", null, "recommendation");
      article.append(element("h3", diagnostic.title || "待验证建议"));
      const dl = element("dl");
      for (const [key, title] of [["evidence", "证据"], ["confidence", "置信度"], ["adjustment", "调整项"], ["risk", "风险"], ["validation", "验证条件"], ["status", "状态"]]) {
        dl.append(element("dt", title), element("dd", valueText(diagnostic[key])));
      }
      article.append(dl);
      target.append(article);
    }
  }
  function renderSweep(summary) {
    const variable = summary.variable === "rate" ? "到达速率 req/s" : "并发数";
    const points = summary.points || [];
    $("#sweep-variable").textContent = variable;
    const eligible = (summary.eligible_points || []).map((point) => number(point)).join("、");
    const best = typeof summary.best_point === "number" ? `已测最佳点：${number(summary.best_point)}` : "无可推荐最佳点";
    $("#sweep-assessment").textContent = `${best}。已测达标点：${eligible || "无"}。${summary.comparable ? "条件可比较。" : "配置存在差异，不能视为受控扫描。"}`;
    $("#sweep-warnings").textContent = (summary.warnings || []).map(valueText).join("\n") || "没有额外告警；结论仍只适用于已测点。";
    const body = $("#sweep-table tbody");
    body.replaceChildren();
    for (const point of points) {
      const tr = element("tr");
      [number(point.value), number(point.repeats), number(point.requests_per_s), number(point.goodput_per_s),
        number(point.p95_e2e_ms), ratio(point.error_rate),
        `${point.eligible ? "达标" : "未获推荐资格"} ${(point.reasons || []).map(valueText).join("；")}`]
        .forEach((value) => tr.append(element("td", value)));
      body.append(tr);
    }
    if (!points.length) { const tr = element("tr"); const td = element("td", "暂无可展示的已测点"); td.colSpan = 7; tr.append(td); body.append(tr); }
    const chart = $("#sweep-chart");
    chart.replaceChildren();
    const known = points.filter((point) => typeof point.requests_per_s === "number" && Number.isFinite(point.requests_per_s) && point.requests_per_s >= 0);
    if (known.length) {
      const svgNode = (tag, attrs, text) => {
        const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
        Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
        if (text) node.textContent = text;
        return node;
      };
      const width = Math.max(580, known.length * 64 + 80);
      const svg = svgNode("svg", {viewBox: `0 0 ${width} 220`, role: "img", "aria-label": `已测${variable}与请求吞吐散点图；精确数值见下表`});
      svg.append(svgNode("text", {x: 12, y: 18}, "请求吞吐 req/s"));
      svg.append(svgNode("line", {x1: 45, y1: 175, x2: width - 20, y2: 175, class: "chart-axis"}));
      const max = Math.max(1, ...known.map((point) => point.requests_per_s));
      known.forEach((point, index) => {
        const x = 65 + index * (width - 110) / Math.max(1, known.length - 1);
        const y = 160 - point.requests_per_s / max * 110;
        svg.append(svgNode("line", {x1: x, y1: 175, x2: x, y2: y, class: "chart-stem"}));
        svg.append(svgNode("circle", {cx: x, cy: y, r: 5, class: "chart-point"}));
        svg.append(svgNode("text", {x, y: y - 14, "text-anchor": "middle"}, number(point.requests_per_s)));
        svg.append(svgNode("text", {x, y: 200, "text-anchor": "middle"}, number(point.value)));
      });
      chart.append(svg);
    } else chart.append(element("p", "吞吐证据未知，待实验完成后刷新。", "muted"));
    $("#sweep-result").hidden = false;
    $("#load-sweep").setAttribute("aria-expanded", "true");
  }
  $("#load-sweep").addEventListener("click", () => action($("#load-sweep"), "#detail-error", async () => {
    const id = state.current.parent_id;
    const summary = await api(`/api/plans/${encodeURIComponent(id)}/summary`);
    state.sweepPlan = id;
    renderSweep(summary);
  }));
  function renderRaw() {
    const node = $("#raw-responses");
    node.replaceChildren();
    node.hidden = !$("#raw-opt-in").checked;
    if (!node.hidden) node.textContent = pretty((state.current?.records || []).map((record) => ({
      request_id: record.request_id, phase: record.phase, status: record.status, output_text: record.output_text ?? null,
    })));
  }
  $("#raw-opt-in").addEventListener("change", renderRaw);
  $("#refresh").addEventListener("click", () => action($("#refresh"), "#global-error", refreshRuns));
  $("#refresh-detail").addEventListener("click", () => action($("#refresh-detail"), "#detail-error", () => openRun(state.current.id)));
  $("#cancel").addEventListener("click", () => action($("#cancel"), "#detail-error", async () => {
    await api(`/api/runs/${encodeURIComponent(state.current.id)}/cancel`, {});
    await refreshRuns();
    await openRun(state.current.id);
  }));
  $("#clone-run").addEventListener("click", () => action($("#clone-run"), "#detail-error", async () => {
    requireAppliedJSON();
    fillForm(state.current.spec);
    $("#editor-feedback").textContent = `已复制基线 ${state.current.id}。请记录环境调整；启动将使用新的有界预算，完成后在基线详情中关联复测。`;
    navigate("editor");
  }));
  $("#labels-file").addEventListener("change", () => action(null, "#detail-error", async () => {
    const text = await readFile($("#labels-file"));
    if (text === null) return;
    const labels = parseJSON(text, "质量标签");
    if (!labels || Array.isArray(labels) || typeof labels !== "object" || !Object.keys(labels).length
        || Object.values(labels).some((label) => !["pass", "fail", "unknown"].includes(label))) {
      throw new Error('标签需要 JSON 对象，例如 {"request-id":"pass"}；值只允许 pass / fail / unknown。');
    }
    state.current = await api(`/api/runs/${encodeURIComponent(state.current.id)}/labels`, labels);
    renderDetail(state.current);
    $("#labels-feedback").textContent = "标签已更新；质量、建议与目标已重新分析。";
    $("#labels-file").value = "";
  }));
  $("#evaluate-retest").addEventListener("click", () => action($("#evaluate-retest"), "#detail-error", async () => {
    const candidate = $("#retest-candidate").value;
    if (!candidate) throw new Error("请选择一个不同于基线的复测候选实验。");
    const change = Number($("#retest-change").value);
    if (!Number.isFinite(change) || change < 0) throw new Error("最小相对改善必须是非负数值。");
    const criterion = {metric: $("#retest-metric").value, direction: $("#retest-direction").value, min_relative_change: change};
    const field = $("#retest-field").value;
    if (field) {
      const before = Number($("#retest-before").value);
      const after = Number($("#retest-after").value);
      if (!Number.isFinite(before) || !Number.isFinite(after) || before <= 0 || after <= 0
          || (field === "load.concurrency" && (!Number.isInteger(before) || !Number.isInteger(after)))) {
        throw new Error("变更前后值必须为正数；并发必须为整数。数值还需与实验快照一致。");
      }
      criterion.change = {field, before, after};
    }
    const result = await api("/api/retest", {baseline_id: state.current.id, candidate_id: candidate, criterion});
    // Keep submitted identities and criterion visible even if an older API omits them from its response.
    const association = {...result, baseline_id: state.current.id, candidate_id: candidate, criterion};
    $("#retest-result").replaceChildren(element("div", statusText(result.status), "result-status"),
      element("div", `基线 ${state.current.id} → 复测 ${candidate}`), element("pre", pretty(association)));
  }));
  function renderCandidates() {
    const selected = new Set($$("#compare-candidates input:checked").map((input) => input.value));
    $("#compare-candidates").replaceChildren();
    if (!state.runs.length) $("#compare-candidates").append(element("p", "暂无实验可比较。先完成基线与候选实验。", "muted"));
    for (const run of state.runs) {
      const label = element("label", null, "check compare-item");
      const input = element("input");
      input.type = "checkbox";
      input.value = run.id;
      input.checked = selected.has(run.id);
      label.append(input, element("span", `${run.spec?.name || run.id} · ${run.spec?.endpoint?.model || "未知模型"} · ${run.id.slice(0, 8)} · ${statusText(run.status)}`));
      $("#compare-candidates").append(label);
    }
  }
  $("#compare").addEventListener("click", () => action($("#compare"), "#global-error", async () => {
    const ids = $$("#compare-candidates input:checked").map((input) => input.value);
    if (ids.length < 2 || ids.length > 32) throw new Error("请选择 2—32 个实验再比较。");
    const result = await api("/api/compare", {ids});
    $("#compare-result").replaceChildren(element("div", result.best_run_id ? `推荐实验：${result.best_run_id}` : "无可推荐胜出实验", "result-status"),
      element("div", result.comparable ? "条件可比较；请核对质量和约束。" : "存在比较限制，请检查差异与证据。"), element("pre", pretty(result)));
  }));
  action(null, "#global-error", refreshRuns);
  window.setInterval(async () => {
    if (document.hidden || state.polling) return;
    state.polling = true;
    try {
      await refreshRuns();
      if (state.view === "detail" && state.current) {
        const run = await api(`/api/runs/${encodeURIComponent(state.current.id)}`);
        if (JSON.stringify(run) !== JSON.stringify(state.current)) {
          state.current = run;
          renderDetail(run);
        }
        if (state.sweepPlan === run.parent_id && !$("#sweep-result").hidden) {
          renderSweep(await api(`/api/plans/${encodeURIComponent(run.parent_id)}/summary`));
        }
      }
    } catch (error) {
      $("#connection").textContent = "本地服务连接异常";
      showError("#global-error", error);
    } finally { state.polling = false; }
  }, 2500);
})();
