#!/usr/bin/env python3
"""综合项目的总验收：五项交付物、九块报告契约、八条自查、五处接缝。

30.6 说这是一套脚手架而不是单个脚本。脚手架的七个目录各放一份模板，这个文件
是它们的验收器：指着一个项目目录，它把 30.1 那五项交付物、30.3 那九块报告契约、
30.4 那八条自查跑一遍，再借第 29 章那五处接缝做一次交叉核对。

三件它拒绝做的事：

  它不把“缺数据”读成“没问题”。一处接缝的两边只要有一个缺，状态是无法核对，
  整份验收不算通过。这一条和 code/ch29/release_check.py 是同一个判断。

  它不在八条自查里只报能自动判的那几条。全部八条都出结论，但其中四条是启发式
  的，报的是告警并注明需人工确认，而不是伪装成确定性判定。

  它不接受一份“只有收益、没有代价”的优化记录。30.4 末尾那五条查的是同一件事，
  所以某一轮只写了主指标改善、护栏为空时，它按失败处理。

用法：

  python3 code/ch30/project/verify.py --project-dir <目录> --level base

只依赖标准库。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 30.1 那五项交付物。
DELIVERABLES = (
    ("runnable", "可运行", "服务能起来，有明确的启动和验收步骤"),
    ("observable", "可观测", "请求级追踪、关键指标、能从聚合下钻到单条"),
    ("explainable", "可解释", "每个性能数字都说清了测的是什么、在什么条件下"),
    ("optimizable", "可优化", "至少一轮完整的定位、改动、验证闭环"),
    ("gated", "有门禁", "自动 Benchmark 加断言，能拦住性能回归"),
)

# 30.3 那九块。顺序即正文顺序。
REPORT_BLOCKS = (
    "system", "workload", "baseline", "observability", "root_cause",
    "optimization", "capacity", "gate", "boundary",
)

# 30.3 第 7、8 块里来自 Part 6 的那几项：没有它们，一个没写回滚预案的项目
# 也能通过基本验收，而 part06 的篇级清单里它是一件物证。查的时候先看报告
# 里那一块，再退回到阶段文件（capacity.json / gate.json）。
ELASTICITY_FIELDS = ("min_instances", "max_instances",
                     "scale_trigger_metric", "cold_start_s",
                     "loop_lag_s")
ROLLBACK_FIELDS = ("trigger_conditions", "steps",
                   "rehearsed_duration_min", "irreversible",
                   "cache_warmup_min")

# 30.3 第九块要求的五项边界。
BOUNDARY_ITEMS = ("model", "workload", "hardware", "config", "chain_structure")

# 项目目录里七个阶段各自的那一份文件。
PROJECT_FILES = {
    "workload": "workload/workload.json",
    "baseline": "baseline/baseline.json",
    "observe": "observe/capabilities.json",
    "experiment": "experiment/rounds.json",
    "capacity": "capacity/capacity.json",
    "gate": "gate/gate.json",
    "report": "report/report.json",
}

# 30.4 那八条。kind 说明这一条是结构判定还是启发式判定。
SELF_CHECKS = (
    (1, "不可用没有被写成 0", "heuristic"),
    (2, "没有把客户端观测当成服务端事实", "heuristic"),
    (3, "每个性能数字都有对应的条件", "heuristic"),
    (4, "留了“测不出来”这个结论的位置", "heuristic"),
    (5, "护栏指标每轮都记了", "structural"),
    (6, "没有一轮改了多项", "structural"),
    (7, "质量是否决项", "structural"),
    (8, "边界五项写齐了", "structural"),
)

# 扩展验收额外要求的对照数据，任选其一。30.5：报告契约完全相同。
EXTENDED_EVIDENCE = ("tensor_parallel_scaling", "pd_disaggregation",
                     "moe_activation", "kernel_profile")
# 这几项本书正文只给到定义，做法留在附录，而附录 B 到 E 目前只登记了要回答的
# 问题。给了对照数据照样计入，但验收不会因为缺它们而要求补。
NOT_YET_REQUIRED = {
    "pd_disaggregation": "PD 分离只在第 13 章给了定义，附录 E 未写，暂不要求",
}

# 客户端口径被当成服务端事实的几种常见说法。第 8 章那一节。
CLIENT_SIDE_PHRASES = ("网络耗时", "分片数即 token 数", "分片数等于 token 数")

# 性能数字要带的条件词。30.4 第三条。
CONDITION_WORDS = ("批量", "batch", "上下文", "context", "缓存", "cache",
                   "冷启动", "并发")


class VerifyError(Exception):
    """A project directory that cannot support the verdict asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise VerifyError(message)


def _load_release_check():
    """借第 29 章那五处接缝，而不是在这里重写一遍。"""
    path = HERE.parent.parent / "ch29" / "release_check.py"
    _require(path.exists(), f"找不到 {path}：本脚本的交叉检查直接用第 29 章那一份")
    spec = importlib.util.spec_from_file_location("release_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# 读项目目录
# --------------------------------------------------------------------------

def load_project(project_dir: Path) -> dict:
    _require(project_dir.is_dir(), f"{project_dir} 不是一个目录")
    docs, missing_files = {}, []
    for key, rel in PROJECT_FILES.items():
        path = project_dir / rel
        if not path.exists():
            missing_files.append(rel)
            continue
        try:
            docs[key] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise VerifyError(f"{rel} 不是合法 JSON：{exc}") from exc
    docs["_missing_files"] = missing_files
    return docs


# --------------------------------------------------------------------------
# 五项交付物
# --------------------------------------------------------------------------

def check_deliverables(docs: dict) -> dict:
    report = docs.get("report") or {}
    observe = docs.get("observe") or {}
    rounds = (docs.get("experiment") or {}).get("rounds") or []
    gate = docs.get("gate") or {}

    evidence = {
        "runnable": bool((report.get("system") or {}).get("startup_steps")),
        "observable": bool(observe.get("request_id_propagated")
                           and observe.get("drilldown_supported")),
        "explainable": bool((report.get("observability") or {})
                            .get("unavailable_stages") is not None),
        "optimizable": any(r.get("verdict") for r in rounds),
        "gated": bool(gate.get("thresholds") and gate.get("assertions")),
    }
    items = {}
    for key, label, detail in DELIVERABLES:
        items[key] = {"label": label, "ok": evidence[key], "detail": detail}
    return {"items": items,
            "missing": [k for k, v in items.items() if not v["ok"]]}


# --------------------------------------------------------------------------
# 九块报告契约
# --------------------------------------------------------------------------

def _block_source(docs: dict, block: str, fallback: str) -> dict:
    """第 7、8 块的细项：报告里写了就看报告，没写就看那一阶段的文件。"""
    value = (docs.get("report") or {}).get(block)
    if isinstance(value, dict):
        merged = dict(docs.get(fallback) or {})
        merged.update(value)
        return merged
    return dict(docs.get(fallback) or {})


def check_report_contract(docs: dict) -> dict:
    report = docs.get("report") or {}
    present, empty = [], []
    for block in REPORT_BLOCKS:
        value = report.get(block)
        if block not in report:
            continue
        present.append(block)
        if value in (None, "", [], {}):
            empty.append(block)
    missing = [b for b in REPORT_BLOCKS if b not in present]

    capacity = _block_source(docs, "capacity", "capacity")
    gate = _block_source(docs, "gate", "gate")
    rollback = gate.get("rollback") or {}
    thin = []
    for field in ELASTICITY_FIELDS:
        if capacity.get(field) in (None, "", [], {}):
            thin.append(f"第 7 块缺 {field}（第 27 章）")
    for field in ROLLBACK_FIELDS:
        if rollback.get(field) in (None, "", {}):
            thin.append(f"第 8 块的回滚预案缺 {field}（第 29 章）")
    if not gate.get("observation_windows"):
        thin.append("第 8 块缺观察窗口（第 29.4 节）")
    if not gate.get("owner"):
        thin.append("第 8 块缺负责人（第 29.2 节第九项）")

    return {"present": present, "missing": missing, "empty": empty,
            "thin": thin,
            "ok": not missing and not empty and not thin,
            "note": ("契约的强制力就在这里：缺一块不算交付，"
                     "写成空的也不算，第 7、8 块里 Part 6 那几项"
                     "缺了也不算。30.3 说它和模板的区别正是这个。")}


# --------------------------------------------------------------------------
# 八条自查
# --------------------------------------------------------------------------

def _report_text(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False)


def self_check(docs: dict) -> dict:
    report = docs.get("report") or {}
    observe = docs.get("observe") or {}
    rounds = (docs.get("experiment") or {}).get("rounds") or []
    text = _report_text(report)

    results = {}

    # 一：不可用被写成 0。第 1 章那条纪律。
    unavailable = set(observe.get("unavailable_stages") or [])
    offenders = [s for s in unavailable
                 if f'"{s}": 0' in text or f'"{s}": 0.0' in text]
    results[1] = {
        "status": "warn" if offenders else "pass",
        "detail": (f"这些阶段在采集能力清单里标为不可用，报告里却出现了 0：{offenders}"
                   if offenders else
                   f"采集能力清单里标为不可用的 {len(unavailable)} 个阶段，"
                   "报告里没有写成 0"),
    }

    # 二：客户端观测当服务端事实。
    hits = [p for p in CLIENT_SIDE_PHRASES if p in text]
    results[2] = {
        "status": "warn" if hits else "pass",
        "detail": (f"报告里出现了这些说法：{hits}。客户端时长减服务端时长不叫网络耗时，"
                   "分片数不等于 token 数" if hits else "没有命中这几种常见说法"),
    }

    # 三：性能数字缺条件。
    bare = []
    for r in rounds:
        cond = json.dumps(r.get("conditions") or {}, ensure_ascii=False)
        if not any(w in cond for w in CONDITION_WORDS):
            bare.append(r.get("id", "?"))
    results[3] = {
        "status": "warn" if bare else "pass",
        "detail": (f"这些轮次的 conditions 里没有批量或上下文的说明：{bare}。"
                   "没有条件的数字会被拿去用在不该用的地方" if bare
                   else "每轮都写了采集条件"),
    }

    # 四：有没有“测不出来”这个结论。第 14 章。
    verdicts = [r.get("verdict") for r in rounds]
    indistinguishable = [v for v in verdicts if v and "不可分辨" in v]
    results[4] = {
        "status": ("warn" if len(rounds) >= 3 and not indistinguishable
                   else "pass"),
        "detail": (f"{len(rounds)} 轮实验全部得出了明确结论，没有一轮是"
                   "“在当前实验精度下不可分辨”。这反而可疑"
                   if len(rounds) >= 3 and not indistinguishable else
                   f"{len(rounds)} 轮里有 {len(indistinguishable)} 轮是不可分辨"),
    }

    # 五：护栏指标每轮都记。
    no_guard = [r.get("id", "?") for r in rounds if not r.get("guardrails")]
    results[5] = {
        "status": "fail" if no_guard else "pass",
        "detail": (f"这些轮次没有护栏指标：{no_guard}。主指标改善而护栏恶化，"
                   "那是交换不是优化，而护栏为空时连交换都看不见" if no_guard
                   else "每轮都记了护栏"),
    }

    # 六：一轮改了多项。
    multi = [r.get("id", "?") for r in rounds
             if len(r.get("changed") or []) > 1]
    results[6] = {
        "status": "fail" if multi else "pass",
        "detail": (f"这些轮次同时改了多项，结论不可用：{multi}" if multi
                   else "每轮只改一项"),
    }

    # 七：质量是否决项。
    precision_no_quality = [
        r.get("id", "?") for r in rounds
        if any("精度" in str(c) or "quant" in str(c).lower()
               for c in (r.get("changed") or []))
        and not r.get("quality")]
    results[7] = {
        "status": "fail" if precision_no_quality else "pass",
        "detail": (f"这些轮次动了精度却没有质量数据：{precision_no_quality}。"
                   "底线要在实验前写死" if precision_no_quality
                   else "动了精度的轮次都带质量数据"),
    }

    # 八：边界五项。
    boundary = (report.get("boundary") or {})
    missing_boundary = [k for k in BOUNDARY_ITEMS if not boundary.get(k)]
    results[8] = {
        "status": "fail" if missing_boundary else "pass",
        "detail": (f"边界缺这几项：{missing_boundary}" if missing_boundary
                   else "五项边界齐全"),
    }

    items = []
    for num, label, kind in SELF_CHECKS:
        row = dict(results[num])
        row.update({"no": num, "label": label, "kind": kind})
        if kind == "heuristic" and row["status"] == "warn":
            row["detail"] += "（启发式判定，需人工确认）"
        items.append(row)
    failed = [r["no"] for r in items if r["status"] == "fail"]
    warned = [r["no"] for r in items if r["status"] == "warn"]
    return {
        "items": items, "failed": failed, "warned": warned,
        "note": ("这八条里任何一条不过关，整份报告的可信度都要打折。"
                 "其中第 5、6、7、8 条查的是同一件事：这次改动换走了什么。"),
    }


# --------------------------------------------------------------------------
# 五处接缝，直接用第 29 章那一份
# --------------------------------------------------------------------------

def cross_check(docs: dict, release_check=None) -> dict:
    rc = release_check or _load_release_check()
    workload = docs.get("workload") or {}
    baseline = docs.get("baseline") or {}
    capacity = docs.get("capacity") or {}
    gate = docs.get("gate") or {}
    report = docs.get("report") or {}
    assembled = {
        "capacity": {"context_tokens": capacity.get("context_tokens"),
                     "output_tokens": capacity.get("output_tokens"),
                     "instances": capacity.get("instances"),
                     "floor_instances": capacity.get("floor_instances"),
                     "binding_constraint": capacity.get("binding_constraint")},
        "runtime": {"prompt_template_tokens": workload.get("context_tokens"),
                    "batch": (report.get("system") or {}).get("batch"),
                    "framework_version": (report.get("system") or {})
                    .get("framework_version")},
        "gate": {"batch": gate.get("batch"),
                 "absolute_ttft_p95_ms": gate.get("absolute_ttft_p95_ms")},
        "baseline": {"framework_version": baseline.get("framework_version")},
        "slo": {"ttft_p95_ms": (workload.get("slo") or {}).get("ttft_p95_ms")},
        "autoscale": {"min_instances": capacity.get("min_instances"),
                      "max_instances": capacity.get("max_instances")},
    }
    return rc.cross_check(assembled)


# --------------------------------------------------------------------------
# 总验收
# --------------------------------------------------------------------------

def check_level(docs: dict, level: str) -> dict:
    _require(level in ("base", "extended"), f"未知验收档位 {level}")
    if level == "base":
        return {"level": "base", "ok": True, "detail": "基本验收不要求额外对照数据"}
    capacity = docs.get("capacity") or {}
    report = docs.get("report") or {}
    have = [k for k in EXTENDED_EVIDENCE
            if capacity.get(k) or (report.get("capacity") or {}).get(k)]
    return {
        "level": "extended", "ok": bool(have), "present": have,
        "not_yet_required": dict(NOT_YET_REQUIRED),
        "detail": ("有对照数据：" + "、".join(have) if have else
                   "扩展验收要求多卡扩展效率、MoE 激活或 Kernel 分析里至少一项的"
                   "对照数据（PD 分离给了也计入，但暂不要求）。30.5 说形态可以换，"
                   "报告契约不变"),
    }


def verify(project_dir: Path, level: str = "base",
           release_check=None) -> dict:
    docs = load_project(project_dir)
    deliverables = check_deliverables(docs)
    contract = check_report_contract(docs)
    checks = self_check(docs)
    seams = cross_check(docs, release_check)
    lvl = check_level(docs, level)

    blocking = []
    if docs["_missing_files"]:
        blocking.append(f"缺文件：{docs['_missing_files']}")
    if deliverables["missing"]:
        blocking.append(f"交付物缺项：{deliverables['missing']}")
    if contract["missing"]:
        blocking.append(f"报告契约缺块：{contract['missing']}")
    if contract["empty"]:
        blocking.append(f"报告契约有空块：{contract['empty']}")
    if contract["thin"]:
        blocking.append("报告契约第 7、8 块缺项：" + "；".join(contract["thin"]))
    if checks["failed"]:
        blocking.append(f"自查未通过：第 {checks['failed']} 条")
    if seams["mismatched"]:
        blocking.append(f"接缝对不上：{seams['mismatched']}")
    if seams["unknown"]:
        blocking.append(f"接缝无法核对：{seams['unknown']}")
    if not lvl["ok"]:
        blocking.append(lvl["detail"])

    return {
        "deliverables": deliverables, "report_contract": contract,
        "self_check": checks, "cross_check": seams, "level": lvl,
        "missing_files": docs["_missing_files"],
        "blocking": blocking,
        "verdict": "pass" if not blocking else "incomplete",
        "warnings": checks["warned"],
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_result(r: dict) -> None:
    print("五项交付物")
    for key, label, _ in DELIVERABLES:
        item = r["deliverables"]["items"][key]
        print(f"  [{' ok ' if item['ok'] else '缺项'}] {label}　{item['detail']}")
    print("九块报告契约")
    print(f"  齐全 {len(r['report_contract']['present'])}/9"
          f"　缺 {r['report_contract']['missing'] or '无'}"
          f"　空 {r['report_contract']['empty'] or '无'}")
    for item in r['report_contract']['thin']:
        print(f"  [缺项] {item}")
    print("八条自查")
    for item in r["self_check"]["items"]:
        mark = {"pass": " ok ", "warn": "告警", "fail": "失败"}[item["status"]]
        kind = "启发式" if item["kind"] == "heuristic" else "结构"
        print(f"  [{mark}] {item['no']}. {item['label']}（{kind}）")
        print(f"         {item['detail']}")
    print("五处接缝")
    for row in r["cross_check"]["rows"]:
        tail = f"　{row['note']}" if row["note"] else ""
        print(f"  [{row['status']}] {row['left']} 对 {row['right']}{tail}")
        if row.get("consequence"):
            print(f"           {row['consequence']['reading']}")
    print(f"档位              {r['level']['detail']}")
    print(f"结论              {r['verdict']}")
    for b in r["blocking"]:
        print(f"                  {b}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--level", default="base",
                        choices=("base", "extended"),
                        help="base 是基本验收；extended 在同一份报告契约上"
                             "额外要求一项换了部署形态的对照数据")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        result = verify(args.project_dir, args.level)
    except VerifyError as exc:
        print(f"REJECTED: {exc}")
        return 1
    print_result(result)
    if args.output is not None:
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
