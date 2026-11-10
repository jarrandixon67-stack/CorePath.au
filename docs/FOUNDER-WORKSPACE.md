# Private Founder workspace

The initial owner-private portal is deployed at:

https://corepath-founder.inquisitiveblade1.chatgpt.site

Use the same ChatGPT account as the project owner. Sites manages sign-in and its owner-only access policy; CorePath does not store a separate password. The current audience contains the owner alone, with no groups or invited visitors.

## What is available

- Sign-in-protected Founder overview, Intelligence Centre library areas, platform/AI architecture, all 22 principles, roadmap and governance view.
- Server-derived identity and sign-out.
- Explicit status showing that live knowledge records and PostgreSQL roles are not connected.

## What this does not establish

This portal does not provision a Founder principal in PostgreSQL, expose the temporary internal bearer token, enable account invitations, or make AI specialists operational. It contains no source-registration write endpoint and no fabricated live database counts.

The FastAPI/PostgreSQL application remains the intended knowledge backend. The next integration must verify identity, load grants from PostgreSQL and enforce its policy on every protected operation before allowing the portal to manage live knowledge records.

## Deployment and maintenance

- Sites project: `appgprj_6af3553b47ec81919b02f77f84e799ed`.
- Initial portal source commit: `78ad51f174d466b257ec4531d93ea8ac2c751b35` in the Site's managed source repository.
- Initial deployment: `appgdep_6af356929ec08191adb2e95dc3d38a31`, verified successful by Sites.
- The Site has a separate source repository; the knowledge backend stays in this GitHub repository.
- Keep the portal owner-private. Explicit server-side memberships must precede any expansion of the audience. The portal's Founder label represents private workspace access, not a database role grant.
- Fourteen local request/response tests passed, including missing identity, escaping, security headers and rejecting write methods. Hosted browser sign-in was not exercised by an agent because browser-control tools were unavailable; the owner must complete the actual sign-in.

See [HANDOVER.md](HANDOVER.md) for the continuing backend build.
