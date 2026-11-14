# Build verification

Executed on 14 November 2026 using Python 3.12.14 and Pydantic 2.13.4.

- `python -m unittest discover -s tests -v`: 45 tests passed.
- `python -m corepath_bots.cli demo --output demo-result.json`: completed a
  synthetic 24-call discussion with all eleven specialists, one routed review
  round, coordinator feedback and Persy's draft.
- `python -m compileall -q corepath_bots tests`: passed.
- `python -m pip wheel --no-deps --no-build-isolation .`: built the installable
  `corepath_bot_foundation-0.2.0-py3-none-any.whl` successfully.

Tests cover all-eleven routing and common initial peer snapshots; exact source
quotes and library scopes; unavailable/invalid contributions and partial
results; confidence capping and missing references; approval before model
processing; profile proposal/review/sharing, consent withdrawal/revision,
cross-owner limits and context bounds above fifty records; public location
freshness; founder-only controls, in-flight shutdown and changed evidence for 12;
negotiating limits; reminder opt-in/quiet hours/duplicates; Decimal budget and
BMI calculations; career input references; specialised nutrition referral;
medical/physiotherapy gates; and business research without sharing owner facts.

All model execution in these checks uses synthetic fixtures. No real API key,
model requests, user records, bank accounts, clinical assessments, invitations,
notifications or deployment were used. The existing backend/PostgreSQL suite was
not executed in this environment and the old services were not modified.

Structural tests do not establish live reasoning quality, source truth,
paraphrase entailment, clinical suitability or production security. See
`INTEGRATION.md` for the remaining service and evaluation work.
