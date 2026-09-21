# F08：实验期间的 Prometheus 观测

本切片只实现 `perfworkbench/telemetry.py`、`tests/test_telemetry.py` 和本文档。
配置校验与实验启动/取消由父级实现；遵循 `contracts.md` 和已批准的架构、sprint。
构造采集器、读取快照不会访问网络。只有显式启动实验后，runner 才调用 `start()`。

## 接入接口

```python
from perfworkbench.telemetry import TelemetryCollector

# spec 已由 ExperimentSpec 校验并 model_dump(mode="json")。
collector = TelemetryCollector(spec["telemetry"], run_dir / "telemetry.jsonl")
collector.start()
try:
    run_explicitly_launched_experiment()
finally:
    collector.stop()
samples = collector.snapshot()
```

- `parse_metrics(text: str, mappings: list) -> dict`：纯解析函数，返回 canonical key → 指标对象。
  非法文本抛出固定消息 `ValueError("invalid_metrics")`，不回显服务端文本。
- `scrape_source(source: dict, timeout_s=3.0) -> dict`：同步、单次 GET，返回一个样本。
  环境变量在每次请求时读取；不会把密钥复制进配置或样本。
- `TelemetryCollector(config: dict, output_path: Path)`：接受 telemetry 配置或含 `telemetry` 的完整配置，
  深拷贝配置；后续修改原配置不改变正在运行的采集。
- `start()` 立即启动第一轮，运行中重复调用幂等。每轮按配置顺序逐个采集，完成一轮后等待
  `interval_s`；慢端点不会产生重叠请求或补发积压轮次。
- `stop()` 先停止调度，唤醒间隔等待，排空当前在途请求并关闭文件；不启动剩余端点。
  正常停止幂等。已停止的实例不可重新启动，应为下个实验构造新实例。
- `snapshot()` 返回本实例全部已成功写入并 flush 的样本深拷贝；不读取文件中的历史实验。
  JSONL 以追加方式写入，每行一个样本，新建文件权限为 `0600`；一个输出路径应由一个采集器独占。
  空 sources 不创建文件或线程。
- 文件打开/写入失败分别通过 `start()`/`stop()` 抛出安全消息
  `OSError("telemetry_output_unavailable")`。其他后台异常在 `stop()` 抛出
  `RuntimeError("telemetry_collection_failed")`；runner 应记录失败，不能将丢失观测当作完整采集。

计划总时限、取消和 sources 数量由父级控制；采集器不自行启动实验，也不做常驻监控。
内存快照与 JSONL 随本次实验的样本数增长，不暗中截断历史；大规模实验需结合间隔、时限与标签基数控制规模。

## 样本语义

```json
{
  "timestamp": 1790000000.0,
  "source": "npu-exporter",
  "status": "ok",
  "metrics": {
    "device_utilization_ratio": {
      "value": 0.5,
      "unit": "ratio",
      "kind": "gauge",
      "series": [
        {"value": 20.0, "labels": {"device": "0"}, "metric": "example_util_percent"},
        {"value": 80.0, "labels": {"device": "1"}, "metric": "example_util_percent"}
      ],
      "status": "available",
      "reason": null
    }
  }
}
```

`timestamp` 是客户端发起采集时的 UTC Unix 秒；不采用 exporter 自带时间计算请求时延，
也不能与另一台机器的时间直接相减推断阶段耗时。
source 的 `ok` 表示 HTTP 与文本解析成功，某个指标仍可为 `missing`。
HTTP/解析失败时 source 为 `error`，附固定 `error` 代码；所有预期指标仍存在，标记缺失。

`series[].value` 保留转换前的原始数值，`metric` 保留实际导出的名字，`labels` 保留选中序列的全部标签。
标签字符串由 Prometheus 解析器解码，不保留原始转义写法或标签排列顺序。
映射的 `kind` 明确指定 gauge/counter；不根据名字猜类型，TYPE/HELP 注释不会改变原始采样名。
`value` 是每条选中序列乘以 `scale` 后的聚合值。`labels` 是精确的子集过滤，不是正则；
`sum` 求和、`max` 取最大、`mean` 是等权平均，不自动按显存容量加权。

缺失或无效值使用 JSON null，绝不补 0；实际观测到的 0 是 available。
NaN/Inf 在序列中也转为 null；任何选中序列非有限、转换/求和溢出、重复序列或负 counter
都会使整个指标缺失，避免部分求和伪装完整结果。ratio 要求每条转换后的值和最终聚合都在 `[0,1]`；
不会通过截断、平均或隐式除以 100 掩盖错误。

指标原因：`metric_not_found`、`labels_not_matched`、`non_finite_value`、`ratio_out_of_range`、
`negative_counter`、`duplicate_series`。完整网络失败原因见后文。

## 空映射的 vLLM 默认值

空 `mappings` 只启用以下六项；非空映射完全替代默认表。
每个 source 的 canonical key 应唯一；同一指标多个设备通过标签与聚合表达。

| Canonical key | 实际 sample 名 | kind | 聚合 | unit / scale |
| --- | --- | --- | --- | --- |
| queue_waiting | vllm:num_requests_waiting | gauge | sum | requests / 1 |
| requests_running | vllm:num_requests_running | gauge | sum | requests / 1 |
| kv_cache_usage_ratio | vllm:kv_cache_usage_perc | gauge | max | ratio / 1 |
| preemptions_total | vllm:num_preemptions_total | counter | sum | events / 1 |
| prefix_hits_total | vllm:prefix_cache_hits_total | counter | sum | tokens / 1 |
| prefix_queries_total | vllm:prefix_cache_queries_total | counter | sum | tokens / 1 |

2026-09-21 核对 [vLLM Production Metrics](https://docs.vllm.ai/en/stable/usage/metrics/)：
KV 的 `*_perc` 已是 0–1，prefix cache 计数单位是 token。
文档中的 counter 构造名不一定带 `_total`；
[Prometheus Python Counter 文档](https://prometheus.github.io/client_python/instrumenting/counter/)
说明文本导出的 sample 名会带此后缀。本实现按导出名字匹配，不添加猜测性的别名。
旧版本或不同 exporter 名称应显式映射；不自动启用硬件指标。

## Ascend exporter 的具体映射方法

当前验证的是 Prometheus HTTP 协议、标签和数值转换，**没有 Ascend/NPU 真机性能验证**。
不同 exporter/驱动版本的命名和单位不能假定相同；以下名字是教学示例，不能当作 Ascend 固定指标名。

1. 在已授权环境查看 exporter `/metrics` 中的实际 sample、HELP 和 TYPE，记录 exporter/驱动版本。
2. 找出设备利用率、已用显存、总显存的实际名字，核实单位和设备/实例标签。
3. 将下面三个 `example_*` 名称替换为现场 sample 名；把 `device` 替换成现场卡号标签名。
4. 利用率若为百分数，配置 `scale: 0.01`；若已是 0–1，则用 `1.0`。
   显存若为 bytes 用 `1`、MiB 用 `1048576`、GiB 用 `1073741824`；MB 与 MiB 不可混用。
5. 映射到 `device_utilization_ratio`、`device_memory_used_bytes`、`device_memory_total_bytes`，
   都设为 gauge。单卡用标签过滤；多卡利用率明确选择 max 或等权 mean，显存总量通常选 sum。
   检查是否同时导出了设备与分区统计，避免父设备/子分区或重复副本被重复求和。
6. 在显式实验期间核对 `series` 原始值/标签与 exporter 一致，并确认 canonical 转换结果。
   `missing` 应修正映射、过滤或单位，不能填零。

```json
{
  "interval_s": 1.0,
  "sources": [{
    "name": "ascend-card-0",
    "url": "http://127.0.0.1:9400/metrics",
    "api_key_env": "ASCEND_METRICS_API_KEY",
    "mappings": [
      {"key": "device_utilization_ratio", "metric": "example_util_percent",
       "kind": "gauge", "scale": 0.01, "labels": {"device": "0"}, "aggregation": "max"},
      {"key": "device_memory_used_bytes", "metric": "example_memory_used_mib",
       "kind": "gauge", "scale": 1048576, "labels": {"device": "0"}, "aggregation": "sum"},
      {"key": "device_memory_total_bytes", "metric": "example_memory_total_mib",
       "kind": "gauge", "scale": 1048576, "labels": {"device": "0"}, "aggregation": "sum"}
    ]
  }]
}
```

只把环境变量名写进配置；如端点不需认证，将 `api_key_env` 设为 null。
认证协议当前仅支持环境变量读取的 Bearer token。硬件 exporter 通常不提供引擎队列/KV 指标；
引擎 source 应独立配置。NVIDIA 或其他硬件 exporter 使用相同的显式映射流程，没有自动硬件探测。

## Counter 与重置

`counter_delta(previous_metric, current_metric)` 接受同一 source、同一 canonical key、同一映射的两个指标对象。
若所有 metric+labels 身份一致且每条原始 counter 单调不减，返回 canonical 聚合值之差。
出现任意设备 counter 减少，返回 `value: null, status: missing, reason: counter_reset, reset: true`。
标签集合变化返回 `series_changed`；任一指标缺失或非 counter 返回 `counter_unavailable`。
原始计数和样本保持不变。调用方负责检查采样时间顺序、间隔和来源；不要把累计值当瞬时速率。
这里只能识别采样间可见的下降；重置后很快超过上次数值无法仅凭两个样本发现。

## 网络边界与脱敏

- 只 GET 配置的 HTTP(S) URL；不自动发现端点，不重试、不跟随任何 3xx，不使用环境代理，正常验证 TLS。
- URL 中的用户名/密码被拒绝；API Key 在发送时从环境变量读取为 `Authorization: Bearer ...`。
- 固定响应上限 2 MiB，同时检查 Content-Length 与累计接收字节；没有 Content-Length 也有上限。
  请求声明 `Accept-Encoding: identity`，拒绝压缩响应，避免解压后膨胀。文本按 UTF-8 严格解码。
- 默认 HTTPX 网络操作超时为 3 秒；每次响应体读取还检查从请求开始计的单调时钟期限。
  这不是跨 DNS、缓慢响应头及在途阻塞读取的硬性墙钟上限，`stop()` 会等待在途同步请求结束。
  runner 的计划时限仍负责整个实验；不要将 HTTPX 的单次读取超时当作整个实验时限。
  参见 [HTTPX timeout 语义](https://www.python-httpx.org/advanced/timeouts/)。
- 错误只含代码：`invalid_url`、`missing_api_key`、`redirect_rejected`、`http_<status>`、
  `response_too_large`、`unsupported_encoding`、`timeout`、`network_error`、`invalid_metrics`。
  不保存 URL、响应体、Location 或异常原文；原始标签是本地观测数据，分享报告仍由报告层脱敏。

## TDD 与验证记录

使用 `aet-implementing-requirement` 和 `test-driven-development`。
按要求执行语言 resolver：Python 在各配置层均无规范，采用 Python 通用最佳实践。
只维护指定的三个文件，不创建额外实现记录，不提交 Git。

- [x] 解析器：先观察 23 个失败，再实现，23 passed。
- [x] 真实本地 HTTP：补充 22 个用例，观察 22 failed / 23 passed；实现后 45 passed。
  首次受 sandbox 的本地监听限制而无法执行，提升到本地 socket 权限后重新确认 red；
  修正测试哨兵与错误代码同名、未监听端口行为依平台而异两个 fixture 问题。
- [x] 生命周期与 counter：补充 12 个用例，观察 12 failed / 45 passed；实现后 57 passed。
- [x] 真实 HTTP、环境认证/代理、重定向、大小限制、无效文本、非有限值、慢响应、JSONL 追加、
  在途停止、多来源失败隔离、快照复制与每设备 reset 均有行为测试；未 mock HTTP 客户端。
- [x] 最终覆盖率检查：本模块 91%（192 statements / 17 missed），57 passed。
- [x] 指定两个 Python 文件的 Ruff 检查与格式检查通过；重构后重新运行 57 个测试通过。

复现（项目目录中，测试需允许 loopback socket）：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_telemetry.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE=/private/tmp/f08-telemetry-coverage \
  .venv/bin/python -m pytest tests/test_telemetry.py -q -p no:cacheprovider \
  --cov=perfworkbench.telemetry --cov-report=term-missing
```

这些用例证明本地协议和生命周期行为，不代表真实模型吞吐或 Ascend/NPU 上的兼容性与性能。
