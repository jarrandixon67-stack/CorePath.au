from app.config import Settings
from app.database import create_pool


def test_database_pool_uses_transactions(monkeypatch) -> None:
    captured: dict = {}

    class FakePool:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("app.database.ConnectionPool", FakePool)

    pool = create_pool(
        Settings(
            database_url="postgresql://corepath:secret@localhost/corepath",
            db_pool_min_size=1,
            db_pool_max_size=5,
        )
    )

    assert isinstance(pool, FakePool)
    assert captured["kwargs"]["autocommit"] is False


def test_database_pool_is_optional_without_database_url() -> None:
    assert create_pool(Settings(database_url=None)) is None
