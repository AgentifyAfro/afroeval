from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from api.settings import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        is_postgres = settings.database_url.startswith("postgresql")
        connect_args = {"sslmode": "require"} if is_postgres else {}
        _engine = create_engine(
            settings.database_url,
            echo=settings.afroeval_env == "development",
            connect_args=connect_args,
        )
    return _engine


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
