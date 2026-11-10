# CorePath — platform overview and AI build brief

This is a structured implementation summary of the founder's supplied Platform Overview & AI Handover Document. It preserves the stated direction and separates requirements, proposals, ambitions and verified implementation. Use [HANDOVER.md](HANDOVER.md) and exact commit/CI results for current technical state.

## 1. Purpose

CorePath is a global life-optimisation platform helping individuals understand themselves, make informed decisions and improve their lives through knowledge, personal understanding, practical application and technology.

Information creates understanding; understanding creates opportunity; opportunity creates change; change comes through action. The objective is increasing people's capability to understand and manage their own lives. Measure success through meaningful improvements in life, rather than platform engagement or revenue alone.

The intended platform connects personal development, knowledge, research, specialist expertise, real-world opportunities and AI. The existing six-component product direction remains: Life Profile, AI personal support, social/community, events/experiences, business/professional referrals, and education/development.

## 2. The 22 foundational principles

### Fundamental principles

1. Joy and enjoyment.
2. Holistic integration.
3. Understanding before advising.
4. Autonomy and ownership.
5. Progress without punishment.
6. Practical application.

### Personalisation and empowerment

7. Personal relevance.
8. Empowerment over dependency.

### Experience and engagement

9. Make the process rewarding.
10. Balance familiarity and discovery.
11. Positive social connection.
12. Celebrate small wins.

### Content and guidance

13. Evidence and open-mindedness.
14. Invitational spirituality.
15. Structure and freedom.

### Safety and sustainability

16. Prevent burnout.
17. Financial empowerment.
18. Mental health boundaries.
19. Privacy and respect.

### Measurement and improvement

20. Measure meaningful outcomes.
21. Remove unnecessary friction.
22. Evolve with the individual.

Every significant decision must answer: **Does this make CorePath better at helping people understand, improve and manage their lives?**

## 3. Connected life dimensions

Recognise personal identity/development, emotional wellbeing, mental development, spirituality/purpose, physical capability, relationships, financial independence, biological characteristics, learning, practical skills and other relevant life dimensions. The final presentation and taxonomy may evolve.

Recognise useful relationships between dimensions without forcing unrelated matters together. For example, physical health can influence emotional wellbeing and financial circumstances can influence relationships.

## 4. Life Profile

The eight Life Profile dimensions are self-identity, emotional, mental, spiritual, physical, social, financial and biological. They are interconnected and may also be analysed separately.

Develop a comprehensive, evolving understanding through meaningful information and as few unnecessary questions as possible. Use hybrid collection, progressive development, natural conversations, reflective questions, behavioural/communication observations, contextual information and ongoing refinement. Do not rely exclusively on questionnaires.

With explicit consent, communication analysis may consider written language, vocabulary, sentence construction, explanations, questions, certainty/uncertainty, response times, typing/editing patterns and voice/speech characteristics. Response speed or typing behaviour alone cannot establish personality, intelligence or psychological characteristics.

Observations are hypotheses with context and varying confidence, not permanent labels. Understand the individual rather than categorise them. Consent, correction and privacy controls must be implemented before collecting sensitive interaction data.

## 5. AI architecture and access boundaries

The intended network has eleven specialist AIs, a Coordinator AI, a Personal AI and a dedicated Life Profiling AI.

| System | Responsibilities and access |
|---|---|
| Personal AI | The only user-facing AI; understands requests, maintains continuity, communicates with the Coordinator and Life Profiling AI, and translates understanding into practical action. |
| Life Profiling AI | The only AI with direct Life Profile access; develops the profile, maintains observations and obtains information through the Personal AI. |
| Coordinator AI | Coordinates specialists, allocates research, compares evidence, identifies contradictions and consolidates findings. Privy to Personal AI–Life Profiling AI conversations unless explicitly excluded, without unrestricted direct Life Profile access. |
| Specialist AI | Independent research and knowledge development within authorised disciplines; evidence assessment, emerging research, unanswered questions and practical recommendations. Peer collaboration requires explicit Coordinator authorisation. |
| Executives and administrators | Specifically delegated platform permissions; organisational authority does not automatically provide access to private profiles or conversations. |

Enforce these boundaries through technical permissions. Model instructions alone are insufficient. Human governance cannot become an alternative specialist-dispatch channel.

## 6. Specialist knowledge and the Intelligence Centre

Libraries may investigate books, scientific/academic research, professional literature, historical and practical knowledge, traditional knowledge, emerging research and independent investigations. Sources and findings must retain provenance.

Investigate independently and examine conflicting evidence. Give serious consideration to natural approaches, nutrition, naturopathy, physical capability, traditional practices and hunter-gatherer perspectives as starting points for investigation, not predetermined conclusions. Keep evidence quality, uncertainty, limitations and safety visible. Do not treat institutional status or natural/traditional origin as proof.

Global research should recognise different jurisdictions. Recommendations implemented locally must meet applicable legal and safety requirements.

The Intelligence Centre will manage eleven specialist libraries, sources, categories, verification, research records, knowledge development and eventual researcher contributions. Make source details, categories and verification status easy to inspect. Registered metadata is not the same as a verified claim.

## 7. Human access governance

The hierarchy is Founder, Executive Administrator, administrators and specialist researchers.

- Founder retains ownership and reserved authority.
- Executive Administrator is an unassigned second-in-command role with broad delegated authority. It cannot remove/replace the Founder, transfer ownership, change reserved Founder powers or appoint/remove another Executive Administrator.
- Administrators receive explicit delegated operational permissions.
- Researchers contribute within assigned libraries. Verification, publication and administrative powers are not automatic.

Information access and authority to change information are separate permissions. Life Profiles do not automatically become available to administrators/researchers. Privileged activity must be auditable.

## 8. Commercial direction

Build a sustainable global platform through appropriate partnerships, specialist services, referrals, knowledge/education and additional products/services that provide genuine value. Do not silently discard existing membership decisions merely because this summary does not repeat their pricing.

The approved Global Business Partner Programme direction includes a fixed commission model, global recruitment, outbound invitations and inbound applications, a standard partner agreement, automated invitations/follow-up, and quality/verification requirements. **10% is the proposed commission**, not a claim that a partner agreement is already implemented.

Businesses must meet CorePath standards before recommendation. Do not lower standards because suitable providers are unavailable. Commercial relationships must not compromise independent recommendations or privacy commitments. This brief does not authorise sending invitations or messages to businesses during development.

Let users report unmet demand for suitable products/services. Aggregated demand can identify unmet needs, underserved communities, new services, business and investment opportunities. Individuals retain control of their private profiles; CorePath will not sell Life Profiles or breach privacy commitments for revenue.

## 9. Global opportunities

Over time, city/regional profiles could describe needs, available services, supply gaps, community/environmental circumstances, education and health/wellbeing resources. The purpose is connecting people with suitable opportunities. These capabilities are planned, not deployed.

## 10. Humanity and technology

Human strengths include creativity, imagination, intuition, empathy, lived experience, physical capability, values and purpose. Technology contributes information processing, pattern recognition, research, analysis, memory/organisation, automation and complex problem-solving.

**Complementary Potential is a proposed principle:** humanity and technology can develop alongside one another, using different strengths to expand understanding, capability and opportunity. Increase human capability rather than dependency. Help people understand, use and direct technology.

Trust in AI must be earned through demonstrated behaviour, transparency, evidence and accountability. Do not manufacture emotional dependency or discourage independent thinking.

## 11. Long-term ambition

The 100-year perspective is an ambition, not a guaranteed outcome. Evolve towards infrastructure supporting individual development, understanding, research, learning, health/wellbeing, communities, business opportunities, technological collaboration and human independence.

Measure how capable people become through CorePath, rather than their dependency on it. Help humanity better understand itself, manage its affairs and improve the world around it.

## 12. Current technical direction

Continue the existing [CorePath.au repository](https://github.com/jarrandixon67-stack/CorePath.au). The supplied handover identifies `feature/knowledge-infrastructure-foundation` as the development branch. Inspection verified a permissions foundation and migration 006 there that were not in the cleaned main-branch baseline; the continuation reconciles them rather than redeveloping or overwriting them.

The foundation contains FastAPI, PostgreSQL migrations, eleven domain/library seeds, sources, categories, verification fields, principals/roles, Executive Administrator boundaries, an action-permission policy foundation and automated tests. A policy engine alone is not a complete authentication/authorisation service.

The supplied priority sequence is:

1. Stabilise automated testing.
2. Complete the permissions engine.
3. Implement trusted identity authentication.
4. Load roles and permissions from PostgreSQL.
5. Enforce permissions on every protected API endpoint.
6. Build secure account and invitation management.
7. Connect the Intelligence Centre to live records.
8. Develop ingestion and retrieval.
9. Develop specialist research workflows.
10. Implement Coordinator-authorised collaboration.
11. Progress towards the complete eleven-specialist architecture and wider platform.

Security, privacy, integrity and operations must be established before a production platform launch. A private Founder portal does not by itself establish a live knowledge backend or grant its database roles.

## 13. Development expectations

No shortcuts, superficial completion, unnecessary architectural limitations, untested assumptions, lost decisions, compromised privacy/security, unnecessary complexity or premature launch. Assess significant features for function, scalability, security, maintainability, interoperability, adaptability and benefit. Test milestones and record decisions. Improve designs without uncontrolled architectural change.

## 14. How an AI should continue

Understand the existing project before proposing changes. Preserve decisions unless a compelling reason warrants challenge; separate approvals from proposals. Challenge assumptions respectfully, investigate independently, explain clearly and consider wider consequences. Avoid repetitive redevelopment and translate ideas into implementation.

Inspect GitHub before editing. Never assume a proposal is implemented or claim tests passed without checking actual results. Ask when material information is missing; do not invent decisions, credentials or deployment status.

## 15. Guiding statements

Make people want to improve their lives, rather than feel obligated. Help them understand themselves and the whole person. Encourage progress over perfection. Build capability over dependency. Measure meaningful life improvements, not time spent in the platform.

CorePath exists to turn information into understanding, understanding into informed decisions, and decisions into consistent action that improves lives. Its long-term ambition is complementary human and technological development.

**Different strengths. One purpose. Humanity and technology advancing together.**
