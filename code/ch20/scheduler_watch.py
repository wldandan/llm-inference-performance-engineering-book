#!/usr/bin/env python3
"""Watch what the scheduler is doing, and read the three onsets out of it.

20.7 names three signals and puts them in order: Running 相对上限最早动，
Waiting 长度次之，抢占计数最晚但最严重。The whole point of this script is the
interval between the first two, because that interval is how much warning you
get, and it decides which metric your alert should sit on.

Three subcommands:

  collect      poll a live vLLM /metrics endpoint and write a time series.
               Needs a real service.
  analyze      read a trace and report the three onsets, the lead time, and a
               verdict (KV 不足 / token 预算不足 / 未饱和). Offline.
  queue-model  the ρ/(1−ρ) table from 20.6, and the comparison 20.6 asks for.
               ρ and S come from the instance's full-load throughput
               (--capacity-qps) and the arrival rate (--arrival-qps):
               ρ = arrival ÷ capacity, S = 1 ÷ capacity. It then adds what
               20.6 adds on top of M/M/1: the Kingman variability factor,
               the P99 of the queue time, an Erlang C comparison for a
               multi-slot instance, and how long a burst takes to drain.
               A trace's mean running_ratio is still accepted as a rough,
               usually low, stand-in for ρ. Offline.

Two decisions that are the script's own, not vLLM's:

  An onset needs `--sustain` consecutive samples, default 3. A single sample
  over the line is noise, and a trace full of one-sample onsets is worse than
  no trace: it puts an alert on jitter.

  analyze refuses rather than guesses. No running_limit means running_ratio is
  unknowable, so there is no saturation onset to report; no preemption counter
  means the most severe of the three signals is simply absent, and a verdict
  that ignores it would be wrong in the one case that matters.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# 20.8 fixes the series field names; the trace format is these keys per sample
# plus the timestamp.
SAMPLE_FIELDS = ("running", "waiting", "running_ratio", "kv_usage",
                 "preemption_total", "batched_tokens")

# vLLM exposes these in Prometheus text format. Names drift between versions,
# so each field lists the candidates in order and collect takes the first hit.
METRIC_CANDIDATES = {
    "running": ("vllm:num_requests_running",),
    "waiting": ("vllm:num_requests_waiting",),
    "kv_usage": ("vllm:gpu_cache_usage_perc", "vllm:kv_cache_usage_perc"),
    "preemption_total": ("vllm:num_preemptions_total",
                         "vllm:num_preemption_total"),
    "batched_tokens": ("vllm:prompt_tokens_total",),
}

# 20.6: ρ/(1−ρ) at the four utilisations the chapter tabulates.
QUEUE_TABLE_RHO = (0.5, 0.8, 0.9, 0.95)

# 20.6 lists three ways LLM serving breaks M/M/1's assumptions. They are part of
# the output, not a footnote, because a millisecond number from this model is
# the wrong thing to take away.
MMK_CAVEATS = (
    "服务台不止一个：式子把整个实例当成一个服务台，就服务台个数这一项而言是上界。批量近乎免费的"
    "区间里实例更像几十个服务台，排队少得多（--slots 给出 Erlang C 的对照），但接近饱和时陡增"
    "这个形状不变。另两条不符把真实排队往上推，三处合起来偏哪边要实测对照。",
    "服务时长不服从指数分布：M/M/1 要求服务时长的变异系数是 1，输出长度长尾时远大于 1，"
    "等待按 Kingman 的 (Ca² + Cs²)/2 放大（--service-cv）；式子给的是平均，P99 另算。",
    "容量本身会缩：抢占要重算 Prefill，等效于服务能力下降、ρ 自己往上走，式子里没有这一项。",
)

# P99 of the queue time under M/M/1: P(W_q > t) = ρ·exp(−(1−ρ)t/S), so the
# 99th percentile is S·ln(100ρ)/(1−ρ). It is zero when ρ ≤ 0.01, because then
# fewer than one request in a hundred waits at all.
P99_TAIL = 0.01


class TraceError(Exception):
    """A trace that cannot support the reading asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise TraceError(message)


# --------------------------------------------------------------------------
# collect: needs a live service
# --------------------------------------------------------------------------

def parse_prometheus(text: str) -> dict[str, float]:
    """Flatten a Prometheus exposition body to {metric_name: value}.

    Labelled series are summed, which is what we want for the per-model labels
    vLLM attaches: one service, one number.
    """
    out: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_:][A-Za-z0-9_:]*)(\{[^}]*\})?\s+(\S+)$", line)
        if not m:
            continue
        name, _labels, raw = m.groups()
        try:
            value = float(raw)
        except ValueError:
            continue
        out[name] = out.get(name, 0.0) + value
    return out


def pick(metrics: dict[str, float], field: str) -> float | None:
    for name in METRIC_CANDIDATES[field]:
        if name in metrics:
            return metrics[name]
    return None


def collect(url: str, interval: float, duration: float,
            running_limit: int | None,
            token_budget: int | None = None,
            fetch=None) -> dict:
    """Poll /metrics and build a trace.

    `fetch` is injected by the tests; in production it is urlopen.
    """
    if fetch is None:
        def fetch(target: str) -> str:  # pragma: no cover - needs a service
            with urllib.request.urlopen(target, timeout=5) as resp:
                return resp.read().decode("utf-8", "replace")

    endpoint = url.rstrip("/") + "/metrics"
    samples: list[dict] = []
    # 采样数由 duration 和 interval 决定，而不是每轮再比一次墙上时间：后者在
    # duration 是 interval 的整数倍时会多采或少采一个，取决于这一次抓取花了多久。
    count = (int(duration / interval) + 1) if interval > 0 else 1
    started = time.monotonic()
    prev_prompt_tokens: float | None = None
    for index in range(count):
        if index > 0:
            time.sleep(interval)
        elapsed = time.monotonic() - started
        try:
            body = fetch(endpoint)
        except (urllib.error.URLError, OSError) as exc:  # pragma: no cover
            samples.append({"t": round(elapsed, 3), "error": str(exc)})
            continue
        metrics = parse_prometheus(body)
        running = pick(metrics, "running")
        prompt_tokens = pick(metrics, "batched_tokens")
        # batched_tokens 在 /metrics 里是累计值，这里差分成“这一个采样间隔里新处理了
        # 多少 prompt token”。它不是“一步处理了多少”：一个间隔里有很多步，而且这个
        # 计数器不含 Decode。所以 trace 里 tokens_per_step 记 False，analyze 不拿它
        # 去和每步的 max_num_batched_tokens 比（20.8）。
        step_tokens = None
        if prompt_tokens is not None:
            if prev_prompt_tokens is not None:
                step_tokens = prompt_tokens - prev_prompt_tokens
            prev_prompt_tokens = prompt_tokens
        sample = {
            "t": round(elapsed, 3),
            "running": running,
            "waiting": pick(metrics, "waiting"),
            "kv_usage": pick(metrics, "kv_usage"),
            "preemption_total": pick(metrics, "preemption_total"),
            "batched_tokens": step_tokens,
        }
        if running is not None and running_limit:
            sample["running_ratio"] = round(running / running_limit, 4)
        samples.append(sample)
    return {
        "url": url,
        "interval_s": interval,
        "duration_s": duration,
        "running_limit": running_limit,
        "max_num_batched_tokens": token_budget,
        "tokens_per_step": False,
        "tokens_field_note": "batched_tokens 是 prompt_tokens_total 在一个采样间隔内的差分，不含 Decode，也不是单步值",
        "samples": samples,
    }


# --------------------------------------------------------------------------
# analyze: offline
# --------------------------------------------------------------------------

def first_sustained(samples: list[dict], key: str, predicate,
                    sustain: int) -> float | None:
    """Timestamp of the first of `sustain` consecutive samples satisfying
    `predicate`, or None.

    Returning the time of the FIRST sample of the run, not the last, is
    deliberate: the onset is when the condition started, and reporting the end
    of the confirmation window would make every lead time look shorter than it
    is.
    """
    run = 0
    start: float | None = None
    for s in samples:
        value = s.get(key)
        if value is not None and predicate(value):
            if run == 0:
                start = s["t"]
            run += 1
            if run >= sustain:
                return start
        else:
            run = 0
            start = None
    return None


def analyze(trace: dict, slo_itl_ms: float | None = None,
            sustain: int = 3,
            saturation_ratio: float = 0.95,
            kv_high: float = 0.9) -> dict:
    samples = trace.get("samples") or []
    _require(len(samples) >= sustain,
             f"样本数 {len(samples)} 少于 --sustain {sustain}，"
             "这段 trace 短到连一个 onset 都确认不了")
    _require(any(s.get("running_ratio") is not None for s in samples),
             "trace 里没有 running_ratio：缺 running_limit 时 Running 相对上限无从计算，"
             "而 20.7 说那是最早动的那个信号，没有它这份 trace 判不出饱和")
    _require(any(s.get("preemption_total") is not None for s in samples),
             "trace 里没有 preemption_total：三个信号里最严重的那个缺失，"
             "此时给出的判断在最要命的那种情形下必然是错的")

    saturation_onset = first_sustained(
        samples, "running_ratio", lambda v: v >= saturation_ratio, sustain)
    queue_onset = first_sustained(
        samples, "waiting", lambda v: v > 0, sustain)

    base_preempt = next((s["preemption_total"] for s in samples
                         if s.get("preemption_total") is not None), 0)
    preemption_onset = first_sustained(
        samples, "preemption_total", lambda v: v > base_preempt, 1)

    lead_time = None
    lead_note = ""
    if saturation_onset is not None and queue_onset is not None:
        lead_time = round(queue_onset - saturation_onset, 3)
        if lead_time > 0:
            lead_note = (f"饱和到开始排队有 {lead_time} 秒预警，"
                         "告警配在 running_ratio 上来得及")
        else:
            # 20.7 的顺序被打破了，这本身是个结论：Running 上限不是约束。
            lead_note = ("排队不晚于饱和，说明 max_num_seqs 不是当前的约束，"
                         "真正的约束在 KV 余量或 token 预算上，"
                         "把告警配在 running_ratio 上会完全失灵")
    elif saturation_onset is None:
        lead_note = "整段未持续饱和，lead_time 无从计算"
    else:
        lead_note = "持续饱和但未排队，说明容量刚好够，再加流量就会开始排队"

    ratios = [s["running_ratio"] for s in samples
              if s.get("running_ratio") is not None]
    kvs = [s["kv_usage"] for s in samples if s.get("kv_usage") is not None]
    tokens = [s["batched_tokens"] for s in samples
              if s.get("batched_tokens") is not None]
    preempts = [s["preemption_total"] for s in samples
                if s.get("preemption_total") is not None]

    mean_ratio = sum(ratios) / len(ratios)
    peak_ratio = max(ratios)
    peak_kv = max(kvs) if kvs else None
    preempt_delta = (max(preempts) - min(preempts)) if preempts else 0

    verdict, reason = _verdict(
        saturation_onset=saturation_onset,
        queue_onset=queue_onset,
        preempt_delta=preempt_delta,
        peak_ratio=peak_ratio,
        peak_kv=peak_kv,
        kv_high=kv_high,
        token_budget=trace.get("max_num_batched_tokens"),
        peak_tokens=max(tokens) if tokens else None,
        tokens_per_step=bool(trace.get("tokens_per_step")),
    )

    result = {
        "samples": len(samples),
        "interval_s": trace.get("interval_s"),
        "sustain": sustain,
        "saturation_onset": saturation_onset,
        "queue_onset": queue_onset,
        "preemption_onset": preemption_onset,
        "lead_time": lead_time,
        "lead_time_note": lead_note,
        "running_ratio_mean": round(mean_ratio, 4),
        "running_ratio_peak": round(peak_ratio, 4),
        "kv_usage_peak": peak_kv,
        "preemptions_in_window": preempt_delta,
        "verdict": verdict,
        "verdict_reason": reason,
    }
    if slo_itl_ms is not None:
        result["slo_itl_ms"] = slo_itl_ms
        result["itl_note"] = (
            "这个脚本采的是调度器状态，不是 ITL。要判 ITL 是否越界，"
            "用第 19 章那份记分卡；这里的 --slo-itl 只用来在结论里提醒你两边要对照着看。")
    return result


def _verdict(*, saturation_onset, queue_onset, preempt_delta, peak_ratio,
             peak_kv, kv_high, token_budget, peak_tokens,
             tokens_per_step=False) -> tuple[str, str]:
    """20.8 allows four verdicts. The order of the tests is the order of
    severity in 20.7: preemption first, because it is the one that feeds back
    on itself.

    The token-budget test only runs on a per-step trace. ``collect`` samples on
    a wall-clock interval, so ``batched_tokens`` there is the prompt-token total
    over many steps; comparing that with a per-step budget would misfire on any
    busy service (20.8).
    """
    if preempt_delta > 0 or (peak_kv is not None and peak_kv >= kv_high):
        return ("KV 不足",
                f"窗口内抢占 {preempt_delta} 次、KV 使用率峰值 {peak_kv}；"
                "先按第 16 章降 max_model_len 或提 gpu_memory_utilization，"
                "调 max_num_seqs 在这里不解决问题")
    if saturation_onset is None and queue_onset is None:
        return ("未饱和",
                f"running_ratio 峰值 {round(peak_ratio, 4)}，整段没有持续排队；"
                "这段 trace 不能用来定参数，要先加压到出现排队")
    if tokens_per_step and peak_ratio < 0.95 and token_budget \
            and peak_tokens is not None \
            and peak_tokens >= 0.95 * token_budget:
        return ("token 预算不足",
                f"请求数没到上限（峰值 {round(peak_ratio, 4)}），"
                f"而单步 token 数触到了 {token_budget} 的天花板；"
                "这是 max_num_batched_tokens 在限制，不是 max_num_seqs")
    return ("请求数上限约束",
            f"running_ratio 达到 {round(peak_ratio, 4)} 并开始排队，"
            "KV 和 token 预算都没触顶；这是 max_num_seqs 在限制，"
            "按第 19 章那条 Goodput 曲线找峰值")


# --------------------------------------------------------------------------
# queue-model: offline
# --------------------------------------------------------------------------

def amplification(rho: float) -> float:
    """ρ/(1−ρ). 20.6 tabulates 0.5→1, 0.8→4, 0.9→9, 0.95→19."""
    _require(0 <= rho < 1,
             f"ρ = {rho} 不在 [0, 1) 内：ρ ≥ 1 时队列没有上界地增长，"
             "任何平均值都不再有意义，这时要看的是队列增长速度")
    return rho / (1.0 - rho)


def kingman_factor(arrival_cv: float = 1.0, service_cv: float = 1.0) -> float:
    """(Ca² + Cs²)/2. Poisson arrivals and exponential service give exactly 1."""
    _require(arrival_cv >= 0 and service_cv >= 0, "变异系数不能是负数")
    return (arrival_cv ** 2 + service_cv ** 2) / 2.0


def p99_wait_factor(rho: float) -> float:
    """P99 of the M/M/1 queue time, in units of S: ln(100ρ)/(1−ρ)."""
    amplification(rho)  # same range check
    if rho <= P99_TAIL:
        return 0.0
    return math.log(rho / P99_TAIL) / (1.0 - rho)


def erlang_c(servers: int, rho: float) -> float:
    """Probability that an arrival waits in M/M/c, with ρ the per-server load."""
    _require(servers >= 1, "服务台数至少是 1")
    amplification(rho)
    offered = rho * servers
    blocking = 1.0
    for k in range(1, servers + 1):  # Erlang B, numerically stable recursion
        blocking = offered * blocking / (k + offered * blocking)
    return blocking / (1.0 - rho * (1.0 - blocking))


def multi_server_wait_factor(servers: int, rho: float) -> float:
    """M/M/c mean queue time in units of S = 1/(total throughput): C/(1−ρ)."""
    return erlang_c(servers, rho) / (1.0 - rho)


def drain_seconds(rho: float, capacity_qps: float, burst_factor: float,
                  burst_s: float) -> dict:
    """20.6: a burst of burst_factor × the arrival rate for burst_s seconds.

    Whatever arrives above capacity piles up as backlog, and afterwards only
    the spare capacity (1−ρ)μ works it off.
    """
    amplification(rho)
    _require(capacity_qps > 0, "满载吞吐必须大于 0")
    _require(burst_factor >= 1 and burst_s >= 0, "突发倍数至少是 1，时长不能是负数")
    burst_rho = rho * burst_factor
    backlog = max(0.0, (burst_rho - 1.0) * capacity_qps * burst_s)
    drain = backlog / ((1.0 - rho) * capacity_qps) if backlog else 0.0
    return {"burst_factor": burst_factor, "burst_s": burst_s,
            "burst_rho": round(burst_rho, 4),
            "backlog_requests": round(backlog, 1),
            "drain_s": round(drain, 1)}


def from_capacity(capacity_qps: float, arrival_qps: float) -> tuple[float, float]:
    """20.6: ρ = arrival ÷ full-load throughput, S = 1 ÷ full-load throughput."""
    _require(capacity_qps > 0, "满载吞吐必须大于 0：用第 19 章的扫描读出实例每秒最多完成几条请求")
    _require(arrival_qps >= 0, "到达速率不能是负数")
    rho = arrival_qps / capacity_qps
    _require(rho < 1,
             f"到达 {arrival_qps} 条/秒不低于满载吞吐 {capacity_qps} 条/秒，ρ = {round(rho, 3)}："
             f"队列每秒净增约 {round(arrival_qps - capacity_qps, 2)} 条，"
             "等待随压测时长线性增长，任何平均值都不再有意义")
    return rho, 1000.0 / capacity_qps


def queue_model(service_time_ms: float | None = None,
                rho: float | None = None,
                measured_queue_ms: float | None = None,
                *, arrival_cv: float = 1.0, service_cv: float = 1.0,
                slots: int | None = None,
                capacity_qps: float | None = None,
                burst_factor: float | None = None,
                burst_s: float = 60.0) -> dict:
    table = [{"rho": r, "amplification": round(amplification(r), 4)}
             for r in QUEUE_TABLE_RHO]
    out: dict = {"table": table,
                 "formula": "W_q ≈ S × ρ/(1−ρ) × (Ca² + Cs²)/2",
                 "caveats": list(MMK_CAVEATS)}
    if rho is None:
        return out
    factor = amplification(rho)
    kingman = kingman_factor(arrival_cv, service_cv)
    out["rho"] = rho
    out["amplification"] = round(factor, 4)
    out["kingman_factor"] = round(kingman, 4)
    out["p99_over_s"] = round(p99_wait_factor(rho) * kingman, 2)
    if slots is not None:
        out["slots"] = slots
        out["erlang_c_wait_probability"] = round(erlang_c(slots, rho), 4)
        out["multi_server_over_s"] = round(multi_server_wait_factor(slots, rho), 4)
    if capacity_qps is not None and burst_factor is not None:
        out["burst"] = drain_seconds(rho, capacity_qps, burst_factor, burst_s)
    if service_time_ms is None:
        return out
    predicted = service_time_ms * factor * kingman
    out["service_time_ms"] = round(service_time_ms, 2)
    out["predicted_queue_ms"] = round(predicted, 2)
    out["predicted_p99_queue_ms"] = round(service_time_ms * out["p99_over_s"], 2)
    if slots is not None:
        out["multi_server_queue_ms"] = round(
            service_time_ms * out["multi_server_over_s"] * kingman, 2)
    if measured_queue_ms is None:
        out["reading"] = ("这是形状和量级，不是预测值。正确用法是回答"
                          "“再加 10% 流量会怎样”，不是把这个毫秒数写进报告。")
        return out
    out["measured_queue_ms"] = measured_queue_ms
    # 20.6 的用法：对不上就说明瓶颈不在排队。这里用 3 倍做“差很远”的界，
    # 因为单服务台式子本身是上界，同一量级内的偏差不构成结论。
    ratio = (measured_queue_ms / predicted) if predicted > 0 else float("inf")
    out["measured_over_predicted"] = round(ratio, 3)
    if predicted == 0:
        out["reading"] = "ρ 为 0 时公式给 0，实测大于 0 说明排队来自突发，不是平均负载"
    elif ratio > 3:
        out["reading"] = (f"实测是式子的 {round(ratio, 2)} 倍，差很远：式子已经是上界，"
                          "瓶颈不在排队本身。先确认 --service-cv 填的是实测的服务时长波动，"
                          "再去看显存和抢占（容量在缩，ρ 比算的高）")
    elif ratio < 1 / 3:
        out["reading"] = (f"实测只有式子的 {round(ratio, 2)} 倍："
                          "要么多服务台效应在起作用，要么等待藏进了 Running"
                          "（批量越过分界点后多出来的负载表现为单步变长，"
                          "Waiting 仍是空的）。对照同期的 running_ratio 和 ITL "
                          "再下结论，别直接判正常")
    else:
        out["reading"] = (f"实测和式子同一量级（{round(ratio, 2)} 倍），"
                          "排队可以解释当前的等待")
    return out


def rho_from_trace(trace: dict) -> float:
    """A rough, usually low, stand-in for ρ: the time-average running_ratio.

    running_ratio is slot occupancy, not 负载率. By Little's law the number
    running is arrival rate × residence time, and a request finishes faster
    when the batch is small, so at partial load occupancy undershoots ρ.
    20.6 prefers --capacity-qps; this stays for traces with nothing else.
    """
    samples = trace.get("samples") or []
    ratios = [s["running_ratio"] for s in samples
              if s.get("running_ratio") is not None]
    _require(bool(ratios), "trace 里没有 running_ratio，无法取 ρ 的代理值")
    mean = sum(ratios) / len(ratios)
    # running_ratio 可以等于 1，而 ρ = 1 在式子里没有定义。这里不做截断，
    # 直接报错，因为悄悄改成 0.99 会给出一个看着合理的假数字。
    _require(mean < 1,
             f"running_ratio 的时间平均是 {round(mean, 4)}，代进 ρ 会除零："
             "这段 trace 全程满载，说明 ρ ≥ 1，该看的是队列增长速度，不是等待时间")
    return mean


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_analyze(r: dict) -> None:
    print(f"样本数            {r['samples']}（间隔 {r['interval_s']} 秒，"
          f"sustain {r['sustain']}）")
    print(f"saturation_onset  {r['saturation_onset']}")
    print(f"queue_onset       {r['queue_onset']}")
    print(f"preemption_onset  {r['preemption_onset']}")
    print(f"lead_time         {r['lead_time']}")
    print(f"                  {r['lead_time_note']}")
    print(f"running_ratio     均值 {r['running_ratio_mean']}，"
          f"峰值 {r['running_ratio_peak']}")
    print(f"kv_usage 峰值     {r['kv_usage_peak']}")
    print(f"窗口内抢占        {r['preemptions_in_window']}")
    print(f"verdict           {r['verdict']}")
    print(f"                  {r['verdict_reason']}")


def print_queue_model(r: dict) -> None:
    print(f"式子              {r['formula']}")
    for row in r["table"]:
        print(f"  ρ = {row['rho']:<5} ρ/(1−ρ) = {row['amplification']}")
    if "rho" in r:
        print(f"本例 ρ            {round(r['rho'], 4)}  放大 {r['amplification']} 倍，"
              f"波动修正 × {r['kingman_factor']}")
        print(f"P99 排队          约 {r['p99_over_s']} 个 S（M/M/1 的形状乘波动修正）")
    if "slots" in r:
        print(f"多服务台对照      {r['slots']} 个槽位按 Erlang C：等待概率 "
              f"{r['erlang_c_wait_probability']}，平均排队 {r['multi_server_over_s']} 个 S")
    if "predicted_queue_ms" in r:
        print(f"预测排队          {r['predicted_queue_ms']} ms"
              f"（S = {r['service_time_ms']} ms），P99 约 {r['predicted_p99_queue_ms']} ms")
    if "multi_server_queue_ms" in r:
        print(f"多服务台下界      {r['multi_server_queue_ms']} ms")
    if "burst" in r:
        b = r["burst"]
        print(f"突发消化          {b['burst_factor']} 倍到达持续 {b['burst_s']} 秒，"
              f"积压 {b['backlog_requests']} 条，消化约 {b['drain_s']} 秒")
    if "measured_queue_ms" in r:
        print(f"实测排队          {r['measured_queue_ms']} ms"
              f"（实测/预测 = {r['measured_over_predicted']}）")
    if "reading" in r:
        print(f"解读              {r['reading']}")
    print("边界")
    for c in r["caveats"]:
        print(f"  - {c}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_collect = sub.add_parser("collect", help="采集调度器状态时间序列（需要真实服务）")
    p_collect.add_argument("--url", required=True)
    p_collect.add_argument("--interval", type=float, default=0.5)
    p_collect.add_argument("--duration", type=float, default=120.0)
    p_collect.add_argument("--max-num-seqs", type=int, default=None,
                           dest="running_limit",
                           help="running_ratio 的分母，不给则该字段为空")
    p_collect.add_argument("--max-num-batched-tokens", type=int, default=None,
                           dest="token_budget",
                           help="每步的 token 预算，写进 trace 供 analyze 对照")
    p_collect.add_argument("--output", type=Path, required=True)

    p_an = sub.add_parser("analyze", help="从 trace 读出三个 onset 与 lead_time")
    p_an.add_argument("--trace", type=Path, required=True)
    p_an.add_argument("--slo-itl", type=float, default=None)
    p_an.add_argument("--sustain", type=int, default=3)
    p_an.add_argument("--saturation-ratio", type=float, default=0.95)
    p_an.add_argument("--output", type=Path, default=None)

    p_q = sub.add_parser("queue-model", help="20.6 那张 ρ/(1−ρ) 表与实测对照")
    p_q.add_argument("--capacity-qps", type=float, default=None,
                     help="整个实例满载时每秒完成几条请求；S = 1/它")
    p_q.add_argument("--arrival-qps", type=float, default=None,
                     help="到达速率；ρ = 它 ÷ --capacity-qps")
    p_q.add_argument("--service-time-ms", type=float, default=None,
                     help="直接给 S；给了 --capacity-qps 时不用填")
    p_q.add_argument("--rho", type=float, default=None)
    p_q.add_argument("--trace", type=Path, default=None,
                     help="没有满载吞吐时，用 running_ratio 时间平均当 ρ 的粗略代理（通常偏低）")
    p_q.add_argument("--arrival-cv", type=float, default=1.0,
                     help="到达间隔的变异系数，泊松到达是 1")
    p_q.add_argument("--service-cv", type=float, default=1.0,
                     help="服务时长的变异系数，指数分布是 1，长尾输出更大")
    p_q.add_argument("--slots", type=int, default=None,
                     help="并发槽位数（如 max_num_seqs），给出 Erlang C 对照")
    p_q.add_argument("--burst-factor", type=float, default=None,
                     help="突发时到达是平时的几倍，给出积压与消化时间")
    p_q.add_argument("--burst-seconds", type=float, default=60.0)
    p_q.add_argument("--measured-queue-ms", type=float, default=None)

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    try:
        if args.cmd == "collect":
            trace = collect(args.url, args.interval, args.duration,
                            args.running_limit,
                            token_budget=args.token_budget)
            args.output.write_text(
                json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"wrote {args.output}（{len(trace['samples'])} 个样本）")
            return 0
        if args.cmd == "analyze":
            trace = json.loads(args.trace.read_text(encoding="utf-8"))
            result = analyze(trace, slo_itl_ms=args.slo_itl,
                             sustain=args.sustain,
                             saturation_ratio=args.saturation_ratio)
            print_analyze(result)
            if args.output is not None:
                args.output.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                print(f"wrote {args.output}")
            return 0
        rho = args.rho
        service = args.service_time_ms
        if args.capacity_qps is not None and args.arrival_qps is not None:
            rho, service = from_capacity(args.capacity_qps, args.arrival_qps)
        elif args.trace is not None:
            trace = json.loads(args.trace.read_text(encoding="utf-8"))
            rho = rho_from_trace(trace)
        if service is None and args.capacity_qps is not None:
            service = 1000.0 / args.capacity_qps
        result = queue_model(service_time_ms=service, rho=rho,
                             measured_queue_ms=args.measured_queue_ms,
                             arrival_cv=args.arrival_cv,
                             service_cv=args.service_cv,
                             slots=args.slots,
                             capacity_qps=args.capacity_qps,
                             burst_factor=args.burst_factor,
                             burst_s=args.burst_seconds)
        print_queue_model(result)
        return 0
    except TraceError as exc:
        print(f"REJECTED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
