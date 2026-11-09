-- CorePath source registration and specialist-library associations.
-- Source records are globally identifiable; associations allow a source to be
-- discoverable from multiple specialist libraries without duplicating metadata.

BEGIN;

CREATE TABLE source_library_links (
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE RESTRICT,
    library_id UUID NOT NULL REFERENCES knowledge_libraries(id) ON DELETE RESTRICT,
    relationship_note TEXT NOT NULL DEFAULT '',
    added_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, library_id)
);

CREATE INDEX source_library_links_library_idx
    ON source_library_links(library_id, created_at DESC);

-- Enforce a canonical source type vocabulary and make source registration
-- safer to consume from the API. Existing rows already satisfy these values.
ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS source_status TEXT NOT NULL DEFAULT 'active'
        CHECK (source_status IN ('active', 'under_review', 'superseded', 'withdrawn')),
    ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS verification_notes TEXT NOT NULL DEFAULT '';

-- Index common source discovery fields. Do not force URL uniqueness: the same
-- URL can legitimately identify different captured versions over time.
CREATE INDEX IF NOT EXISTS knowledge_sources_type_status_idx
    ON knowledge_sources(source_type, source_status);
CREATE INDEX IF NOT EXISTS knowledge_sources_publication_date_idx
    ON knowledge_sources(publication_date DESC);

-- Register existing document/library associations in the shared link table.
INSERT INTO source_library_links (source_id, library_id, added_by)
SELECT DISTINCT source_id, library_id, 'migration'
FROM knowledge_documents
ON CONFLICT (source_id, library_id) DO NOTHING;

COMMIT;
