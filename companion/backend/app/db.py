from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .paths import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False, "timeout": 5},
    pool_reset_on_return="rollback",
)


@event.listens_for(engine, "connect")
def _sqlite_unlock(dbapi_conn, _connection_record) -> None:
    """WAL：读不占写锁。事务结束就把锁放开，别把连接挂在整段语音上。"""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=3000")
    cur.execute("PRAGMA wal_autocheckpoint=1000")
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.close()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_columns()
    _ensure_indexes()


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


# 已有表不会因为模型上新加了 Field(index=True) 就补索引。这里按真实查询建。
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_chatmessage_char_id ON chatmessage(character_id, id)",
    "CREATE INDEX IF NOT EXISTS ix_chatmessage_char_role_created ON chatmessage(character_id, role, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_chatmessage_char_kind_id ON chatmessage(character_id, kind, id)",
    "CREATE INDEX IF NOT EXISTS ix_memory_fact_char_updated ON memory_fact(character_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_memory_fact_char_kind ON memory_fact(character_id, kind)",
    "CREATE INDEX IF NOT EXISTS ix_memory_fact_char_rank ON memory_fact(character_id, pinned, importance)",
    "CREATE INDEX IF NOT EXISTS ix_memory_episode_char_id ON memory_episode(character_id, id)",
    "CREATE INDEX IF NOT EXISTS ix_pinned_char_id ON pinned_message(character_id, id)",
    "CREATE INDEX IF NOT EXISTS ix_pinned_char_msg ON pinned_message(character_id, message_id)",
    "CREATE INDEX IF NOT EXISTS ix_keepsake_char_created ON keepsake(character_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_asset_kind_name ON asset(kind, name)",
    "CREATE INDEX IF NOT EXISTS ix_cam_review_verdict ON cam_review(verdict)",
)


def _ensure_indexes() -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for sql in _INDEXES:
        table = sql.split(" ON ", 1)[1].split("(", 1)[0].strip()
        if table not in tables:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
        except Exception as exc:
            print(f"[db] index skipped: {exc}")


def get_session():
    with Session(engine) as session:
        yield session
