# Workflow integration QA slice

Scope: `tests/test_workflow_integration.py` and this document only. No production
code, dependency configuration, existing tests, or commits are changed by this
slice. The bounded independent review of the repaired core is recorded below.

## What actually runs

The tests use the production FastAPI application through `TestClient`, its real
`ExperimentManager`, the on-disk `RunStore`, isolated EvalScope 1.12.0 workers,
the actual analysis/export functions, and the CLI. No manager, route, store,
analysis function, or HTTP client is replaced with a mock. A synthetic API key is
injected into the environment solely to test authenticated local requests.

The model/exporter substitute is a `ThreadingHTTPServer` bound to `127.0.0.1`
on an operating-system-assigned port. It serves JSON and SSE completions with
fixed text and usage, authenticated Prometheus samples, and an exporter error.
A separate test runs the shipped demo HTTP server through the real manager.
Servers, clients, and managers are closed during fixture teardown.

Every generated run retains `protocol_fixture: true`. Comparisons and retests
must therefore refuse model ranking and optimization claims even after all
manual labels pass. These tests do not establish model quality, hardware
performance, Ascend compatibility, capacity, or speedup. They intentionally do
not clear the fixture flag or fabricate successful run records to exercise a
positive ranking branch.

## Coverage of user workflows

| Workflow | Assertions using real interfaces |
| --- | --- |
| JSONL import / profile (F03) | CLI and web profile fingerprints agree; sample categories and unknown token lengths survive; duplicate IDs are rejected without sending generation requests. |
| Explicit preflight (F02/F14) | Web route invokes the real manager; exactly two generations, one synchronous and one streaming, each capped at eight output tokens; context length is attributed to the models endpoint. |
| Complete plan (F04–F07/F14) | Two concurrency points with two repetitions, two measured requests and one warmup each; exactly 12 worker generation sends, unique IDs, metadata absent from HTTP bodies, correct per-point snapshots and measured counts. |
| Telemetry lifecycle (F08) | Authenticated scrapes persist device labels, aggregate queue values, scale percentages, and distinguish missing metrics from HTTP 503; polling stops before the manager reports plan completion. |
| Manual quality refresh (F09) | Unknown → partially labeled → fully labeled; coverage and goodput refresh; labels survive opening a new store; foreign request IDs are rejected without changing the summary. |
| Comparison (F10) | Repeated runs are aligned; changed concurrency is exposed as a confound; protocol fixtures never receive a winning-model ranking. |
| Declared-change retest (F12) | Exact concurrency declaration passes condition alignment, preserves before/after metrics, and persists the baseline/candidate/criterion association without changing input snapshots or raw records; fixture limitation remains explicit. |
| Sanitized export (F13) | JSON, Markdown, and HTML preserve numeric evidence and traceability while omitting private prompts, output text, upstream errors, credentials, environment-variable names, and endpoint addresses; HTML is delivered with a sandbox policy. |
| Scan summary (F06) | Measured points retain their child-run IDs and repetition counts; throughput arithmetic matches persisted results; protocol data cannot yield a qualifying capacity or best point. |
| CLI interoperability | CLI reads web-created runs, persists labels, refreshes analysis, compares, records a declared retest, and exports a sanitized report. |
| Access / admission (F14) | Missing action header, foreign Origin/Host, and plans exceeding total count/output reservations are rejected before generation sends. |
| Shipped demo | The actual demo supports preflight, a real nonstream EvalScope run, default telemetry mapping, quality rules, and unavailable nonstream TTFT/TPOT. |

## Test-first execution evidence

Tests were added before any execution or validation documentation. This is a QA
slice against an existing implementation, so an initially passing behavioral
test is valid evidence; no artificial product failure was introduced.

1. Initial sandbox attempt: `1 failed, 12 errors` because local socket binding
   raised `PermissionError: [Errno 1] Operation not permitted`. No application
   workflow ran; this is an environment restriction, not a product red result.
2. Same tests with localhost-listener permission: **13 passed in 18.32s**.
   No production edits were needed. Two upstream deprecation warnings concern
   Starlette's HTTPX/AnyIO interfaces.
3. The new test file passed Ruff checking and format checking.
4. First combined integration-only run: **29 passed, 1 failed, 454 deselected
   in 73.03s**, with **67%** package coverage. The existing fractional-timeout
   regression failed before any request; its worker retained a
   `ValidationError`. This was reported immediately, not hidden as a passing
   coverage gate. Production files were being repaired concurrently.
5. Fresh bounded core check: **30 passed in 7.63s**, including missing usage,
   exact 50 ms request timeout, preflight exclusion, monotonic interruption,
   dictionary-key redaction, parent watchdog, incremental progress, and lock
   cleanup. The previous validation failure did not reproduce.
6. Focused malformed-message and bounded fallback-read checks: **6 passed,
   84 deselected in 0.02s**.
7. Final combined integration-only rerun: **30 passed, 455 deselected,
   2 warnings in 72.82s**, with **76%** package statement coverage
   (2,238 statements, 540 missed). This exceeds the >60% integration target.
   All 13 workflow cases passed both standalone and in the combined runs.

Final coverage evidence was written to
`/private/tmp/workflow-integration-qa.rLVOyU/final-integration-coverage.json`.
The denominator covers all production modules using the existing configuration;
this snapshot includes concurrent core fixes and is not an isolated percentage
attribution to this test file.

## Reproduce

From the workbench directory, in an environment that permits localhost sockets:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest \
  -p no:cacheprovider tests/test_workflow_integration.py -q --tb=short
```

For the full integration-marked suite, use a fresh temporary directory to keep
coverage evidence separate from concurrent QA runs:

```sh
workflow_qa_dir=$(mktemp -d /private/tmp/workflow-integration-qa.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE="$workflow_qa_dir/integration.coverage" \
  .venv/bin/python -B -m pytest -p no:cacheprovider -m integration \
  --cov=perfworkbench --cov-config=pyproject.toml --cov-report=term-missing \
  --cov-report="json:$workflow_qa_dir/integration-coverage.json" \
  --basetemp="$workflow_qa_dir/pytest" -q --tb=short
```

The coverage denominator is the entire `perfworkbench` package with the existing
coverage configuration. Unit tests are not relabeled as integration tests and
business modules are not excluded to raise the percentage. Coverage is measured
on the current working tree; other workers are concurrently repairing and
finalizing production files, so the final release must measure its own snapshot.

## Remaining release work

- Integration coverage is not a substitute for the bounded core review below
  or a full release review of the final working-tree snapshot.
- `TestClient` covers HTTP workflows, not rendering or browser interaction;
  browser QA remains separate.
- True model/Ascend performance and positive optimization evidence require
  separately authorized experiments on actual endpoints.

## Bounded independent core re-review

Read-only scope: the seven previously reported findings in
`perfworkbench/evalscope_worker.py` and `perfworkbench/runner.py`, plus the
requested parent-death, incremental-progress, and store-lock fixes. This is not
a new general audit or release approval.

| Previously reported issue | Current implementation and verification |
| --- | --- |
| Missing usage aborts EvalScope aggregation | Canonical JSON retains null usage before the plugin fills only private upstream numeric fields. The real-worker two-request regression completes after a missing-usage response. |
| Invalid message counted as successful HTTP 200 | Normalization validates the message/delta object and content shape before accepting finish evidence. All four malformed-message cases pass. |
| Preflight bypasses active-plan exclusion | Preflight and submit share the manager mutex, active-preflight state, and workspace file lock. Same-manager and other-process exclusion regressions pass. |
| Response cap bypassed by parser fallback | Byte count and exceeded state survive subsequent reads; overflow closes the response and fallback raises again. Bounded-read regressions pass. |
| Secrets survive in dictionary keys | Recursive scrubbing covers keys and values, including nested dictionaries. Redaction regression passes. |
| Fractional request timeout rounded up | Integer EvalScope arguments remain compatible with its model; an outer `asyncio.timeout` enforces the exact configured deadline. Real 50 ms regression passes. |
| Interrupted timing depends on wall-clock adjustment | Starts retain a monotonic anchor and reconciliation uses that clock; no anchor means unknown latency. Clock-jump regression passes. |
| Parent-death / progress / failed creation | Worker starts a parent-PID watchdog before loading EvalScope; progress counts newly appended lines and updates only the manifest; failed store creation closes the workspace lock descriptor. Focused regressions pass. |

Decision: **APPROVED for the reviewed fixes.** No remaining actionable blocker
was found in these specific fixes. Approval is limited to the reviewed contracts
and fixture-backed behavior; it does not certify browser acceptance, all
F01–F14 release criteria, or actual model performance.
