"""Database session lifecycle."""

import os
from collections.abc import Iterator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_factory: sessionmaker[Session] | None = None
load_dotenv(Path(__file__).resolve().parents[4] / ".env", override=False)


def get_session() -> Iterator[Session]:
    global _factory
    if _factory is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise HTTPException(status_code=503, detail="DB_UNAVAILABLE")
        _factory = sessionmaker(create_engine(url, pool_pre_ping=True))
    with _factory() as session:
        yield session
