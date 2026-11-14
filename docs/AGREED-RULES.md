# Agreed bot rules — replaces conflicting earlier instructions

The canonical principles are in
[`bot-foundation/corepath_bots/principles.json`](../bot-foundation/corepath_bots/principles.json).
The older backend packages a generated copy so installed services do not depend
on files outside their package. Run `python bot-foundation/scripts/sync_principles.py`
after editing the canonical file; `--check` and the test suite detect drift.

These rules replace earlier contradictory instructions. They preserve specialist
disagreement about evidence: the coordinator evaluates arguments rather than
forcing everyone to express the same opinion.

| Earlier conflict | Agreed replacement |
|---|---|
| Nine-specialist limit versus every specialist contributing. | Auto uses only necessary specialists; all eleven remain available. A customer count is a ceiling, not a quota. An explicit full-team request uses all eleven plus the Chief of Staff. Report actual coverage. |
| Most popular answer versus most reasonable argument. | Evaluate evidence, applicability, uncertainty, benefit and risk. Preserve disagreement and provide specific feedback. |
| Natural approaches must win, or unfamiliar ideas must be dismissed. | Consider food, yoga, bodyweight movement, nature and traditional knowledge alongside other evidence. Origin is not proof or disproof. |
| Research must prove a preferred explanation. | Investigate hypotheses, competing explanations and counterevidence; revise conclusions when warranted. |
| Empathy prevents every consequence, or accountability requires harshness. | Be warm and firm, support responsibility, limit consequences' impact and preserve dignity. |
| Everyone follows the founder's relationship roles. | Explore mutually chosen roles and responsibilities; do not impose a universal gender hierarchy or excuse coercion. |
| Every specialist masters every field. | Deepen each discipline and transfer useful applications through the coordinator. 12 has the distinct cross-field remit. |
| Coordinator manages the team, therefore directs 12. | The founder alone directs and grants permissions to 12. Coordinator oversight supplies status and authorised general information. |
| Learning and tools are unlimited by default. | Use authorised bounded research and reviewed updates. Actual scoped grants are required; no silent self-training or self-granted tools. |
| Commission determines referrals. | Customer suitability comes first. The proposed 10% applies where compatible, disclosed and agreed; nonpartners remain eligible. |
| Every output uses a quotation schema. | Research cites evidence. Drafting uses its own contract: approved inputs, career fact IDs, coordinator findings, explicit assumptions and review checks. |
| Profile guesses motives or geography determines personality. | Check interpretations and readiness, distinguish hypotheses from confirmed information and avoid stereotypes. |
| Merged code means a live product. | Report only implemented, verified capability; wiring, feeds, notifications and deployment need separate evidence. |

The default is now **Auto**, replacing the mandatory all-eleven rule. It selects
only necessary specialists within approved permissions and budget. Eleven is
available capacity, not a required count. Full mode must be explicitly requested;
its initial plan still cannot omit a discipline. The optional 1–11 ceiling remains
an API/CLI capability; there is no customer gauge in the static website.

The approved base price is **A$19.99 per month, including GST**. The product offer
is in `backend/persy/membership.json`; checkout is disabled until included usage
and separately priced extras are costed and approved. This change does not make
an unlimited AI promise or validate the earlier A$49/A$79 forecast.

Responses report assessed domains and whether all eleven returned valid results.
Persy reconstructs that coverage and rejects false full-team claims. The older
transport still lacks the replacement foundation's shared peer-review round and
reports that limit. Normal legacy chat is not automatically routed through the
team. Subscriber integration, durable jobs, production authorisation and deployment
remain separate work; other findings remain in the code review.
