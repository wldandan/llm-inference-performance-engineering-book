# Internal V0.1 contracts

All external input is validated by `config.ExperimentSpec`; consumers use `model_dump(mode="json")`.
Unknown values are JSON null, never NaN. IDs are generated hex identifiers, not paths.

## Experiment spec

```json
{
  "name": "baseline",
  "endpoint": {"base_url": "http://127.0.0.1:8000/v1", "model": "my-model", "api_key_env": null, "context_length": null, "environment": {}},
  "dataset": [{"id": "sample-1", "messages": [{"role": "user", "content": "Summarize this."}], "category": "default", "max_tokens": null}],
  "load": {"mode": "concurrency", "concurrency": 1, "rate": 1.0, "count": 10, "warmup": 0, "repeats": 1, "scan": [], "mix": {}, "seed": 42},
  "generation": {"stream": true, "max_tokens": 128, "temperature": 0.0, "top_p": 1.0, "extra": {}},
  "goals": {"mode": "offline", "min_requests_per_s": null, "max_p95_e2e_ms": null, "max_p95_ttft_ms": null, "max_p95_tpot_ms": null, "min_quality_pass_rate": 1.0, "max_error_rate": 0.0, "deadline_s": null, "target_requests": null},
  "quality": {"mode": "rules", "require_json": false, "json_fields": [], "required_text": [], "min_chars": 1, "reject_truncated": true},
  "safety": {"max_requests": 1000, "max_concurrency": 64, "max_duration_s": 300, "request_timeout_s": 30, "max_output_tokens": 128000, "max_response_bytes": 2097152},
  "telemetry": {"interval_s": 1.0, "sources": []},
  "cache_condition": "unknown",
  "tokenizer_path": null,
  "notes": "",
  "protocol_fixture": false
}
```

Defaults are product defaults, not benchmark recommendations. Safety max_requests/max_output_tokens apply across a full plan (scan × repeats × (count + warmup)). Plans reject impossible bounds before dispatch. max_duration_s is plan-wide, including worker initialization and drain. Preflight is a separate explicit action (at most 2 generation requests × 8 output tokens); no implicit per-run preflight.

Telemetry source: `{name, url, api_key_env:null, mappings:[{key, metric, kind:"gauge"|"counter", scale:1.0, labels:{}, aggregation:"sum"|"max"|"mean"}]}`. Canonical keys: queue_waiting, requests_running, kv_cache_usage_ratio, preemptions_total, prefix_hits_total, prefix_queries_total, device_utilization_ratio, device_memory_used_bytes, device_memory_total_bytes. Preserve per-series labels and raw metric names; don't hide missing sources.

## Request record

```json
{"request_id":"...","sample_id":"sample-1","category":"default","phase":"measure","started_at":1790000000.0,"start_s":0.1,"end_s":0.4,"status":"success","success":true,"http_status":200,"error_kind":null,"is_stream":true,"input_tokens":32,"output_tokens":8,"e2e_ms":300.0,"ttft_ms":100.0,"tpot_ms":28.57,"inter_chunk_ms":[50.0,150.0],"output_text":"answer","finish_reason":"stop","manual_label":null}
```

start_s/end_s use a single worker-relative monotonic origin, started_at is UTC epoch for plotting only. Request-end independently captured after reading response, including failure. TTFT is first observable output chunk; TPOT is an estimated average `(e2e_ms-ttft_ms)/(output_tokens-1)` not ITL. No token timing on nonstream, no TPOT with <=1 or unknown output tokens. `client_rejected` and `interrupted` distinct from service failure; warmup excluded from measured performance, retained in audit. Started events persist before network sends for crash recovery. Quality derived in analysis, manual labels join by request_id.

## Analysis interface (dict-only)

- `analysis.evaluate_quality(record, quality) -> {status: pass|fail|unknown, reasons: list[str]}`.
- `analysis.analyze(records, spec, telemetry=None, status="completed") -> dict`: return `metrics`, `groups`, `goals`, `quality`, `warnings`, `definitions`, `sample_count`.
- Metrics: numeric/null values for `duration_s`, `requests_per_s`, `actual_sent_per_s`, `offered`, `target_rate`, `input_tokens_per_s`, `output_tokens_per_s`, `goodput_per_s`, `error_rate`, `sent`, `succeeded`, `failed`, `client_rejected`, `interrupted`, `ttft_ms`, `tpot_ms`, `e2e_ms`, `inter_chunk_ms`. Distribution values are `{count,mean,p50,p95,p99}`. Goals list entries `{name,target,actual,status}`. Quality `{pass,fail,unknown,coverage,pass_rate}`; denominator policy documented. Groups keyed by category, with same metric summaries.
- `analysis.diagnose(summary, spec, telemetry=None) -> list[dict]`: `{id,title,evidence:list,confidence,adjustment,risk,validation,status:"pending"}`. No unsupported exact tuning values. Insufficient evidence explicitly represented.
- `analysis.compare_runs(runs) -> dict`: runs have id/spec/summary/status; return comparable, reasons, candidates, best_run_id (nullable), differences. Different endpoint/model/environment allowed as candidates but workload/dataset/generation/quality goals must align. Each eligible run must be completed with measured evidence and pass quality/constraints. Do not rank fixture as real performance.
- `analysis.evaluate_retest(baseline, candidate, criterion) -> dict`: criterion `{metric:"requests_per_s",direction:"increase",min_relative_change:0.0}` optionally includes `change:{field:"load.concurrency"|"load.rate",before,after}`. Return status effective|ineffective|insufficient_evidence, reasons, change, before, after, differences. Require aligned conditions, quality/goal gates and exactly one declared intervention. Fixture cannot prove optimization. Web and CLI persist a flat association `{...result,baseline_id,candidate_id,criterion}` on the candidate; `parent_id` remains the original experiment plan.
- `report.export_report(run, fmt="markdown") -> str`: markdown/json/html, standalone readable report; default strips inputs/output_text, credentials, private URLs and raw errors. HTML escaped. No unpickle or arbitrary file import.

## Run/store/manager interface

- `store.RunStore(root)`: `create(spec, profile=None, parent_id=None) -> run`, `get(id) -> run`, `list() -> list`, `update(id, **fields) -> run`, `run_dir(id) -> Path`, `records(id) -> list`, `label(id, labels:dict[request_id,str]) -> run`. `get` includes records on terminal runs. JSON records use request schema above. Run `{id, created_at,status,spec,profile,parent_id,summary,diagnostics,error,records,telemetry,progress}`.
- `runner.ExperimentManager(root)`: `.store`; `submit(spec:dict) -> {plan_id,run_ids}`, `cancel(plan_id_or_run_id) -> dict`, `wait(plan_id, timeout=None) -> list[run]`, `preflight(endpoint:dict) -> dict`, `close()`. One plan running at a time, reject concurrent submission. Scan/repeats create individual runs with actual per-point spec and shared plan ID. Background process/controller executes accepted plan; cancellation never starts remaining points.
- `runner.refresh_analysis(store, run_id) -> run` recomputes quality/summary/diagnostics after manual labels.
- `dataset.profile_dataset(samples, tokenizer_path=None) -> dict`; `dataset.build_plan(spec) -> list[dict]` expanded per-point spec; `dataset.materialize_requests(spec) -> list[dict]` deterministic phase/category/sample/request IDs+body metadata, counts/mix exact by largest remainder then seeded shuffle; `dataset.load_jsonl(text) -> list[dict]`.

## Local web endpoints

`create_app(root) -> FastAPI`; dependency manager stored at app.state.manager; lifespan closes manager.

- GET /api/runs and /api/runs/{id}; GET /api/example (starter spec, never auto-run).
- GET /api/plans/{id}/summary: measured load points, repeats, eligible_points, nullable best_point, warnings. No interpolation or unmeasured capacity guarantee.
- POST /api/profile `{dataset,tokenizer_path?}`; POST /api/preflight endpoint; POST /api/runs spec.
- POST /api/runs/{id}/cancel; POST /api/runs/{id}/labels labels; POST /api/compare `{ids}`.
- POST /api/retest `{baseline_id,candidate_id,criterion}`; GET /api/runs/{id}/report?format=markdown|json|html.
- All mutating calls require X-Workbench-Action: local and reject foreign Origin; no permissive CORS. Host restricted to localhost/127.0.0.1/testserver. Input body bounded. No filesystem paths accepted for report IDs.
- UI fields and advanced JSON must reach every F01—F14 capability; query errors rendered as text, not HTML. Downloads are sanitized export, not arbitrary raw file access. Raw response viewing is local only and intentionally selected.
