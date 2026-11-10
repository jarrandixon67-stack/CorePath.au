-- Apply only to the separate Life Profile database, never the knowledge database.
BEGIN;

CREATE TABLE life_profiles (
    subject TEXT PRIMARY KEY CHECK (length(subject) BETWEEN 1 AND 200),
    consent_ciphertext BYTEA NOT NULL,
    consent_revision INTEGER NOT NULL DEFAULT 1 CHECK (consent_revision > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE life_profile_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject TEXT NOT NULL REFERENCES life_profiles(subject) ON DELETE CASCADE,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'accepted', 'rejected')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    payload_ciphertext BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX life_profile_items_subject_idx ON life_profile_items(subject, created_at);

CREATE TABLE life_profile_item_versions (
    item_id UUID NOT NULL REFERENCES life_profile_items(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    state TEXT NOT NULL,
    payload_ciphertext BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (item_id, version)
);

CREATE TABLE life_profile_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject TEXT NOT NULL REFERENCES life_profiles(subject) ON DELETE CASCADE,
    action TEXT NOT NULL,
    target_id UUID,
    request_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX life_profile_audit_subject_idx ON life_profile_audit(subject, created_at);

COMMIT;
