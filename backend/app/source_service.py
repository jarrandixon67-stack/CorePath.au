from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.schemas import SourceCreate


class LibraryNotFoundError(Exception):
    pass


def list_library_sources(pool: ConnectionPool, library_id: UUID) -> list[dict]:
    with pool.connection() as conn:
        library = conn.execute(
            "SELECT id FROM knowledge_libraries WHERE id = %s",
            (library_id,),
        ).fetchone()
        if library is None:
            raise LibraryNotFoundError

        rows = conn.execute(
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
        return rows


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
                %(language_code)s, %(licence)s, %(access_notes)s,
                %(source_metadata)s
            )
            RETURNING id
            """,
            {
                **source.model_dump(mode="json", exclude={"relationship_note"}),
                "canonical_url": str(source.canonical_url) if source.canonical_url else None,
            },
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
