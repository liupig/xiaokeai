"""开游戏：中国区先 WeGame，库里有才开；Steam 和 Epic 同一套；网址看进程。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.play.host import Proc, Shortcut  # noqa: E402
from app.modules.play.intent import extract_query  # noqa: E402
from app.modules.play import service  # noqa: E402


def _p(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


class FakeHost:
    def __init__(self) -> None:
        self.files: set[str] = set()
        self.dirs: set[str] = set()
        self.texts: dict[str, str] = {}
        self.blobs: dict[str, bytes] = {}
        self.listing: dict[str, list[str]] = {}
        self.reg: dict[tuple[str, str, str], str] = {}
        self.subs: dict[tuple[str, str], list[str]] = {}
        self.env_map: dict[str, str] = {}
        self.drive_list = ["C:\\", "D:\\"]
        self.spawned: list[list[str]] = []
        self.procs: list[Proc] = []
        self.links: list[Shortcut] = []
        self.clock = 0.0

    def add_file(self, path: str) -> None:
        self.files.add(_p(path))

    def add_dir(self, path: str) -> None:
        self.dirs.add(_p(path))

    def put_text(self, path: str, text: str) -> None:
        self.texts[_p(path)] = text

    def reg_value(self, hive: str, path: str, name: str) -> str:
        return self.reg.get((hive, path, name), "")

    def reg_subkeys(self, hive: str, path: str) -> list[str]:
        return list(self.subs.get((hive, path), []))

    def is_file(self, path: str) -> bool:
        return _p(path) in self.files

    def is_dir(self, path: str) -> bool:
        return _p(path) in self.dirs

    def read_text(self, path: str) -> str:
        return self.texts.get(_p(path), "")

    def read_bytes(self, path: str) -> bytes:
        return self.blobs.get(_p(path), b"")

    def list_dir(self, path: str) -> list[str]:
        return list(self.listing.get(_p(path), []))

    def env(self, key: str) -> str:
        return self.env_map.get(key, "")

    def drives(self) -> list[str]:
        return list(self.drive_list)

    def spawn(self, argv: list[str]) -> None:
        self.spawned.append(list(argv))

    def processes(self) -> list[Proc]:
        return list(self.procs)

    def shortcuts(self) -> list[Shortcut]:
        return list(self.links)

    def now(self) -> float:
        return self.clock


def _wegame(host: FakeHost) -> str:
    exe = os.path.join("D:\\", "WeGame", "wegame.exe")
    host.add_file(exe)
    return exe


def _lol(host: FakeHost) -> str:
    exe = _wegame(host)
    install = os.path.join("D:\\", "英雄联盟")
    client = os.path.join(install, "LeagueClient", "LeagueClient.exe")
    host.add_dir(install)
    host.add_file(client)
    host.subs[("HKCU", r"Software\Tencent")] = ["LOL"]
    host.reg[("HKCU", r"Software\Tencent\LOL", "InstallPath")] = install
    host.reg[("HKCU", r"Software\Tencent\LOL", "setup")] = client
    catalog = os.path.join(os.path.dirname(exe), "data", "cfg_bin")
    host.add_dir(catalog)
    blob_name = "areas.bin"
    host.listing[_p(catalog)] = [blob_name]
    host.blobs[_p(os.path.join(catalog, blob_name))] = (26).to_bytes(4, "little") + "英雄联盟".encode("utf-8") + b"\x00"
    return client


def _steam(host: FakeHost, *, name: str, appid: str, installdir: str) -> str:
    exe = os.path.join("C:\\", "Steam", "steam.exe")
    root = os.path.join("C:\\", "Steam")
    apps = os.path.join(root, "steamapps")
    common = os.path.join(apps, "common", installdir)
    manifest = f"appmanifest_{appid}.acf"
    host.add_file(exe)
    host.add_dir(common)
    host.reg[("HKCU", r"Software\Valve\Steam", "SteamPath")] = root
    host.listing[_p(apps)] = [manifest]
    host.put_text(os.path.join(apps, manifest), "\n".join([
        '"AppState"',
        "{",
        f'  "appid" "{appid}"',
        f'  "name" "{name}"',
        f'  "installdir" "{installdir}"',
        '  "StateFlags" "4"',
        "}",
    ]))
    return exe


def _epic(host: FakeHost) -> str:
    exe = os.path.join(
        "C:\\", "Program Files", "Epic Games", "Launcher", "Portal", "Binaries", "Win64",
        "EpicGamesLauncher.exe",
    )
    data = os.path.join("C:\\", "ProgramData")
    manifests = os.path.join(data, "Epic", "EpicGamesLauncher", "Data", "Manifests")
    install = os.path.join("D:\\", "Fortnite")
    host.env_map["ProgramFiles"] = os.path.join("C:\\", "Program Files")
    host.env_map["PROGRAMDATA"] = data
    host.add_file(exe)
    host.add_dir(install)
    host.listing[_p(manifests)] = ["fortnite.item"]
    host.put_text(os.path.join(manifests, "fortnite.item"), json.dumps({
        "DisplayName": "Fortnite",
        "AppName": "Fortnite",
        "CatalogNamespace": "fn",
        "CatalogItemId": "4fe75bbc5a674f4f9b356b5c90567da5",
        "InstallLocation": install,
        "LaunchExecutable": r"FortniteGame\Binaries\Win64\FortniteClient-Win64-Shipping.exe",
        "bIsIncompleteInstall": False,
    }))
    return exe


def setup_function() -> None:
    service.reset()


def test_cn_lol_opens_wegame_then_client_when_installed():
    host = FakeHost()
    client = _lol(host)
    job = service.open_game("英雄联盟", region="cn", host=host)
    assert job["ok"] is True
    assert job["platform"] == "wegame"
    assert job["installed"] is True
    assert job["state"] == "waiting"
    assert job["opened"] is False
    assert job["status_url"] == f"/api/modules/play/jobs/{job['id']}"
    assert host.spawned == [["wegame://action=StartFor&game_id=26"]]

    host.procs.append(Proc("LeagueClient.exe"))
    seen = service.job_status(job["id"], host)
    assert seen is not None
    assert seen["opened"] is True
    assert seen["state"] == "opened"
    assert seen["game_running"] is True


def test_duplicate_lol_keeps_the_install_that_has_a_client():
    host = FakeHost()
    _wegame(host)
    stale = os.path.join("D:\\", "wegameapps", "英雄联盟")
    live = os.path.join("H:\\", "WeGameApps", "英雄联盟")
    client = os.path.join(live, "LeagueClient", "LeagueClient.exe")
    host.add_dir(stale)
    host.add_dir(live)
    host.add_file(client)
    host.subs[("HKCU", r"Software\Tencent")] = ["LOL", "WeType"]
    host.reg[("HKCU", r"Software\Tencent\LOL", "InstallPath")] = stale
    host.add_dir(os.path.join("C:\\", "Program Files", "Tencent", "WeType"))
    host.reg[("HKCU", r"Software\Tencent\WeType", "InstallPath")] = os.path.join(
        "C:\\", "Program Files", "Tencent", "WeType",
    )
    host.subs[("HKLM", r"SOFTWARE\Tencent")] = ["LOL"]
    host.reg[("HKLM", r"SOFTWARE\Tencent\LOL", "InstallPath")] = live
    host.reg[("HKLM", r"SOFTWARE\Tencent\LOL", "setup")] = client
    job = service.open_game("英雄联盟", region="cn", host=host)
    assert job["install_dir"] == live
    assert _p(host.spawned[1][0]) == _p(client)
    names = [game["name"] for game in service.installed(host=host, region="cn")["games"]]
    assert names.count("英雄联盟") == 1
    assert "WeType" not in names
    assert all("3.0" not in name for name in names)


def test_lol_missing_from_library_only_opens_wegame():
    host = FakeHost()
    exe = _wegame(host)
    job = service.open_game("英雄联盟", region="cn", host=host)
    assert job["state"] == "not_installed"
    assert job["opened"] is False
    assert job["ok"] is True
    assert host.spawned == [[exe]]


def test_missing_wegame_does_not_spawn():
    host = FakeHost()
    job = service.open_game("lol", region="cn", host=host)
    assert job["state"] == "no_launcher"
    assert job["opened"] is False
    assert job["ok"] is False
    assert host.spawned == []


def test_status_url_becomes_launcher_only_after_the_game_never_starts():
    host = FakeHost()
    _lol(host)
    job = service.open_game("league of legends", region="cn", host=host)
    host.procs.append(Proc("wegame.exe"))
    host.clock = service.GAME_WAIT_SEC + 1
    seen = service.job_status(job["id"], host)
    assert seen is not None
    assert seen["opened"] is False
    assert seen["state"] == "launcher_only"
    assert seen["launcher_running"] is True


def test_already_running_does_not_spawn_again():
    host = FakeHost()
    _lol(host)
    host.procs.append(Proc("League of Legends.exe"))
    job = service.open_game("英雄联盟", region="cn", host=host)
    assert job["opened"] is True
    assert job["state"] == "opened"
    assert host.spawned == []


def test_steam_library_launches_by_appid():
    host = FakeHost()
    exe = _steam(host, name="Counter-Strike 2", appid="730", installdir="Counter-Strike Global Offensive")
    job = service.open_game("cs2", region="intl", host=host)
    assert job["platform"] == "steam"
    assert job["installed"] is True
    assert host.spawned == [[exe, "-applaunch", "730"]]
    host.procs.append(Proc("cs2.exe"))
    seen = service.job_status(job["id"], host)
    assert seen is not None and seen["opened"] is True


def test_steam_title_not_in_library_only_opens_steam():
    host = FakeHost()
    exe = os.path.join("C:\\", "Steam", "steam.exe")
    host.add_file(exe)
    host.reg[("HKCU", r"Software\Valve\Steam", "SteamExe")] = exe
    job = service.open_game("艾尔登法环", region="intl", host=host)
    assert job["state"] == "not_installed"
    assert job["platform"] == "steam"
    assert host.spawned == [[exe]]


def test_epic_library_uses_launch_uri():
    host = FakeHost()
    exe = _epic(host)
    job = service.open_game("堡垒之夜", region="intl", host=host)
    assert job["platform"] == "epic"
    assert job["installed"] is True
    assert host.spawned[0][0] == exe
    uri = host.spawned[0][1]
    assert uri.startswith("com.epicgames.launcher://apps/")
    assert "fn%3A4fe75bbc5a674f4f9b356b5c90567da5%3AFortnite" in uri
    assert "action=launch" in uri
    assert "silent=true" in uri


def test_cn_prefers_wegame_when_both_libraries_have_the_name():
    host = FakeHost()
    _wegame(host)
    install = os.path.join("D:\\", "Hades")
    host.add_dir(install)
    host.subs[("HKCU", r"Software\Tencent")] = ["Hades"]
    host.reg[("HKCU", r"Software\Tencent\Hades", "InstallPath")] = install
    _steam(host, name="Hades", appid="1145360", installdir="Hades")
    cn = service.open_game("Hades", region="cn", host=host)
    assert cn["platform"] == "wegame"
    intl_host = FakeHost()
    _wegame(intl_host)
    intl_host.add_dir(install)
    intl_host.subs[("HKCU", r"Software\Tencent")] = ["Hades"]
    intl_host.reg[("HKCU", r"Software\Tencent\Hades", "InstallPath")] = install
    _steam(intl_host, name="Hades", appid="1145360", installdir="Hades")
    intl = service.open_game("Hades", region="intl", host=intl_host)
    assert intl["platform"] == "steam"
    assert intl_host.spawned[0][1:] == ["-applaunch", "1145360"]


def test_chat_opens_lol_and_ignores_other_opens():
    host = FakeHost()
    _lol(host)
    note = service.on_user_text("我要玩英雄联盟", "zh-CN", host)
    assert "英雄联盟" in note
    assert host.spawned == [["wegame://action=StartFor&game_id=26"]]
    before = len(host.spawned)
    assert service.on_user_text("打开塔罗", "zh-CN", host) == ""
    assert service.on_user_text("英雄联盟真好玩", "zh-CN", host) == ""
    assert service.on_user_text("今天天气不错", "zh-CN", host) == ""
    assert len(host.spawned) == before
    loose = FakeHost()
    _lol(loose)
    assert service.on_user_text("今天好想玩英雄联盟", "zh-CN", loose)
    assert loose.spawned == [["wegame://action=StartFor&game_id=26"]]


def test_unknown_game_is_not_found():
    host = FakeHost()
    _wegame(host)
    job = service.open_game("一个不存在的游戏", region="cn", host=host)
    assert job["state"] == "not_found"
    assert job["opened"] is False
    assert host.spawned == []


def test_shortcut_shell_is_not_the_game():
    host = FakeHost()
    exe = _wegame(host)
    install = os.path.join("E:\\", "Games", "英雄联盟")
    shell = os.path.join(install, "WeGameLauncher", "launcher.exe")
    client = os.path.join(install, "LeagueClient", "LeagueClient.exe")
    host.add_dir(install)
    host.add_dir(os.path.join(install, "WeGameLauncher"))
    host.add_dir(os.path.join(install, "LeagueClient"))
    host.add_file(shell)
    host.add_file(client)
    host.listing[_p(install)] = ["WeGameLauncher", "LeagueClient"]
    host.listing[_p(os.path.join(install, "WeGameLauncher"))] = ["launcher.exe"]
    host.listing[_p(os.path.join(install, "LeagueClient"))] = ["LeagueClient.exe"]
    host.subs[("HKCU", r"Software\Tencent")] = ["LOL"]
    host.reg[("HKCU", r"Software\Tencent\LOL", "InstallPath")] = install
    host.links = [Shortcut("英雄联盟WeGame版", shell, "", install)]
    host.procs.append(Proc("launcher.exe", shell))
    job = service.open_game("英雄联盟", region="cn", host=host)
    assert job["opened"] is False
    assert host.spawned[0] == [exe]
    assert host.spawned[1] == [client]
    host.procs.append(Proc("LeagueClient.exe", client))
    seen = service.job_status(job["id"], host)
    assert seen is not None and seen["opened"] is True


def test_epic_launcher_comes_from_its_shortcut():
    host = FakeHost()
    exe = os.path.join(
        "D:\\", "BingSoft", "Epic", "Epic Games", "Launcher", "Portal", "Binaries", "Win32",
        "EpicGamesLauncher.exe",
    )
    host.add_file(exe)
    host.links = [Shortcut("Epic Games Launcher", exe, "", "")]
    found = service.launchers(host)["epic"]
    assert found["found"] is True
    assert _p(found["exe"]) == _p(exe)


def test_extract_query_strips_politeness():
    assert extract_query("帮我打开一下英雄联盟吧") == "英雄联盟"
    assert extract_query("play fortnite please") == "fortnite"
    assert extract_query("打开视觉") == ""
