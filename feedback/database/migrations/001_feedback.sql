BEGIN;
CREATE TABLE feedback_actors (
    subject text PRIMARY KEY,
    role text NOT NULL CHECK(role IN ('member','founder','executive_administrator','administrator','service')),
    permissions text[] NOT NULL DEFAULT '{}',
    active boolean NOT NULL DEFAULT true,
    last_checked_at timestamptz
);
CREATE TABLE feedback_targets (
    target text PRIMARY KEY,
    kind text NOT NULL CHECK(kind IN ('corepath','business')),
    active boolean NOT NULL DEFAULT true
);
INSERT INTO feedback_targets(target,kind) VALUES ('corepath','corepath');
CREATE TABLE feedback_preferences (
    owner_key text PRIMARY KEY,
    allow_requests boolean NOT NULL DEFAULT true,
    last_any_prompt_at timestamptz
);
CREATE TABLE feedback_prompts (
    owner_key text NOT NULL,
    target text NOT NULL REFERENCES feedback_targets(target),
    last_prompt_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(owner_key,target)
);
CREATE TABLE feedback_records (
    id uuid PRIMARY KEY,
    target text NOT NULL REFERENCES feedback_targets(target),
    owner_key text NOT NULL,
    source_key text NOT NULL UNIQUE,
    source_kind text NOT NULL CHECK(source_kind IN ('member','public_review')),
    payload bytea,
    ai_allowed boolean NOT NULL DEFAULT false,
    active boolean NOT NULL DEFAULT true,
    version bigint NOT NULL DEFAULT 1,
    reported_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON feedback_records(target,created_at);
CREATE VIEW feedback_analysis_sources AS
    SELECT id,target,owner_key,source_kind,payload,version,reported_at,created_at
    FROM feedback_records WHERE active AND ai_allowed AND payload IS NOT NULL;
CREATE TABLE feedback_themes (
    id uuid PRIMARY KEY,
    target text NOT NULL REFERENCES feedback_targets(target),
    fingerprint text NOT NULL UNIQUE,
    kind text NOT NULL CHECK(kind IN ('praise','improvement','concern')),
    severity text NOT NULL CHECK(severity IN ('ordinary','urgent')),
    contributor_count int NOT NULL,
    source_ids uuid[] NOT NULL,
    payload bytea,
    state text NOT NULL DEFAULT 'open' CHECK(state IN ('open','acknowledged','investigating','resolved','dismissed','retracted')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE feedback_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_key text NOT NULL,
    action text NOT NULL,
    reference text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
COMMIT;
