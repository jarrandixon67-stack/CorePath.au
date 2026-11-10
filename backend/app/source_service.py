from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.schemas import CategoryCreate, SourceCreate, VerificationUpdate


class LibraryNotFoundError(Exception):
    pass


class SourceNotFoundError(Exception):
    pass


class CategoryNotFoundError(Exception):
    pass


def list_libraries(pool: ConnectionPool) -> list[dict]:
    with pool.connection() as conn:
        return conn.cursor(row_factory=dict_row).execute(
            """
            SELECT l.id AS library_id, l.name AS library_name, l.status,
                   d.id AS domain_id, d.slug AS domain_slug, d.name AS domain_name
            FROM knowledge_libraries AS l
            JOIN specialist_domains AS d ON d.id = l.domain_id
            ORDER BY d.name
            """ ,
        ).fetchall()


def get_library_overview(pool: ConnectionPool, library_id: UUID) -> dict:
    with pool.connection() as conn:
        library = conn.cursor(row_factory=dict_row).execute(
            """
            SELECT l.id AS library_id, l.name AS library_name, l.status,
                   d.slug AS domain_slug, d.name AS domain_name, d.description
            FROM knowledge_libraries l
            JOIN specialist_domains d ON d.id = l.domain_id
            WHERE l.id = %s
            """,
            (library_id,) ,
        ).fetchone()
        if library is None:
            raise LibraryNotFoundError

        counts = conn.cursor(row_factory=dict_row).execute(
            """
            SELECT
              count(DISTINCT link.source_id)::integer AS registered_sources,
              count(DISTINCT link.source_id) FILTER (
                WHERE source.verification_status = 'verified'
              )::integer AS verified_records
            FROM source_library_links link
            JOIN knowledge_sources source ON source.id = link.source_id
            WHERE link.library_id = %s
            """,
            (library_id,) ,
        ).fetchone()

        findings = conn.cursor(row_factory=dict_row).execute(
            """
            SELECT count(*)::integer AS research_findings
            FROM research_findings finding
            JOIN knowledge_libraries library ON library.domain_id = finding.domain_id
            WHERE library.id = %s AND finding.status = 'accepted'
            """,
            (library_id,) ,
        ).fetchone()

        categories = conn.cursor(row_factory=dict_row).execute(
            """
            SELECT c.id, c.name, c.slug, c.description, c.display_order,
                   count(link.source_id)::integer AS source_count
            FROM knowledge_categories c
            LEFT JOIN source_library_links link ON link.category_id = c.id
            WHERE c.library_id = %s AND c.is_active = TRUE
            GROUP BY c.id
            ORDER BY c.display_order, c.name
            """,
            (library_id,) ,
        ).fetchall()

        return {**library, **counts, **findings, "categories": categories}


def list_library_sources(pool: ConnectionPool, library_id: UUID) -> list[dict]:
    with pool.connection() as conn:
        library = conn.cursor(row_factory=dict_row).execute(
            "SELECT id FROM knowledge_libraries WHERE id = %s",
            (library_id,),
        ).fetchone()
        if library is None:
            raise LibraryNotFoundError

        return conn.cursor(row_factory=dict_row).execute(
            """
            SELECT s.id, s.source_type, s.title, s.authors, s.publisher,
                   s.publication_date, s.canonical_url, s.isbn, s.doi,
                   s.language_code, s.licence, s.access_notes,
                   s.source_status, s.verification_status, s.created_at,
                   c.id AS category_id, c.name AS category_name
            FROM source_library_links link
            JOIN knowledge_sources s ON s.id = link.source_id
            LEFT JOIN knowledge_categories c ON c.id = link.category_id
            WHERE link.library_id = %s
            ORDER BY s.title ASC, s.created_at DESC
            """,
            (library_id,) ,
        ).fetchall()


def create_library_category(
    pool: ConnectionPool,
    library_id: UUID,
    category: CategoryCreate,
) -> dict:
    with pool.connection() as conn:
        library = conn.cursor(row_factory=dict_row).execute(
            "SELECT id FROM knowledge_libraries WHERE id = %s",
            (library_id,),
        ).fetchone()
        if library is None:
            raise LibraryNotFoundError

        slug = "-".join(category.name.lower().split())
        row = conn.cursor(row_factory=dict_row).execute(
            """
            INSERT INTO knowledge_categories (library_id, slug, name, description)
            VALUES (%s, %s, %s, %s)
            RETURNING id, library_id, slug, name, description, display_order
            """,
            (library_id, slug, category.name, category.description) ,
        ).fetchone()
        return row


def register_library_source(
    pool: ConnectionPool,
    library_id: UUID,
    source: SourceCreate,
    actor: str = "internal-api",
) -> dict:
    with pool.connection() as conn:
        library = conn.cursor(row_factory=dict_row).execute(
            "SELECT id FROM knowledge_libraries WHERE id = %s",
            (library_id,),
        ).fetchone()
        if library is None:
            raise LibraryNotFoundError

        if source.category_id is not None:
            category = conn.cursor(row_factory=dict_row).execute(
                "SELECT id FROM knowledge_categories WHERE id = %s AND library_id = %s",
                (source.category_id, library_id),
            ).fetchone()
            if category is None:
                raise CategoryNotFoundError

        values = source.model_dump(
            mode="json",
            exclude={"relationship_note", "source_metadata", "category_id"},
        )
        values["canonical_url"] = str(source.canonical_url) if source.canonical_url else None

        created = conn.cursor(row_factory=dict_row).execute(
            """
            INSERT INTO knowledge_sources (
                source_type, title, authors, publisher, publication_date,
                canonical_url, isbn, doi, language_code, licence,
                access_notes, source_metadata
            )
            VALUES (
                %(source_type)s, %(title)s, %(authors)s, %(publisher)s,
                %(publication_date)s, %(canonical_url)s, %(isbn)s, %(doi)s,
                %(language_code)s, %(licence)s, %(access_notes)s, %(source_metadata)s
            )
            RETURNING id
            """,
            {**values, "source_metadata": Jsonb(source.source_metadata)},
        ).fetchone()

        source_id = created["id"]
        conn.cursor(row_factory=dict_row).execute(
            """
            INSERT INTO source_library_links
                (source_id, library_id, relationship_note, added_by, category_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (source_id, library_id, source.relationship_note, actor, source.category_id),
        )

        row = conn.cursor(row_factory=dict_row).execute(
            """
            SELECT s.id, s.source_type, s.title, s.authors, s.publisher,
                   s.publication_date, s.canonical_url, s.isbn, s.doi,
                   s.language_code, s.licence, s.access_notes, s.source_status,
                   s.verification_status, s.created_at,
                   c.id AS category_id, c.name AS category_name
            FROM knowledge_sources s
            JOIN source_library_links link ON link.source_id = s.id
            LEFT JOIN knowledge_categories c ON c.id = link.category_id
            WHERE s.id = %s AND link.library_id = %s
            """,
            (source_id, library_id) ,
        ).fetchone()

        conn.cursor(row_factory=dict_row).execute(
            """
            INSERT INTO audit_events
                (actor_label, action, target_type, target_id, purpose, outcome)
            VALUES (%s, 'source.register', 'knowledge_source', %s,
                    'Register source in specialist library', 'succeeded')
            """,
            (actor, source_id),
        )
        return row


def update_source_verification(
    pool: ConnectionPool,
    library_id: UUID,
    source_id: UUID,
    update: VerificationUpdate,
    actor: str = "internal-api",
) -> dict:
    with pool.connection() as conn:
        linked = conn.cursor(row_factory=dict_row).execute(
            """
            SELECT 1 FROM source_library_links
            WHERE library_id = %s AND source_id = %s
            """,
            (library_id, source_id),
        ).fetchone()
        if linked is None:
            raise SourceNotFoundError

        row = conn.cursor(row_factory=dict_row).execute(
            """
            UPDATE knowledge_sources
            SET verification_status = %s,
                verification_notes = %s,
                last_verified_at = CASE WHEN %s = 'verified' THEN now() ELSE last_verified_at END,
                verified_at = CASE WHEN %s = 'verified' THEN now() ELSE NULL END,
                verified_by = CASE WHEN %s = 'verified' THEN %s ELSE NULL END,
                updated_at = now()
            WHERE id = %s
            RETURNING id, title, verification_status, verification_notes,
                      verified_at, verified_by
            """,
            (
                update.verification_status,
                update.verification_notes,
                update.verification_status,
                update.verification_status,
                update.verification_status,
                actor,
                source_id,
            ) ,
        ).fetchone()

        conn.cursor(row_factory=dict_row).execute(
            """
            INSERT INTO audit_events
                (actor_label, action, target_type, target_id, purpose, outcome)
            VALUES (%s, 'source.verify', 'knowledge_source', %s,
                    'Update source verification status', 'succeeded')
            """,
            (actor, source_id),
        )
        return row


def link_existing_source(
    pool: ConnectionPool,
    library_id: UUID,
    source_id: UUID,
    actor: str = "internal-api",
) -> None:
    with pool.connection() as conn:
        library = conn.cursor(row_factory=dict_row).execute(
            "SELECT id FROM knowledge_libraries WHERE id = %s",
            (library_id,),
        ).fetchone()
        if library is None:
            raise LibraryNotFoundError

        source = conn.cursor(row_factory=dict_row).execute(
            "SELECT id FROM knowledge_sources WHERE id = %s",
            (source_id,),
        ).fetchone()
        if source is None:
            raise SourceNotFoundError

        conn.cursor(row_factory=dict_row).execute(
            """
            INSERT INTO source_library_links (source_id, library_id, added_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (source_id, library_id) DO NOTHING
            """,
            (source_id, library_id, actor),
        )
        conn.cursor(row_factory=dict_row).execute(
            """
            INSERT INTO audit_events
                (actor_label, action, target_type, target_id, purpose, outcome)
            VALUES (%s, 'source.link_library', 'knowledge_source', %s,
                    'Link existing source to specialist library', 'succeeded')
            """,
            (actor, source_id),
        )
