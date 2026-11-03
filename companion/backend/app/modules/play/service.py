"""下发开游戏，再用网址看游戏进程在不在。

中国区先 WeGame，再 Steam，再 Epic。国外反过来，Epic 排在 Steam 后面。
库里没有这个游戏时只打开平台，不替它点安装。
"""
from __future__ import annotations

import os
import threading
import uuid
from typing import Any

from . import intent
from .host import Proc, get_host
from .platforms import LABELS, launcher, library
from .platforms.model import Game
from .titles import names_match, platform_name, prefer, title_of

GAME_WAIT_SEC = 45
_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_MAX = 40
_LAUNCHERS = {
    "wegame": ("wegame.exe", "tgp_daemon.exe"),
    "steam": ("steam.exe",),
    "epic": ("epicgameslauncher.exe",),
}
_NOISE = ("crashreport", "easyanticheat", "beservice", "redist", "installer", "unins", "cefsubprocess")
_LAUNCHER_BASES = {name for names in _LAUNCHERS.values() for name in names}


def reset() -> None:
    with _LOCK:
        _JOBS.clear()


def status_path(job_id: str) -> str:
    return f"/api/modules/play/jobs/{job_id}"


def open_game(query: str, *, platform: str = "", region: str = "cn", host=None) -> dict[str, Any]:
    host = host or get_host()
    name = (query or "").strip()
    chosen = _platform_id(platform)
    if platform.strip() and not chosen:
        return _finish(_blank(name, "", "not_found", "不认识这个平台"), host)

    asked = platform_name(name)
    if asked or (not name and chosen):
        pid = chosen or asked
        return _open_launcher(host, pid, name or LABELS.get(pid, pid))

    if not name:
        return _finish(_blank("", "", "not_found", "没有游戏名"), host)

    game, kind = _resolve(host, name, region, chosen)
    if kind == "not_found" or game is None:
        return _finish(_blank(name, chosen, "not_found", "库里没有这个游戏"), host)
    if kind == "no_launcher" or not game.launcher_argv:
        label = LABELS.get(game.platform if game else chosen, "平台")
        return _finish(_blank(name, game.platform if game else chosen, "no_launcher", f"没找到{label}"), host)

    job = _from_game(game, "game")
    if game.installed and _game_up(host, job):
        job["state"] = "opened"
        job["opened"] = True
        job["ok"] = True
        job["detail"] = f"{game.name}已经在运行"
        return _finish(job, host)

    spawned: list[list[str]] = []
    errors: list[str] = []
    commands = [list(game.launcher_argv)]
    if game.installed and game.game_argv:
        commands.append(list(game.game_argv))
    for argv in commands:
        if not argv:
            continue
        if _already_running(host, argv[0]):
            spawned.append(argv)
            continue
        try:
            host.spawn(argv)
            spawned.append(argv)
        except OSError as exc:
            errors.append(str(exc))
    job["spawned"] = spawned
    if not spawned and errors:
        job["state"] = "failed"
        job["ok"] = False
        job["error"] = errors[0]
        job["detail"] = errors[0]
        return _finish(job, host)
    if errors:
        job["error"] = errors[0]
    job["spawned"] = spawned
    if any(cmd and str(cmd[0]).startswith("wegame://") for cmd in spawned):
        press = getattr(host, "press_wegame_start", None)
        if callable(press):
            try:
                press()
            except OSError as exc:
                job["error"] = str(exc)
    if not game.installed:
        job["state"] = "not_installed"
        job["ok"] = True
        job["opened"] = False
        job["detail"] = f"{LABELS.get(game.platform, '平台')}已打开，库里没有{game.name}"
        return _finish(job, host)
    job["detail"] = f"正在用{LABELS.get(game.platform, '平台')}打开{game.name}"
    return _finish(job, host)


def job_status(job_id: str, host=None) -> dict[str, Any] | None:
    host = host or get_host()
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        _refresh(job, host)
        return _public(job)


def launchers(host=None) -> dict[str, Any]:
    host = host or get_host()
    found = {}
    for pid in ("wegame", "steam", "epic"):
        exe = launcher(pid, host)
        found[pid] = {"label": LABELS[pid], "found": bool(exe), "exe": exe}
    return found


def installed(host=None, region: str = "cn") -> dict[str, Any]:
    host = host or get_host()
    games = []
    for pid in prefer(region):
        for game in library(pid, host):
            games.append({
                "platform": game.platform,
                "name": game.name,
                "key": game.key,
                "install_dir": game.install_dir,
            })
    return {"region": "intl" if region == "intl" else "cn", "launchers": launchers(host), "games": games}


def on_user_text(text: str, locale: str, host=None) -> str:
    """聊天里点名才开。认不出游戏就当没说，不打断对话。"""
    query = intent.extract_query(text)
    if not query:
        return ""
    host = host or get_host()
    region = "cn" if (locale or "").lower().startswith("zh") else "intl"
    if not _will_handle(host, query, region):
        return ""
    try:
        job = open_game(query, region=region, host=host)
    except OSError as exc:
        print(f"[play] {exc}")
        return ""
    from ..sight.service import hold_name

    hold_name(query)
    return _hint(job)


def _will_handle(host, query: str, region: str) -> bool:
    if platform_name(query) or title_of(query):
        return True
    for pid in prefer(region):
        for game in library(pid, host):
            if names_match(query, game.name):
                return True
    return False


def _hint(job: dict[str, Any]) -> str:
    name = job.get("game") or "游戏"
    label = job.get("platform_label") or "平台"
    state = job.get("state")
    if state == "opened" and job.get("target") == "launcher":
        return f"【开游戏】{label}已经打开。用一句话告诉对方。不要编菜单路径。"
    if state == "opened":
        return f"【开游戏】{name}已经在运行。用一句话告诉对方开好了。不要教对方自己去点。"
    if state == "waiting":
        return f"【开游戏】你已经叫{label}去开{name}。用一句话告诉对方正在开。不要说已经进游戏。"
    if state == "not_installed":
        return f"【开游戏】{label}已经打开，库里没有{name}。告诉对方库里没有。不要假装游戏已经开了。"
    if state == "no_launcher":
        return f"【开游戏】这台电脑上没找到{label}。告诉对方没找到。不要编安装路径。"
    if state == "launcher_only":
        return f"【开游戏】{label}开了，{name}没有起来。告诉对方平台开了，游戏没开成。"
    if state == "failed":
        return "【开游戏】打开失败。告诉对方没开成。不要编原因。"
    return ""


def _open_launcher(host, pid: str, label: str) -> dict[str, Any]:
    exe = launcher(pid, host)
    if not exe:
        return _finish(_blank(label, pid, "no_launcher", f"没找到{LABELS.get(pid, pid)}"), host)
    game = Game(platform=pid, name=label, installed=False, launcher_argv=(exe,))
    job = _from_game(game, "launcher")
    if _launcher_up(host, job):
        job["state"] = "opened"
        job["opened"] = True
        job["ok"] = True
        job["detail"] = f"{LABELS.get(pid, pid)}已经在运行"
        return _finish(job, host)
    try:
        host.spawn([exe])
    except OSError as exc:
        job["state"] = "failed"
        job["ok"] = False
        job["error"] = str(exc)
        job["detail"] = "启动失败"
        return _finish(job, host)
    job["spawned"] = [[exe]]
    job["detail"] = f"正在打开{LABELS.get(pid, pid)}"
    return _finish(job, host)


def _resolve(host, query: str, region: str, platform: str) -> tuple[Game | None, str]:
    order = (platform,) if platform else prefer(region)
    fallback: Game | None = None
    for pid in order:
        for game in library(pid, host):
            if not game.installed or not names_match(query, game.name):
                continue
            if game.launcher_argv:
                return game, "installed"
            fallback = fallback or game
    if fallback is not None:
        return fallback, "no_launcher"
    title = title_of(query)
    home = platform or (title.home if title else "")
    if not home:
        return None, "not_found"
    exe = launcher(home, host)
    if not exe:
        return Game(platform=home, name=title.names[0] if title else query), "no_launcher"
    shown = title.names[0] if title else query
    return Game(platform=home, name=shown, installed=False, launcher_argv=(exe,)), "not_installed"


def _from_game(game: Game, target: str) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:12],
        "ok": True,
        "state": "waiting",
        "opened": False,
        "game": game.name,
        "platform": game.platform,
        "platform_label": LABELS.get(game.platform, game.platform),
        "installed": game.installed,
        "target": target,
        "launcher": game.launcher_argv[0] if game.launcher_argv else "",
        "install_dir": game.install_dir,
        "processes": [item.lower() for item in game.processes],
        "launcher_names": list(_LAUNCHERS.get(game.platform, ())),
        "spawned": [],
        "status_url": "",
        "detail": "",
        "launcher_running": False,
        "game_running": False,
        "started": 0.0,
        "error": "",
    }


def _blank(game: str, platform: str, state: str, detail: str) -> dict[str, Any]:
    job = _from_game(Game(platform=platform, name=game), "game")
    job["ok"] = False
    job["state"] = state
    job["detail"] = detail
    job["platform_label"] = LABELS.get(platform, "平台")
    return job


def _finish(job: dict[str, Any], host) -> dict[str, Any]:
    job["started"] = float(host.now())
    job["status_url"] = status_path(job["id"])
    _refresh(job, host)
    with _LOCK:
        _JOBS[job["id"]] = job
        while len(_JOBS) > _MAX:
            _JOBS.pop(next(iter(_JOBS)))
    print(f"[play] {job.get('platform') or '-'} {job.get('game') or '-'} {job['state']}")
    return _public(job)


def _refresh(job: dict[str, Any], host) -> None:
    if job["state"] in {"not_found", "no_launcher", "failed"}:
        job["launcher_running"] = _launcher_up(host, job)
        job["game_running"] = False
        job["opened"] = False
        return
    game_up = _game_up(host, job)
    launcher_up = _launcher_up(host, job)
    job["game_running"] = game_up
    job["launcher_running"] = launcher_up
    if not job.get("installed") and job.get("target") != "launcher":
        job["state"] = "not_installed"
        job["opened"] = False
        job["ok"] = True
        return
    if job.get("target") == "launcher":
        if launcher_up:
            job["state"] = "opened"
            job["opened"] = True
            job["ok"] = True
            return
        if _age(job, host) < GAME_WAIT_SEC:
            job["state"] = "waiting"
            job["opened"] = False
            return
        job["state"] = "failed"
        job["ok"] = False
        job["opened"] = False
        job["detail"] = f"{job.get('platform_label') or '平台'}没有起来"
        return
    if game_up:
        job["state"] = "opened"
        job["opened"] = True
        job["ok"] = True
        job["detail"] = f"{job.get('game') or '游戏'}已打开"
        return
    if _age(job, host) < GAME_WAIT_SEC:
        job["state"] = "waiting"
        job["opened"] = False
        job["ok"] = True
        return
    job["opened"] = False
    job["ok"] = False
    if launcher_up:
        job["state"] = "launcher_only"
        job["detail"] = f"{job.get('platform_label') or '平台'}开了，{job.get('game') or '游戏'}没开起来"
        return
    job["state"] = "failed"
    job["detail"] = "游戏没有起来"


def _already_running(host, exe: str) -> bool:
    want = os.path.normcase(os.path.normpath(exe))
    base = os.path.basename(want)
    generic = {"launcher.exe", "client.exe"}
    for proc in host.processes():
        if proc.exe and os.path.normcase(os.path.normpath(proc.exe)) == want:
            return True
        if not proc.exe and base not in generic and (proc.name or "").lower() == base:
            return True
    return False


def _age(job: dict[str, Any], host) -> float:
    return float(host.now()) - float(job.get("started") or 0)


def _launcher_up(host, job: dict[str, Any]) -> bool:
    names = {item.lower() for item in job.get("launcher_names") or ()}
    if not names:
        return False
    return any((proc.name or "").lower() in names for proc in host.processes())


def _game_up(host, job: dict[str, Any]) -> bool:
    names = {item.lower() for item in job.get("processes") or ()}
    root = job.get("install_dir") or ""
    if not names and not root:
        return False
    for proc in host.processes():
        if _is_game(proc, names, root):
            return True
    return False


def _stub_proc(name: str, exe: str) -> bool:
    """WeGame 的启动壳不算游戏已经打开。"""
    if name in {"launcher.exe", "bugreport.exe", "repair.exe"}:
        return True
    folded = (exe or "").replace("/", "\\").lower()
    return any(part in folded for part in ("\\wegamelauncher\\", "\\tcls\\", "\\riot client\\"))


def _is_game(proc: Proc, names: set[str], root: str) -> bool:
    name = (proc.name or "").lower()
    exe = proc.exe or ""
    if not name or any(bit in name for bit in _NOISE):
        return False
    if name in _LAUNCHER_BASES or _stub_proc(name, exe):
        return False
    if name in names:
        return True
    exe = proc.exe or ""
    if not root or not exe:
        return False
    base = os.path.basename(exe).lower()
    if base in _LAUNCHER_BASES or any(bit in base for bit in _NOISE):
        return False
    return _under(root, exe)


def _under(root: str, exe: str) -> bool:
    try:
        left = os.path.normcase(os.path.normpath(root))
        right = os.path.normcase(os.path.normpath(exe))
        return os.path.commonpath([left, right]) == left and right != left
    except ValueError:
        return False


def _platform_id(raw: str) -> str:
    text = (raw or "").strip().lower().replace(" ", "")
    if text in {"wegame", "steam", "epic", "epicgames"}:
        return "epic" if text.startswith("epic") else text
    return ""


def _public(job: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "ok", "id", "state", "opened", "game", "platform", "platform_label",
        "installed", "target", "launcher", "install_dir", "status_url", "detail",
        "launcher_running", "game_running", "error", "spawned",
    )
    out = {key: job.get(key) for key in keep}
    out["spawned"] = [list(item) for item in job.get("spawned") or []]
    return out
