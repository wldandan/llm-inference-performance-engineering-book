# T3 implementation and validation

Date: 2026-09-21. Scope: the approved F01–F14 workbench, bounded T3 slice.
The caller confirmed Maxwell's /arch and /ui approvals before implementation.

## Ownership and workflow

Only these files were created/edited by this slice:

- `perfworkbench/analysis.py`
- `perfworkbench/report.py`
- `tests/test_analysis.py`
- `tests/test_report.py`
- `docs/t3-validation.md`

No commits, global settings changes, dependency changes, or edits to other contributors' files.
The implementation and test-driven-development skills were read directly. The implementation
skill's standards resolver was run before writing code:

```text
node /Users/leiw/.codex/skills/aet-implementing-requirement/scripts/resolve-standards.mjs \
  --files perfworkbench/analysis.py,perfworkbench/report.py,tests/test_analysis.py,tests/test_report.py
python ← 无规范,回退通用最佳实践
```

The caller's explicit file boundary overrides skill defaults for sprint/implementation records;
this file is the implementation record. The caller explicitly prohibited a commit.

- [x] Read `docs/contracts.md`, `docs/architecture.md`, and `docs/sprints/v0.1.md`.
- [x] Write and run failing tests before implementation.
- [x] Implement the dict-only interfaces without depending on config/dataset/runner modules.
- [x] Add failing regression tests before tightening evidence and confound checks.
- [x] Add failing declared-load retest tests following the caller's F12 clarification.
- [x] Add failing F04/F13 enhancement tests for actual sent load and useful redacted reports.
- [x] Refactor/format and rerun tests, coverage, and lint for the owned slice.

## TDD evidence

Initial tests explicitly failed when importing the not-yet-implemented T3 API, rather than
failing test collection. Representative errors were `T3 analysis API has not been implemented`
and `T3 report API has not been implemented`.

| Stage | Observed output | What the red stage established |
| --- | --- | --- |
| Initial red | `97 failed in 0.13s` | Neither T3 module existed; all interface behaviors were specified first. |
| Initial green | `97 passed in 0.09s` | Metrics, quality, goals, diagnosis, comparison, retest, exports. |
| Evidence regression red | `14 failed, 106 passed in 0.21s` | Partial latency coverage, missing snapshots, nested changes, telemetry source/series/gap confounds, overflowing JSON numbers. |
| Evidence regression green | `120 passed in 0.10s` | Those checks became conservative; unaffected behavior stayed green. |
| Declared-load retest red | `5 failed, 145 passed in 0.18s` | Concurrency/rate retest needed an explicit exception; percentile retest coverage and actual runner timeout label also needed handling. |
| Declared-load retest green | `150 passed in 0.13s` | Explicit bounded workload interventions work; confound/quality/fixture gates remain enforced. |
| Original post-format coverage run | `150 passed in 0.33s` | Original slice tests passed after formatting. |
| F04/F13 enhancement red | `30 failed, 151 passed in 0.34s` | Missing dispatch-rate metrics, typed report context/evidence, retest serialization, and readable Markdown/HTML. |
| F04/F13 enhancement green | `181 passed in 0.11s` | Complete safe report content and actual sent-load semantics implemented. |
| Report consistency red | `4 failed, 190 passed in 0.19s` | Profile/result category aliases disagreed; declaration-only changes, safe rule/sampler settings, and source-error tables were missing. |
| Report consistency green | `194 passed in 0.15s` | Aliases, configuration details, declaration-derived differences, and telemetry source tables corrected. |
| Final enhancement coverage run | `194 passed in 0.59s` | All slice tests passed after formatting, with branch coverage enabled. |

Tests run against the working tree with the existing `.venv`, Python 3.12.14. Reproduce:

```sh
PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE=/private/tmp/llm-perf-workbench-t3-coverage \
  .venv/bin/python -m pytest -p no:cacheprovider \
  tests/test_analysis.py tests/test_report.py \
  --cov=perfworkbench.analysis --cov=perfworkbench.report \
  --cov-branch --cov-report=term-missing -q

.venv/bin/ruff check --no-cache \
  perfworkbench/analysis.py perfworkbench/report.py tests/test_analysis.py tests/test_report.py

.venv/bin/ruff format --no-cache --check --quiet \
  perfworkbench/analysis.py perfworkbench/report.py tests/test_analysis.py tests/test_report.py
```

Final coverage output (branch coverage enabled, no business-code exclusions):

```text
Name                        Stmts   Miss Branch BrPart  Cover
-----------------------------------------------------------
perfworkbench/analysis.py       404      7    214      6    98%
perfworkbench/report.py         244      1     94      2    99%
-----------------------------------------------------------
TOTAL                         648      8    308      8    98%
```

Lint: `All checks passed!`. Formatting check: exit 0.
Coverage output goes to `/private/tmp`; test and formatter caches are disabled.

Existing entry-point checks were also run, without editing their files:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider \
  tests/test_web.py::test_run_details_cancel_and_redacted_exports \
  tests/test_web.py::test_retest_latency_percentile_and_persistent_association \
  tests/test_web.py::test_retest_accepts_exact_declared_load_change_and_rejects_others \
  tests/test_cli.py::test_cli_compare_label_report_and_declared_retest -q --tb=short
```

Output: `4 passed, 2 warnings in 0.28s`. The warnings are existing Starlette/httpx and
AnyIO deprecations. No dependency or settings changes were made to suppress them.

## Metric and quality policies

- Only `phase="measure"` contributes. Warmups remain in the caller's audit data.
- Duration spans the first measured start through the last measured end, including failed
  tails and rejected-arrival timestamps. Missing, invalid, reversed, or nonfinite intervals
  invalidate the whole window instead of shortening it. Zero duration gives nullable rates.
- Request throughput is successful requests divided by that entire window. `sent` includes
  failures and interruptions, excludes `client_rejected`; service error rate is failed/sent.
  Interruption and admission rejection are separate counters and disqualify ranking.
- `actual_sent_per_s=(sent - 1)/(last sent start_s - first sent start_s)`, based on all
  measured sent records, including failed/interrupted sends and excluding warmups/rejections.
  Fewer than two sends, any missing/nonfinite start, or zero start span yields null with a
  warning. Record order does not matter. A missing completion end invalidates completion
  rates without erasing valid start-spacing evidence. `offered` counts recorded measured
  arrivals (including client rejection), and `target_rate` is the configured rate only in
  rate mode. These definitions deliberately use different windows from completion throughput.
- Latency distributions use successful requests, finite nonnegative values, their own sample
  counts, and linear interpolation at `(n - 1) * percentile`. A latency goal or percentile
  retest cannot pass on an incomplete successful-request latency subset.
- Nonstream TTFT/TPOT/chunk timing is unavailable. TPOT is recomputed from E2E, first observable
  chunk, and known usage as `(e2e - ttft)/(output_tokens - 1)`. No estimate for <=1 tokens.
  Chunk intervals are explicitly not token ITL.
- Token rates count successful-request usage over the complete window. Every successful
  request must have a known, nonnegative integer count; zero is valid, unknown is not zero.
  Missing counts make that rate null and emit coverage warnings. Prompt usage may include
  cached tokens and is explicitly not compute TPS.
- Quality evaluates hard completion/filter/truncation failures first, then manual labels or
  rules (JSON, top-level fields, required text, minimum length). Manual pass cannot override
  a failed/filtered/truncated response. Nonfinite JSON constants and overflow are rejected.
- Quality denominator is all sent measured requests: `coverage=(pass+fail)/sent`,
  `pass_rate=pass/sent`; unassessed/interrupted is unknown, never pass. Empty denominator is null.
- Goodput counts quality passes also meeting every configured per-request latency limit,
  divided by the full measured window. Unknown required timing does not qualify.
- Offline deadline actual is `target_requests / requests_per_s` when a target count is set,
  otherwise measured duration. It is a projection in seconds, not a reports/hour conversion
  or a capacity guarantee. Partial/fixture/coverage limitations are explicit warnings.

## Comparison and F12 retest

`compare_runs` is a fair-candidate comparison, not a load-sweep optimizer. Dataset, load,
generation, quality rules, goals, cache declaration, tokenizer identity, safety settings,
and telemetry configuration must align. Different endpoint/model/environment candidates
are allowed and their changed paths are exposed. Load differences remain incomparable,
with `best_run_id=null`; the caller can present per-point runner summaries for sweeps.

Individual eligibility requires a completed, nonfixture run, positive measured evidence,
planned/measured count agreement, complete quality coverage, passed constraints, and known
throughput. Ineligible candidates retain reasons and cannot win. Eligible aligned candidates
are ranked by goodput, successful requests/s, then lower p95 E2E.

Default `evaluate_retest(baseline, candidate, criterion)` requires exactly one recorded
endpoint/environment change. Nested changes count separately. Missing changes or multiple
changes are insufficient evidence. Metrics support scalar rates and latency names such as
`e2e_ms.p95`; change is signed `(candidate - baseline) / abs(baseline)`. A zero/missing baseline,
invalid criterion, unmet quality/goal gate, or fixture cannot establish effectiveness.
No measured gain or a quality regression is ineffective, even with a zero requested threshold.

The caller explicitly requested F12 support for bounded concurrency optimization while keeping
the existing interface. The optional declaration below authorizes precisely one load change:

```json
{
  "metric": "requests_per_s",
  "direction": "increase",
  "min_relative_change": 0.10,
  "change": {"field": "load.concurrency", "before": 1, "after": 2}
}
```

`load.rate` is also supported in rate mode, with concurrency held fixed. Declaration values
must match the snapshots; concurrency must be a positive integer; both runs must have a
recorded unchanged `safety.max_concurrency` covering their actual concurrency. The declared
variable must be the only load change, with no model/environment intervention. All other
comparison, quality, completion, latency, and fixture gates still apply. An internal detached
comparison view masks just the declared load field; original inputs are never mutated.
This establishes an observed workload-tuning result, not a fair model ranking or statistical
proof. Repeat the same experiment to validate the result.

Retest results additionally retain typed `before`/`after` metric values and changed field
paths in `differences` for later reports, including insufficient-evidence outcomes. The
existing status/reasons/change interface is retained. Export supports both the CLI's nested
`retest.result` association and the web endpoint's inline association.

## Diagnosis and export boundaries

Diagnostics provide evidence, confidence, adjustment, risk, validation, and pending status.
They are candidate explanations without exact tuning prescriptions. KV occupancy alone
produces insufficient evidence. A KV candidate additionally requires same-source preemption
growth with stable raw-series identity, no observed resets/gaps/errors, and co-observed queue
pressure and high occupancy. Missing telemetry coverage remains explicit. Fixture diagnostics
request real model evidence rather than claiming optimization.

F04 also emits low-confidence `admission_rejection` and `generator_shortfall` signals when
typed evidence shows rejected arrivals or observed sends below the target arrival rate.
They include the relevant counts/rates, adjustment, risk, and validation. Neither signal
asserts a server bottleneck or root cause; a short sampling window, client scheduling,
transport, and admission can all affect dispatch spacing.

Exports are allowlisted JSON, Markdown, and escaped standalone HTML with no scripts or remote
assets. All raw records, input/output text, notes, endpoint URLs, credentials/environment-variable
names, arbitrary model/environment strings, exception bodies, raw telemetry labels, and source
free-text warnings/diagnostic prose are omitted. Categories use consistent numbered aliases
across dataset profile and measured results. Known metric, quality, goal, status, and definition
fields remain readable and traceable by the local run ID.
All nonfinite/invalid numeric values become JSON null. Unknown fields fail closed. The tests
inject secret canaries in ordinary fields, nested fields, diagnostics, warnings, and numeric
slots and check all three formats; HTML injection is removed/escaped. Inputs are not mutated.

The F13 enhancement retains useful evidence through these explicit safe channels:

| Report content | Retained representation |
| --- | --- |
| Environment | SHA256 model/environment identities; numeric context length and known parallelism, device-count, memory, and scheduling fields; explicit engine/precision/device/quantization enums. Source is always `experiment_spec`, verification `user_declared`; arbitrary source text cannot claim observed hardware verification. |
| Dataset profile | Canonical JSON SHA256 for dataset and stored profile, validated SHA256 version/prompt fingerprints, numeric character/token distributions and counts, category aliases, duplicate/prefix counts, token-count source enum. Missing data stays null. |
| Configuration | Typed load/generation/goal/safety settings, quality rule flags and counts, numeric sampler extras, and SHA256 identities for rules/extras whose free text is omitted. |
| Telemetry | Per-source SHA256 identity, sample/error counts, and canonical metric count/missing/min/max/mean/last values with fixed units/kinds. Sources never merge; invalid/nonfinite ratios and error samples remain missing. Counter readings are not inferred rates/deltas, and collection may include warmup. |
| Differences | Exact allowlisted changed paths, validated hex run IDs, and finite numeric before/after values. No prefix matching or arbitrary descendants. An explicit retest declaration supplies its typed difference even without another snapshot. |
| Recommendations | Known diagnosis IDs map to canonical title/adjustment/risk/validation. Evidence is reconstructed from typed summary and per-source telemetry values; original titles, evidence text, advice, risks, and validation strings are never copied. Recommendations remain pending, low-confidence candidates. |
| Retest verification | Hex baseline/candidate linkage; metric/direction enums; finite threshold, declaration values, before/after metric values, and signed relative change; known outcome enum and safe changed paths. Saved fixture effectiveness is downgraded to insufficient evidence. The report identifies this as a saved assessment rather than an independent rerun. |

Markdown and HTML share the same structured section/table model: run, environment, dataset
profile, configuration, measured performance, latency, quality, goals, categories, telemetry
sources/values/interpretation, differences, recommendations/verification, retest, definitions,
and limitations. HTML is a standalone document with semantic tables, escaped cells, local CSS,
and horizontally scrollable tables. Neither format embeds an entire JSON dump. JSON export
retains the same sanitized evidence in structured form.

Fingerprints use SHA256 of sorted-key UTF-8 JSON, matching the dataset module's canonical
serialization without importing that module. Hashes support equality/identity checks, not
encryption; they do not authenticate a model, verify a declared environment, or prove quality.

## Scope of evidence

The 194 tests are meaningful deterministic unit tests of this slice's policies, including
success, failures, partial runs, missing/NaN data, quality, load confounds, safety declarations,
telemetry confounds, all new report evidence sections, and export security. The slice unit tests
require no parent implementation or live service; four additional existing entry-point tests
verify the web/CLI report and retest flows against the integrated modules.
The caller separately reported the first two real EvalScope integration scenarios passing;
that is integration-owner evidence, not a test run performed by this slice. This record makes
no real model, Ascend, device-capacity, or optimization-performance claim. Protocol fixtures
never qualify as optimization evidence. Final cross-module review/QA belongs to the enclosing
workbench workflow.
