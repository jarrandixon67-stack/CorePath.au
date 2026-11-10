-- General, scoped specialist research runs. No Life Profile records belong here.
BEGIN;

CREATE TABLE specialist_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_id UUID NOT NULL REFERENCES service_identities(id) ON DELETE RESTRICT,
    request_id TEXT NOT NULL CHECK (length(request_id) BETWEEN 1 AND 100),
    domain_id UUID NOT NULL REFERENCES specialist_domains(id) ON DELETE RESTRICT,
    library_id UUID NOT NULL REFERENCES knowledge_libraries(id) ON DELETE RESTRICT,
    run_kind TEXT NOT NULL CHECK (run_kind IN ('coordinator_task', 'independent_research')),
    input_hash CHAR(64) NOT NULL CHECK (input_hash ~ '^[a-f0-9]{64}$'),
    policy_hash CHAR(64) NOT NULL CHECK (policy_hash ~ '^[a-f0-9]{64}$'),
    model_id TEXT,
    state TEXT NOT NULL DEFAULT 'running'
        CHECK (state IN ('running', 'completed', 'needs_evidence', 'failed')),
    result JSONB,
    error_code TEXT,
    lease_expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '2 minutes',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (requester_id, request_id),
    CHECK ((state IN ('completed', 'needs_evidence')) = (result IS NOT NULL)),
    CHECK ((state = 'running') = (completed_at IS NULL))
);
CREATE INDEX specialist_runs_budget_idx ON specialist_runs(requester_id, created_at);
CREATE INDEX specialist_runs_domain_idx ON specialist_runs(domain_id, created_at);
CREATE INDEX document_sections_english_search_idx
    ON document_sections USING gin (to_tsvector('english', coalesce(heading, '') || ' ' || content_text));

COMMIT;
