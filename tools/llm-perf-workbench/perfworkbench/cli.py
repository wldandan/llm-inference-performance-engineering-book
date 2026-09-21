"""Local CLI; no remote deployment, no implicit benchmarking on startup."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .config import ExperimentSpec
from .dataset import load_jsonl, profile_dataset
from .store import RunStore, write_json


def _emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2))


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parser():
    parser = argparse.ArgumentParser(
        prog="perfworkbench", description="本地 LLM 推理性能优化工作台 · EvalScope"
    )
    parser.add_argument("--root", default=".workbench", help="私有实验目录")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="启动本地网页")
    serve.add_argument("--host", choices=["127.0.0.1", "localhost"], default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8800)
    demo = sub.add_parser("demo", help="启动本地协议测试端点，不是模型")
    demo.add_argument("--port", type=int, default=9010)
    init = sub.add_parser("init", help="生成本地协议示例配置")
    init.add_argument("--output")
    for name in ("validate", "run", "sweep", "preflight"):
        command = sub.add_parser(name)
        command.add_argument("config", help="实验 JSON 配置文件")
    profile = sub.add_parser("profile")
    profile.add_argument("dataset")
    profile.add_argument("--tokenizer")
    sub.add_parser("list")
    for name in ("show", "cancel"):
        sub.add_parser(name).add_argument("id")
    compare = sub.add_parser("compare")
    compare.add_argument("ids", nargs="+", help="至少两个实验 ID")
    retest = sub.add_parser("retest")
    retest.add_argument("baseline_id")
    retest.add_argument("candidate_id")
    retest.add_argument("--metric", default="requests_per_s")
    retest.add_argument("--direction", choices=["increase", "decrease"], default="increase")
    retest.add_argument("--min-change", type=float, default=0)
    retest.add_argument(
        "--allow-change", choices=["load.concurrency", "load.rate"], help="声明唯一负载实验变量"
    )
    label = sub.add_parser("label")
    label.add_argument("id")
    label.add_argument("file", help='JSON: {"request_id": "pass|fail|unknown"}')
    report = sub.add_parser("report")
    report.add_argument("id")
    report.add_argument("--format", choices=["markdown", "json", "html"], default="markdown")
    report.add_argument("--output")
    return parser


def _dispatch(args):
    if args.command == "serve":
        import uvicorn

        from .web import create_app

        uvicorn.run(create_app(args.root), host=args.host, port=args.port, access_log=False)
        return 0
    if args.command == "demo":
        from .demo import create_server

        server = create_server(args.port)
        print(
            f"Protocol fixture ONLY: http://127.0.0.1:{server.server_port}/v1 ; no real model",
            file=sys.stderr,
        )
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return 0
    if args.command == "init":
        from .demo import example_spec

        spec = example_spec()
        if args.output:
            path = Path(args.output)
            if path.exists():
                raise ValueError("Output already exists; choose a new filename")
            write_json(path, spec)
        else:
            _emit(spec)
        return 0
    if args.command == "profile":
        _emit(profile_dataset(load_jsonl(Path(args.dataset).read_text()), args.tokenizer))
        return 0
    if args.command in {"validate", "run", "sweep", "preflight"}:
        spec = ExperimentSpec.model_validate(_load(args.config)).model_dump(mode="json")
        if args.command == "validate":
            _emit({"valid": True, "dataset_samples": len(spec["dataset"])})
            return 0
        from .runner import ExperimentManager

        manager = ExperimentManager(args.root)
        try:
            if args.command == "preflight":
                result = manager.preflight(spec["endpoint"])
                _emit(result)
                return 0 if result["ready"] else 1
            plan = manager.submit(spec)
            results = manager.wait(plan["plan_id"])
            _emit(
                {
                    **plan,
                    "runs": [
                        {"id": run["id"], "status": run["status"], "summary": run["summary"]}
                        for run in results
                    ],
                }
            )
            return 0 if all(run["status"] == "completed" for run in results) else 1
        finally:
            manager.close()
    store = RunStore(args.root)
    if args.command == "list":
        _emit(store.list())
    elif args.command == "show":
        _emit(store.get(args.id))
    elif args.command == "compare":
        from .analysis import compare_runs

        _emit(compare_runs([store.get(identifier) for identifier in args.ids]))
    elif args.command == "retest":
        from .analysis import evaluate_retest

        criterion = {
            "metric": args.metric,
            "direction": args.direction,
            "min_relative_change": args.min_change,
        }
        baseline, candidate = store.get(args.baseline_id), store.get(args.candidate_id)
        if args.allow_change:
            key = args.allow_change.split(".")[1]
            criterion["change"] = {
                "field": args.allow_change,
                "before": baseline["spec"]["load"][key],
                "after": candidate["spec"]["load"][key],
            }
        result = evaluate_retest(baseline, candidate, criterion)
        store.update(
            args.candidate_id,
            retest={
                **result,
                "baseline_id": args.baseline_id,
                "candidate_id": args.candidate_id,
                "criterion": criterion,
            },
        )
        _emit(result)
    elif args.command == "label":
        from .runner import refresh_analysis

        store.label(args.id, _load(args.file))
        _emit(refresh_analysis(store, args.id))
    elif args.command == "cancel":
        from .runner import ExperimentManager

        manager = ExperimentManager(args.root)
        try:
            _emit(manager.cancel(args.id))
        finally:
            manager.close()
    elif args.command == "report":
        from .report import export_report

        document = export_report(store.get(args.id), args.format)
        if args.output:
            path = Path(args.output)
            if path.exists():
                raise ValueError("Output already exists; choose a new filename")
            path.write_text(document, encoding="utf-8")
        else:
            print(document)
    return 0


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        return _dispatch(args)
    except ValidationError as exc:
        issues = [
            {"field": ".".join(map(str, e["loc"])), "type": e["type"]}
            for e in exc.errors(include_input=False, include_context=False)
        ]
        print(json.dumps({"error": "配置校验失败", "issues": issues}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TimeoutError) as exc:
        print(f"操作未完成（{type(exc).__name__}）。请检查文件、配置、实验 ID 或端点状态。", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已停止；部分实验记录保留。", file=sys.stderr)
        return 130
