import os
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
        # Echo SQL in development, but allow an explicit override (AFROEVAL_SQL_ECHO=0) so
        # callers that surface stdout to users — e.g. the console's HITL action subprocesses —
        # can suppress the query firehose without changing the deployment env.
        echo = settings.afroeval_env == "development" and os.getenv("AFROEVAL_SQL_ECHO", "1") != "0"
        _engine = create_engine(
            settings.database_url,
            echo=echo,
            connect_args=connect_args,
        )
    return _engine


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
