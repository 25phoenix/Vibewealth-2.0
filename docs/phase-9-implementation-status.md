# Phase 9 implementation, corrections and release gates

The canonical contract is `phase-9b-assistant-architecture.md`. Phase 9 is **not
complete or release-ready**. This document separates corrected source, automated
verification, unexecuted PostgreSQL tests and unsupported provider capabilities.
It does not approve an endpoint, select a model, or change the 45/60/90 deadlines.

## Current phase status

| Phase | Implementation | Verification / remaining gates |
| --- | --- | --- |
| 9D | Complete SQL population aggregates/counts and separately limited detail projections now share authoritative account, budget and allocation selectors. Context construction consumes bounded examples rather than whole ORM populations. The exact read-only repeatable-read observation statement and India observation date remain unchanged. | Unit/SQLite coverage passed. Snapshot, large-population/truncation and PostgreSQL equivalence tests remain guarded and skipped. Do not declare 9D accepted from unit results alone. |
| 9E | Claim selection/rendering remains strict and backend-authored. Synchronous preparation helpers reject event-loop execution. All preparation counters, including the former synthetic process counter, are rejected before admission. Deadline-complete process preparation is explicitly unsupported; no serializer thread or child is started. | No verified production token counter is implemented or admitted. Synthetic process counts do not establish token accuracy. Grounded production execution remains unavailable. |
| 9F | Exact literal-loopback candidate configuration validation remains. The installed httpx/httpcore dispatch path is explicitly unsupported and refuses before creating/calling a client or transport. | Installed cleanup has internal shields and no supported hard-close acknowledgement. A reviewed bounded transport implementation is required BEFORE activation; a benchmark/approval boolean cannot manufacture this capability. No transport/model benchmark was performed. |
| 9G | Recovery retains normalized payload and key in memory; only a versioned owner-scoped pointer enters tab storage. Same-key resend is explicit. Reload recovery permits history review and explicit warned reconciliation. Reads are aborted/invalidation-fenced across mutation, deletion, navigation and session teardown. Lifecycle/ErrorDto validation is strict and conflicts preserve authorized current state. | 157 frontend tests passed; typecheck/build passed. Live browser, reload/reconciliation UX and accessibility review remain outstanding. |
| 9H | Automated verification only; **PARTIAL/BLOCKED**. | Dedicated PostgreSQL verification, reviewed transport/counter implementations, exact endpoint/peer approval, actual-machine model benchmark, browser and operational/deployment review are all outstanding. |

## Corrections made in this pass

1. **Transport shutdown:** removed the unsafe executable adapter path. The local
   candidate always reports `supports_bounded_shutdown=False`; direct selection
   refuses without starting work. It exposes an explicit termination-complete
   signal (initially true because no owned transport exists). Both admission and
   `_execute` reject it before invocation; capacity/quota refusal cleanup remains
   under the C4 owner. Inference and original work deadline arguments are kept
   separate at the boundary. No test claims an active real transport was closed.
2. **Preparation/counting (superseding the prior process claim):** no available
   primitive establishes bounded serialization-thread termination, subprocess
   startup AND reap within the original work deadline. The executable process
   path has therefore been retired. All counters fail capability checks, even
   test counters; direct async preparation refuses before examining input,
   serialization, queueing, startup or cleanup. The old worker entry point exits
   without reading or printing input. No detached work or new cleanup budget is
   introduced. This is safety through refusal, NOT proven process shutdown.
   The sealed C4 test executor has a resource-free asynchronous preparation gate
   solely to exercise real orchestration cancellation; it is not a tokenizer.
3. **Ambiguous recovery:** the in-memory operation retains exact normalized
   content and the key. Lookup 404 is explicitly inconclusive. Explicit resend
   reuses both values; it cannot invent a replacement key. Saved history stays
   accessible while tracking is unresolved. Reload has no reconstructed payload:
   history review and a separate warned confirmation may stop tracking, without
   resending, claiming rollback or cancelling server work. Recovery 401 uses the
   established authentication-expiry path. Aborted mutations retain the pointer.
4. **Stale polling:** mutation/deletion starts a new lifecycle generation and
   aborts reads. Every application checks the active conversation/generation;
   older attempts and terminal-state regressions are rejected. An in-flight poll
   deliberately ignoring abort cannot restore deleted state. Resubmission after
   browsing history returns to its original conversation rather than mixing views.
5. **Conflict contracts:** the shared client permits a domain error parser and
   preserves validated `current_turn`. Assistant errors enforce exact keys,
   status/code/detail mapping, safe issues and current-turn rules. Only documented
   pre-reservation refusals discard that refused operation's pointer. A late
   ATTEMPT_CONFLICT reconciles from matching current state or retains its key for
   lookup; a bare 409 is never proof of rollback.
6. **Financial construction:** full SQL totals/counts are independent of bounded
   ordered examples. Goal descriptions are never selected into reporting rows.
   Category comparisons rank the full grouped relation in SQL before LIMIT.
   Shared account/ledger predicates and monthly budget arithmetic preserve API
   defaults and the cash-flow/budget distinction. Context has explicit counts,
   totals and truncation; required query failures never become fabricated zeros.
   Python fact construction is bounded and checks the worker deadline.
7. **DTO validation:** primitive enums, real UTC dates/timestamps (including
   microsecond ordering), paired observation/date fields, India date derivation,
   message metadata, completion/lease/error/action flags and pagination bounds
   are validated. Malformed or contradictory responses are rejected.
8. **HTTP cancellation:** all assistant methods accept AbortSignal. The hook
   aborts requests on session/unmount/navigation teardown, retains uncertain
   submission metadata, and keeps epoch checks even when fetch ignores abort.

## Prior verification (historical; not rerun in the preparation correction pass)

Commands ran from the indicated WSL directory using existing dependencies.
Tracebacks were suppressed for database-capable suites. Short assertion traces
were used only while debugging the DB-free process tests; no credentials or
connection diagnostics were printed.

| Directory | Exact command | Final result |
| --- | --- | --- |
| backend | `.venv/bin/python -m pytest -q -p no:cacheprovider --tb=no` | Exit 0: **561 passed, 342 skipped**, one existing Starlette/httpx deprecation warning. |
| backend | `.venv/bin/python -m pytest -q -p no:cacheprovider --tb=no tests/test_assistant_preparation.py tests/test_assistant_reporting.py tests/test_assistant_contracts.py tests/test_accounts.py tests/test_budgets.py tests/test_goals.py tests/test_dashboard.py` | Earlier focused run: exit 0, **353 passed**; the subsequent full suite includes the final additional guards/tests. |
| frontend | `node --test scripts/assistant.test.mjs` | Earlier focused run: exit 0, **17 passed**; the subsequent full suite includes an additional conversation-scope regression. |
| frontend | `npm run test` | Exit 0: **157 passed**, zero failed/skipped. |
| frontend | `npm run typecheck` | Exit 0. |
| frontend | `npm run build` | Exit 0; Vite emitted plugin timing advice. |
| frontend | `npm run lint` | Exit 0; ten warnings: seven existing provider/UI warnings and three assistant-hook effect-driven state/reset/load warnings. |

PostgreSQL tests did **not** run: the existing opt-in guards did not establish an
explicitly configured dedicated disposable test target. This includes the seven
reporting PostgreSQL tests and existing assistant lifecycle/concurrency/execution
boundary integration tests. No environment values or secret files were inspected
to seek a target. No development/production database or migration was touched,
and their current revisions are deliberately not asserted.

The earlier standalone `/count` tests did not prove assistant-handler disconnect
wiring or deadline-bounded startup/reap; they have been replaced. Current refusal
regressions arm serialization/startup/reap tripwires and prove none is entered,
including with an expired deadline. No claim of terminating an active process is
made. The real `generate()` orchestration boundary now owns the only ASGI receive
monitor before preparation and through dispatch/execution/finalization. The body
has already been bounded and consumed by the route; `_execute` receives no second
consumer. DB-free tests deliver `http.disconnect` while the sealed test preparation
gate is blocked and assert its waiter is gone before capacity release, no dispatch
or late completion, and provisional quota refund. These tests use fake DB phases
and do not establish durable PostgreSQL behavior. A separate actual-handler test
with guarded PostgreSQL reservation/by-key recovery is added but not run here.
An already queued disconnect is now observed before reservation; cancellation
after reservation leaves durable pending state for normal lifecycle recovery.

## Preparation correction verification

No database access is authorized in this pass. Focused commands explicitly set
`RUN_POSTGRES_INTEGRATION=0` for that subprocess, retaining the existing guard and
preventing database connections without reading any configuration values.
From `backend/`, the initial focused command was:

```sh
RUN_POSTGRES_INTEGRATION=0 .venv/bin/python -m pytest -q -p no:cacheprovider --tb=no tests/test_assistant_preparation.py tests/test_assistant_execution_boundaries.py tests/test_assistant_turn_lifecycle.py tests/test_assistant_contracts.py
```

Exit 0: **279 passed, 0 failed, 77 skipped**, one existing Starlette/httpx
TestClient deprecation warning. The expanded command, repeated after the final
refusal/recovery assertions, was:

```sh
RUN_POSTGRES_INTEGRATION=0 .venv/bin/python -m pytest -q -p no:cacheprovider --tb=no tests/test_assistant_preparation.py tests/test_assistant_execution_boundaries.py tests/test_assistant_turn_lifecycle.py tests/test_assistant_contracts.py tests/test_assistant_reporting.py
```

Final exit 0: **324 passed, 0 failed, 77 skipped**, same one warning, 26.46 seconds.
All guarded PostgreSQL cases were deliberately skipped, including the new actual
handler preparation-disconnect/lookup/retry test. No dedicated target was sought
or inspected. DB-free orchestration assertions are verified; PostgreSQL durable
recovery is source-only coverage, not an executed result. Blocked-stage tests
prove refusal before resource acquisition; they do NOT prove bounded execution
or reap of an active native worker. No deadline-complete process/tokenizer is
supported. Frontend files were not changed and frontend checks were not rerun.

## Changed files in this correction pass

Backend application:

- `backend/app/services/accounts.py` — shared account snapshot statement.
- `backend/app/services/budgets.py` — shared monthly snapshot statement and rounding.
- `backend/app/services/goals.py` — shared allocation-net statement.
- `backend/app/services/dashboard.py` — optional bounded budget details; API defaults preserved.
- `backend/app/services/financial_reporting.py` — complete SQL aggregates and bounded detail pages.
- `backend/app/services/assistant_context.py` — bounded construction and worker-only serialization guard.
- `backend/app/services/assistant_orchestrator.py` — supported-boundary checks and async preparation entry.
- `backend/app/services/assistant_provider.py` — explicit unsupported-transport refusal.
- `backend/app/services/assistant_turns.py` — pre-admission/execution capability checks.
- `backend/app/core/assistant_database.py` — expose the existing worker deadline to bounded context construction; existing fences/post-cleanup checks retained.
- `backend/app/services/assistant_preparation.py` — fail-closed preparation capability boundary (no executable process).
- `backend/app/services/assistant_preparation_worker.py` — retired child entry point; refuses without reading input.

Tests:

- `backend/tests/test_assistant_preparation.py` — refusal tripwires, real orchestration receive/cancellation, quota and construction tests.
- `backend/tests/test_assistant_reporting.py` — fail-closed transport/counter expectations; grounding tests retained.
- `backend/tests/test_assistant_reporting_postgres.py` — SQL projection/equivalence and refusal coverage, all guarded.
- `frontend/scripts/assistant.test.mjs` — strict DTO, 404/401 recovery, reload, conflict, deletion race, abort and conversation-scope regressions.

Frontend:

- `frontend/src/services/api/apiClient.ts` — domain error parser and validated current-turn preservation.
- `frontend/src/services/api/assistantApi.ts` — signals and strict lifecycle/error contracts.
- `frontend/src/hooks/useAssistantConversation.ts` — retained payload/key, reconciliation, cancellation and response fencing.
- `frontend/src/pages/AssistantPage.tsx` — explicit resend/review/acknowledgement controls; draft clears only after acceptance.

Documentation: this file. Existing unrelated dirty files were preserved; no
migration, dependency manifest, database safety helper, credential or Git history
change was made.

## Outstanding decisions and operational work

- Implement/review enforceably bounded preparation startup/serialization/termination/reap,
  a transport with enforceable termination and a verified model/template-specific
  counter before any provider admission.
- Separately approve exact endpoint/peer and topology, an already-present model,
  and actual-machine grounding/resource/45-second inference/60-second work limits.
- Run guarded PostgreSQL suites against an explicitly configured dedicated
  disposable target; never the development or production database.
- Complete live-browser recovery/deletion/logout/accessibility checks and
  deployment/log-redaction/operational review. Keep one worker/replica until shared
  admission is designed. Do not deploy or enable a provider by implication.
- A prior report identified credential exposure. The owner should rotate the
  exposed credential through the secure operational process. This task did not
  inspect, copy, repeat or rotate it.

## Files changed in the preparation-only correction pass

- `backend/app/services/assistant_preparation.py`: retire unsupported execution;
  refuse every counter/preparation call without starting owned work.
- `backend/app/services/assistant_preparation_worker.py`: refuse old launchers.
- `backend/app/services/assistant_turns.py`: one full-operation disconnect owner;
  sealed resource-free test preparation seam; existing fences remain unchanged.
- `backend/tests/test_assistant_preparation.py`: refusal and real orchestration tests.
- `backend/tests/test_assistant_execution_boundaries.py`: guarded actual-handler
  preparation disconnect/recovery coverage and earlier queued-disconnect assertion.
- This status document: replace overstated process guarantees and distinguish
  historical checks, current source, DB-free coverage and unrun PostgreSQL tests.
