"""Steam。库来自 libraryfolders.vdf 和 appmanifest，启动用 -applaunch。"""
from __future__ import annotations

import os
import re

from ..titles import title_of
from .model import Game

_KEYS = (
    ("HKCU", r"Software\Valve\Steam", "SteamExe"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    ("HKLM", r"SOFTWARE\Valve\Steam", "InstallPath"),
    ("HKCU", r"Software\Valve\Steam", "SteamPath"),
)


def launcher(host) -> str:
    for hive, path, name in _KEYS:
        raw = host.reg_value(hive, path, name).strip().strip('"')
        found = _as_exe(host, raw)
        if found:
            return found
    for shortcut in _shortcuts(host):
        label = getattr(shortcut, "name", "") or ""
        if "卸载" in label or "uninstall" in label.lower():
            continue
        target = (getattr(shortcut, "target", "") or "").strip().strip('"')
        if os.path.basename(target).lower() == "steam.exe" and host.is_file(target):
            return target
    root = host.env("ProgramFiles(x86)")
    if root:
        cand = os.path.join(root, "Steam", "steam.exe")
        if host.is_file(cand):
            return cand
    return ""


def _shortcuts(host) -> list:
    fn = getattr(host, "shortcuts", None)
    if not callable(fn):
        return []
    try:
        return list(fn())
    except OSError:
        return []


def library(host) -> list[Game]:
    exe = launcher(host)
    if not exe:
        return []
    found: list[Game] = []
    seen: set[str] = set()
    for folder in _libraries(host, os.path.dirname(exe)):
        apps = os.path.join(folder, "steamapps")
        for item in host.list_dir(apps):
            if not item.lower().startswith("appmanifest_") or not item.lower().endswith(".acf"):
                continue
            text = host.read_text(os.path.join(apps, item))
            game = _manifest(host, text, folder, exe)
            if game is None:
                continue
            if game.key in seen:
                continue
            seen.add(game.key)
            found.append(game)
    return found


def _as_exe(host, raw: str) -> str:
    if not raw:
        return ""
    if raw.lower().endswith(".exe") and host.is_file(raw):
        return raw
    cand = os.path.join(raw, "steam.exe")
    if host.is_file(cand):
        return cand
    return ""


def _libraries(host, root: str) -> list[str]:
    found: list[str] = []
    for rel in (os.path.join("steamapps", "libraryfolders.vdf"), os.path.join("config", "libraryfolders.vdf")):
        text = host.read_text(os.path.join(root, rel))
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            path = os.path.normpath(match.group(1).replace("\\\\", "\\"))
            if path and path not in found:
                found.append(path)
    if root and root not in found:
        found.insert(0, root)
    return found


def _manifest(host, text: str, folder: str, exe: str) -> Game | None:
    appid = _field(text, "appid")
    name = _field(text, "name")
    installdir = _field(text, "installdir")
    if not appid or not name or not installdir:
        return None
    if "redistributable" in name.lower() or "steamworks common" in name.lower():
        return None
    installed = os.path.join(folder, "steamapps", "common", installdir)
    if not host.is_dir(installed):
        return None
    title = title_of(name)
    processes = title.processes if title else ()
    return Game(
        platform="steam",
        name=name,
        key=appid,
        install_dir=installed,
        installed=True,
        processes=processes,
        launcher_argv=(exe, "-applaunch", appid),
    )


def _field(text: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s+"([^"]*)"', text)
    return match.group(1).strip() if match else ""
