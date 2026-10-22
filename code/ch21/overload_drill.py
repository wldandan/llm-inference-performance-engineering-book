#!/usr/bin/env python3
"""Drill a service past its capacity and read what shape it breaks in.

21.1 puts the whole chapter in one contrast: 全部接受 turns "a few users fail"
into "everyone fails, slowly"; 部分拒绝 keeps the accepted requests healthy. The
only way to know which one you have is to go past capacity on purpose.

Four subcommands:

  run           ramp offered load past capacity and record each step.
                Needs a real service.
  analyze       read a drill report and classify the goodput curve: 健康 /
                退化 / 危险. Offline.
  retry-storm   21.5's amplifier. Two modes: given a failure-rate sequence it
                walks the loop (案例一's table); given a drill report it reads
                the failure rates off the measured ramp, which is the answer to
                案例一's own discussion question. Offline.
  cancel-check  send one long generation, disconnect, and watch whether the
                Running set and KV usage drop. Needs a real service.

Two things this script will not do:

  It will not classify a ramp that never reached capacity. A curve with no
  rejections and no goodput decline says the ramp was too gentle, not that the
  service is healthy, and reporting 健康 there is the one wrong answer that
  would get someone hurt.

  It will not call a flat goodput curve healthy when nothing was rejected.
  Goodput holding while offered load climbs and rejections stay at zero means
  the load generator, not the service, is the bottleneck.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# 21.8 fixes the per-step field names.
STEP_FIELDS = ("offered_qps", "accepted_qps", "rejected_qps", "goodput",
               "p95_ttft", "error_breakdown")

# 21.8: the two curve shapes, and the band between them. A service that keeps
# 90% of its peak goodput past capacity is doing its job; below half, it is
# answering overload by failing everyone.
HEALTHY_FLOOR = 0.90
DANGEROUS_FLOOR = 0.50

# 21.5 lists the errors that may be retried. 超时 is deliberately absent: you do
# not know whether the server is still working on it, and for an LLM request a
# retry means paying for the whole generation twice.
RETRYABLE_ERRORS = ("connection_failed", "503", "429_with_retry_after")
NON_RETRYABLE_ERRORS = ("timeout", "429_without_retry_after")


class DrillError(Exception):
    """A drill report that cannot support the reading asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise DrillError(message)


# --------------------------------------------------------------------------
# 21.5 the amplifier
# --------------------------------------------------------------------------

def bounded_amplification(p: float, retries: int) -> float:
    """1 + p × r. 21.5's shorthand upper bound for a bounded retry policy.

    It is what you get if every retry fails too. With each attempt failing
    independently at the same p the exact value is `exact_amplification`.
    """
    _require(0 <= p <= 1, f"失败率 {p} 不在 [0, 1] 内")
    _require(retries >= 0, f"重试次数 {retries} 不能为负")
    return 1.0 + p * retries


def exact_amplification(p: float, retries: int) -> float:
    """1 + p + p² + … + p^r. 21.5's exact form when attempts fail independently.

    The i-th retry is only sent if the first i attempts all failed, which
    happens with probability p^i. At p = 0.5, r = 2 this is 1.75, not 2.00.
    """
    _require(0 <= p <= 1, f"失败率 {p} 不在 [0, 1] 内")
    _require(retries >= 0, f"重试次数 {retries} 不能为负")
    return sum(p ** i for i in range(retries + 1))


def unbounded_amplification(p: float) -> float:
    """1/(1−p). 21.5's closed form for retrying without limit."""
    _require(0 <= p < 1,
             f"失败率 {p} 到了 1：无限重试下放大系数发散，"
             "这不是一个可以报出来的数字，它就是雪崩本身")
    return 1.0 / (1.0 - p)


def user_visible_failure(p: float, retries: int) -> float:
    """p^(r+1). r 次重试意味着一条请求最多尝试 r+1 次。

    案例一 uses this to tie its own two numbers together: p = 0.73 at the end
    of the loop gives 0.73⁴ ≈ 28%, i.e. 72% availability, which is where the
    stated 71% sits.
    """
    _require(0 <= p <= 1, f"失败率 {p} 不在 [0, 1] 内")
    _require(retries >= 0, f"重试次数 {retries} 不能为负")
    return p ** (retries + 1)


def retry_loop(failure_rates: list[float], retries: int) -> dict:
    """Walk the loop one round per given failure rate.

    The rates are inputs, not predictions: 21.5 says plainly that `p` is a
    function of load, and 案例一's discussion question asks where its 15% came
    from. Feeding measured rates in from a drill (see `rates_from_drill`) is
    that question's answer; feeding the chapter's own sequence in reproduces
    its table.
    """
    _require(bool(failure_rates), "至少要给一个失败率")
    rounds = []
    for i, p in enumerate(failure_rates):
        factor = exact_amplification(p, retries)
        row = {
            "round": i,
            "failure_rate": p,
            "amplification": round(factor, 4),
            "upper_bound": round(bounded_amplification(p, retries), 4),
            "next_load": round(factor, 4),
        }
        if p < 1:
            row["unbounded_amplification"] = round(unbounded_amplification(p), 4)
        rounds.append(row)
    final_p = failure_rates[-1]
    attempts = retries + 1
    fail = user_visible_failure(final_p, retries)
    return {
        "retries": retries,
        "attempts_per_request": attempts,
        "rounds": rounds,
        "final_failure_rate": final_p,
        "user_visible_failure_rate": round(fail, 6),
        "availability": round(1.0 - fail, 6),
        "reading": (
            f"单次失败率走到 {round(final_p * 100, 1)}% 时，一条请求最多试 {attempts} 次，"
            f"用户看到失败的概率是 {round(final_p * 100, 1)}% 的 {attempts} 次方"
            f" = {round(fail * 100, 1)}%，也就是可用性 {round((1 - fail) * 100, 1)}%。"
            "没有任何一轮是负载翻了三倍，是几轮叠出来的。"),
    }


def rates_from_drill(report: dict, initial_p: float, retries: int,
                     max_rounds: int = 40) -> dict:
    """Iterate the loop using failure rates read off a measured ramp.

    This is 案例一's discussion question answered with data: the drill already
    measured how `p` responds to load, so the loop does not need a guess for
    round 1.
    """
    curve = failure_curve(report)
    _require(len(curve) >= 2,
             "失败率曲线至少要两个点才能插值，一档压测说明不了 p 随负载怎么走")
    rates = [initial_p]
    load = exact_amplification(initial_p, retries)
    diverged = False
    for _ in range(max_rounds - 1):
        p = interpolate(curve, load)
        rates.append(p)
        if p >= 1.0:
            diverged = True
            break
        nxt = exact_amplification(p, retries)
        if abs(nxt - load) < 1e-3:
            break  # 不动点，回路稳住了
        load = nxt
    result = retry_loop(rates, retries)
    result["source"] = "drill"
    result["curve_points"] = curve
    result["diverged"] = diverged
    result["fixed_point"] = (not diverged
                             and len(rates) < max_rounds)
    return result


def failure_curve(report: dict) -> list[tuple[float, float]]:
    """[(load_multiple, failure_rate)] from a drill report, sorted by load.

    A step's failure rate is the share of offered requests that did not come
    back as a good request: rejections and errors alike, because from the
    client's point of view both are a failure that its retry policy will act
    on.
    """
    steps = report.get("steps") or []
    _require(bool(steps), "drill 报告里没有 steps")
    capacity = report.get("capacity_qps")
    _require(bool(capacity),
             "drill 报告里没有 capacity_qps：没有它就无法把 offered_qps 换成"
             "容量的倍数，而 21.5 那个回路走的是倍数，不是绝对 QPS")
    out = []
    for s in steps:
        offered = s.get("offered_qps")
        good = s.get("goodput")
        _require(offered is not None and good is not None,
                 "每一档都要有 offered_qps 和 goodput")
        _require(offered > 0, "offered_qps 必须为正")
        p = max(0.0, min(1.0, 1.0 - good / offered))
        out.append((round(offered / capacity, 6), round(p, 6)))
    out.sort(key=lambda pair: pair[0])
    return out


def interpolate(curve: list[tuple[float, float]], load: float) -> float:
    """Linear interpolation, clamped at both ends.

    Clamping rather than extrapolating is deliberate. Extrapolating a failure
    curve past the last measured point produces a number with no measurement
    behind it, and this is exactly the place where an invented number reads as
    reassuring: beyond the ramp, the real curve is steeper than any straight
    line through it.
    """
    if load <= curve[0][0]:
        return curve[0][1]
    if load >= curve[-1][0]:
        return curve[-1][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= load <= x1:
            if x1 == x0:
                return y1
            t = (load - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0), 6)
    return curve[-1][1]


def classify_retry_policy(errors: list[str]) -> dict:
    """21.5's first discipline, as a check rather than a paragraph."""
    unknown = [e for e in errors
               if e not in RETRYABLE_ERRORS and e not in NON_RETRYABLE_ERRORS]
    bad = [e for e in errors if e in NON_RETRYABLE_ERRORS]
    return {
        "retried": [e for e in errors if e in RETRYABLE_ERRORS],
        "must_not_retry": bad,
        "unknown": unknown,
        "ok": not bad and not unknown,
        "reading": ("只重试了明确可重试的错误" if not bad and not unknown
                    else f"重试了不该重试的错误：{bad or unknown}；"
                         "超时尤其危险，一次超时的请求可能已经花了几秒 GPU 时间"),
    }


# --------------------------------------------------------------------------
# analyze: the curve shape
# --------------------------------------------------------------------------

def analyze(report: dict) -> dict:
    steps = sorted(report.get("steps") or [],
                   key=lambda s: s.get("offered_qps", 0))
    _require(len(steps) >= 3,
             f"只有 {len(steps)} 档：至少要三档才能看出曲线形状，"
             "一档在容量以下、一档在附近、一档明显超过")
    for s in steps:
        for field in ("offered_qps", "accepted_qps", "rejected_qps", "goodput"):
            _require(s.get(field) is not None, f"某一档缺 {field}")

    goodputs = [s["goodput"] for s in steps]
    peak = max(goodputs)
    _require(peak > 0, "所有档位的 goodput 都是 0，这份演练没有可读的信息")
    peak_index = goodputs.index(peak)
    tail = goodputs[peak_index:]
    final = goodputs[-1]
    retained = final / peak

    past_peak = steps[peak_index + 1:]
    # 形状只关心「峰值之后拒过没有」；各档的拒绝速率不能相加，那是两个不同
    # 负载档位上的速率，加起来不对应任何时刻的状态。报出去的是末档那一个。
    rejected_past_peak = any(s["rejected_qps"] > 0 for s in past_peak)
    rejected_final = steps[-1]["rejected_qps"]

    # 这里的顺序要紧。先判“压根没压到容量”，否则一条根本没到饱和的曲线会被
    # 判成健康，而那是唯一一种会让人挨伤的错答案。
    if peak_index == len(steps) - 1 and not rejected_past_peak:
        shape = "未到容量"
        reading = ("goodput 一路涨到最后一档且全程没有拒绝，说明这次加压没有超过容量。"
                   "这份演练判不出形状，把 ramp 的上限往上抬再跑一遍。")
    elif retained >= HEALTHY_FLOOR and rejected_past_peak:
        shape = "健康"
        reading = (f"超过容量后 goodput 保持在峰值的 {round(retained * 100, 1)}%，"
                   f"多余流量被拒（末档拒了 {round(rejected_final, 2)} QPS）。"
                   "这是 21.1 那个 B 的形状。")
    elif retained >= HEALTHY_FLOOR and not rejected_past_peak:
        shape = "可疑"
        reading = ("goodput 平稳而一条都没拒：瓶颈可能在压测客户端，不在服务端。"
                   "先确认施压端能打出标称的 offered_qps。")
    elif retained >= DANGEROUS_FLOOR:
        shape = "退化"
        reading = (f"超过容量后 goodput 掉到峰值的 {round(retained * 100, 1)}%："
                   "准入生效了但不够早：Waiting 的阈值不要超过“满载吞吐 × 排队超时”，"
                   "超过这个数的请求注定等不到，再往前挪一点。")
    else:
        shape = "危险"
        reading = (f"超过容量后 goodput 掉到峰值的 {round(retained * 100, 1)}%："
                   "准入没有生效，系统正在用全员失败的方式回应过载，"
                   "这就是 21.1 那个 A。")

    knee = steps[peak_index]
    errors = {}
    for s in steps:
        for kind, count in (s.get("error_breakdown") or {}).items():
            errors[kind] = errors.get(kind, 0) + count

    return {
        "steps": len(steps),
        "goodput_peak": peak,
        "goodput_peak_at_offered_qps": knee["offered_qps"],
        "goodput_final": final,
        "goodput_retained": round(retained, 4),
        "rejected_final_qps": round(rejected_final, 4),
        "rejected_past_peak": rejected_past_peak,
        "shape": shape,
        "reading": reading,
        "error_totals": errors,
        "p95_ttft_at_peak": knee.get("p95_ttft"),
    }


# --------------------------------------------------------------------------
# run / cancel-check: need a real service
# --------------------------------------------------------------------------

def _post(url: str, payload: dict, timeout: float) -> tuple[int, float, str]:
    """POST and return (status, seconds_to_first_byte, error_kind)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(1)
            return resp.status, time.monotonic() - started, ""
    except urllib.error.HTTPError as exc:  # pragma: no cover - needs a service
        kind = "429_with_retry_after" if (
            exc.code == 429 and exc.headers.get("Retry-After")) else str(exc.code)
        return exc.code, time.monotonic() - started, kind
    except TimeoutError:  # pragma: no cover - needs a service
        return 0, time.monotonic() - started, "timeout"
    except (urllib.error.URLError, OSError):  # pragma: no cover
        return 0, time.monotonic() - started, "connection_failed"


def run(url: str, workload: dict, ramp: list[float], capacity_qps: float,
        slo_ttft_ms: float, slo_itl_ms: float, step_seconds: float = 30.0,
        send=None) -> dict:  # pragma: no cover - needs a service
    """Ramp offered load through the given multiples of capacity."""
    if send is None:
        def send(qps: float, seconds: float) -> list[dict]:
            results = []
            interval = 1.0 / qps if qps > 0 else 0.0
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                status, ttft, kind = _post(
                    url.rstrip("/") + "/v1/completions",
                    workload.get("request", {}), timeout=slo_ttft_ms / 1000 * 4)
                results.append({"status": status, "ttft_ms": ttft * 1000,
                                "error": kind})
                time.sleep(max(0.0, interval * (0.5 + random.random())))
            return results

    steps = []
    for multiple in ramp:
        offered = capacity_qps * multiple
        raw = send(offered, step_seconds)
        steps.append(summarize_step(offered, raw, slo_ttft_ms))
    return {
        "url": url,
        "capacity_qps": capacity_qps,
        "ramp": ramp,
        "slo_ttft_ms": slo_ttft_ms,
        "slo_itl_ms": slo_itl_ms,
        "steps": steps,
    }


def summarize_step(offered_qps: float, results: list[dict],
                   slo_ttft_ms: float) -> dict:
    """Turn one step's raw results into the six fields 21.8 lists.

    goodput counts a request only when it succeeded AND met the TTFT SLO, which
    is the ch05 definition narrowed to what a load generator can see per request:
    this drill records a first-token time, not per-token intervals, so the ITL
    half of the SLO is out of reach here. ``slo_itl_ms`` is carried in the report
    to say which ITL line the run was taken under; judging ITL is ch19's
    scorecard. A fast failure is not goodput, and neither is a slow success.
    """
    total = len(results)
    _require(total > 0, "这一档没有任何请求结果")
    seconds = total / offered_qps if offered_qps > 0 else 1.0
    accepted = [r for r in results if r.get("status") == 200]
    rejected = [r for r in results if r.get("status") == 429]
    good = [r for r in accepted if r.get("ttft_ms", 0) <= slo_ttft_ms]
    errors: dict[str, int] = {}
    for r in results:
        kind = r.get("error")
        if kind:
            errors[kind] = errors.get(kind, 0) + 1
    ttfts = sorted(r["ttft_ms"] for r in accepted if r.get("ttft_ms") is not None)
    p95 = None
    if ttfts:
        idx = min(len(ttfts) - 1, int(round(0.95 * (len(ttfts) - 1))))
        p95 = round(ttfts[idx], 2)
    return {
        "offered_qps": round(offered_qps, 4),
        "accepted_qps": round(len(accepted) / seconds, 4),
        "rejected_qps": round(len(rejected) / seconds, 4),
        "goodput": round(len(good) / seconds, 4),
        "p95_ttft": p95,
        "error_breakdown": errors,
    }


def cancel_check(before: dict, after: dict,
                 tolerance: float = 0.05) -> dict:
    """21.4's verification, as a comparison of two scheduler snapshots.

    Taking two snapshots rather than one number is the point: 21.4 says any
    segment of the chain can swallow the cancellation, and the only way to see
    it is that Running and KV did not move after the client went away.
    """
    for name, snap in (("before", before), ("after", after)):
        for field in ("running", "kv_usage"):
            _require(snap.get(field) is not None,
                     f"{name} 快照缺 {field}：取消是否生效只能从这两个数看出来")
    running_drop = before["running"] - after["running"]
    kv_drop = before["kv_usage"] - after["kv_usage"]
    propagated = running_drop >= 1 and kv_drop > tolerance
    return {
        "running_before": before["running"],
        "running_after": after["running"],
        "kv_before": before["kv_usage"],
        "kv_after": after["kv_usage"],
        "running_drop": running_drop,
        "kv_drop": round(kv_drop, 4),
        "propagated": propagated,
        "reading": ("取消已传播到引擎，KV 立即释放" if propagated else
                    "Running 或 KV 没有立即下降，链路上有一段吞掉了取消信号，"
                    "最常见的断点是网关：很多网关在收到完整响应之前不会关闭上游连接"),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_analyze(r: dict) -> None:
    print(f"档位数            {r['steps']}")
    print(f"goodput 峰值      {r['goodput_peak']}"
          f"（offered {r['goodput_peak_at_offered_qps']} QPS）")
    print(f"末档 goodput      {r['goodput_final']}"
          f"（峰值的 {round(r['goodput_retained'] * 100, 1)}%）")
    print(f"末档拒绝          {r['rejected_final_qps']} QPS")
    print(f"形状              {r['shape']}")
    print(f"解读              {r['reading']}")
    if r["error_totals"]:
        print(f"错误分布          {r['error_totals']}")


def print_retry(r: dict) -> None:
    print(f"重试次数          {r['retries']}"
          f"（一条请求最多尝试 {r['attempts_per_request']} 次）")
    print("轮次   单次失败率 p    放大系数    上界 1+p·r    下一轮负载")
    for row in r["rounds"]:
        print(f" {row['round']:<5} {row['failure_rate'] * 100:>6.1f}%"
              f"        {row['amplification']:<11.3g}"
              f" {row['upper_bound']:<13.3g}"
              f" {round(row['next_load'], 2)} 倍")
    print(f"用户侧失败        {round(r['user_visible_failure_rate'] * 100, 1)}%")
    print(f"可用性            {round(r['availability'] * 100, 1)}%")
    print(f"解读              {r['reading']}")
    if r.get("diverged"):
        print("警告              失败率走到 1，回路发散，这就是雪崩")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="阶梯加压（需要真实服务）")
    p_run.add_argument("--url", required=True)
    p_run.add_argument("--workload", type=Path, required=True)
    p_run.add_argument("--ramp", default="0.5,1,1.5,2,3")
    p_run.add_argument("--capacity-qps", type=float, required=True)
    p_run.add_argument("--slo-ttft", type=float, default=1500.0)
    p_run.add_argument("--slo-itl", type=float, default=80.0)
    p_run.add_argument("--step-seconds", type=float, default=30.0)
    p_run.add_argument("--output", type=Path, required=True)

    p_an = sub.add_parser("analyze", help="判 goodput 曲线的形状")
    p_an.add_argument("--report", type=Path, required=True)
    p_an.add_argument("--output", type=Path, default=None)

    p_rs = sub.add_parser("retry-storm", help="21.5 那个放大器")
    p_rs.add_argument("--retries", type=int, default=3)
    p_rs.add_argument("--failure-rates", default=None,
                      help="逐轮的单次失败率，逗号分隔，例如 0.04,0.15,0.40,0.73")
    p_rs.add_argument("--report", type=Path, default=None,
                      help="给了就从这份演练的曲线上读失败率，而不是手填")
    p_rs.add_argument("--initial-p", type=float, default=0.04)
    # 默认和 rates_from_drill 的函数默认一致：8 轮会在回路还没走到头时截断，
    # 读者照 21.8 的命令跑出来的数就和正文对不上（Part 5 审阅 P0-2）。
    p_rs.add_argument("--max-rounds", type=int, default=40)

    p_cc = sub.add_parser("cancel-check", help="21.4 那条链路的验证")
    p_cc.add_argument("--before", type=Path, required=True,
                      help="断开前的调度器快照，可用 ch20 的 collect 取")
    p_cc.add_argument("--after", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    try:
        if args.cmd == "run":  # pragma: no cover - needs a service
            workload = json.loads(args.workload.read_text(encoding="utf-8"))
            ramp = [float(x) for x in args.ramp.split(",")]
            report = run(args.url, workload, ramp, args.capacity_qps,
                         args.slo_ttft, args.slo_itl, args.step_seconds)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"wrote {args.output}")
            return 0
        if args.cmd == "analyze":
            report = json.loads(args.report.read_text(encoding="utf-8"))
            result = analyze(report)
            print_analyze(result)
            if args.output is not None:
                args.output.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                print(f"wrote {args.output}")
            return 0
        if args.cmd == "retry-storm":
            _require(bool(args.failure_rates) or args.report is not None,
                     "retry-storm 需要 --failure-rates 或 --report 之一")
            if args.report is not None:
                report = json.loads(args.report.read_text(encoding="utf-8"))
                result = rates_from_drill(report, args.initial_p, args.retries,
                                          args.max_rounds)
            else:
                rates = [float(x) for x in args.failure_rates.split(",")]
                result = retry_loop(rates, args.retries)
            print_retry(result)
            return 0
        before = json.loads(args.before.read_text(encoding="utf-8"))
        after = json.loads(args.after.read_text(encoding="utf-8"))
        result = cancel_check(before, after)
        for key in ("running_before", "running_after", "kv_before", "kv_after",
                    "running_drop", "kv_drop", "propagated"):
            print(f"{key:<18}{result[key]}")
        print(f"解读              {result['reading']}")
        return 0 if result["propagated"] else 1
    except DrillError as exc:
        print(f"REJECTED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
