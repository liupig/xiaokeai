"""Keep mutable user data outside versioned application folders.

Release archives contain a seed ``data/app.db``.  Before the stable data home
was introduced, that same folder also held the user's chats and wallet.  On
the first start of a new release, import the newest old profile which actually
contains user activity; afterwards the package's seed database is never used
to overwrite the stable profile.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


# Large downloadable resources and disposable files are not user profiles.
_SKIP_DIRS = {"speech", "embed", "tmp", "logs", "__pycache__"}
_SKIP_FILES = {"app.db-wal", "app.db-shm", "wallet.lock"}


def default_data_home() -> Path:
    """A location shared by every unpacked/installed release of the app."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "xiaoke-ai" / "data"
        return Path.home() / "AppData" / "Local" / "xiaoke-ai" / "data"
    return Path.home() / ".local" / "share" / "xiaoke-ai" / "data"


def _has_user_activity(data_dir: Path) -> bool:
    db_path = data_dir / "app.db"
    if not db_path.is_file():
        return False
    # Wallet files are authoritative even when the SQL database has no chats.
    if any((data_dir / name).is_file() for name in (
        "wallet.seal", "wallet.knot", "wallet.pending",
    )):
        return True
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            tables = {
                row[0] for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for table in ("chatmessage", "memory_fact", "memory_episode",
                          "pinned_message", "keepsake", "coin_note"):
                if table in tables and con.execute(
                    f'SELECT 1 FROM "{table}" LIMIT 1'
                ).fetchone():
                    return True
        finally:
            con.close()
    except sqlite3.Error:
        # Do not select a corrupt database over a healthy older profile.
        return False
    return False


def _legacy_candidates(app_root: Path, package_data: Path) -> list[Path]:
    candidates = [package_data]
    try:
        siblings = list(app_root.parent.iterdir())
    except OSError:
        siblings = []
    for sibling in siblings:
        if sibling == app_root or not sibling.is_dir():
            continue
        name = sibling.name.lower()
        if not name.startswith("xiaoke-ai") or "-b-" in name or name.endswith("-b"):
            continue
        data = sibling / "data"
        if (data / "app.db").is_file():
            candidates.append(data)
    # Prefer actual user activity, then the most recently used profile.  The
    # current package is only a fallback seed and must not win by build time.
    return sorted(
        candidates,
        key=lambda p: (
            _has_user_activity(p),
            (p / "app.db").stat().st_mtime_ns if (p / "app.db").is_file() else 0,
        ),
        reverse=True,
    )


def _copy_profile(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    # The wallet's five shares span two encrypted files and four SQL rows.
    # Take the SQL backup and copy those files under the same interprocess
    # lock used by coins_box, so they all come from one wallet generation.
    with _source_wallet_lock(source):
        source_db = sqlite3.connect(str(source / "app.db"), timeout=10)
        target_db = sqlite3.connect(str(destination / "app.db"))
        try:
            source_db.backup(target_db)
        finally:
            target_db.close()
            source_db.close()
        for item in source.iterdir():
            if item.name in _SKIP_FILES or item.name == "app.db":
                continue
            target = destination / item.name
            if item.is_dir():
                if item.name in _SKIP_DIRS:
                    continue
                shutil.copytree(item, target, dirs_exist_ok=True)
            elif item.is_file():
                shutil.copy2(item, target)


@contextmanager
def _source_wallet_lock(source: Path):
    """Match coins_box._wallet_lock while taking a migration snapshot."""
    lock_path = source / "wallet.lock"
    with open(lock_path, "a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + 15
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("旧版正在写入金币账本，请关闭旧版后重新打开新版")
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def prepare_user_data(app_root: Path, package_data: Path, data_home: Path) -> str:
    """Migrate once, returning a short startup status for diagnostics."""
    if (data_home / "app.db").is_file():
        return "existing"
    candidates = _legacy_candidates(app_root, package_data)
    source = next((p for p in candidates if _has_user_activity(p)), None)
    if source is None and (package_data / "app.db").is_file():
        source = package_data
    if source is None:
        return "new"
    data_home.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".migrate-", dir=data_home.parent))
    try:
        _copy_profile(source, temp)
        # Another process may have completed migration while we were copying.
        if (data_home / "app.db").exists():
            return "existing"
        os.replace(temp, data_home)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return "package-seed" if source == package_data and not _has_user_activity(source) else "legacy-imported"


def prepare_default_data(package_data: Path, fallback_home: Path) -> None:
    """Start from package defaults after a failed import without blocking retry.

    The fallback is deliberately outside the real data_home.  A failed import
    therefore never looks successful on the next launch, and new chats written
    in the fallback are reused for that release instead of being reset.
    """
    if (fallback_home / "app.db").is_file():
        return
    if not (package_data / "app.db").is_file():
        fallback_home.mkdir(parents=True, exist_ok=True)
        return
    fallback_home.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".default-", dir=fallback_home.parent))
    try:
        _copy_profile(package_data, temp)
        if (fallback_home / "app.db").exists():
            return
        os.replace(temp, fallback_home)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def backup_before_schema_change(db_path: Path, target_version: int) -> Path | None:
    """Keep a consistent rollback copy before any DDL changes an old database."""
    if not db_path.is_file():
        return None
    source = sqlite3.connect(str(db_path), timeout=10)
    try:
        version = int(source.execute("PRAGMA user_version").fetchone()[0])
        if version >= target_version:
            return None
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("旧数据库完整性校验失败，已停止升级，原数据未修改")
        backup = db_path.with_name(f"app.before-schema-v{target_version}.db")
        if backup.exists():
            return backup
        target = sqlite3.connect(str(backup))
        try:
            source.backup(target)
        finally:
            target.close()
        return backup
    finally:
        source.close()


def _columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in con.execute(f'PRAGMA table_info("{table}")')]


def _rows(con: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    return list(con.execute(f'SELECT * FROM "{table}"'))


def sync_package_catalog(user_db: Path, package_db: Path, release: str) -> None:
    """Package owns director/camera review and the motion/asset catalog.

    User tables are untouched.  Character rows are user data, so their model
    references are remapped when the same model exists in the new package.
    This first migration intentionally uses only the package asset catalog.
    New imports are now marked user/user-aplaybox so a later release can
    preserve them without guessing their ownership.
    """
    if not package_db.is_file() or package_db.resolve() == user_db.resolve():
        return
    package = sqlite3.connect(str(package_db))
    user = sqlite3.connect(str(user_db))
    try:
        package_tables = {r[0] for r in package.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "asset" not in package_tables:
            return
        old_assets = {int(r["id"]): dict(r) for r in _rows(user, "asset")}
        old_chars = [dict(r) for r in _rows(user, "character")] if "character" in {
            r[0] for r in user.execute("SELECT name FROM sqlite_master WHERE type='table'")
        } else []
        package_assets = [dict(r) for r in _rows(package, "asset")]
        package_chars = [dict(r) for r in _rows(package, "character")] if "character" in package_tables else []
        asset_cols = [c for c in _columns(user, "asset") if c in _columns(package, "asset")]
        char_cols = _columns(user, "character")
        backup = user_db.with_name(f"app.before-catalog-{release}.db")
        if not backup.exists():
            backup_con = sqlite3.connect(str(backup))
            try:
                user.backup(backup_con)
            finally:
                backup_con.close()
        with user:
            user.execute("DELETE FROM asset")
            if package_assets:
                marks = ",".join("?" for _ in asset_cols)
                user.executemany(
                    f'INSERT INTO asset ({",".join(asset_cols)}) VALUES ({marks})',
                    [[row.get(c) for c in asset_cols] for row in package_assets],
                )
            by_path = {
                (str(row.get("kind") or ""), str(row.get("path") or "")): int(row["id"])
                for row in package_assets
            }
            package_char_model = {
                str(row.get("name") or ""): int(row.get("model_asset_id") or 0)
                for row in package_chars
            }
            for char in old_chars:
                old_id = int(char.get("model_asset_id") or 0)
                asset = old_assets.get(old_id)
                new_id = 0
                if asset:
                    key = (str(asset.get("kind") or ""), str(asset.get("path") or ""))
                    new_id = by_path.get(key, 0)
                if not new_id:
                    new_id = package_char_model.get(str(char.get("name") or ""), 0)
                if "model_asset_id" in char_cols:
                    user.execute("UPDATE character SET model_asset_id=? WHERE id=?", (new_id, char["id"]))
            if "cam_review" in package_tables:
                review_cols = [c for c in _columns(user, "cam_review") if c in _columns(package, "cam_review")]
                reviews = [dict(r) for r in _rows(package, "cam_review")]
                user.execute("DELETE FROM cam_review")
                if reviews:
                    marks = ",".join("?" for _ in review_cols)
                    user.executemany(
                        f'INSERT INTO cam_review ({",".join(review_cols)}) VALUES ({marks})',
                        [[row.get(c) for c in review_cols] for row in reviews],
                    )
    finally:
        user.close()
        package.close()


def sync_package_catalog_once(user_db: Path, package_db: Path, release: str) -> bool:
    """Run catalog replacement once per release, not on every application start."""
    import json
    marker = user_db.parent / "catalog-sync.json"
    try:
        done = json.loads(marker.read_text(encoding="utf-8"))
        if done.get("release") == release:
            return False
    except (OSError, ValueError, TypeError):
        pass
    sync_package_catalog(user_db, package_db, release)
    temp = marker.with_suffix(".tmp")
    temp.write_text(json.dumps({"release": release}), encoding="utf-8")
    os.replace(temp, marker)
    return True
