from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.schemas import SourceCreate


class LibraryNotFoundError(Exception):
    pass


def list_libraries(pool: ConnectionPool) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            """
            SELECT l.id AS library_id, l.name AS library_name, l.status,
                   d.id AS domain_id, d.slug AS domain_slug, d.name AS domain_name
            FROM knowledge_libraries AS l
            JOIN specialist_domains AS d ON d.id = l.domain_id
            ORDER BY d.name
            """,
            row_factory=dict_row,
        ).fetchall()


def list_library_sources(pool: ConnectionPool, library_id: UUID) -> list[dict]:
    with pool.connection() as conn:
        library = conn.execute(
            "SELECT id FROM knowledge_libraries WHERE id = %s",
            (library_id,),
        ).fetchone()
        if library is None:
            raise LibraryNotFoundError

        return conn.execute(
            """
            SELECT s.id, s.source_type, s.title, s.authors, s.publisher,
                   s.publication_date, s.canonical_url, s.isbn, s.doi,
                   s.language_code, s.licence, s.access_notes,
                   s.source_status, s.created_at
            FROM source_library_links AS link
            JOIN knowledge_sources AS s ON s.id = link.source_id
            WHERE link.library_id = %s
            ORDER BY s.title ASC, s.created_at DESC
            """,
            (library_id,),
            row_factory=dict_row,
        ).fetchall()


def register_library_source(
    pool: ConnectionPool,
    library_id: UUID,
    source: SourceCreate,
    actor: str = "internal-api",
) -> dict:
    with pool.connection() as conn:
        library = conn.execute(
            "SELECT id FROM knowledge_libraries WHERE id = %s",
            (library_id,),
        ).fetchone()
        if library is None:
            raise LibraryNotFoundError

        values = source.model_dump(mode="json", exclude={"relationship_note", "source_metadata"})
        values["canonical_url"] = str(source.canonical_url) if source.canonical_url else None

        created = conn.execute(
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

        source_id = created[0]
        conn.execute(
            """
            INSERT INTO source_library_links (source_id, library_id, relationship_note, added_by)
            VALUES (%s, %s, %s, %s)
            """,
            (source_id, library_id, source.relationship_note, actor),
        )

        row = conn.execute(
            """
            SELECT id, source_type, title, authors, publisher, publication_date,
                   canonical_url, isbn, doi, language_code, licence, access_notes,
                   source_status, created_at
            FROM knowledge_sources WHERE id = %s
            """,
            (source_id,),
            row_factory=dict_row,
        ).fetchone()

        conn.execute(
            """
            INSERT INTO audit_events
                (actor_label, action, target_type, target_id, purpose, outcome)
            VALUES (%s, 'source.register', 'knowledge_source', %s,
                    'Register source in specialist library', 'succeeded')
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
        library = conn.execute(
            "SELECT id FROM knowledge_libraries WHERE id = %s",
            (library_id,),
        ).fetchone()
        if library is None:
            raise LibraryNotFoundError

        source = conn.execute(
            "SELECT id FROM knowledge_sources WHERE id = %s",
            (source_id,),
        ).fetchone()
        if source is None:
            raise SourceNotFoundError

        conn.execute(
            """
            INSERT INTO source_library_links (source_id, library_id, added_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (source_id, library_id) DO NOTHING
            """,
            (source_id, library_id, actor),
        )
        conn.execute(
            """
            INSERT INTO audit_events
                (actor_label, action, target_type, target_id, purpose, outcome)
            VALUES (%s, 'source.link_library', 'knowledge_source', %s,
                    'Link existing source to specialist library', 'succeeded')
            """,
            (actor, source_id),
        )


class SourceNotFoundError(Exception):
    pass
