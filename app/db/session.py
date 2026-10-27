"""Engine, session factory, and startup migration (create tables)."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _sqlite_file(url: str) -> Path | None:
    if not url.startswith("sqlite"):
        return None
    if url in {"sqlite://", "sqlite:///:memory:"} or url.endswith(":memory:"):
        return None
    raw = url.split("sqlite:///", 1)[-1]
    if not raw or raw == ":memory:":
        return None
    return Path(raw)


def _prepare_url(url: str) -> tuple[str, dict]:
    path = _sqlite_file(url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
    connect_args: dict = {}
    engine_kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        engine_kwargs["connect_args"] = connect_args
        if url in {"sqlite://", "sqlite:///:memory:"} or ":memory:" in url:
            engine_kwargs["poolclass"] = StaticPool
    return url, engine_kwargs


def init_engine(settings: Settings) -> Engine:
    global _engine, _SessionLocal
    url, kwargs = _prepare_url(settings.database_url)
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        if engine.dialect.name != "sqlite":
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    _engine = engine
    _SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
        expire_on_commit=False,
    )
    return engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine is not initialized")
    return _engine


def get_session_factory() -> sessionmaker:
    if _SessionLocal is None:
        raise RuntimeError("Database session factory is not initialized")
    return _SessionLocal


def session_scope() -> Generator[Session, None, None]:
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def dispose_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
