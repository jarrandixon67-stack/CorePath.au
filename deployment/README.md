# CorePath 20-member trial launch

Use only [`trial/20-member-allowlist-20261119`](https://github.com/jarrandixon67-stack/CorePath.au/tree/trial/20-member-allowlist-20261119). The existing draft PR tracks branch CI. Keep the trial closed until the hosting and model spend, deployment and domain change have explicit approval.

## Cost estimate in AUD

The Blueprint uses five single-instance Starter services in Singapore and three Basic 256 MB Postgres databases with 1 GB of storage each. Percy is the browser application. The Coordinator, specialist runtime, Life Profile and capability exchange use separate processes and HTTPS endpoints with signed capabilities or machine authentication. There is one specialist runtime for all eleven domains. PostgreSQL external access is disabled.

| Item | Monthly USD | Monthly AUD |
| --- | ---: | ---: |
| Five Starter services at US$7 each | $35.00 | A$54.25 |
| Three Postgres compute plans at US$6 each | $18.00 | A$27.90 |
| Three 1 GB Postgres disks at US$0.30/GB | $0.90 | A$1.40 |
| **Render subtotal** | **$53.90** | **A$83.55** |

The estimate uses an assumed US$1 = A$1.55. Check the Render workspace plan, taxes, currency rate, transfer, backups and pricing before approving the actual quote. At GPT‑4.1 mini list prices, an illustrative trial with 1,000 model calls averaging 4,000 uncached input tokens and 600 output tokens would use US$2.56 (about A$3.97) in model fees. That makes the illustrative total about A$88 before any additional charges. A research turn can contain several model calls. Model spend depends on usage, model and context length. Set a trial OpenAI project budget alert and monitor actual billing daily because OpenAI project budgets are alert thresholds. The app applies its own request limits.

[Render pricing](https://render.com/pricing) · [GPT‑4.1 mini pricing](https://developers.openai.com/api/docs/models/gpt-4.1-mini) · [OpenAI project budgets](https://help.openai.com/en/articles/9186755-managing-your-work-in-the-api-platform-with-projects)

## Launch sequence

1. Review the draft PR checks, confirm the roster and trial end date, and approve a Render resource plan and a model test budget. Use dedicated trial resources. Keep Blueprint auto-sync, automatic deployment and PR previews off. Hold the production domain change until the staging checks pass.
2. Create the three databases after approval. Apply migrations with the migration-owner connection from a trusted operator environment. Use `DATABASE_URL=<migration DSN> python -m app.migrations --directory <directory>` from `backend/` and rerun with `--check`. Apply `../database/migrations` to knowledge, `../persy/database/migrations` to conversations, and `../life-profile/database/migrations` to Life Profile. Apply the restricted role templates in `coordinator/database/`, `specialists/database/`, `persy/database/` and `life-profile/database/`. Create a distinct runtime login for each role and verify that it can connect only to its intended database with internal TLS required. Keep ownership, migration credentials, schema creation and login administration outside the app roles. If applying to a previously provisioned Percy role, apply migration 002 and grant that role only the new `EXECUTE` privilege from its template.
3. Populate the knowledge runtime with owner-approved, verified and model-use-approved excerpts in trial libraries. Activate only reviewed libraries. Run `psql -v ON_ERROR_STOP=1 -v trial_end='<agreed end timestamp>' -f deployment/trial-knowledge.sql` against the dedicated knowledge database as its operator. Review the grants and use an approved question for each of the eleven domains in the staging smoke test. Libraries without qualifying excerpts yield evidence gaps.
4. Generate three independent Ed25519 key pairs and separate Fernet encryption keys for conversations and Life Profile. Generate independent Percy and Coordinator machine credentials and one shared read-only metrics credential of at least 48 random characters. Wire the services as shown below. Start on a staging HTTPS origin and set `TRIAL_ORIGIN` to that exact origin with no trailing slash. Configure the reviewed model and server-only OpenAI project credentials per runtime. Set the metrics rate variables to the model's uncached input and output USD per million tokens in the form `0.40,1.60`. Never place credentials in Git or browser code.
5. Run `python deployment/invite.py` in a private terminal for each approved member, including the administrator. Build `TRIAL_ACCOUNTS` as one JSON object mapping the generated pseudonymous subjects to their verifiers. Set `EXCHANGE_ALLOWED_MEMBER_SUBJECTS` to the same comma-separated subjects, with a maximum of 20 and no duplicates. Set `TRIAL_ADMINISTRATOR` to the approved administrator subject. Share each invite privately and keep any roster mapping outside the deployment. Keep one Percy process and instance because sign-in sessions, rate windows and dashboard counters live in memory. A restart signs members out. Remove erased or withdrawn invitations from both secret values and redeploy the approved branch.
6. While staging, use synthetic accounts and messages to check sign-in, consent, one ordinary reply, the reviewed Percy → Coordinator → specialist → Percy flow, ambiguity, evidence gaps, all eleven routing cases, owner-only review/correction/erasure, limits, failure handling and the administrator dashboard. Confirm TLS, logs, key handling, database-role isolation and deletion against the operated environment. Inspect provider retention and backup policy before inviting volunteers. Database erasure leaves a payload-free revocation marker and does not erase historical backups or provider records on demand.
7. After approval to change public hosting, point the approved trial host at Percy, update `TRIAL_ORIGIN` and repeat the smoke checks. The current custom domain routing and any existing Sites pages need an explicit integration or cutover decision. Keep a DNS rollback path. At trial end, revoke invitations and provider keys, disable access and follow the approved data retention and infrastructure shutdown plan.

## Service wiring

| Item | Configuration |
| --- | --- |
| Member signing | Private key in `TRIAL_MEMBER_SIGNING_KEY` on Percy. Public key in `PERSY_GATEWAY_PUBLIC_KEY` and `EXCHANGE_MEMBER_PUBLIC_KEY`. |
| Research delegation | Private key in `EXCHANGE_SIGNING_PRIVATE_KEY`. Its public key goes to `PERSY_COORDINATOR_PUBLIC_KEY`, `COORDINATOR_GATEWAY_PUBLIC_KEY`, `COORDINATOR_SPECIALIST_PUBLIC_KEY` and `SPECIALISTS_GATEWAY_PUBLIC_KEY`. |
| Life Profile delegation | Private key in `EXCHANGE_PROFILE_SIGNING_PRIVATE_KEY`. Its public key goes to `PERSY_PROFILE_PUBLIC_KEY` and `LIFE_PROFILE_GATEWAY_PUBLIC_KEY`. |
| Exchange | `PERSY_EXCHANGE_URL` ends in `/exchange/percy`. `COORDINATOR_EXCHANGE_URL` ends in `/exchange/coordinator`. Pair the corresponding service token with `EXCHANGE_PERCY_MACHINE_TOKEN` or `EXCHANGE_COORDINATOR_MACHINE_TOKEN`. |
| Runtime origins | Set `PERSY_COORDINATOR_URL`, `PERSY_PROFILE_URL`, `COORDINATOR_SPECIALIST_URL` and `TRIAL_SPECIALIST_URL` to the appropriate fixed Render HTTPS origins. |
| Storage | Use a restricted runtime DSN and `sslmode=require`. Coordinator and specialists have separate roles in knowledge. Private data stores have separate credentials and encryption keys. |
| Monitoring | Set `TRIAL_METRICS_TOKEN` consistently across Percy, Coordinator, specialists and Life Profile. The administrator sees counts, failures, total milliseconds, token totals and estimated USD microunits. Metrics reset on restart. Render application logs carry aggregate events without member IDs, messages, credentials or exception bodies. |

## Verification boundary

The automated suite uses real disposable PostgreSQL databases and tests the signed HTTP contracts with synthetic evidence and model doubles. This verifies the application path and permission checks. Live model behaviour, actual provider billing, Render TLS and database setup, DNS, and staging log retention require operator verification. Jarmby is described in the project as a visual character. There is no approved operational design in this branch, so the trial does not offer Jarmby as an AI service.
