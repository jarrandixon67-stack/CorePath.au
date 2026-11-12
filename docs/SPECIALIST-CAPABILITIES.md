# Specialist capability and tool requirements

Status: founder-requested direction, development specification and first tooling
milestone. This document does not certify comprehensive expertise, clinical
accuracy, financial competence or live deployment. A larger prompt is not an
expert qualification.

The founder subsequently approved applying this standard to all bots. The
[shared bot standard](BOT-STANDARD.md) now covers all sixteen implemented AI
roles. Every specialist has an expanded mandate, explicit proposed tool
requirements and domain-specific evaluation focus in the canonical catalogue.
Role-specific permissions and output contracts remain in force.

## Agreed direction

- Understand brief, informal descriptions and ask only materially necessary
  questions. Sparse wording is not permission to invent circumstances.
- Give useful solutions with concise explanations, evidence, uncertainty and
  practical next steps. Offer more detail when the individual wants it.
- Distinguish evidence-supported best practice from a smallest useful action
  when appropriate. State trade-offs; retain essential safety and legal steps.
- Collaborate through the Coordinator when another discipline would help.
  Interpret the requested maximum as **ten bots total: the Coordinator and up
  to nine distinct specialists**, including the initial specialist. All eleven
  disciplines remain available for selection. Persy presents the result outside
  that internal research team. Do not assemble a large team for a simple issue.
- Ask each specialist which tools it needs. Its answer is a proposed development
  requirement, not a grant of access or evidence that the tool works.

The current Coordinator supports an initial team and one authorised follow-up
round with unused requested disciplines. It does not implement an unrestricted
multi-round conversation. The existing member-reviewed general-research question,
domain permissions, replay checks and quotas still apply. Shared discussions do
not give any specialist access to another library or the Life Profile.

## Nutrition: required coverage

The founder wants broad, detailed knowledge of anatomy, every major body system,
organs, muscles, hormones, nutrient functions and how nutritional requirements
change with life stage, activity, diet, medicines and relevant conditions. Build
an explicit coverage map and test it; do not claim to know every issue already.

Map nutrients to supported physiological functions, metabolic pathways and
interactions, including deficiency, excess, contraindications and evidence
limitations. There is no assumed unique nutrient prescription for every hormone,
muscle or body part. Natural, traditional and conventional approaches all receive
serious, critical consideration; origin alone establishes neither merit nor harm.

Blood-result interpretation is a requested personalised capability, within
reason. It must be able to explain what an actual report supports and offer
appropriate practical steps, rather than defaulting to a generic refusal.

The planned workflow must:

1. Obtain purpose-specific consent and extract only necessary report information.
   Keep raw health reports outside shared knowledge libraries. Show extracted
   values for correction before interpretation; abstain on unreadable values.
2. Preserve test name, specimen/collection date, value, units, the reporting
   laboratory's reference intervals and flags. Record methodology when relevant.
   Ask for missing intervals/context that could materially change interpretation.
   Do not silently substitute a universal range or assume an absent result.
3. Consider relevant context such as symptoms, age/life stage, medicines,
   supplements, fasting and related results when necessary. Distinguish source
   evidence from user-provided context; never invent either.
4. Clearly distinguish a result that supports a deficiency, one suggesting a
   possible deficiency, an alternative explanation, and a question the report
   cannot answer. A normal marker does not establish every tissue is adequately
   supplied; an abnormal result can have several causes. Do not equate hormone
   changes with a nutrient deficiency without supporting evidence.
5. Give proportionate dietary options, relevant follow-up and suitable clinical
   support. Personal supplement doses, medical diets, treatment changes and
   urgent-result escalation need separately validated clinical scope and review.
   Never use a model-invented critical threshold or advise stopping medication.
6. Preserve report provenance, extraction corrections, rule/source versions,
   uncertainty and access audit records. Test unit conversions, contradictory
   results, missing context, falsely reassuring normal results and urgent cases.

This intake and clinical workflow is **not implemented** by the current
general-research endpoint. Expanding its mandate does not authorise sending
identifiable blood reports through that endpoint.

## Financial Capability: required coverage

The founder wants strong mathematical reasoning, financial law, markets, debt,
budgeting and practical household planning, including people receiving Centrelink.
Start with Australia while keeping jurisdiction explicit.

- Use deterministic decimal calculations for cash flow, interest, fees and
  comparisons, with checked units, rounding, payment frequency and assumptions.
  Distinguish a calendar-month average from the cash available in a particular
  fortnight. Variable or uncertain income needs scenarios, not invented certainty.
- Build a useful budget from income and essential expenses, accommodate benefit
  payment dates, rent, debts, irregular bills, concessions and changing earnings.
  Avoid shame and assumptions that someone has money available to invest.
- Retrieve dated official information from Services Australia, legislation,
  ATO, ASIC/Moneysmart and relevant regulators. Applicable payment type, income
  tests, assets, household circumstances, reporting rules and effective dates
  matter. Never present an eligibility estimate as an official entitlement.
- Use appropriately licensed market data with timestamps, currency, delay and
  corporate-action context. Distinguish historical prices from current quotes.
- Explain options, costs, conflicts and risk. Personalised regulated investment,
  legal or tax recommendations need the applicable licensed scope and handoff.
  The ability to calculate and budget does not authorise trades, payments,
  account access, Centrelink submissions or disclosure of private finances.

The current research service has no connected calculator, benefits rules engine,
live legal retrieval or market-data feed. Individual financial-data intake and
validated budgeting tools remain to be built.

## Initial tool proposals

These are the developer's provisional proposals, **not answers from live bots**.
The consultation command below gathers separate model responses when configured.

| Specialist | Initial proposed tools |
|---|---|
| All eleven | Own-library evidence retrieval; source dates/provenance and conflicting evidence; versioned evaluation cases; Coordinator-scoped peer requests |
| Personal Development | Owner-controlled goal/action planning and outcome reflection; habit evidence with limitations |
| Physical Development | Anatomy/movement reference, exercise progression planning, contraindication and scope checks |
| Nutrition | Licensed anatomy/physiology and nutrient references; food-composition data; nutrient/medicine interaction evidence; consented document extraction with correction; validated lab/unit/range checks and clinical escalation |
| Mental Wellbeing | Reviewed coping resources; current location-appropriate human support directory; validated urgent-support routing |
| Relationships | Reviewed communication/conflict frameworks; private scenario reflection with minimal data and safety handoffs |
| Learning & Intelligence | Learning plans, accessible practice generation and checked explanations; no inferred intelligence scores |
| Financial Capability | Decimal calculator; fortnightly cash-flow planner; effective-dated official Australian benefits/legal retrieval; scenario-based Centrelink estimator; licensed market-data feed |
| Career & Business | Current occupation/skills references, user-approved CV analysis and business cash-flow/scenario tools |
| Practical Life Skills | Reviewed step-by-step skill references, materials/cost calculator and hazard/trade-scope checks |
| Parenting & Family | Age/context-appropriate development references, reviewed resources and safeguarding handoffs |
| Recreation & Discovery | Current accessible activity, weather and location information from permitted sources; availability timestamps |

Every proposed integration needs its purpose, minimum necessary data, source
rights, retention, access scopes, cost/rate limits, failure behaviour and an
independent validation plan. Tools receive action-specific technical permissions;
a model request cannot add credentials, read profiles or execute a transaction.

## Ask the specialists what they need

From `backend/`, prepare briefs without provider calls:

```bash
python -m specialists.tool_needs --output /tmp/corepath-tool-briefs.json
```

Once specialist model(s) and credentials are configured through the secret
manager, consult Nutrition and Finance first:

```bash
python -m specialists.tool_needs --live --domain nutrition --domain financial-capability --output /tmp/corepath-tool-responses.json
```

Omit `--domain` to consult all eleven individually. The explicit `--live` option
makes one provider request per selected discipline, at most eleven, with no
automatic retry. This is an operator planning command, not a member-facing
endpoint or a team research run. It sends fixed requirements and discipline
briefs only; never add member health/financial records, profile facts or secrets.

Reports distinguish prepared briefs, received model responses and failures;
include model/brief/policy identifiers; and always mark access ungranted,
expertise unverified and responses review-required. Existing output files are
never overwritten. The consultation itself cannot call proposed tools, grant
permissions, publish findings or certify its own expertise.

## Evidence required before claiming expertise

Create a field coverage matrix and independently written held-out cases reviewed
by qualified subject experts. Compare the configured specialist against a general
model using the same cases and conditions. Score accuracy, practical usefulness,
source support, relevant clarifying questions, concise communication, uncertainty,
unsafe omissions and appropriate escalation. Set release thresholds with reviewers
before measuring; record model, prompt, tool, source and rule versions.

Nutrition cases must cover physiology, interactions, genuine and misleading
deficiency patterns, extraction errors and unit/reference-range variation.
Finance cases must cover independently checked arithmetic, payment timing,
changing official rules, different benefits/circumstances and missing inputs.
Include peer disagreements, ten-bot cap enforcement and permission attacks.
Repeat relevant evaluations after material changes. Engineering tests and a
specialist's own assessment do not establish subject-matter competence.

## Subscriber referrals: approved direction, implementation pending

Persy understands the subscriber's goal, location, budget and preferences. The
Life Profiling AI may provide only relevant owner-approved understanding; the
profile itself stays private. When useful, the Coordinator asks relevant
specialists to define suitable service criteria. A separate matching service
then checks active contracted partners for scope, quality, location, price,
accessibility and availability.

Persy explains the shortlist and uncertainties and discloses commission before
the subscriber chooses. Any introduction shares only the specific data the
subscriber reviewed and consented to send. Feedback can identify praise and
concerns for review. Qualification alone is neither an active partnership nor
individual suitability. Commercial gain must not determine suitability; if no
suitable partner exists, explain that and help find alternatives without lowering
standards. Recruitment and feedback services do not yet implement this matching,
subscriber consent or introduction-tracking workflow.
