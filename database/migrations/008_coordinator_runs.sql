-- Coordinator orchestration records; no Life Profiles or private conversations.
BEGIN;
ALTER TABLE service_identities DROP CONSTRAINT service_identities_service_role_check;
ALTER TABLE service_identities ADD CONSTRAINT service_identities_service_role_check
    CHECK (service_role IN ('coordinator', 'specialist', 'personal_ai', 'research_worker', 'knowledge_admin', 'api_service'));
ALTER TABLE access_permissions DROP CONSTRAINT access_permissions_action_check;
ALTER TABLE access_permissions ADD CONSTRAINT access_permissions_action_check
    CHECK (action IN ('discover', 'ingest', 'retrieve', 'research', 'coordinate', 'write_finding', 'assess', 'administer'));

CREATE TABLE coordinator_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_id UUID NOT NULL REFERENCES service_identities(id) ON DELETE RESTRICT,
    coordinator_id UUID NOT NULL REFERENCES service_identities(id) ON DELETE RESTRICT,
    request_id TEXT NOT NULL CHECK (length(request_id) BETWEEN 1 AND 100),
    input_hash CHAR(64) NOT NULL CHECK (input_hash ~ '^[a-f0-9]{64}$'),
    policy_hash CHAR(64) NOT NULL CHECK (policy_hash ~ '^[a-f0-9]{64}$'),
    model_id TEXT,
    allowed_domains TEXT[] NOT NULL CHECK (cardinality(allowed_domains) BETWEEN 1 AND 11),
    allow_collaboration BOOLEAN NOT NULL DEFAULT FALSE,
    max_calls INTEGER NOT NULL CHECK (max_calls BETWEEN 1 AND 11),
    calls_used INTEGER NOT NULL DEFAULT 0 CHECK (calls_used BETWEEN 0 AND max_calls),
    state TEXT NOT NULL DEFAULT 'running' CHECK (state IN ('running', 'completed', 'partial', 'needs_evidence', 'needs_clarification', 'failed')),
    plan JSONB,
    report JSONB,
    error_code TEXT,
    lease_expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (requester_id, request_id),
    CHECK ((state = 'running') = (completed_at IS NULL)),
    CHECK (state IN ('running', 'failed') OR report IS NOT NULL)
);
CREATE INDEX coordinator_runs_budget_idx ON coordinator_runs(requester_id, created_at);
CREATE TABLE coordinator_tasks (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES coordinator_runs(id) ON DELETE RESTRICT,
    domain_id UUID NOT NULL REFERENCES specialist_domains(id) ON DELETE RESTRICT,
    phase TEXT NOT NULL CHECK (phase IN ('initial', 'collaboration')),
    task_hash CHAR(64) NOT NULL CHECK (task_hash ~ '^[a-f0-9]{64}$'),
    rationale TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'running' CHECK (state IN ('running', 'completed', 'needs_evidence', 'failed')),
    specialist_run_id UUID,
    result JSONB,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (run_id, domain_id),
    CHECK ((state = 'running') = (completed_at IS NULL)),
    CHECK ((state IN ('completed', 'needs_evidence')) = (result IS NOT NULL))
);
CREATE INDEX coordinator_tasks_run_idx ON coordinator_tasks(run_id);
COMMIT;
