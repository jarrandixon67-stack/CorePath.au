# Integrating the replacement foundation

Base reviewed: `jarrandixon67-stack/CorePath.au`, commit
`efe601151d5264f01725637d86abd7aa2ee74435`. The branch is an additive review build;
no existing service entry points, production database migrations or Render
deployment files are changed.

## One policy per execution path

The earlier nine-specialist rule has been replaced in the backend. It supports
eleven available assessments and rejects an incomplete explicit full-team plan,
but defaults to relevant-domain Auto routing and retains optional unused-domain
follow-up. This package also defaults to Auto; shared peer review is optional. The common principles are canonical and shared;
the two discussion transports remain distinct. Switch a versioned path deliberately
after evaluating it. `roles.json` is the single source of the new role content;
`registry.instructions()` assembles shared, specialist and role instructions.
Generated prompt exports are inspection copies, not editable authorities.

## Recommended integration sequence

1. Run the standalone tests and synthetic CLI demo, then inspect the exact role
   definitions and the unresolved decisions in `HANDOVER.md`.
2. Map authenticated server identities and founder grants into trusted Python
   callers. Keep the new package internal; do not expose its caller/owner
   parameters as unauthenticated public API inputs.
3. Add an explicit versioned discussion job and pending/status/result interface.
   Record its approved question, consent revision, assignment fields, policy
   hashes, sources, results, issues and review state. Do not run 24 model calls
   synchronously inside the old Persy 60-second HTTP request.
4. Adapt reviewed public source retrieval to `Source`, preserving license,
   provenance and domain scopes. Enforce current source permissions and consent
   before dispatch and before accepting results, not merely in the prompts.
5. Adapt consented profile proposal/review behaviour to the existing encrypted,
   isolated Life Profile database. The new local SQLite store is a development
   reference, not a migration plan for private subscriber records.
6. Route business research and every specialist peer request through the Chief
   of Staff. Complete one bounded review; queue further research as a separate
   authorised task rather than recursively expanding discussion.
7. Add reviewed knowledge publication, correction/retraction propagation and
   opt-in research schedules. 12 receives only independently reviewed general
   findings after nonpersonal-data review. It has no arbitrary tools.
8. Add persistent, independently authenticated founder controls for 12, a founder
   report channel, cancellation signals and an operator-tested deletion policy.
   Status oversight does not grant coordinator assignment authority.
9. Connect approved event/market/geographic sources and optional notifications.
   Resolve bank, assessment and demonstration provider choices separately.
10. Evaluate the staged path with realistic questions and explicit human review.
    Compare failures, benefit, risk, latency and actual cost. Change routing only
    after passing those gates; retain rollback to the previous version.

## Existing conflicts that still need integration fixes

The earlier review's nine-specialist policy conflict is corrected. It also
identified mismatched Persy/coordinator timeouts and work
leases, coordinator run budgets versus specialist execution budgets, knowledge
API authorisation enforcement, unbounded profile context versus Persy's limit,
feedback database role permissions, contributor thresholds above snapshot sizes,
section limits labelled as source limits, and aggregate response size limits.
This new package avoids using those old paths for its local demo; it does not
claim to fix the old endpoints. They require explicit changes and regression
tests during service integration.

## Production constraints

- No deployment, merges, external messages, invitations or transactions are
  performed by importing or testing this package.
- Jobs need durable idempotency and retries with remaining-budget checks. The
  local reminder helper takes a previously delivered date; delivery systems must
  persist and atomically claim that key before sending. It is not a durable queue.
- The local SQL store uses explicit short write transactions for consent
  decisions and 12's result acceptance, with no network requests under those
  locks. Production multi-worker jobs, encryption, database isolation, durable
  cancellation and per-service credentials still need integration and evaluation.
- Profile excerpts must carry reviewed category/sensitivity metadata. Do not
  forward whole raw conversations and rely on output filtering after a model
  has received them. Treat this as an intentional input-contract change and
  authenticate the coordinator before constructing draft builders.
- A model can still make an unsupported paraphrase despite a matching source
  quote. Keep independent evidence and response review; structural checks are
  necessary but insufficient.
- Fast discussion may need a measured bounded concurrent dispatch adapter and
  lower per-role output budgets. No faster latency is promised by this build.
