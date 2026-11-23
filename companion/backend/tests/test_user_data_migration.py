import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.user_data import prepare_user_data
from app.user_data import backup_before_schema_change
from app.user_data import sync_package_catalog
from app.user_data import sync_package_catalog_once


def seed_db(path: Path, text: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE character (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("CREATE TABLE chatmessage (id INTEGER PRIMARY KEY, content TEXT)")
    con.execute("INSERT INTO character VALUES (1, '清宵')")
    if text is not None:
        con.execute("INSERT INTO chatmessage VALUES (1, ?)", (text,))
    con.commit()
    con.close()


def chat_text(path: Path) -> str:
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT content FROM chatmessage").fetchone()[0]
    finally:
        con.close()


def test_imports_old_release_and_keeps_wallet_and_settings(tmp_path: Path):
    old = tmp_path / "xiaoke-ai-agent-A-20261028000000" / "data"
    current = tmp_path / "xiaoke-ai-agent-A-20261105000000" / "data"
    seed_db(old / "app.db", "上次聊到这里")
    (old / "wallet.seal").write_bytes(b"sealed wallet")
    (old / "wallet.knot").write_bytes(b"knot")
    (old / "wallet.pending").write_bytes(b"pending")
    con = sqlite3.connect(old / "app.db")
    con.execute("CREATE TABLE kx_slot (slot TEXT PRIMARY KEY, n INTEGER, p TEXT, q TEXT, r TEXT, s TEXT)")
    con.execute("INSERT INTO kx_slot VALUES ('slot-2', 9, 'share', 'bind', 'ring', 'mac')")
    con.commit()
    con.close()
    (old / ".env").write_text("API_KEY=private", encoding="utf-8")
    seed_db(current / "app.db")
    home = tmp_path / "stable" / "data"

    status = prepare_user_data(current.parent, current, home)

    assert status == "legacy-imported"
    assert chat_text(home / "app.db") == "上次聊到这里"
    assert (home / "wallet.seal").read_bytes() == b"sealed wallet"
    assert (home / "wallet.knot").read_bytes() == b"knot"
    assert (home / "wallet.pending").read_bytes() == b"pending"
    con = sqlite3.connect(home / "app.db")
    assert con.execute("SELECT n, p, s FROM kx_slot").fetchone() == (9, "share", "mac")
    con.close()
    assert (home / ".env").read_text(encoding="utf-8") == "API_KEY=private"


def test_new_package_seed_does_not_replace_existing_profile(tmp_path: Path):
    old = tmp_path / "xiaoke-ai-20261028" / "data"
    current = tmp_path / "xiaoke-ai-20261105" / "data"
    home = tmp_path / "stable" / "data"
    seed_db(old / "app.db", "保留我")
    seed_db(current / "app.db")
    prepare_user_data(current.parent, current, home)
    con = sqlite3.connect(current / "app.db")
    con.execute("INSERT INTO chatmessage VALUES (1, '新包初始内容')")
    con.commit()
    con.close()

    assert prepare_user_data(current.parent, current, home) == "existing"
    assert chat_text(home / "app.db") == "保留我"


def test_corrupt_newer_db_does_not_hide_healthy_old_profile(tmp_path: Path):
    old = tmp_path / "xiaoke-ai-20261028" / "data"
    broken = tmp_path / "xiaoke-ai-20261101" / "data"
    current = tmp_path / "xiaoke-ai-20261105" / "data"
    seed_db(old / "app.db", "旧聊天仍在")
    broken.mkdir(parents=True)
    (broken / "app.db").write_bytes(b"not a sqlite database")
    os.utime(broken / "app.db", (2000000000, 2000000000))
    seed_db(current / "app.db")
    home = tmp_path / "stable" / "data"

    prepare_user_data(current.parent, current, home)
    assert chat_text(home / "app.db") == "旧聊天仍在"


def test_packed_path_uses_stable_data_home(tmp_path: Path):
    backend = Path(__file__).resolve().parents[1]
    root = tmp_path / "release"
    seed_db(root / "data" / "app.db")
    env = os.environ.copy()
    env.update({
        "COMPANION_ROOT": str(root),
        "COMPANION_DATA": str(tmp_path / "shared-data"),
        "PYTHONPATH": str(backend),
    })
    code = "from app.paths import DATA_DIR; import os; from pathlib import Path; assert DATA_DIR == Path(os.environ['COMPANION_DATA']).resolve()"
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_schema_upgrade_preserves_rows_and_creates_rollback(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "data" / "app.db"
    db_path.parent.mkdir()
    con = sqlite3.connect(db_path)
    # 10-28 风格的旧表：没有后来增加的 kind / full_content。
    con.execute("CREATE TABLE chatmessage (id INTEGER PRIMARY KEY, character_id INTEGER, role VARCHAR, content VARCHAR, created_at DATETIME)")
    con.execute("INSERT INTO chatmessage VALUES (1, 7, 'user', '旧消息', '2026-10-28 12:00:00')")
    con.execute("CREATE TABLE character (id INTEGER PRIMARY KEY, name VARCHAR)")
    con.execute("INSERT INTO character VALUES (7, '旧角色')")
    con.commit()
    con.close()

    from sqlmodel import create_engine
    import app.db as db_module
    import app.models  # noqa: F401 - register every table before init_db
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "engine", create_engine(f"sqlite:///{db_path}"))

    db_module.init_db()
    backup = db_path.with_name(f"app.before-schema-v{db_module.SCHEMA_VERSION}.db")
    assert backup and backup.is_file()
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT content, kind, full_content FROM chatmessage").fetchone()
    columns = {r[1] for r in con.execute("PRAGMA table_info(chatmessage)")}
    version = con.execute("PRAGMA user_version").fetchone()[0]
    life_enabled = con.execute("SELECT character_life_enabled FROM character WHERE id=7").fetchone()[0]
    con.close()

    assert row == ("旧消息", "qa", "")
    assert {"kind", "full_content"} <= columns
    assert version == db_module.SCHEMA_VERSION
    assert life_enabled == 0
    assert backup_before_schema_change(db_path, 1) is None
    old = sqlite3.connect(backup)
    assert old.execute("SELECT content FROM chatmessage").fetchone()[0] == "旧消息"
    old.close()


def test_failed_import_starts_with_defaults_and_retries_next_time(tmp_path: Path, monkeypatch):
    import app.paths as paths
    import app.user_data as user_data
    root = tmp_path / "xiaoke-ai-agent-A-20261118000000"
    seed_db(root / "data" / "app.db")
    home = tmp_path / "stable" / "data"
    monkeypatch.setenv("COMPANION_ROOT", str(root))
    monkeypatch.setenv("COMPANION_DATA", str(home))
    monkeypatch.setattr(user_data, "prepare_user_data", lambda *args: (_ for _ in ()).throw(OSError("copy failed")))

    _, data_dir, _ = paths._detect()

    assert data_dir == home.parent / f"default-{root.name}"
    assert (data_dir / "app.db").is_file()
    assert not (home / "app.db").exists()  # 下次启动仍会执行正式迁移。


def test_latest_catalog_replaces_old_assets_but_preserves_user_data(tmp_path: Path):
    old = tmp_path / "old.db"
    new = tmp_path / "new.db"
    for path in (old, new):
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE asset (id INTEGER PRIMARY KEY, kind TEXT, name TEXT, path TEXT)")
        con.execute("CREATE TABLE character (id INTEGER PRIMARY KEY, name TEXT, model_asset_id INTEGER)")
        con.execute("CREATE TABLE chatmessage (id INTEGER PRIMARY KEY, content TEXT)")
        con.execute("CREATE TABLE cam_review (combo_id TEXT PRIMARY KEY, verdict TEXT)")
        con.commit(); con.close()
    con = sqlite3.connect(old)
    con.executemany("INSERT INTO asset VALUES (?,?,?,?)", [
        (1, "motion", "旧动作", "motions/old.vmd"),
        (2, "model", "默认模型", "models/default/model.pmx"),
        (3, "model", "用户模型", "models/custom/model.pmx"),
    ])
    con.executemany("INSERT INTO character VALUES (?,?,?)", [(1, "清宵", 2), (2, "我的角色", 3)])
    con.execute("INSERT INTO chatmessage VALUES (1, '用户聊天')")
    con.execute("INSERT INTO cam_review VALUES ('old-shot', 'ok')")
    con.commit(); con.close()
    con = sqlite3.connect(new)
    con.executemany("INSERT INTO asset VALUES (?,?,?,?)", [
        (10, "motion", "新动作", "motions/new.vmd"),
        (20, "model", "默认模型", "models/default/model.pmx"),
    ])
    con.execute("INSERT INTO character VALUES (1, '清宵', 20)")
    con.execute("INSERT INTO cam_review VALUES ('new-shot', 'ok')")
    con.commit(); con.close()

    sync_package_catalog(old, new, "20261118")

    con = sqlite3.connect(old)
    assert con.execute("SELECT id, name FROM asset WHERE kind='motion'").fetchall() == [(10, "新动作")]
    assert con.execute("SELECT model_asset_id FROM character WHERE name='清宵'").fetchone()[0] == 20
    assert con.execute("SELECT model_asset_id FROM character WHERE name='我的角色'").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM asset WHERE path='models/custom/model.pmx'").fetchone()[0] == 0
    assert con.execute("SELECT content FROM chatmessage").fetchone()[0] == "用户聊天"
    assert con.execute("SELECT * FROM cam_review").fetchall() == [("new-shot", "ok")]
    con.close()


def test_catalog_sync_runs_only_once_per_release(tmp_path: Path):
    user = tmp_path / "user.db"
    package = tmp_path / "package.db"
    for path in (user, package):
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE asset (id INTEGER PRIMARY KEY, kind TEXT, name TEXT, path TEXT)")
        con.execute("CREATE TABLE character (id INTEGER PRIMARY KEY, name TEXT, model_asset_id INTEGER)")
        con.execute("CREATE TABLE cam_review (combo_id TEXT PRIMARY KEY, verdict TEXT)")
        con.commit(); con.close()
    con = sqlite3.connect(package)
    con.execute("INSERT INTO asset VALUES (1, 'motion', '第一版', 'motions/v1.vmd')")
    con.commit(); con.close()

    assert sync_package_catalog_once(user, package, "release-a") is True
    con = sqlite3.connect(package)
    con.execute("UPDATE asset SET name='不应再次覆盖' WHERE id=1")
    con.commit(); con.close()
    assert sync_package_catalog_once(user, package, "release-a") is False
    con = sqlite3.connect(user)
    assert con.execute("SELECT name FROM asset").fetchone()[0] == "第一版"
    con.close()
    assert sync_package_catalog_once(user, package, "release-b") is True
