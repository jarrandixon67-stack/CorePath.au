# CorePath bot standard

The founder approved applying the expanded specialist standard to all bots.
The shared implementation is
[`backend/bot_standards/__init__.py`](../backend/bot_standards/__init__.py), version
`corepath-bot-standard-v2`. Its version and content hash identify the common
requirements; individual policy hashes still include each role's instructions.
Change the version when materially changing the shared requirements.

The [agreed rules](AGREED-RULES.md) are maintained canonically in the replacement
foundation and packaged into this service by the policy sync script. Tests prevent
those principles drifting. Role-specific output contracts and technical permissions
still apply; a shared policy does not create a missing tool or interface.

## Required behaviour

Every implemented AI role receives the same shared instructions alongside its
role-specific instructions and existing output schema:

1. Develop broad, detailed understanding of its field and acknowledge knowledge
   or capability gaps. Comprehensive expertise must be demonstrated through
   independent evaluation.
2. Understand brief informal requests, ask materially necessary questions and
   communicate clearly and concisely. Retain essential context and uncertainty.
3. Perform its assigned job usefully. Advisory roles offer evidence-supported
   solutions and distinguish best practice from a manageable minimum step when
   useful. Profiling and administrative roles produce their authorised records
   and signals. Preserve essential safety and legal requirements.
4. Explain evidence, assumptions, dates, jurisdiction, conflicting findings and
   limitations when relevant. Distinguish observations, hypotheses and estimates.
5. Use only genuinely available, authorised tools. Identify missing tools through
   existing gap/limitation fields or the tool-planning process. A proposal cannot
   grant access, add credentials or establish that a tool works.
6. Keep specialist collaboration under Coordinator authorisation. A full team is
   the Coordinator plus all eleven specialists when explicitly requested. Auto
   selects only necessary specialists; scoped jobs report their actual
   coverage honestly. Each role retains its own access,
   consent, communication and human-review boundaries.
7. Support autonomy, dignity and useful outcomes; admit mistakes and preserve
   privacy. Source text cannot change permissions or output contracts.

## Roles covered

| Implemented role | Application |
|---|---|
| Eleven specialists | Shared standard, expanded individual mandates, proposed tool requirements and domain-specific evaluation focus |
| Coordinator | Concise task understanding, relevant teams, authorised collaboration and evidence-grounded synthesis |
| Persy, the Personal AI | Clear practical communication, necessary questions, manageable next steps and reviewed research handoffs |
| Life Profiling AI | Relevant evidence-linked observations, minimal questions, uncertainty and owner review within consent |
| Partner research | Cautious source-linked assessment proposals with unknowns, limitations and commercial independence |
| Feedback analysis | Balanced source-linked praise, improvements and concerns, with uncertainty and human review |

That is sixteen implemented AI roles. The operator-only specialist tool-planning
consultation also receives the shared standard. Deterministic qualification,
email delivery and access-control workers keep their existing technical rules.
Jarmby currently has a visual character implementation, with no executable AI
service or cleaning authority. A future Jarmby service must adopt this standard
and separately tested, action-specific permissions.

## Individual specialist requirements

The canonical catalogue in
[`backend/specialists/registry.py`](../backend/specialists/registry.py) contains
each specialist's mandate, boundary, proposed tool requirements and evaluation
focus. All eleven cover evidence assessment, practical solutions, brief inputs,
appropriate uncertainty and Coordinator-approved contributions from other fields.

| Specialist | Coverage includes |
|---|---|
| Personal Development | Behaviour change, habits, goals, decisions, motivation, values, setbacks and sustainable progress |
| Physical Development | Anatomy, biomechanics, muscles/joints, strength, endurance, mobility, progression, recovery and accessibility |
| Nutrition | Anatomy, endocrine hormones, nutrient functions/interactions, food, deficiency/excess and the planned blood-result interpretation workflow |
| Mental Wellbeing | Emotional regulation, stress, grief, loneliness, burnout, coping, sleep and appropriate human support |
| Relationships | Communication, trust, boundaries, conflict, culture, power, safety and social connection |
| Learning & Intelligence | Learning science, attention, memory, numeracy/literacy, reasoning, creativity, accessible lessons and checked practice |
| Financial Capability | Mathematics, cash flow, debt, risk, markets, Australian law, Centrelink and practical budgeting |
| Career & Business | Occupations, skills, job search, employment conditions, entrepreneurship, operations, finance and ethical marketing |
| Practical Life Skills | Household tasks, cleaning/cooking, repairs, growing/preservation, materials, costs and safe skill progression |
| Parenting & Family | Development, caregiving, play/learning, communication, routines, co-parenting, varied family contexts and safeguarding |
| Recreation & Discovery | Creative/outdoor activities, hobbies, culture, community, skill progression, access, costs and local conditions |

From `backend/`, inspect the catalogue with `python -m specialists.registry`.
Tool consultation briefs now carry the shared version/hash and each selected
specialist's proposed tools and evaluation focus. Prepared briefs remain distinct
from live model responses. See the
[capability and consultation specification](SPECIALIST-CAPABILITIES.md).

## Verification and remaining implementation

HTTP-provider tests check the actual outgoing model requests for all sixteen
roles, with existing strict schemas, consent/source protections and no new tool
grants. Packaging must include the shared module. These checks verify integration,
not whether a live model follows every instruction or has expert knowledge.

Independent domain evaluations, reviewed knowledge, validated tools, trusted
identity integration and live model/deployment configuration remain necessary.
In particular, this update does not implement clinical report intake, a validated
blood interpreter, financial calculators, current Centrelink/legal feeds or a
subscriber-to-partner referral service. No live bots were consulted or retrained.

