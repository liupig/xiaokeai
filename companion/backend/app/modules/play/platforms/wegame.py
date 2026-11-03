"""WeGame。启动器和游戏 exe 从注册表、快捷方式里读，不写死盘符。"""
from __future__ import annotations

import os
import re

from ..titles import Title, norm, title_of
from .model import Game

_LAUNCHER_KEYS = (
    ("HKCU", r"Software\Tencent\WeGame"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Tencent\WeGame"),
    ("HKLM", r"SOFTWARE\Tencent\WeGame"),
)
_GAME_ROOTS = (
    ("HKCU", r"Software\Tencent"),
    ("HKLM", r"SOFTWARE\Tencent"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Tencent"),
    ("HKCU", r"Software\Rail"),
    ("HKLM", r"SOFTWARE\Rail"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Rail"),
)
_UNINSTALL = (
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
)
_SKIP = {
    "wegame", "qq", "qqmusic", "qqbrowser", "wechat", "weixin", "tim",
    "qqlive", "tenio", "tcls", "bugreport", "qzone", "tencent", "qdesk",
    "wetype", "qqpcmgr", "qqgame",
}
_TAILS = (
    r"WeGame\wegame.exe",
    r"腾讯软件\WeGame\wegame.exe",
    r"Program Files (x86)\WeGame\wegame.exe",
    r"Program Files\WeGame\wegame.exe",
    r"Tencent\WeGame\wegame.exe",
)
_PATH_NAMES = ("InstallPath", "InstallDir", "InstallLocation", "GamePath", "Path")
_SKIP_WALK = {
    "wegamelauncher", "tcls", "riot client", "game", "plugins",
    "anticheatexpert", "locales", "config", "tenio",
}


def launcher(host) -> str:
    for hive, path in _UNINSTALL:
        for sub in host.reg_subkeys(hive, path):
            full = path + "\\" + sub
            label = host.reg_value(hive, full, "DisplayName").lower()
            if "wegame" not in label:
                continue
            for key in ("DisplayIcon", "InstallLocation"):
                found = _as_exe(host, host.reg_value(hive, full, key))
                if found:
                    return found
    app = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\wegame.exe"
    found = _as_exe(host, host.reg_value("HKLM", app, ""))
    if found:
        return found
    for hive, path in _LAUNCHER_KEYS:
        for key in _PATH_NAMES:
            found = _as_exe(host, host.reg_value(hive, path, key))
            if found:
                return found
    for shortcut in _shortcuts(host):
        if _skipped_name(shortcut.name):
            continue
        target = (shortcut.target or "").strip().strip('"')
        if os.path.basename(target).lower() != "wegame.exe" or not host.is_file(target):
            continue
        if norm(shortcut.name) == "wegame":
            return target
    ini = _ini_exe(host)
    if ini:
        return ini
    for root in _program_roots(host):
        cand = os.path.join(root, "WeGame", "wegame.exe")
        if host.is_file(cand):
            return cand
    for drive in host.drives():
        for tail in _TAILS:
            cand = os.path.join(drive, tail)
            if host.is_file(cand):
                return cand
    return ""


def library(host) -> list[Game]:
    exe = launcher(host)
    found: list[Game] = []
    seen: set[str] = set()
    for hive, root in _GAME_ROOTS:
        for game in _walk(host, hive, root, exe, 0):
            key = os.path.normcase(os.path.normpath(game.install_dir))
            if key in seen:
                continue
            seen.add(key)
            found.append(game)
    return _collapse(found)


def _collapse(games: list[Game]) -> list[Game]:
    """同一个名字留一份。有客户端的那份优先。"""
    kept: dict[str, Game] = {}
    order: list[str] = []
    for game in games:
        key = norm(game.name) or os.path.normcase(os.path.normpath(game.install_dir))
        old = kept.get(key)
        if old is None:
            kept[key] = game
            order.append(key)
            continue
        if game.game_argv and not old.game_argv:
            kept[key] = game
    return [kept[key] for key in order]


def _program_roots(host) -> list[str]:
    roots = []
    for key in ("ProgramFiles(x86)", "ProgramFiles"):
        value = host.env(key)
        if value:
            roots.append(value)
    return roots


def _as_exe(host, raw: str) -> str:
    text = (raw or "").strip().strip('"')
    if not text:
        return ""
    if text.lower().endswith(".exe") and host.is_file(text):
        return text
    cand = os.path.join(text, "wegame.exe")
    if host.is_file(cand):
        return cand
    return ""


def _skip(name: str) -> bool:
    folded = name.lower()
    return (
        folded in _SKIP
        or folded.startswith("qq")
        or folded.startswith("wechat")
        or folded.startswith("weixin")
    )


def _walk(host, hive: str, path: str, exe: str, depth: int) -> list[Game]:
    install = ""
    for key in _PATH_NAMES:
        raw = host.reg_value(hive, path, key).strip().strip('"')
        if raw and host.is_dir(raw):
            install = raw
            break
    if install:
        return [_game(host, hive, path, install, exe)]
    if depth >= 1:
        return []
    found: list[Game] = []
    for sub in host.reg_subkeys(hive, path):
        if _skip(sub):
            continue
        found.extend(_walk(host, hive, path + "\\" + sub, exe, depth + 1))
    return found


def _game(host, hive: str, path: str, install: str, exe: str) -> Game:
    key = path.rsplit("\\", 1)[-1]
    title = title_of(key) or title_of(_folder_name(install))
    name = _display(host, hive, path, install, title)
    client = _client(host, hive, path, install, name)
    processes = list(title.processes if title else ())
    if client:
        base = os.path.basename(client)
        if base.lower() not in {item.lower() for item in processes}:
            processes.append(base)
    wegame_id = _folder_id(install) or _catalog_id(host, exe, name)
    launcher_argv: tuple[str, ...] = ()
    game_argv: tuple[str, ...] = ()
    if exe and wegame_id:
        # 自己拉 LeagueClient 会被 TCLS 判成平台没开，马上退出。交给 WeGame 的启动按钮。
        launcher_argv = (f"wegame://action=StartFor&game_id={wegame_id}",)
    elif client and exe and _same(client, exe):
        launcher_argv = (exe,)
    elif client and not exe:
        launcher_argv = (client,)
    else:
        if exe:
            launcher_argv = (exe,)
        if client:
            game_argv = (client,)
    return Game(
        platform="wegame",
        name=name,
        key=key,
        install_dir=install,
        installed=True,
        processes=tuple(processes),
        launcher_argv=launcher_argv,
        game_argv=game_argv,
    )


def _display(host, hive: str, path: str, install: str, title: Title | None) -> str:
    if title:
        return title.names[0]
    for key in ("DisplayName", "GameName"):
        raw = host.reg_value(hive, path, key).strip()
        if raw:
            return raw
    return _folder_name(install) or path.rsplit("\\", 1)[-1]


def _folder_name(install: str) -> str:
    base = os.path.basename(install.rstrip("\\/"))
    return re.sub(r"\(\d{1,10}\)\s*$", "", base).strip()


def _client(host, hive: str, path: str, install: str, game_name: str) -> str:
    product = _product_exe(host, install)
    if product:
        return product
    for key in ("setup_x64", "setup", "Install"):
        raw = host.reg_value(hive, path, key).strip().strip('"')
        if _usable_exe(host, raw):
            return raw
    named = ""
    for shortcut in _shortcuts(host):
        if _skipped_name(shortcut.name):
            continue
        target = (shortcut.target or "").strip().strip('"')
        if not _usable_exe(host, target):
            continue
        if _under(install, target):
            return target
        if not named and _name_hit(shortcut.name, game_name):
            named = target
    return named


def _product_exe(host, install: str) -> str:
    """在游戏目录里找客户端。跳过 WeGame 自己的启动壳。"""
    found: list[str] = []
    _collect_exes(host, install, 0, found)
    if not found:
        return ""
    found.sort(key=_exe_rank, reverse=True)
    return found[0]


def _collect_exes(host, folder: str, depth: int, found: list[str]) -> None:
    if depth > 2 or not folder:
        return
    try:
        names = host.list_dir(folder)
    except OSError:
        return
    for name in names:
        full = os.path.join(folder, name)
        if host.is_dir(full):
            if name.lower() in _SKIP_WALK:
                continue
            _collect_exes(host, full, depth + 1, found)
            continue
        if _usable_exe(host, full):
            found.append(full)


def _exe_rank(path: str) -> tuple[int, int]:
    base = os.path.basename(path).lower()
    if base.endswith("client.exe") and base != "client.exe":
        rank = 80
    elif "client" in base:
        rank = 50
    else:
        rank = 10
    return rank, -path.count("\\")


def _usable_exe(host, path: str) -> bool:
    if not path or not path.lower().endswith(".exe") or not host.is_file(path):
        return False
    if _stub_path(path):
        return False
    base = os.path.basename(path).lower()
    if "unins" in base or base in {"bugreport.exe", "repair.exe", "launcher.exe"}:
        return False
    return True


def _shortcuts(host) -> list:
    fn = getattr(host, "shortcuts", None)
    if not callable(fn):
        return []
    try:
        return list(fn())
    except OSError:
        return []


def _skipped_name(name: str) -> bool:
    folded = (name or "").lower()
    return "卸载" in (name or "") or "uninstall" in folded or "uninst" in folded


def _name_hit(shortcut_name: str, game_name: str) -> bool:
    left = norm(shortcut_name)
    right = norm(game_name)
    return bool(left and right and (left == right or right in left or left in right))


def _catalog_id(host, wegame_exe: str, game_name: str) -> str:
    """游戏号写在 WeGame 自己的区服表里，名字前面那个整数。不写死 26 这种号。"""
    if not wegame_exe or not game_name:
        return ""
    root = os.path.join(os.path.dirname(wegame_exe), "data", "cfg_bin")
    if not host.is_dir(root):
        return ""
    target = game_name.encode("utf-8")
    found: set[int] = set()
    read = getattr(host, "read_bytes", None)
    if not callable(read):
        return ""
    for name in host.list_dir(root):
        if not name.lower().endswith(".bin"):
            continue
        path = os.path.join(root, name)
        data = read(path)
        if not data or len(data) > 5_000_000:
            continue
        start = 0
        while True:
            at = data.find(target, start)
            if at < 0:
                break
            if at < 4:
                start = at + 1
                continue
            end = at + len(target)
            if end < len(data) and data[end] != 0:
                start = at + 1
                continue
            value = int.from_bytes(data[at - 4:at], "little")
            if 0 < value <= 50_000_000:
                found.add(value)
            start = end
    if len(found) != 1:
        return ""
    return str(found.pop())


def _folder_id(install: str) -> str:
    mark = re.search(r"\((\d{1,10})\)\s*$", os.path.basename(install.rstrip("\\/")))
    return mark.group(1) if mark else ""


def _same(left: str, right: str) -> bool:
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


def _stub_path(path: str) -> bool:
    folded = (path or "").replace("/", "\\").lower()
    return any(part in folded for part in ("\\wegamelauncher\\", "\\tcls\\", "\\riot client\\"))


def _under(root: str, exe: str) -> bool:
    try:
        base = os.path.normcase(os.path.normpath(root))
        path = os.path.normcase(os.path.normpath(exe))
        return os.path.commonpath([base, path]) == base and path != base
    except ValueError:
        return False


def _ini_exe(host) -> str:
    root = host.env("APPDATA")
    if not root:
        return ""
    text = host.read_text(os.path.join(root, "Tencent", "WeGameLauncher", "launcher.ini"))
    for line in text.splitlines():
        if line.lower().startswith("wegamepath="):
            path = line.split("=", 1)[1].strip().strip('"')
            if path.lower().endswith(".exe") and host.is_file(path):
                return path
    return ""
