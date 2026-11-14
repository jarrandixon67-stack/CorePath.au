# Second code review — 14 November 2026

Reviewed the merged foundation and existing backend at main commit
`f71f919edb5cc25a65d1408ab3b17abbab07ba90` (same tree as original foundation
commit `29d8a10019d1f1e50a271fc737232576db94c177`). The original 45 tests and both
repository CI jobs passed. Boundary checks nevertheless found real defects.
Corrections are proposed separately from main.

Follow-up rule rewrite: the earlier nine-specialist policy is now removed from
the older server, prompts, boundary tests and current documentation. The default
and cap support eleven; fully authorised plans must include all eleven and Persy
validates actual coverage. Principles have one canonical source and a tested
packaged snapshot. The table below records the original review; other integration
findings remain unresolved.

## Foundation findings corrected

| Severity | Finding and concrete effect | Correction and verification |
|---|---|---|
| High | A profile correction retained its original nonsensitive flag and could be shared with sensitive sharing disabled. | Corrections become sensitive; sharing requires the corresponding permission. Regressions cover private/shared corrections. |
| High | Raw profile inputs lacked required category/sensitivity checks before transmission. Direct proposal recording skipped model-processing permission and message validation. | Require reviewed classified excerpts; check permission before transmission and again at recording. Reject duplicate IDs. Classification remains a trusted application/owner responsibility. |
| High | Deleting/recreating a profile reused consent revision 1, allowing an old in-flight proposal to match the new consent. | Monotonic revisions survive owner deletion. A regression rejects the stale proposal. |
| High | SQLite context managers did not lock permission/source reads until the first write. Revocation could race proposal/report acceptance. | Explicit short transactions enclose checks and writes. Trace tests assert ordering; second-connection shutdown rejects in-flight work. No network calls run under locks. |
| High | Synthesis could omit specialist uncertainty, referrals, questions and original evidence limitations; Persy retained only the synthesis's wording. | Keep deterministic inventories outside synthesis, include them in the draft and retain source links. An omitting coordinator cannot remove the warnings. |
| Medium | Research required source quotations, while draft-builder schemas lacked quotation fields and used owner facts. Both received the same instructions. | Separate stage-specific policies/hashes; coordinator-only builder dispatch; reject unknown specialist stages. |
| Medium | Copied/mutated model instances could bypass validation at service hand-offs, including public-source flags. | Revalidate instances and assignments. Copied nonpublic sources are rejected before execution. |
| Medium | Nonobject JSON or malformed nested output raised uncontrolled errors. | Validate structure explicitly and handle transport failures consistently. Mocked regressions cover malformed and valid responses. |
| Medium | Eleven responses with zero supported claims could be labelled completed research. | Return `needs_evidence` while retaining gaps. |
| Medium | Profile evidence lost conversation IDs; reviewed findings allowed duplicate source IDs; old 12 reports did not flag retractions. | Persist provenance, reject duplicate IDs and use report source fingerprints to expose `needs_review`. |

Validation: **69 local tests passed**, the synthetic 24-call demo completed,
instruction export/compilation succeeded and the corrected wheel built. Original
build reproductions fail on output/provider/privacy defects; corrected regressions
pass. No real model requests or private subscriber data were used.

## Existing backend findings still requiring integration

Confirmed in existing source. The new package has not replaced the older
HTTP/database path, so its changes do not silently fix these issues.

| Severity | Existing code | Effect / required work |
|---|---|---|
| Resolved policy conflict | `backend/coordinator/limits.py`, `coordinator/policy.py`, `bot_standards/__init__.py` | The follow-up rewrite removes the nine-specialist ceiling, shares canonical principles and enforces eleven initial assignments for fully authorised research. Automatic subscriber routing and the older transport's peer-review round remain integration work. |
| High | `backend/persy/settings.py:service_timeout_seconds`, `coordinator/settings.py:max_duration_seconds`, `persy/runtime.py:research` | Persy defaults to 60 seconds; coordinator work may continue for 180. Upstream failure can coexist with downstream work. Add durable status, cancellation and reconciliation. |
| High | `backend/app/main.py`, `backend/app/security.py` | Knowledge routes use a shared internal token; the identity/library permission engine is not enforced there. Integrate endpoint-level authorisation before subscriber exposure. |
| Medium | `backend/life_profile/repository.py:context`, `backend/persy/services.py:ApprovedContext` | Old context is unbounded; Persy rejects more than fifty items. Larger profiles can break personalisation. Add bounded relevant retrieval and contract tests. |
| Medium | `backend/specialists/repository.py:start`, `backend/coordinator/repository.py:start` | Both default to twenty/day, but count specialist executions versus whole research runs. Align end-to-end work/cost budgets. |
| Medium | `feedback/database/runtime-grants.sql`, `backend/feedback/main.py:analyse` | Analysis uses the API pool, but only a separate analysis role can read the consented source view. Wire a restricted analysis connection, preserving raw-record restrictions. |
| Medium | `backend/feedback/settings.py:min_contributors`, `feedback/repository.py:snapshot` | Threshold can be thirty but snapshot is ten records. Higher thresholds cannot yield ordinary themes. Align distinct-contributor/sample/context budgets. |
| Medium | `backend/specialists/repository.py:retrieve` | `max_sources` limits section rows, not distinct sources. Correct the retrieval contract and independence reporting. |
| Medium | `backend/coordinator/settings.py`, `persy/settings.py`, `coordinator/transport.py` | Individually valid outputs can exceed aggregate character/byte limits. Define compatible summaries/evidence retrieval across services. |

Existing backend CI passed with its configured database tests. No additional local
PostgreSQL suite was run for this review. Passing tests do not cover all these
integration combinations.

## Release limits

This remains an internal development foundation, not an authenticated deployed
product. Local SQLite is unencrypted. Production identity, separate encrypted
databases, durable jobs, review controls, notifications, worldwide location data,
bank feeds and reviewed demonstrations remain required. Source matches establish
provenance, not truth or clinical suitability. Valid fact IDs do not prove a
paraphrase follows from those facts. Retain human review and evaluate live quality.
