#!/usr/bin/env python3
"""From business numbers to card count to the monthly bill, and back again.

26.1 asks a question the first five parts cannot answer: 明年用户量翻五倍，预算
要报多少。This script is that answer, and it is deliberately opinionated about
the two places the answer usually goes wrong.

Subcommands:

  size     the whole chain: 日活 → QPS → token 速率 → 卡数 → 账单. Offline.
  whatif   the same chain under a list of scenarios, each reported against the
           baseline. 26.5 calls this the part that makes the model useful.
  margin   26.3's margin table. For each card count: the load rate ρ, the
           load with one card down (N+1), how long a one-minute 3× burst takes
           to drain, and the mean queue twice over: M/M/1 per replica (the
           upper bound, right when requests are pinned to a replica) and Erlang
           C across all cards (load-balanced dispatch). Offline.

Four things this script refuses to do:

  It will not report a saturated-basis unit cost by default. 26.4 names that
  口径 as the standard way self-hosting gets underestimated, so `--show-saturated`
  is opt-in and the number comes out with a warning attached.

  It will not report a unit cost without the utilisation beside it. The two are
  the same fact stated twice, and the second one is what explains the first.

  It will not carry a per-card concurrency over from a different load profile.
  第 16 章那张表的条数是在某个平均总长度下算出来的，所以`--gpu-concurrency` 要
  和 `--concurrency-at-tokens` 成对给，脚本按本次负载的总长度折算。29.8 案例一
  整个就是在讲不折算的后果。

  It will not let input length move the card count unless it knows how much
  of a card's time goes to Prefill, and at what input/output ratio that share
  was measured. The defaults carry 第 19 章那次压测的合成设定（输入输出比约
  1.5 时占 10%）; `--ignore-prefill` drops the term and reproduces the static
  two-constraint answer, in which input length has no channel to cards.
  Moving the share from one ratio to another uses the odds form, not a
  straight scale: a request holds the card for 输入/Prefill 速率 + 输出/Decode
  速率, so 占时/(1−占时) is what grows linearly with the ratio.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

SECONDS_PER_MONTH = 86400 * 30
SECONDS_PER_DAY = 86400

# 26.4 的三种口径。满载那一种是可以算的，但不是默认输出。
COST_BASES = ("per_token_actual", "per_token_saturated", "per_user", "per_session")

# 26.3 的两个约束。
CONSTRAINTS = ("memory", "throughput")

# 第 19 章那次批量扫描的负载（prompt P50 600、输出 P50 400），1560 就是在它上面
# 量的；Prefill 在那次压测里约占单卡忙碌时间的 10%（合成设定）。
DEFAULT_PREFILL_SHARE = 0.10
DEFAULT_MEASURED_IO_RATIO = 1.5


class ModelError(Exception):
    """An input that cannot support the number asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ModelError(message)


# --------------------------------------------------------------------------
# 26.2 业务指标 → token 速率
# --------------------------------------------------------------------------

def demand(*, dau: float, sessions_per_user: float, peak_to_mean: float,
           calls_per_session: float, input_tokens: float,
           output_tokens: float) -> dict:
    """26.2 那条链，每一步的乘数都单独报出来。

    peak_to_mean 是峰均比：峰值 QPS ÷ 全天平均 QPS。它不是第 22 章的峰谷比
    （峰值 ÷ 波谷），两者的换算是 峰均比 = 峰谷比 × 波谷 ÷ 日均。把 11.25 的峰谷
    比当峰均比代进来，卡数会多出三四倍。
    """
    for name, v in (("dau", dau), ("sessions_per_user", sessions_per_user),
                    ("peak_to_mean", peak_to_mean),
                    ("calls_per_session", calls_per_session),
                    ("input_tokens", input_tokens),
                    ("output_tokens", output_tokens)):
        _require(v > 0, f"{name} 必须为正")
    _require(peak_to_mean >= 1, "峰均比不能小于 1：峰值不会低于均值")

    daily_sessions = dau * sessions_per_user
    mean_session_qps = daily_sessions / SECONDS_PER_DAY
    peak_session_qps = mean_session_qps * peak_to_mean
    peak_call_qps = peak_session_qps * calls_per_session
    return {
        "daily_sessions": round(daily_sessions, 2),
        "mean_session_qps": round(mean_session_qps, 4),
        "peak_session_qps": round(peak_session_qps, 4),
        "peak_call_qps": round(peak_call_qps, 4),
        "peak_input_tps": round(peak_call_qps * input_tokens, 2),
        "peak_output_tps": round(peak_call_qps * output_tokens, 2),
        "mean_call_qps": round(mean_session_qps * calls_per_session, 4),
        "tokens_per_call": input_tokens + output_tokens,
        "note": ("mean_session_qps 是对话数每秒，peak_call_qps 是模型调用数每秒。"
                 "两者差 峰均比 × 每次对话的调用数 倍，26.8 案例一就是把这两个"
                 "量当成同一个数用了。"),
    }


def inflight(peak_call_qps: float, request_duration_s: float) -> float:
    """Little's Law：L = λW。

    26.3: 它对到达分布和服务分布都不作要求，但要求稳态。这里不检查稳态，因为
    脚本看不到到达过程；正文那条纪律是“用高峰期的实测停留时间”，不是日均值。
    """
    _require(peak_call_qps >= 0, "QPS 不能为负")
    _require(request_duration_s > 0, "平均请求时长必须为正")
    return peak_call_qps * request_duration_s


# --------------------------------------------------------------------------
# 26.3 token 速率 → 卡数
# --------------------------------------------------------------------------

def scale_concurrency(concurrency: float, measured_at_tokens: float,
                      actual_tokens: float) -> float:
    """把另一个负载画像下测到的单卡并发折算到本次负载。

    KV 占用与总长度成正比，所以并发上限与总长度成反比。不折算就是 29.8 案例一
    那种错法。
    """
    _require(concurrency > 0, "单卡并发必须为正")
    _require(measured_at_tokens > 0 and actual_tokens > 0,
             "两个总长度都必须为正")
    return concurrency * measured_at_tokens / actual_tokens


def prefill_share_at(share_measured: float, measured_io_ratio: float,
                     actual_io_ratio: float) -> float:
    """把一个输入输出比下量到的 Prefill 占时，换到另一个输入输出比。

    一条请求占卡的时间是 输入 ÷ Prefill 速率 + 输出 ÷ Decode 速率，所以与输入
    输出比成正比的是 占时 ÷ (1 − 占时)，不是占时本身。线性放大占时会在长输入
    负载上算出超过 100% 的荒谬值。
    """
    _require(0 <= share_measured < 1,
             f"Prefill 占时 {share_measured} 要在 [0, 1) 内")
    _require(measured_io_ratio > 0 and actual_io_ratio > 0,
             "两个输入输出比都必须为正")
    odds = share_measured / (1 - share_measured) * actual_io_ratio / measured_io_ratio
    return odds / (1 + odds)


def prefill_adjusted_output_tps(output_tps: float, *,
                                measured_io_ratio: float | None,
                                actual_io_ratio: float,
                                prefill_share_at_measure: float | None) -> dict:
    """26.3 那一项：单卡的一秒钟分给 Prefill 和 Decode。

    给了 `prefill_share_at_measure` 才做折算。不给就原样返回，并在结果里写明
    输入长度在这套模型里对卡数没有影响。宁可说不知道，也不要报一个凭感觉的
    收益。
    """
    if prefill_share_at_measure is None:
        return {
            "output_tps": output_tps,
            "adjusted": False,
            "note": ("没有算 Prefill 占时，所以输入长度在这个模型里不影响卡数。"
                     "想让它影响，要先量出 Prefill 占单卡忙碌时间的比例和当时的"
                     "输入输出比。量法是卡时口径：一个窗口里含 Prefill token 的"
                     "那些引擎步耗时之和 ÷ 同一窗口的总忙碌时间（第 9 章的步级"
                     "观测），不是 23.7 那种单条请求的墙钟分段，两者能差近十倍。"),
        }
    _require(0 <= prefill_share_at_measure < 1,
             f"Prefill 占时 {prefill_share_at_measure} 要在 [0, 1) 内")
    _require(measured_io_ratio is not None and measured_io_ratio > 0,
             "给了 --prefill-share 就要给 --measured-io-ratio，"
             "否则不知道那个占比是在什么输入输出比下测的")
    _require(actual_io_ratio > 0, "本次负载的输入输出比必须为正")
    pure_decode = output_tps / (1 - prefill_share_at_measure)
    share = prefill_share_at(prefill_share_at_measure, measured_io_ratio,
                             actual_io_ratio)
    return {
        "output_tps": round(pure_decode * (1 - share), 2),
        "adjusted": True,
        "pure_decode_tps": round(pure_decode, 2),
        "prefill_share_measured": prefill_share_at_measure,
        "measured_io_ratio": measured_io_ratio,
        "actual_io_ratio": round(actual_io_ratio, 4),
        "prefill_share_actual": round(share, 4),
        "note": (f"Prefill 占时在输入输出比 {measured_io_ratio} 时是 "
                 f"{prefill_share_at_measure:.0%}，本次 {actual_io_ratio:.2f}，"
                 f"按 占时/(1−占时) 与比值成正比折到 {share:.1%}；"
                 f"单卡输出吞吐 {output_tps:.0f} → {pure_decode * (1 - share):.0f} token/s"),
    }


def size_cards(*, peak_output_tps: float, gpu_output_tps: float,
               inflight_requests: float, gpu_concurrency: float,
               headroom: float, output_tokens: float | None = None,
               request_duration_s: float | None = None) -> dict:
    _require(gpu_output_tps > 0, "单卡输出吞吐必须为正")
    _require(gpu_concurrency > 0, "单卡并发必须为正")
    _require(headroom >= 0, "余量不能为负")
    by_throughput = peak_output_tps / gpu_output_tps
    by_memory = inflight_requests / gpu_concurrency
    binding = "throughput" if by_throughput >= by_memory else "memory"
    minimum = max(by_throughput, by_memory)
    required = math.ceil(minimum * (1 + headroom))
    per_card: dict = {}
    if output_tokens and request_duration_s:
        # 两个约束统一成“每卡在途”：吞吐那一侧按 Little's Law 换成在途条数，
        # 和显存允许的条数放在同一把尺子上比。
        rate = gpu_output_tps / output_tokens
        per_card = {
            "per_card_request_rate": round(rate, 3),
            "per_card_inflight_at_full_throughput": round(rate * request_duration_s, 2),
            "per_card_inflight_memory_allows": round(gpu_concurrency, 2),
            "per_card_service_time_ms": round(1000 / rate, 1),
        }
    return {
        "gpus_by_throughput": round(by_throughput, 3),
        "gpus_by_memory": round(by_memory, 3),
        "binding_constraint": binding,
        "gpus_minimum_exact": round(minimum, 3),
        "gpus_minimum": math.ceil(minimum),
        "headroom": headroom,
        "gpus_required": required,
        "utilisation_at_required": round(minimum / required, 4),
        **per_card,
        "reading": (
            f"{binding} 先满（{round(by_throughput,1)} 对 {round(by_memory,1)}）。"
            f"刚好够是 {math.ceil(minimum)} 张，加 {headroom:.0%} 余量后 {required} 张"),
    }


def floor_cards(*, minimum_at_peak: float, peak_to_mean: float,
                trough_to_mean: float, headroom: float) -> dict:
    """下限卡数：波谷那一刻要的卡数，第 27 章最小实例数和第 29 章接缝核对的那个数。

    波谷 QPS = 日均 × trough_to_mean，峰值 QPS = 日均 × peak_to_mean，两个约束都
    和 QPS 成正比，所以波谷要的卡数就是峰值的那个数按两者之比缩下来，再加同样的
    余量。至少 2 张：挂一张时还要有一张在服务。
    """
    _require(0 < trough_to_mean <= 1, "谷均比要在 0 和 1 之间：波谷不会高于日均")
    _require(peak_to_mean >= 1, "峰均比不能小于 1")
    at_trough = minimum_at_peak * trough_to_mean / peak_to_mean
    floor = max(2, math.ceil(at_trough * (1 + headroom)))
    return {
        "trough_to_mean": trough_to_mean,
        "gpus_at_trough_exact": round(at_trough, 3),
        "gpus_floor": floor,
        "peak_to_trough": round(peak_to_mean / trough_to_mean, 2),
        "reading": (f"波谷是日均的 {trough_to_mean:.0%}，刚好够 {at_trough:.1f} 张，"
                    f"加同样的余量、且不少于 2 张，下限 {floor} 张。扩缩容的最小"
                    f"实例数不低于它，最大实例数不低于峰值卡数"),
    }


def erlang_c(servers: int, rho: float) -> float:
    """M/M/c 里一条请求要排队的概率，ρ 是每个服务台的负载率。"""
    _require(servers >= 1, "服务台数至少是 1")
    _require(0 <= rho < 1, f"负载率 {rho} 不在 [0, 1) 内")
    offered = rho * servers
    blocking = 1.0
    for k in range(1, servers + 1):
        blocking = offered * blocking / (k + offered * blocking)
    return blocking / (1.0 - rho * (1.0 - blocking))


def drain_minutes(rho: float, burst_factor: float = 3.0,
                  burst_s: float = 60.0) -> float:
    """20.6：到达变成 burst_factor 倍、持续 burst_s 秒，积压要多少分钟消化。"""
    _require(0 <= rho < 1, f"负载率 {rho} 不在 [0, 1) 内")
    excess = burst_factor * rho - 1.0
    if excess <= 0:
        return 0.0
    return excess * burst_s / (1.0 - rho) / 60.0


def margin_table(minimum_cards: float, options: list[int]) -> list[dict]:
    """26.3 那张余量表。

    每一行回答四件事：负载率 ρ；挂一张卡（N+1，或滚动升级时摘一张）之后的负载率；
    一分钟三倍突发要多久消化；平均排队两种算法。M/M/1 把每张卡当一个各排各的
    队的服务台，是请求被前缀亲和钉在副本上时的上界；Erlang C 把全部卡当成按
    负载派发的多服务台。两者都以“单卡的服务时间 S”为单位。
    """
    _require(minimum_cards > 0, "刚好够的卡数必须为正")
    rows = []
    for cards in sorted(options):
        _require(cards > 0, "卡数必须为正")
        rho = minimum_cards / cards
        row = {"cards": cards, "rho": round(rho, 4),
               "headroom": round(cards / minimum_cards - 1, 4)}
        if rho >= 1:
            row.update({"amplification": None, "erlang_c_wait": None,
                        "erlang_c_wait_probability": None,
                        "rho_one_down": None, "drain_minutes": None,
                        "reading": "ρ ≥ 1，等待时间发散，这个配置不能上线"})
            rows.append(row)
            continue
        row["amplification"] = round(rho / (1 - rho), 2)
        c = erlang_c(cards, rho)
        row["erlang_c_wait_probability"] = round(c, 4)
        row["erlang_c_wait"] = round(c / (cards * (1 - rho)), 4)
        one_down = minimum_cards / (cards - 1) if cards > 1 else float("inf")
        row["rho_one_down"] = round(one_down, 4)
        row["drain_minutes"] = round(drain_minutes(rho), 1)
        parts = [f"钉在副本上最多等 {row['amplification']} 个 S",
                 f"按负载派发约 {row['erlang_c_wait']} 个 S"]
        parts.append("挂一张仍扛得住" if one_down < 1 else "挂一张就过载")
        parts.append(f"一分钟三倍突发约 {row['drain_minutes']} 分钟消化完")
        row["reading"] = "，".join(parts)
        rows.append(row)
    return rows


def target_load(*, n_plus_one_cards: int, total_cards: float,
                forecast_error: float, burst_rho: float) -> float:
    """26.3 的余量四项，合成一个目标负载率。

    N+1 与滚动升级各要求多出 n_plus_one_cards 张；预测误差按比例放大需求；突发
    一项给出平时负载率的上限（由消化时间定）。取三者里最紧的那个。
    """
    _require(total_cards > n_plus_one_cards, "卡数要多于冗余张数")
    redundancy = (total_cards - n_plus_one_cards) / total_cards
    return min(redundancy / (1 + forecast_error), burst_rho)


# --------------------------------------------------------------------------
# 26.4 三种口径
# --------------------------------------------------------------------------

def costs(*, gpus: int, gpu_monthly: float, mean_call_qps: float,
          input_tokens: float, output_tokens: float,
          api_input_price: float, api_output_price: float,
          dau: float, sessions_per_user: float,
          gpu_output_tps: float, show_saturated: bool = False,
          useful_share: float = 1.0) -> dict:
    """26.4 的三种口径。满载那一种要显式要。

    分母是有用的产出：实际用量里成功、在 SLO 之内、没被用户放弃的那部分
    （useful_share）。实际单位成本 = 满载单位成本 ÷ 平均负载率 ÷ 有用比例。
    """
    _require(gpus > 0, "卡数必须为正")
    _require(0 < useful_share <= 1, f"有用比例 {useful_share} 要在 (0, 1] 内")
    monthly_calls = mean_call_qps * SECONDS_PER_MONTH
    monthly_input = monthly_calls * input_tokens
    monthly_output = monthly_calls * output_tokens
    monthly_tokens = monthly_input + monthly_output
    _require(monthly_tokens > 0, "月度 token 数为 0，单位成本无从谈起")

    selfhost = gpus * gpu_monthly
    api = (monthly_input / 1000 * api_input_price
           + monthly_output / 1000 * api_output_price)

    # 分母按有用的实际产出进，分子按峰值配置出。26.4 那个陷阱就在这里。
    per_token_actual = selfhost / (monthly_tokens * useful_share / 1_000_000)
    capacity_output = gpus * gpu_output_tps * SECONDS_PER_MONTH
    utilisation = monthly_output / capacity_output

    out = {
        "gpus": gpus,
        "selfhost_monthly": round(selfhost, 2),
        "api_monthly": round(api, 2),
        "monthly_tokens": round(monthly_tokens, 0),
        "cost_per_million_token_actual": round(per_token_actual, 4),
        "useful_share": useful_share,
        "utilization": round(utilisation, 4),
        "actual_over_saturated": round(1 / (utilisation * useful_share), 3),
        "utilization_note": (
            "平均负载率，按输出 token 算：月度实际输出 ÷ 这些卡满载能产出的输出。"
            "它是解释单位成本高低的依据，所以和单位成本一起报："
            "实际单位成本 = 满载单位成本 ÷ 平均负载率 ÷ 有用比例。"),
        "cost_per_user_monthly": round(selfhost / dau, 4) if dau else None,
        "cost_per_session": round(
            selfhost / (dau * sessions_per_user * 30), 6) if dau else None,
        "cheaper": "自托管" if selfhost < api else "共享 API",
        "reading": (
            f"自建 {round(selfhost)} 对 API {round(api)}，"
            f"平均负载率 {utilisation:.1%}"),
    }
    if show_saturated:
        saturated_tokens = capacity_output * (
            (input_tokens + output_tokens) / output_tokens)
        out["cost_per_million_token_saturated"] = round(
            selfhost / (saturated_tokens / 1_000_000), 4)
        out["saturated_warning"] = (
            "满载口径：分子按峰值配置出，分母按卡 24 小时跑满进。"
            "它不能用来和 API 报价比，26.8 案例二就是这么把 11.9 元算成 3.2 元的。")
        if useful_share < 1:
            out["saturated_warning"] += "满载口径也不扣无用产出。"
    return out


# --------------------------------------------------------------------------
# 串起来
# --------------------------------------------------------------------------

def build_model(params: dict) -> dict:
    d = demand(dau=params["dau"], sessions_per_user=params["sessions_per_user"],
               peak_to_mean=params["peak_to_mean"],
               calls_per_session=params["calls_per_session"],
               input_tokens=params["input_tokens"],
               output_tokens=params["output_tokens"])
    l = inflight(d["peak_call_qps"], params["request_duration"])

    total_tokens = params["input_tokens"] + params["output_tokens"]
    conc = params["gpu_concurrency"]
    conc_note = None
    if params.get("concurrency_at_tokens"):
        scaled = scale_concurrency(conc, params["concurrency_at_tokens"],
                                   total_tokens)
        conc_note = (f"单卡并发 {conc} 条是在总长度 "
                     f"{params['concurrency_at_tokens']:g} token 下测的，"
                     f"本次负载 {total_tokens:g} token，折算为 {scaled:.0f} 条")
        conc = scaled

    share = None if params.get("ignore_prefill") else params.get(
        "prefill_share", DEFAULT_PREFILL_SHARE)
    tps = prefill_adjusted_output_tps(
        params["gpu_output_tps"],
        measured_io_ratio=params.get("measured_io_ratio", DEFAULT_MEASURED_IO_RATIO),
        actual_io_ratio=params["input_tokens"] / params["output_tokens"],
        prefill_share_at_measure=share)

    sizing = size_cards(peak_output_tps=d["peak_output_tps"],
                        gpu_output_tps=tps["output_tps"],
                        inflight_requests=l, gpu_concurrency=conc,
                        headroom=params["headroom"],
                        output_tokens=params["output_tokens"],
                        request_duration_s=params["request_duration"])
    floor = floor_cards(minimum_at_peak=sizing["gpus_minimum_exact"],
                        peak_to_mean=params["peak_to_mean"],
                        trough_to_mean=params.get("trough_to_mean", 0.3),
                        headroom=params["headroom"])
    c = costs(gpus=sizing["gpus_required"], gpu_monthly=params["gpu_monthly"],
              mean_call_qps=d["mean_call_qps"],
              input_tokens=params["input_tokens"],
              output_tokens=params["output_tokens"],
              api_input_price=params["api_input_price"],
              api_output_price=params["api_output_price"],
              dau=params["dau"], sessions_per_user=params["sessions_per_user"],
              gpu_output_tps=tps["output_tps"],
              show_saturated=params.get("show_saturated", False),
              useful_share=params.get("useful_share", 1.0))
    return {
        "params": params,
        "demand": d,
        "inflight": round(l, 2),
        "gpu_concurrency_used": round(conc, 2),
        "gpu_concurrency_note": conc_note,
        "gpu_output_tps_used": tps,
        "sizing": sizing,
        "floor": floor,
        "costs": c,
    }


SCENARIO_KEYS = {
    "traffic": ("dau", "倍数，同时放大日活"),
    "peak_to_mean": ("peak_to_mean", "绝对值"),
    "input_tokens": ("input_tokens", "绝对值"),
    "output_tokens": ("output_tokens", "绝对值"),
    "calls_per_session": ("calls_per_session", "绝对值"),
    "gpu_output_tps": ("gpu_output_tps", "绝对值"),
    "headroom": ("headroom", "绝对值"),
}


def apply_scenario(params: dict, spec: str) -> dict:
    _require("=" in spec, f"场景写法是 key=value，收到的是 {spec!r}")
    key, raw = spec.split("=", 1)
    key = key.strip()
    _require(key in SCENARIO_KEYS,
             f"不认识的场景键 {key}，可用的是 {sorted(SCENARIO_KEYS)}")
    out = dict(params)
    field, kind = SCENARIO_KEYS[key]
    raw = raw.strip()
    if key == "traffic":
        _require(raw.endswith("x"), "traffic 要写成倍数，例如 traffic=3x")
        out[field] = params[field] * float(raw[:-1])
    else:
        out[field] = float(raw)
    return out


def whatif(params: dict, scenarios: list[str]) -> dict:
    base = build_model(params)
    rows = []
    for spec in scenarios:
        alt = build_model(apply_scenario(params, spec))
        g0 = base["sizing"]["gpus_required"]
        g1 = alt["sizing"]["gpus_required"]
        c0 = base["costs"]["selfhost_monthly"]
        c1 = alt["costs"]["selfhost_monthly"]
        rows.append({
            "scenario": spec,
            "gpus": g1,
            "gpus_delta": g1 - g0,
            "selfhost_monthly": c1,
            "cost_change": round(c1 / c0 - 1, 4) if c0 else None,
            "binding_constraint": alt["sizing"]["binding_constraint"],
            "unit_cost": alt["costs"]["cost_per_million_token_actual"],
        })
    flat = [r for r in rows if r["gpus_delta"] == 0]
    return {
        "baseline": {"gpus": base["sizing"]["gpus_required"],
                     "selfhost_monthly": base["costs"]["selfhost_monthly"]},
        "scenarios": rows,
        "no_effect": [r["scenario"] for r in flat],
        "no_effect_note": (
            "这些场景没有改变卡数。多半是它们只动了非约束的那一侧，"
            "比如显存不紧时改输入长度。这不是模型坏了，是那个杠杆在当前配置下"
            "确实不通；26.3 末尾那一节说的就是这件事。"),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_model(r: dict) -> None:
    d, s, c = r["demand"], r["sizing"], r["costs"]
    print(f"日请求量          {d['daily_sessions']:.0f} 次对话")
    print(f"平均对话 QPS      {d['mean_session_qps']}")
    print(f"峰值调用 QPS      {d['peak_call_qps']}")
    print(f"峰值 token 速率   输入 {d['peak_input_tps']:.0f}，"
          f"输出 {d['peak_output_tps']:.0f} token/s")
    print(f"峰值在途          {r['inflight']:.0f} 条（Little's Law）")
    if r["gpu_concurrency_note"]:
        print(f"                  {r['gpu_concurrency_note']}")
    if not r["gpu_output_tps_used"]["adjusted"]:
        print(f"                  {r['gpu_output_tps_used']['note']}")
    else:
        print(f"                  {r['gpu_output_tps_used']['note']}")
    print(f"按吞吐            {s['gpus_by_throughput']:.1f} 张")
    print(f"按显存            {s['gpus_by_memory']:.1f} 张")
    if "per_card_inflight_at_full_throughput" in s:
        print(f"每卡在途          吞吐允许 {s['per_card_inflight_at_full_throughput']:.0f} 条，"
              f"显存允许 {s['per_card_inflight_memory_allows']:.0f} 条"
              f"（单卡 S ≈ {s['per_card_service_time_ms']:.0f} ms）")
    print(f"卡数              {s['gpus_required']} 张  {s['reading']}")
    f = r["floor"]
    print(f"下限卡数          {f['gpus_floor']} 张  {f['reading']}")
    print(f"自建月成本        {c['selfhost_monthly']}")
    print(f"API 月成本        {c['api_monthly']}")
    print(f"单位成本          每百万 token "
          f"{c['cost_per_million_token_actual']} 元（有用产出口径）")
    print(f"平均负载率        {c['utilization']:.1%}，"
          f"实际单位成本是满载口径的 {c['actual_over_saturated']} 倍")
    print(f"                  {c['utilization_note']}")
    print(f"每用户每月        {c['cost_per_user_monthly']}")
    if "cost_per_million_token_saturated" in c:
        print(f"满载单位成本      每百万 token "
              f"{c['cost_per_million_token_saturated']}")
        print(f"警告              {c['saturated_warning']}")


def print_whatif(r: dict) -> None:
    b = r["baseline"]
    print(f"基线              {b['gpus']} 张，月成本 {b['selfhost_monthly']}")
    for row in r["scenarios"]:
        delta = "" if row["cost_change"] is None else f"{row['cost_change']:+.1%}"
        print(f"  {row['scenario']:<24}{row['gpus']:>3} 张"
              f"（{row['gpus_delta']:+d}）  月成本 {delta}"
              f"  约束在 {row['binding_constraint']}")
    if r["no_effect"]:
        print(f"没有影响          {r['no_effect']}")
        print(f"                  {r['no_effect_note']}")


def print_margin(rows: list[dict]) -> None:
    for row in rows:
        amp = "发散" if row["amplification"] is None else f"{row['amplification']}"
        erl = "—" if row["erlang_c_wait"] is None else f"{row['erlang_c_wait']}"
        print(f"  {row['cards']:>3} 张   ρ = {row['rho']:.3f}   "
              f"单副本上界 {amp:<6} Erlang C {erl:<7} 加 {row['headroom']:.0%} 余量")
        print(f"          {row['reading']}")


def _params_from_args(args) -> dict:
    return {
        "dau": args.dau, "sessions_per_user": args.sessions_per_user,
        "peak_to_mean": args.peak_to_mean,
        "trough_to_mean": args.trough_to_mean,
        "calls_per_session": args.calls_per_session,
        "input_tokens": args.input_tokens, "output_tokens": args.output_tokens,
        "request_duration": args.request_duration,
        "gpu_concurrency": args.gpu_concurrency,
        "concurrency_at_tokens": args.concurrency_at_tokens,
        "gpu_output_tps": args.gpu_output_tps,
        "prefill_share": args.prefill_share,
        "measured_io_ratio": args.measured_io_ratio,
        "ignore_prefill": args.ignore_prefill,
        "useful_share": args.useful_share,
        "gpu_monthly": args.gpu_monthly, "headroom": args.headroom,
        "api_input_price": args.api_input_price,
        "api_output_price": args.api_output_price,
        "show_saturated": getattr(args, "show_saturated", False),
    }


def _add_model_args(sub) -> None:
    sub.add_argument("--dau", type=float, default=500000)
    sub.add_argument("--sessions-per-user", type=float, default=3.2)
    sub.add_argument("--peak-to-mean", type=float, default=3.0,
                     dest="peak_to_mean",
                     help="峰均比：峰值 QPS ÷ 全天平均 QPS（不是第 22 章的峰谷比）")
    sub.add_argument("--trough-to-mean", type=float, default=0.3,
                     dest="trough_to_mean",
                     help="谷均比：波谷 QPS ÷ 全天平均 QPS，用来算下限卡数")
    sub.add_argument("--calls-per-session", type=float, default=2.4)
    sub.add_argument("--input-tokens", type=float, default=2600)
    sub.add_argument("--output-tokens", type=float, default=220)
    sub.add_argument("--request-duration", type=float, default=4.2)
    sub.add_argument("--gpu-concurrency", type=float, default=130,
                     help="单卡并发，配 --concurrency-at-tokens 一起给")
    sub.add_argument("--concurrency-at-tokens", type=float, default=2300,
                     help="上面那个并发是在多长的平均总长度下测的")
    sub.add_argument("--gpu-output-tps", type=float, default=1560)
    sub.add_argument("--prefill-share", type=float, default=DEFAULT_PREFILL_SHARE,
                     help="Prefill 占单卡忙碌时间的比例，在 --measured-io-ratio 下量的")
    sub.add_argument("--measured-io-ratio", type=float,
                     default=DEFAULT_MEASURED_IO_RATIO,
                     help="上面那个占比是在什么输入输出比下测的")
    sub.add_argument("--ignore-prefill", action="store_true",
                     help="不算 Prefill 占时，复现只有两个静态约束的结果")
    sub.add_argument("--useful-share", type=float, default=1.0,
                     help="有用产出占实际产出的比例（成功、达标、未被放弃）")
    sub.add_argument("--gpu-monthly", type=float, default=12000)
    sub.add_argument("--headroom", type=float, default=0.3)
    sub.add_argument("--api-input-price", type=float, default=0.0008)
    sub.add_argument("--api-output-price", type=float, default=0.002)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_s = sub.add_parser("size", help="26.2 到 26.4 那整条链")
    _add_model_args(p_s)
    p_s.add_argument("--show-saturated", action="store_true")
    p_s.add_argument("--output", type=Path, default=None)

    p_w = sub.add_parser("whatif", help="26.5 的假设分析")
    _add_model_args(p_w)
    p_w.add_argument("--scenario", action="append", default=[])
    p_w.add_argument("--output", type=Path, default=None)

    p_m = sub.add_parser("margin", help="26.3 那张余量表")
    p_m.add_argument("--minimum-cards", type=float, required=True)
    p_m.add_argument("--options", default="")
    p_m.add_argument("--headrooms", default="0.125,0.3,0.5",
                     help="不给 --options 时，按这些余量比例推出卡数")

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    try:
        if args.cmd == "margin":
            if args.options:
                opts = [int(x) for x in args.options.split(",")]
            else:
                opts = sorted({math.ceil(args.minimum_cards * (1 + float(h)))
                               for h in args.headrooms.split(",")})
            rows = margin_table(args.minimum_cards, opts)
            print_margin(rows)
            return 0
        params = _params_from_args(args)
        if args.cmd == "size":
            result = build_model(params)
            print_model(result)
        else:
            _require(bool(args.scenario), "whatif 至少要一个 --scenario")
            result = whatif(params, args.scenario)
            print_whatif(result)
        if args.output is not None:
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"wrote {args.output}")
        return 0
    except ModelError as exc:
        print(f"REJECTED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
