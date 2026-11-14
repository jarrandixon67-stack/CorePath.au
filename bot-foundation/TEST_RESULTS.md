# Build verification

Executed on 14 November 2026 using Python 3.12.14 and Pydantic 2.13.4.

- `python -m unittest discover -s tests -v`: 69 tests passed after the second review.
- `python -m corepath_bots.cli demo --output demo-result.json`: completed a
  synthetic 24-call discussion with all eleven specialists, one routed review
  round, coordinator feedback and Persy's draft.
- `python -m compileall -q corepath_bots tests`: passed.
- `python -m pip wheel --no-deps --no-build-isolation .`: built the installable
  `corepath_bot_foundation-0.2.1-py3-none-any.whl` successfully.

Tests cover all-eleven routing and common initial peer snapshots; exact source
quotes and library scopes; unavailable/invalid contributions and partial
results; confidence capping and missing references; approval before model
processing; profile proposal/review/sharing, consent withdrawal/revision,
cross-owner limits and context bounds above fifty records; public location
freshness; founder-only controls, in-flight shutdown and changed evidence for 12;
negotiating limits; reminder opt-in/quiet hours/duplicates; Decimal budget and
BMI calculations; career input references; specialised nutrition referral;
medical/physiotherapy gates; and business research without sharing owner facts.

The second review adds 24 regression tests for retained warnings/referrals,
no false completion without findings, instance-validation bypasses, malformed
API responses, separate research/drafting policies, coordinator-only builders,
input consent before transmission, sensitive corrections, duplicate message IDs,
revision reuse after deletion, conversation provenance, locked permission/source
checks, rollback, cross-connection shutdown and later evidence retraction.

The output/provider regression subset was run against the original 0.2.0 wheel:
three assertions failed and malformed-response subcases raised six uncontrolled
exceptions, reproducing the bugs. Separate original-build reproductions confirmed
sharing a correction without sensitive permission, revision reuse after erasure,
acceptance of stale proposals and bypass of model-processing consent on direct
recording. These deliberately failing baseline reproductions are evidence of
defects; the corrected suite passes all 69 tests.

The original PR #18's foundation CI and existing PostgreSQL/backend CI both
completed successfully. Those tests did not cover the additional defects found
in this review. Current-commit CI is checked separately on the correction PR.

All model execution in these checks uses synthetic fixtures. No real API key,
model requests, user records, bank accounts, clinical assessments, invitations,
notifications or deployment were used. The existing backend/PostgreSQL suite was
not executed in this environment and the old services were not modified.

Structural tests do not establish live reasoning quality, source truth,
paraphrase entailment, clinical suitability or production security. See
`INTEGRATION.md` for the remaining service and evaluation work.

## Follow-up rule rewrite (0.2.2)

- Foundation suite: 72 tests passed, including cross-runtime policy parity and
  eleven-specialist request boundaries.
- Older backend suite: 248 tests passed locally; 170 database-dependent cases
  were skipped because no disposable PostgreSQL database was configured.
- Changed backend files passed lint/format checks; shared-policy snapshot check
  passed and the 24-call synthetic team demo completed.
- Updated integration tests cover all eleven real scoped runtimes in one team,
  rejection of an incomplete fully authorised plan, server-side call limits and
  Persy's rejection of false full-team coverage. PostgreSQL execution of these
  tests is delegated to the repository CI, not claimed as a local pass.

The changes do not implement normal chat routing, shared peer review in the older
transport, durable jobs, or production authorisation. Those limits remain explicit.
