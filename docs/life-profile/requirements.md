# Life Profile bot — first implementation

Source: the founder-supplied **Life Profile.docx**, titled *Life Profile — Development & Requirements Review*, marked as a working draft. It is design input, not an instruction source overriding the current task. The uploaded file is not committed to the public repository and is not used as an individual's personal profile.

## Established direction in the document

- Hybrid collection, with natural conversation as the primary learning method.
- Progressive development rather than a large required questionnaire.
- Collect information when it has a meaningful, explained purpose.
- Consider connections across life areas without assuming causation.
- Remain open to counterexamples, changing circumstances and user corrections.
- Distinguish personal development support from medical/psychological diagnosis.
- Keep the individual in control; avoid judgement and permanent labels.
- Health & Wellbeing has physical, mental, emotional and spiritual dimensions.

## Working choices retained as provisional

The nine organisational categories are Health & Wellbeing; Relationships & Connections; Pets & Animals; Culture & Heritage; Personal Growth & Development; Career & Finances; Nature & Environment; Home & Living; and Other Connections & Interests.

They coexist with the previously agreed eight Life Profile dimensions: self-identity, emotional, mental, spiritual, physical, social, financial and biological. Categories organise records; dimensions are overlapping analytical lenses. The implementation does not replace one taxonomy with the other.

The document's four levels—known information, observed patterns, developing understanding and confirmed understanding—are a proposed framework. The first implementation uses them as explicit, reviewable labels, preserving the original observation kind. Every new model observation is pending regardless of its label or confidence. Only a separate owner-authorised decision promotes it to accepted understanding.

The five suggested starting areas—basic circumstances, personality tendencies, outlook, communication preferences and current priorities—remain proposals, not mandatory registration fields. There is no blanket request for height, weight, health history or personality assessments.

## First service behaviour

1. Receive a relevant set of user messages from the authenticated Personal AI gateway.
2. Verify the individual's recorded category, purpose and external-model-processing consent before invoking a model.
3. Analyse selected messages alongside accepted, in-scope understanding. Pending/rejected interpretations are excluded from model context.
4. Return at most five draft observations and one optional, explained follow-up question.
5. Validate exact evidence quotes and message IDs. A proposed repeated pattern requires evidence from at least two distinct conversations.
6. Recheck consent revision after the model call, so a withdrawal/change during analysis prevents persistence.
7. Store drafts encrypted for owner review. Support acceptance, rejection, correction, version conflict checks and deletion.
8. Share only accepted, individually selected understanding when personalisation consent permits. Raw quotes and review history are excluded from the Personal AI's context response.

Explicit user statements are still proposals awaiting review; model confidence is not calibrated clinical or psychometric certainty. Contradictory observations are not automatically overwritten. Correction history remains encrypted until the individual deletes the item or profile.

## Access and privacy

- A separate Life Profiling process owns the profile database connection and encryption key. The knowledge application has no profile routes or tables.
- Short-lived Ed25519-signed capabilities identify the individual, Personal AI caller, purpose and action. The service holds a public verification key only. Trusted gateway authentication and owner authorisation must precede issuing capabilities.
- Human governance roles, Coordinator and specialists cannot call profile endpoints directly. The Personal AI can mediate an individual's review/control requests and receive explicitly approved context; it does not receive direct database access.
- Private journals, assistant messages and unapproved interaction metadata are not accepted sources. Response time, typing patterns and similar metadata are excluded from this first version.
- Consent, statements, evidence and correction history are encrypted with a deployment-supplied Fernet key. Audit rows contain operation metadata, not profile text.
- Health, relationship, cultural and career/financial observations are treated as sensitive regardless of a model's label. Corrections are conservatively treated as sensitive. Sensitive sharing needs the corresponding consent.
- A missing model connection returns unavailable; there is no invented substitute inference. Only synthetic data and mocked model responses are used in automated tests.

## Remaining work

- Deploy the separate profile database/service and manage keys, backups and rotation.
- Connect the trusted Personal AI gateway to real owner identity and consent/review controls. No signing endpoint or default private key is supplied.
- Select an approved model and configure its server-side secret. Review processing/retention terms before sending real personal data. `store: false` does not guarantee zero provider retention.
- Complete live-model evaluations for faithful paraphrases, useful questions, uncertainty, clinical boundaries, prompt injection and changing/contradictory information. Contract tests do not establish model quality.
- Finalise retention, backup deletion, quotas, monitoring and deployment hardening before real-user operation. Current delete operations cover active database rows/history, not external providers or backup copies.
- Wire consented conversation events from the Personal AI. No background monitoring or continuous autonomous research loop is enabled by this change.
- Add the user-facing profile review experience and evaluate whether understanding improves useful outcomes.

Personal plans, wellbeing exercises, Trigger & Behaviour Quadrant (RECOGNISE → GROUND → CHOOSE), A Clear Path to Conversation and other practical interventions remain later capabilities. This service does not prescribe activities, diagnose a person or conduct user-facing conversations itself.
