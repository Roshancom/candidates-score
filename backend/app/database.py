from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, DateTime
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.types import TypeDecorator

DATABASE_URL = "sqlite:///./techkraft.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class UtcDateTime(TypeDecorator):
    """
    Custom type that coerces naive datetimes from SQLite into UTC-aware datetimes.
    SQLite does not store timezone info, so `datetime.now(timezone.utc)` is stored
    as `"2026-07-05 12:00:00.000000"` and read back as a naive datetime.
    This type automatically applies UTC timezone on read to fix timezone loss.
    """
    impl = DateTime
    cache_ok = True

    def process_result_value(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
