"""Epic Games。和 Steam 一样是国际商店，库在 Manifests 的 .item 里。"""
from __future__ import annotations

import json
import os
from urllib.parse import quote

from .model import Game

_UNINSTALL = (
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
)
_RELS = (
    r"Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
    r"Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
)


def launcher(host) -> str:
    for shortcut in _shortcuts(host):
        name = getattr(shortcut, "name", "") or ""
        if "卸载" in name or "uninstall" in name.lower():
            continue
        target = (getattr(shortcut, "target", "") or "").strip().strip('"')
        if os.path.basename(target).lower() == "epicgameslauncher.exe" and host.is_file(target):
            return target
    for hive, path in _UNINSTALL:
        for sub in host.reg_subkeys(hive, path):
            full = path + "\\" + sub
            label = host.reg_value(hive, full, "DisplayName").lower()
            if "epic games" not in label and "epicgames" not in label:
                continue
            for key in ("DisplayIcon", "InstallLocation"):
                found = _as_exe(host, host.reg_value(hive, full, key))
                if found:
                    return found
    command = host.reg_value(
        "HKCU", r"Software\Classes\com.epicgames.launcher\shell\open\command", "",
    )
    found = _as_exe(host, command)
    if found:
        return found
    roots = [host.env(key) for key in ("ProgramFiles(x86)", "ProgramFiles")]
    for root in roots:
        if not root:
            continue
        for rel in _RELS:
            cand = os.path.join(root, rel)
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
    data = host.env("PROGRAMDATA") or r"C:\ProgramData"
    folder = os.path.join(data, "Epic", "EpicGamesLauncher", "Data", "Manifests")
    found: list[Game] = []
    seen: set[str] = set()
    for item in host.list_dir(folder):
        if not item.lower().endswith(".item"):
            continue
        try:
            payload = json.loads(host.read_text(os.path.join(folder, item)) or "{}")
        except json.JSONDecodeError:
            continue
        game = _item(host, payload, exe)
        if game is None or game.key in seen:
            continue
        seen.add(game.key)
        found.append(game)
    return found


def _as_exe(host, raw: str) -> str:
    text = (raw or "").strip()
    mark = text.lower().find(".exe")
    if mark < 0:
        if text and host.is_dir(text):
            for rel in _RELS:
                cand = os.path.join(text, rel)
                if host.is_file(cand):
                    return cand
        return ""
    path = text[: mark + 4].strip().strip('"')
    if host.is_file(path):
        return path
    return ""


def _item(host, payload: dict, exe: str) -> Game | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("bIsIncompleteInstall"):
        return None
    name = str(payload.get("DisplayName") or "").strip()
    app = str(payload.get("AppName") or "").strip()
    launch = str(payload.get("LaunchExecutable") or "").strip()
    install = str(payload.get("InstallLocation") or "").strip()
    if not name or not app or not launch.lower().endswith(".exe") or not install:
        return None
    if not host.is_dir(install):
        return None
    folded = f"{name} {app} {launch}".lower()
    if "unrealeditor" in folded or "crashreport" in folded:
        return None
    namespace = str(payload.get("CatalogNamespace") or "").strip()
    catalog = str(payload.get("CatalogItemId") or "").strip()
    if namespace and catalog:
        ident = quote(f"{namespace}:{catalog}:{app}", safe="")
    else:
        ident = quote(app, safe="")
    uri = f"com.epicgames.launcher://apps/{ident}?action=launch&silent=true"
    argv = (exe, uri) if exe else ()
    return Game(
        platform="epic",
        name=name,
        key=app,
        install_dir=install,
        installed=True,
        processes=(os.path.basename(launch),),
        launcher_argv=argv,
    )
