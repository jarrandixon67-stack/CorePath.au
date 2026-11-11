-- PRIVATE Persy database. Never apply to the knowledge or Life Profile database.
BEGIN;
CREATE TABLE persy_members (
    owner_key CHAR(64) PRIMARY KEY CHECK (owner_key ~ '^[a-f0-9]{64}$'),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    model_processing_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    history_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    profile_context_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    communication_style TEXT NOT NULL DEFAULT 'plain' CHECK (communication_style IN ('plain', 'balanced', 'detailed')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE persy_nonces (
    owner_key CHAR(64) NOT NULL,
    request_id TEXT NOT NULL CHECK (length(request_id) BETWEEN 1 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_key, request_id)
);
CREATE TABLE persy_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_key CHAR(64) NOT NULL REFERENCES persy_members(owner_key) ON DELETE RESTRICT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX persy_conversations_owner_idx ON persy_conversations(owner_key);
CREATE TABLE persy_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_key CHAR(64) NOT NULL REFERENCES persy_members(owner_key) ON DELETE RESTRICT,
    conversation_id UUID REFERENCES persy_conversations(id) ON DELETE SET NULL,
    request_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('chat', 'research', 'profile_analysis', 'profile_control')),
    privacy_revision INTEGER NOT NULL,
    conversation_revision INTEGER,
    state TEXT NOT NULL DEFAULT 'running' CHECK (state IN ('running', 'completed', 'failed')),
    payload_ciphertext BYTEA,
    policy_hash CHAR(64) NOT NULL,
    model_id TEXT,
    error_code TEXT,
    lease_expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (owner_key, request_id),
    CHECK ((state = 'running') = (completed_at IS NULL))
);
CREATE INDEX persy_operations_budget_idx ON persy_operations(owner_key, created_at);
CREATE UNIQUE INDEX persy_conversation_busy_idx ON persy_operations(conversation_id)
    WHERE state = 'running' AND kind IN ('chat', 'research');
CREATE TABLE persy_research_proposals (
    id UUID PRIMARY KEY,
    owner_key CHAR(64) NOT NULL REFERENCES persy_members(owner_key) ON DELETE RESTRICT,
    conversation_id UUID NOT NULL REFERENCES persy_conversations(id) ON DELETE CASCADE,
    privacy_revision INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    payload_ciphertext BYTEA,
    expires_at TIMESTAMPTZ NOT NULL,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (state NOT IN ('pending', 'running') OR payload_ciphertext IS NOT NULL)
);
ALTER TABLE persy_operations ADD COLUMN proposal_id UUID REFERENCES persy_research_proposals(id) ON DELETE SET NULL;
CREATE TABLE persy_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_key CHAR(64) NOT NULL,
    request_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX persy_audit_owner_idx ON persy_audit(owner_key, created_at);
COMMIT;
