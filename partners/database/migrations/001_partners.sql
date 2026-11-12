BEGIN;
CREATE TABLE partner_actors (
    subject text PRIMARY KEY CHECK (length(subject) BETWEEN 1 AND 200),
    role text NOT NULL CHECK (role IN ('founder','executive_administrator','administrator','service')),
    permissions text[] NOT NULL DEFAULT '{}',
    active boolean NOT NULL DEFAULT true,
    last_checked_at timestamptz
);
CREATE TABLE partner_businesses (
    id uuid PRIMARY KEY,
    identity_key text UNIQUE NOT NULL,
    document jsonb NOT NULL,
    revision bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE partner_policies (
    id uuid PRIMARY KEY,
    document jsonb NOT NULL,
    approved boolean NOT NULL DEFAULT false,
    approved_by text REFERENCES partner_actors(subject),
    approved_at timestamptz,
    last_checked_at timestamptz,
    CHECK (NOT approved OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE TABLE partner_evidence (
    id uuid PRIMARY KEY,
    business_id uuid NOT NULL REFERENCES partner_businesses(id),
    document jsonb NOT NULL,
    verified boolean NOT NULL DEFAULT false,
    active boolean NOT NULL DEFAULT true,
    reviewed_by text REFERENCES partner_actors(subject),
    CHECK (NOT verified OR reviewed_by IS NOT NULL)
);
CREATE INDEX ON partner_evidence(business_id);
CREATE TABLE partner_assessments (
    id uuid PRIMARY KEY,
    business_id uuid NOT NULL REFERENCES partner_businesses(id),
    policy_id uuid NOT NULL REFERENCES partner_policies(id),
    business_revision bigint NOT NULL,
    document jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE partner_contacts (
    business_id uuid PRIMARY KEY REFERENCES partner_businesses(id),
    email text NOT NULL,
    document jsonb NOT NULL,
    verified_by text NOT NULL REFERENCES partner_actors(subject),
    last_checked_at timestamptz,
    active boolean NOT NULL DEFAULT true
);
CREATE TABLE partner_suppressions (
    email text PRIMARY KEY,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE partner_outbox (
    id uuid PRIMARY KEY,
    business_id uuid NOT NULL UNIQUE REFERENCES partner_businesses(id),
    assessment_id uuid NOT NULL REFERENCES partner_assessments(id),
    recipient text NOT NULL UNIQUE,
    unsubscribe_hash text NOT NULL UNIQUE,
    unsubscribe_token text NOT NULL,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','dispatching','sent','blocked','unknown')),
    content jsonb,
    provider_id text,
    dispatch_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON partner_outbox(state,created_at);
CREATE TABLE partner_dispatch_nonces (
    request_id text PRIMARY KEY,
    subject text NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE TABLE partner_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject text NOT NULL,
    action text NOT NULL,
    reference text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
COMMIT;
