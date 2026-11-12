-- Private journal records belong only to the isolated Life Profile database.
BEGIN;
CREATE TABLE life_profile_journal_settings (
    subject TEXT PRIMARY KEY REFERENCES life_profiles(subject) ON DELETE CASCADE,
    payload_ciphertext BYTEA NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0)
);
CREATE TABLE life_profile_journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject TEXT NOT NULL REFERENCES life_profiles(subject) ON DELETE CASCADE,
    client_reference UUID NOT NULL,
    payload_ciphertext BYTEA NOT NULL,
    include_in_profile BOOLEAN NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    analysed_version INTEGER,
    analysis_state TEXT NOT NULL CHECK (analysis_state IN
        ('pending', 'excluded', 'awaiting_consent', 'processed', 'unavailable')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(subject, id),
    UNIQUE(subject, client_reference)
);
CREATE INDEX journal_entries_owner_order
    ON life_profile_journal_entries(subject, created_at DESC, id DESC);
-- Keep payload-free retry tombstones so delayed creates cannot restore deleted entries.
CREATE TABLE life_profile_journal_deleted_references (
    subject TEXT NOT NULL REFERENCES life_profiles(subject) ON DELETE CASCADE,
    client_reference UUID NOT NULL,
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(subject, client_reference)
);
ALTER TABLE life_profile_items ADD CONSTRAINT life_profile_items_owner_id UNIQUE(subject, id);
CREATE TABLE life_profile_journal_observations (
    subject TEXT NOT NULL,
    entry_id UUID NOT NULL,
    item_id UUID NOT NULL,
    entry_version INTEGER NOT NULL CHECK (entry_version > 0),
    PRIMARY KEY(entry_id, item_id),
    FOREIGN KEY(subject, entry_id) REFERENCES life_profile_journal_entries(subject, id)
        ON DELETE CASCADE,
    FOREIGN KEY(subject, item_id) REFERENCES life_profile_items(subject, id)
        ON DELETE CASCADE
);
COMMIT;
