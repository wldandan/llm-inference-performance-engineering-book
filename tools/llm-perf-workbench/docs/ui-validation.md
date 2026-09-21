# T4 local web / UI implementation and validation

Date: 2026-09-21. This record covers only the bounded local frontend/web slice.
The caller supplied approved architecture/UI gates and explicitly prohibited commits.

## Files owned by this slice

- `perfworkbench/web.py`
- `perfworkbench/static/index.html`
- `perfworkbench/static/app.js`
- `perfworkbench/static/style.css`
- `tests/test_web.py`
- `tests/e2e/test_dashboard.py`
- `docs/ui-validation.md`

No changes to `__init__`, CLI, configuration, dataset, runner, worker, store, analysis,
sweep, report, examples, dependency files, or other contributors' files. No commit was made.
Browser screenshots and coverage data are temporary artifacts outside the repository.

Read directly: `docs/contracts.md`, `docs/architecture.md`, `docs/sprints/v0.1.md`,
and subsequently `docs/t3-validation.md` plus actual manager/store/sweep interfaces.
Read the complete frontend-design and test-driven-development skills and the latter's
testing anti-patterns reference. The frontend skill informed the warm gray notebook,
deep teal navigation, compact technical typography and deliberately empty initial screen.
The TDD skill informed the failing-test-first workflow below.

The standards resolver was run before implementation:

```sh
node /Users/leiw/.codex/skills/aet-implementing-requirement/scripts/resolve-standards.mjs \
  --files perfworkbench/web.py,perfworkbench/static/index.html,perfworkbench/static/app.js,perfworkbench/static/style.css,tests/test_web.py,tests/e2e/test_dashboard.py
```

It found no configured Python, TypeScript/JavaScript, or CSS standards and prescribed
general best practices. Existing pinned dependencies were preserved. Current official
[FastAPI lifespan guidance](https://fastapi.tiangolo.com/advanced/events/) and
[Playwright screenshot guidance](https://playwright.dev/python/docs/screenshots) were checked.

## Red → Green evidence

| Stage | Observed result | Evidence |
| --- | --- | --- |
| Initial entry point / browser Red | 2 failed | Missing `web.py` assertion and missing empty-state heading in real Chrome. The earlier scaffold probe reported fixture setup assertions; those were not counted as passing route behavior. |
| Full initial browser Red | 6 failed | Missing overview, editor, JSONL/profile/preflight, submit/cancel, detail/raw/labels/retest, comparison and error interactions. |
| First working UI/API pass | 36 passed, 1 failed | All six browser workflows passed; unexpected server exceptions still propagated through TestClient. |
| Manager/interface regression Red | 6 failed | Actual ValueError conflict → 409; latency percentile retest/persistence; timed-out labels; plain-text 404; overflow JSON; completed-before-analysis refresh race. |
| Declared load-change Red | 1 failed | API rejected the newly requested `criterion.change` before implementation. Browser percentile/controlled-change assertions were added before the controls. |
| Plan/sweep Red | 2 failed, then 1 failed | New plan summary returned 404; missing browser scan control; separate running-plan summary test returned 404. |
| Final input-boundary Red | 2 failed | Profile-only input incorrectly inherited a default generation budget; malformed retest direction returned 500 instead of 422. |
| Final complete owned suite | **51 passed in 33.76s** | **41 API tests + 10 real-Chrome tests**, including the two real-backend tests below. |
| Separately measured real-backend tests | **2 passed, 8 deselected in 15.56s** | Real FastAPI + manager + store + EvalScope process against a loopback protocol endpoint; no manager monkeypatch. |

The first real-backend browser attempt successfully ran EvalScope, but its assertion saw
the starter name: the test edited fields before the asynchronous starter-load completed.
The harness now explicitly waits for the starter value before editing; the subsequent
real-backend workflow passed. Browser selector assertions use accessible combobox names.

Reproduce from this project root using the existing `.venv` and installed Chrome:

```sh
PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE=/private/tmp/llm-workbench-t4-final-coverage \
  .venv/bin/pytest tests/test_web.py tests/e2e/test_dashboard.py \
  -q --tb=short -p no:cacheprovider \
  --cov=perfworkbench.web --cov-branch --cov-report=term-missing

PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE=/private/tmp/llm-workbench-t4-integration-coverage \
  .venv/bin/pytest tests/e2e/test_dashboard.py -m integration \
  -q --tb=short -p no:cacheprovider \
  --cov=perfworkbench.web --cov-branch --cov-report=term-missing

.venv/bin/ruff check --no-cache perfworkbench/web.py tests/test_web.py tests/e2e/test_dashboard.py
.venv/bin/ruff format --no-cache --check perfworkbench/web.py tests/test_web.py tests/e2e/test_dashboard.py
node --check perfworkbench/static/app.js
```

Final web coverage, with branch measurement enabled (the percentage combines statements
and branches; it is not a JavaScript or whole-project coverage claim):

| Run | Statements | Missing statements | Branches | Partial branches | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Complete owned suite | 290 | 20 | 88 | 13 | **91%** |
| Only real-backend browser integration | 290 | 97 | 88 | 23 | **61%** |

Lint: all checks passed. Formatting: 3 files already formatted. JavaScript syntax: exit 0.
The full test invocation emitted two third-party deprecation warnings from the pinned
Starlette/TestClient HTTPX and AnyIO portal compatibility paths. They were not suppressed;
dependency upgrades are outside this slice. The separate real-browser invocation had no warnings.

## What the evidence proves

`tests/test_web.py` uses a narrow manager/store route double. It tests real ASGI security,
request parsing, route dispatch, configuration/dataset/analysis/export behavior and error
handling. It **does not prove experiment execution integration**.

Eight browser tests run actual Chrome against a clearly labeled lightweight local HTTP
API fixture. They verify UI state, form/JSON preservation, import, explicit confirmation,
polling, cancellation interaction, metrics/unknowns, error escaping, comparison, retest
payloads, raw opt-in and scan table/curve. Fixture timings are not performance evidence.

Two additional browser tests use the actual `create_app`, `ExperimentManager`, `RunStore`,
analysis, export and installed EvalScope worker. Only the model server is a local protocol
fixture; no manager/store patch or fake run is inserted:

1. Empty history → load/edit starter → dataset profile → explicitly confirm preflight
   → submit a streamed experiment → observe completion → import manual labels → see
   quality re-analysis → explicitly view local responses → download sanitized JSON.
   The endpoint observed **exactly two preflight generation calls, each capped at 8 output
   tokens, plus exactly two measured calls**, with no hidden preflight/retries. Two successful
   records were stored. The downloaded report omitted response text and the private endpoint.
2. Submit a bounded two-point concurrency scan → view the running plan table → cancel
   from the browser → inspect stored terminal states and plan summary. Both child runs
   became cancelled; remaining points did not dispatch. The UI kept best capacity unknown.

These are local protocol/execution validations, not real model, accelerator, capacity,
or optimization-performance claims. Comparison/retest policy correctness remains backed by
the parent's analysis tests; this slice additionally checks its UI and API contracts.

## F01—F14 reachable UI map

| Feature | Local UI entry and behavior |
| --- | --- |
| F01 goals | Online/offline goal form, throughput/latency/error/quality fields; advanced JSON retains deadline and target request count; result goal judgments. |
| F02 service | Model/base URL/key environment name/context/environment form; separate bounded preflight confirmation and output. |
| F03 dataset | Local JSONL file/text import with line-specific parse errors and duplicate-ID check; profile including fingerprint, lengths, categories and tokenizer availability. |
| F04 traffic | Concurrency/rate/count/warmup/repeats/scan/mix/seed form, complete payload preservation and actual progress/audit. |
| F05 baseline | Persisted run list, progress/cancel, full local snapshot/profile, measured/warmup request audit and explicit raw-response checkbox. |
| F06 scan | Plan summary API, on-demand measured-point curve and accessible table, eligible points, nullable best point, generator warnings; repeated P95 values are means of per-run P95, never a pooled new P95. |
| F07 metrics | Units and sample counts, TTFT/TPOT caveats, unknown values, category table, all distributions/definitions available. |
| F08 telemetry | Source/mapping JSON with local env-name credentials; resource panel retains raw metric names, labels, time, units and missing/error states. |
| F09 quality | Rules/manual/none, text/JSON fields/truncation configuration; request-ID label JSON import and refreshed analysis. |
| F10 compare | Multi-select recorded model/config candidates, compatibility/differences/reasons, nullable winner; no invented winner. |
| F11 recommendations | Evidence, confidence, adjustment, risk, validation condition and status; explicit insufficient-evidence display. |
| F12 retest | Clone baseline configuration, select candidate, scalar/P95 metric/direction/threshold, optional one declared concurrency/rate change; persisted baseline/candidate/criterion/result association. |
| F13 export | Sanitized Markdown/JSON/HTML downloads; original response text only in explicitly selected local view. |
| F14 protections | Plan-wide budget fields and estimate, explicit submit, independent preflight confirmation, stop-plan control; server revalidates the entire spec. |

## Integration details for the parent

- `create_app(root)` creates one manager in lifespan, puts it in `app.state.manager`, and
  closes it at shutdown. The inline starter depends only on `ExperimentSpec`, not examples.
- All documented endpoints are implemented. Added by caller request:
  `GET /api/plans/{id}/summary` filters `store.list()` by `parent_id`, gets each full child,
  and calls `sweep.summarize_sweep`. Nullable not-yet-analyzed summaries become empty dicts
  in a detached reducer input; stored snapshots are untouched. Empty/invalid plans return
  actionable 404/422 text. No interpolated or unmeasured capacity claims are added.
- `POST /api/retest` accepts `criterion.change = {field, before, after}`. Only
  `load.concurrency` or `load.rate` is allowed; values must be finite and positive, and
  concurrency integral. The analysis module checks snapshot agreement and confounds.
- Retest results are saved with `store.update(candidate_id, retest=association)`;
  association includes baseline ID, candidate ID, criterion, status, reasons and change.
  Existing `parent_id` remains the scan/plan association. Candidate detail renders the
  saved association on later visits. No raw prompts or response text is added to it.
- Errors are text, including unrecognized route 404s. Actual manager busy/missing-plan
  ValueErrors map to 409/404. Unexpected exceptions are intercepted before server logging;
  raw error values are not echoed. Validation errors omit Pydantic input/context.
- Host allowlist and exact same-origin validation cover reads/assets and writes; writes
  also need `X-Workbench-Action: local`. No permissive CORS. Actual streamed/chunked bodies
  are capped at 2 MiB, not just trusted Content-Length. JSON rejects duplicate keys,
  nonfinite/overflowing numbers, invalid UTF-8 and excessive nesting.
- IDs must be generated 32-digit lowercase hex; asset names and report formats are
  allowlisted. Report HTML is a sandboxed attachment. CSP limits resources to this origin;
  scripts/styles are separate local files and font sources use `local(...)` only.
- UI renders external strings through text nodes, never HTML insertion. The original
  response viewer starts empty, requires selection and clears on deselection/navigation.
  No raw responses or credentials are stored in browser localStorage.

## Visual and accessibility checks

Inspected actual Chrome screenshots at 1440×1000, 1440×1280 (recaptured detail), and 390×844. Verified Chinese hierarchy,
warm gray/deep teal composition, readable units, explicit empty state, labeled native
controls, keyboard skip link, native modal confirmation, focus outlines and reduced-motion
support. No page-wide horizontal overflow in overview, editor or detail at 390px; data
tables/charts scroll within their containers. Raw progress internals live in a collapsed
detail instead of dominating the result view. No uncaught page errors in the browser suite.

Temporary evidence directory: `/private/tmp/workbench-t4-visual-4uhnx8iq`.
Overview/editor images use the real app with an empty store and do not send model requests.
Detail/sweep images are explicitly **API-fixture visual checks**, not measurement evidence:

- `overview-desktop.png`, `overview-mobile.png`
- `editor-desktop.png`, `editor-mobile.png`
- `detail-fixture-desktop.png`, `detail-fixture-mobile.png`
- `detail-metrics-fixture-mobile.png`
- `sweep-fixture-desktop.png`, `sweep-fixture-mobile.png`

### Screenshot correction after main review

The earlier `detail-fixture-desktop.png` was captured before asynchronous navigation
finished and incorrectly showed the overview. Its filename and the previous unconditional
inspection claim were not sufficient evidence of the detail view. Disregard that earlier
copy. The detail/sweep desktop and mobile screenshots were recaptured from the current
frontend after explicitly waiting for the detail heading, hidden overview, completed
status, all six rendered metric cards and category content. Sweep capture additionally
waited for the visible result, two SVG points, two table rows and the no-best-point warning.

All five current detail/sweep PNGs listed above were then opened as actual images via
exec/base64 (the image-view tool cannot access this host path) and visually inspected:
desktop detail contains the heading and all six metric cards, including unknown values
and units; desktop sweep contains both points, the table and protocol/generator warnings;
mobile detail and its separate metrics capture contain the intended detail content.
The mobile sweep chart/table intentionally scroll horizontally inside their containers;
the default viewport shows the left side. No page-wide horizontal overflow or uncaught
browser errors were observed. Captures disable entry animations and wait for font readiness.

SHA-256 hashes of `web.py`, `index.html`, `app.js` and `style.css` were unchanged before
and after recapture. Only temporary PNG evidence and this correction were updated; no
production or test files changed. These remain API-fixture visual checks, not real-model
or GPU measurements. The temporary paths are supporting local evidence, not runtime
dependencies or required documentation assets.
