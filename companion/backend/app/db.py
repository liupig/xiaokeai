from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .paths import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_columns()


def _migrate_columns() -> None:
    """给已有 SQLite 表补新列（create_all 不会 ALTER）。"""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "chatmessage" in tables:
        cols = {c["name"] for c in insp.get_columns("chatmessage")}
        if "kind" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE chatmessage ADD COLUMN kind VARCHAR DEFAULT 'qa'"))
        if "full_content" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE chatmessage ADD COLUMN full_content VARCHAR DEFAULT ''"))
    if "character" in tables:
        cols = {c["name"] for c in insp.get_columns("character")}
        if "boundary" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE "character" ADD COLUMN boundary VARCHAR '
                    "DEFAULT 'strict'"))
    if "memory_fact" in tables:
        cols = {c["name"] for c in insp.get_columns("memory_fact")}
        alters = {
            "speaker": "VARCHAR DEFAULT ''",
            "source_message_id": "INTEGER DEFAULT 0",
            "emotion": "VARCHAR DEFAULT ''",
            "emotion_intensity": "FLOAT DEFAULT 0",
        }
        for name, typedef in alters.items():
            if name not in cols:
                with engine.begin() as conn:
                    conn.execute(text(
                        f"ALTER TABLE memory_fact ADD COLUMN {name} {typedef}"))
    if "coin_wallet" in tables:
        cols = {c["name"] for c in insp.get_columns("coin_wallet")}
        alters = {
            "nonce": "INTEGER DEFAULT 0",
            "address": "VARCHAR DEFAULT ''",
        }
        for name, typedef in alters.items():
            if name not in cols:
                with engine.begin() as conn:
                    conn.execute(text(
                        f"ALTER TABLE coin_wallet ADD COLUMN {name} {typedef}"))
    if "memory_episode" in tables:
        cols = {c["name"] for c in insp.get_columns("memory_episode")}
        if "key_events" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE memory_episode ADD COLUMN key_events VARCHAR DEFAULT '[]'"))


def get_session():
    with Session(engine) as session:
        yield session
