"""Separate SQLite files per cost domain (demo: multi-source budget aggregation)."""

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Cohort / visits live in cinema.db (app.db.DB_PATH).
COST_SOURCE_PATHS = {
    "marketing": DATA_DIR / "marketing.db",
    "fnb": DATA_DIR / "cost_fnb.db",
    "staff": DATA_DIR / "cost_staff.db",
    "utilities": DATA_DIR / "cost_utilities.db",
    "other": DATA_DIR / "cost_other.db",
}

# Cached engines: SQLite defaults to NullPool (new file open per checkout).
_POOL_KW = {
    "poolclass": QueuePool,
    "pool_size": 4,
    "max_overflow": 8,
    "pool_pre_ping": True,
}


def _sqlite_engine(path: Path):
    return create_engine(
        "sqlite:///{0}".format(path),
        connect_args={"check_same_thread": False},
        **_POOL_KW,
    )


ENGINES = {name: _sqlite_engine(path) for name, path in COST_SOURCE_PATHS.items()}
SessionMarketing = sessionmaker(bind=ENGINES["marketing"], expire_on_commit=False)
SessionFnb = sessionmaker(bind=ENGINES["fnb"], expire_on_commit=False)
SessionStaff = sessionmaker(bind=ENGINES["staff"], expire_on_commit=False)
SessionUtilities = sessionmaker(bind=ENGINES["utilities"], expire_on_commit=False)
SessionOther = sessionmaker(bind=ENGINES["other"], expire_on_commit=False)


@contextmanager
def cost_store_sessions():
    """One ORM session per cost database; connections return to the engine pool on close."""
    marketing = SessionMarketing()
    fnb = SessionFnb()
    staff = SessionStaff()
    utilities = SessionUtilities()
    other = SessionOther()
    try:
        yield {
            "marketing": marketing,
            "fnb": fnb,
            "staff": staff,
            "utilities": utilities,
            "other": other,
        }
    finally:
        for session in (marketing, fnb, staff, utilities, other):
            session.close()


def marketing_session() -> Session:
    return SessionMarketing()


class MarketingBase(DeclarativeBase):
    pass


class OpsCostBase(DeclarativeBase):
    pass
