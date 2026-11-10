BEGIN;

CREATE TABLE knowledge_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    library_id UUID NOT NULL REFERENCES knowledge_libraries(id) ON DELETE RESTRICT,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (library_id, slug),
    UNIQUE (library_id, name)
);

ALTER TABLE source_library_links
    ADD COLUMN category_id UUID REFERENCES knowledge_categories(id) ON DELETE SET NULL;

ALTER TABLE knowledge_sources
    ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (verification_status IN ('unverified', 'under_review', 'verified', 'rejected')),
    ADD COLUMN verified_at TIMESTAMPTZ,
    ADD COLUMN verified_by TEXT;

CREATE INDEX knowledge_categories_library_idx
    ON knowledge_categories(library_id, display_order);
CREATE INDEX source_library_links_category_idx
    ON source_library_links(category_id);
CREATE INDEX knowledge_sources_verification_idx
    ON knowledge_sources(verification_status);

INSERT INTO knowledge_categories (library_id, slug, name, display_order)
SELECT l.id, c.slug, c.name, c.display_order
FROM knowledge_libraries l
JOIN specialist_domains d ON d.id = l.domain_id
CROSS JOIN LATERAL (
    SELECT value->>0 AS slug, value->>1 AS name, (value->>2)::integer AS display_order
    FROM jsonb_array_elements(
      CASE d.slug
        WHEN 'personal-development' THEN '[["habits","Habits",1],["motivation","Motivation",2],["self-awareness","Self-awareness",3]]'::jsonb
        WHEN 'physical-development' THEN '[["strength","Strength",1],["mobility","Mobility",2],["movement","Movement",3]]'::jsonb
        WHEN 'nutrition' THEN '[["whole-foods","Whole foods",1],["nutrition-science","Nutrition science",2],["food-production","Food production",3],["food-preservation","Food preservation",4]]'::jsonb
        WHEN 'mental-wellbeing' THEN '[["emotional-regulation","Emotional regulation",1],["stress-resilience","Stress and resilience",2],["psychology","Psychology",3]]'::jsonb
        WHEN 'relationships' THEN '[["communication","Communication",1],["family-relationships","Family relationships",2],["conflict-resolution","Conflict resolution",3]]'::jsonb
        WHEN 'learning-intelligence' THEN '[["memory","Memory",1],["critical-thinking","Critical thinking",2],["creativity","Creativity",3]]'::jsonb
        WHEN 'financial-capability' THEN '[["budgeting","Budgeting",1],["investing","Investing principles",2],["financial-independence","Financial independence",3]]'::jsonb
        WHEN 'career-business' THEN '[["leadership","Leadership",1],["business-development","Business development",2],["career-planning","Career planning",3]]'::jsonb
        WHEN 'practical-life-skills' THEN '[["gardening","Growing vegetables",1],["seed-saving","Seed saving",2],["survival-skills","Survival skills",3]]'::jsonb
        WHEN 'parenting-family' THEN '[["child-development","Child development",1],["parenting","Parenting approaches",2],["family-wellbeing","Family wellbeing",3]]'::jsonb
        ELSE '[["outdoor-skills","Outdoor skills",1],["hobbies","Hobbies",2],["adventure","Adventure",3]]'::jsonb
      END
    ) AS value
) AS c
ON CONFLICT (library_id, slug) DO NOTHING;

COMMIT;
