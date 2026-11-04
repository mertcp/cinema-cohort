from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "cinema.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

ENGINE = create_engine(
    "sqlite:///{0}".format(DB_PATH),
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=ENGINE, expire_on_commit=False)


def create_tables():
    from app.models import Base

    Base.metadata.create_all(ENGINE)


def get_session() -> Session:
    return SessionLocal()
