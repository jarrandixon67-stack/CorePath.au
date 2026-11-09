-- CorePath Knowledge Infrastructure
-- Initial PostgreSQL migration: domain registry and provenance-first knowledge model.
-- Vector columns are intentionally deferred until an embedding model is selected.

BEGIN;

CREATE TABLE specialist_domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_libraries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL UNIQUE REFERENCES specialist_domains(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'active', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type TEXT NOT NULL
        CHECK (source_type IN ('book', 'journal_article', 'report', 'website', 'manual', 'archive', 'dataset', 'other')),
    title TEXT NOT NULL,
    authors TEXT[] NOT NULL DEFAULT '{}',
    publisher TEXT,
    publication_date DATE,
    canonical_url TEXT,
    isbn TEXT,
    doi TEXT,
    language_code TEXT,
    licence TEXT,
    access_notes TEXT,
    source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (canonical_url IS NULL OR canonical_url ~ '^https?://'),
    CHECK (doi IS NULL OR length(trim(doi)) > 0)
);

CREATE UNIQUE INDEX knowledge_sources_doi_uq
    ON knowledge_sources (lower(doi)) WHERE doi IS NOT NULL;
CREATE INDEX knowledge_sources_title_idx
    ON knowledge_sources USING gin (to_tsvector('simple', title));

CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE RESTRICT,
    library_id UUID NOT NULL REFERENCES knowledge_libraries(id) ON DELETE RESTRICT,
    document_title TEXT NOT NULL,
    edition TEXT,
    storage_key TEXT,
    canonical_url TEXT,
    retrieved_at TIMESTAMPTZ,
    checksum_sha256 CHAR(64),
    mime_type TEXT,
    file_size_bytes BIGINT CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    extraction_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (extraction_status IN ('pending', 'processing', 'completed', 'failed', 'reference_only')),
    extraction_error TEXT,
    document_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (canonical_url IS NULL OR canonical_url ~ '^https?://'),
    CHECK (checksum_sha256 IS NULL OR checksum_sha256 ~ '^[a-fA-F0-9]{64}$')
);
CREATE INDEX knowledge_documents_library_idx ON knowledge_documents(library_id);
CREATE INDEX knowledge_documents_source_idx ON knowledge_documents(source_id);
CREATE INDEX knowledge_documents_status_idx ON knowledge_documents(extraction_status);

CREATE TABLE document_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    section_number INTEGER NOT NULL CHECK (section_number >= 0),
    heading TEXT,
    content_text TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    locator TEXT,
    checksum_sha256 CHAR(64),
    token_count INTEGER CHECK (token_count IS NULL OR token_count >= 0),
    section_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, section_number),
    CHECK (page_start IS NULL OR page_start > 0),
    CHECK (page_end IS NULL OR page_end > 0),
    CHECK (page_start IS NULL OR page_end IS NULL OR page_end >= page_start)
);
CREATE INDEX document_sections_document_idx ON document_sections(document_id);
CREATE INDEX document_sections_text_idx
    ON document_sections USING gin (to_tsvector('simple', coalesce(heading, '') || ' ' || content_text));

CREATE TABLE research_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES specialist_domains(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    research_question TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT '',
    research_mode TEXT NOT NULL
        CHECK (research_mode IN ('scheduled', 'question_driven', 'knowledge_gap', 'coordinator_directed')),
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled')),
    requested_by TEXT,
    budget_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX research_projects_domain_status_idx ON research_projects(domain_id, status);

CREATE TABLE research_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES research_projects(id) ON DELETE RESTRICT,
    domain_id UUID NOT NULL REFERENCES specialist_domains(id) ON DELETE RESTRICT,
    claim TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    evidence_classification TEXT NOT NULL
        CHECK (evidence_classification IN (
            'established_evidence',
            'emerging_research',
            'traditional_historical_knowledge',
            'professional_opinion',
            'unverified_claim',
            'mixed_or_contested'
        )),
    confidence_label TEXT NOT NULL DEFAULT 'not_assessed'
        CHECK (confidence_label IN ('not_assessed', 'low', 'moderate', 'high')),
    limitations TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'under_review', 'accepted', 'superseded', 'withdrawn')),
    created_by TEXT,
    reviewed_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX research_findings_domain_class_idx ON research_findings(domain_id, evidence_classification);
CREATE INDEX research_findings_project_idx ON research_findings(project_id);

CREATE TABLE finding_sources (
    finding_id UUID NOT NULL REFERENCES research_findings(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE RESTRICT,
    section_id UUID REFERENCES document_sections(id) ON DELETE RESTRICT,
    relationship TEXT NOT NULL
        CHECK (relationship IN ('supports', 'challenges', 'contextualises', 'derived_from', 'cites')),
    notes TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (finding_id, source_id, relationship)
);
CREATE INDEX finding_sources_source_idx ON finding_sources(source_id);

CREATE TABLE evidence_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id UUID NOT NULL REFERENCES research_findings(id) ON DELETE RESTRICT,
    assessment_method TEXT NOT NULL DEFAULT '',
    methodology_notes TEXT NOT NULL DEFAULT '',
    strengths TEXT NOT NULL DEFAULT '',
    limitations TEXT NOT NULL DEFAULT '',
    conflicts_of_interest TEXT NOT NULL DEFAULT '',
    reviewer TEXT,
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    assessment_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX evidence_assessments_finding_idx ON evidence_assessments(finding_id, assessed_at DESC);

CREATE TABLE source_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE RESTRICT,
    related_source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE RESTRICT,
    relationship TEXT NOT NULL
        CHECK (relationship IN ('supports', 'challenges', 'contextualises', 'duplicates', 'supersedes', 'derived_from', 'cites')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (source_id <> related_source_id),
    UNIQUE (source_id, related_source_id, relationship)
);
CREATE INDEX source_relationships_related_idx ON source_relationships(related_source_id);

CREATE TABLE knowledge_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL
        CHECK (entity_type IN ('research_finding', 'knowledge_document', 'knowledge_source')),
    entity_id UUID NOT NULL,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    snapshot JSONB NOT NULL,
    change_reason TEXT NOT NULL,
    changed_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_type, entity_id, version_number)
);
CREATE INDEX knowledge_versions_entity_idx ON knowledge_versions(entity_type, entity_id, version_number DESC);

CREATE TABLE service_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    service_role TEXT NOT NULL
        CHECK (service_role IN ('coordinator', 'specialist', 'research_worker', 'knowledge_admin', 'api_service')),
    domain_id UUID REFERENCES specialist_domains(id) ON DELETE RESTRICT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (service_role = 'specialist' AND domain_id IS NOT NULL)
        OR (service_role <> 'specialist')
    )
);

CREATE TABLE access_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_identity_id UUID NOT NULL REFERENCES service_identities(id) ON DELETE CASCADE,
    library_id UUID REFERENCES knowledge_libraries(id) ON DELETE CASCADE,
    action TEXT NOT NULL
        CHECK (action IN ('discover', 'ingest', 'retrieve', 'research', 'write_finding', 'assess', 'administer')),
    granted_by TEXT NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    CHECK (expires_at IS NULL OR expires_at > granted_at),
    UNIQUE (service_identity_id, library_id, action)
);
CREATE INDEX access_permissions_identity_idx ON access_permissions(service_identity_id);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_identity_id UUID REFERENCES service_identities(id) ON DELETE SET NULL,
    actor_label TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id UUID,
    purpose TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL CHECK (outcome IN ('allowed', 'denied', 'succeeded', 'failed')),
    event_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_created_idx ON audit_events(created_at DESC);
CREATE INDEX audit_events_target_idx ON audit_events(target_type, target_id);

INSERT INTO specialist_domains (slug, name, description) VALUES
('personal-development', 'Personal Development', 'Goals, habits, motivation, self-awareness and personal growth.'),
('physical-development', 'Physical Development', 'Movement, strength, fitness, mobility and physical capability.'),
('nutrition', 'Nutrition', 'Food, nutrition, food quality, preparation and dietary knowledge.'),
('mental-wellbeing', 'Mental Wellbeing', 'Emotional awareness, coping, psychological wellbeing and related education.'),
('relationships', 'Relationships', 'Communication, interpersonal relationships, family and social connection.'),
('learning-intelligence', 'Learning & Intelligence', 'Learning, thinking, problem-solving, creativity and knowledge development.'),
('financial-capability', 'Financial Capability', 'Financial literacy, budgeting, planning and informed financial decisions.'),
('career-business', 'Career & Business', 'Employment, career development, entrepreneurship and leadership.'),
('practical-life-skills', 'Practical Life Skills', 'DIY, gardening, self-sufficiency, food production and practical skills.'),
('parenting-family', 'Parenting & Family', 'Parenting knowledge, child development and family life.'),
('recreation-discovery', 'Recreation & Discovery', 'Hobbies, outdoor activities, exploration and enjoyable experiences.')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO knowledge_libraries (domain_id, name, description)
SELECT id, name || ' Library', 'Dedicated knowledge collection for ' || name || '.'
FROM specialist_domains
ON CONFLICT (domain_id) DO NOTHING;

COMMIT;
