#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Companion Studio 大打包：做成双击即开的加密 exe 目录。

用法（在 companion 目录，用后端 venv 的 Python）：
    python build_exe.py
    python build_exe.py --skip-7z   # 只出目录，不打 7z

产物不进仓库：输出到与 games 同级的 xiaoke_ai_YYYYMMDDHHMMSS/，
默认再打一份同名 7z。中间构建目录也在 games 同级。
"""
from __future__ import annotations

import compileall
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

COMPANION = Path(__file__).resolve().parent
BACKEND = COMPANION / "backend"
FRONTEND = COMPANION / "frontend"
DESKTOP = COMPANION / "desktop"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"

# 国内拉 Electron/Chromium 预编译包（不装 Chrome，内核打进发行目录）
ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"

# games 仓库根；产物放到它的上一级（与 games 同级），避免撑爆仓库
GAMES_ROOT = COMPANION.parent
OUT_ROOT = GAMES_ROOT.parent
WORK_DIR = OUT_ROOT / "_xiaoke_ai_work"

SEVEN_ZIP_CANDIDATES = (
    Path(r"D:\BingSoft\7-Zip\7z.exe"),
    Path(r"C:\Program Files\7-Zip\7z.exe"),
    Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
)

SPEECH_KEEP = (
    "sensevoice",
    "qwen3-tts-0.6b-customvoice",
    "qwen3-tts-1.7b-customvoice",
    "qwen3-tts-tokenizer",
)


def run(cmd, cwd=None, check=True, env=None):
    print(f"\n>> {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, cwd=cwd or COMPANION, env=env)
    if check and r.returncode != 0:
        raise SystemExit(f"命令失败（{r.returncode}）：{cmd[0]}")
    return r


def robocopy(src: Path, dst: Path, extra_xd=None) -> None:
    if not src.exists():
        print(f"  skip（不存在）{src}")
        return
    dst.mkdir(parents=True, exist_ok=True)
    xd = ["__pycache__", ".git", ".venv", "conda-meta", "pkgs", "conda-meta"]
    if extra_xd:
        xd.extend(extra_xd)
    cmd = [
        "robocopy", str(src), str(dst),
        "/E", "/COPY:DAT", "/R:1", "/W:1",
        "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np",
        "/XF", "*.pyc",
    ]
    for name in xd:
        cmd.extend(["/XD", name])
    r = subprocess.run(cmd)
    if r.returncode >= 8:
        raise SystemExit(f"robocopy 失败 {r.returncode}: {src} -> {dst}")
    print(f"  ok {src} -> {dst}")


def venv_python() -> Path:
    if VENV_PY.is_file():
        return VENV_PY
    return Path(sys.executable)


def base_prefix(py: Path) -> Path:
    out = subprocess.check_output(
        [str(py), "-c", "import sys; print(sys.base_prefix)"],
        text=True,
    ).strip()
    return Path(out)


def find_7z() -> Path:
    for p in SEVEN_ZIP_CANDIDATES:
        if p.is_file():
            return p
    w = shutil.which("7z") or shutil.which("7z.exe")
    if w:
        return Path(w)
    raise SystemExit(
        "找不到 7z.exe。请安装 7-Zip，或把它放到 D:\\BingSoft\\7-Zip\\7z.exe"
    )


def latest_pack_dir(exclude: Path | None = None) -> Path | None:
    cands = []
    for p in OUT_ROOT.glob("xiaoke_ai_*"):
        if not p.is_dir():
            continue
        if exclude and p.resolve() == exclude.resolve():
            continue
        if (p / "runtime" / "python.exe").is_file():
            cands.append(p)
    if not cands:
        return None
    return max(cands, key=lambda p: p.name)


def step_frontend(py: Path) -> None:
    print("\n[1/8] 构建前端（压缩混淆）")
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("找不到 npm，请先安装 Node.js")
    if not (FRONTEND / "node_modules").is_dir():
        run([npm, "install", "--legacy-peer-deps"], cwd=FRONTEND)
    else:
        run([npm, "install", "--legacy-peer-deps", "terser@^5.31.0"], cwd=FRONTEND)
    run([npm, "run", "build"], cwd=FRONTEND)
    dist = FRONTEND / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("前端构建失败：没有 dist/index.html")


def npm_env() -> dict:
    env = os.environ.copy()
    env.setdefault("ELECTRON_MIRROR", ELECTRON_MIRROR)
    return env


def step_electron(dist_dir: Path) -> None:
    print("\n[2/8] 嵌入 Chromium 内核（Electron，不依赖本机 Chrome）")
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("找不到 npm，请先安装 Node.js（打包机用来下载 Electron 内核）")
    if not (DESKTOP / "main.js").is_file() or not (DESKTOP / "package.json").is_file():
        raise SystemExit(f"缺少桌面壳：{DESKTOP / 'main.js'}")
    run([npm, "install"], cwd=DESKTOP, env=npm_env())
    src = DESKTOP / "node_modules" / "electron" / "dist"
    if not (src / "electron.exe").is_file():
        raise SystemExit(f"Electron 内核下载失败：没有 {src / 'electron.exe'}")
    dest = dist_dir / "electron"
    if dest.exists():
        shutil.rmtree(dest)
    robocopy(src, dest)
    app_dir = dest / "resources" / "app"
    if app_dir.exists():
        shutil.rmtree(app_dir)
    app_dir.mkdir(parents=True, exist_ok=True)
    for name in ("main.js", "preload.js", "package.json", "icon.png"):
        src_file = DESKTOP / name
        if src_file.is_file():
            shutil.copy2(src_file, app_dir / name)
        elif name != "icon.png":
            raise SystemExit(f"缺少桌面壳文件：{src_file}")
    if not (dest / "electron.exe").is_file():
        raise SystemExit("electron/electron.exe 缺失")
    print(f"  ok {dest / 'electron.exe'}")


def step_copy_runtime(dist_dir: Path, py: Path) -> None:
    print("\n[3/8] 复制 Python 运行时（含 torch / CUDA）")
    runtime = dist_dir / "runtime"
    if (runtime / "python.exe").is_file():
        print(f"  已有 runtime，跳过重拷（{runtime}）")
        venv_sp = BACKEND / ".venv" / "Lib" / "site-packages"
        if venv_sp.is_dir():
            robocopy(venv_sp, runtime / "Lib" / "site-packages")
        return
    prev = latest_pack_dir(exclude=dist_dir)
    if prev is not None:
        print(f"  从上一版拷 runtime：{prev}")
        robocopy(prev / "runtime", runtime)
        venv_sp = BACKEND / ".venv" / "Lib" / "site-packages"
        if venv_sp.is_dir():
            robocopy(venv_sp, runtime / "Lib" / "site-packages")
        if (runtime / "python.exe").is_file():
            return
        print("  上一版 runtime 不完整，改从当前 Python 环境拷")
    src = base_prefix(py)
    print(f"  base_prefix = {src}")
    robocopy(
        src,
        runtime,
        extra_xd=[
            "Doc", "docs", "include", "man", "tcl", "conda-meta", "pkgs", "etc",
            "vllm", "ray", "IPython", "jupyter", "notebook", "nbconvert",
        ],
    )
    venv_sp = BACKEND / ".venv" / "Lib" / "site-packages"
    if venv_sp.is_dir():
        print("  叠加 venv site-packages")
        robocopy(venv_sp, runtime / "Lib" / "site-packages")
    if not (runtime / "python.exe").is_file():
        raise SystemExit("runtime/python.exe 缺失")


def step_encrypt_app(dist_dir: Path, py: Path) -> None:
    print("\n[4/8] 加密后端源码（编译为 .pyc，删除 .py）")
    dest = dist_dir / "app"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        BACKEND / "app",
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    ok = compileall.compile_dir(str(dest), force=True, legacy=True, quiet=1)
    if not ok:
        raise SystemExit("compileall 失败")
    n = 0
    for p in dest.rglob("*.py"):
        p.unlink()
        n += 1
    print(f"  已删除 {n} 个 .py，仅保留字节码")


if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from app.personas import GENERIC_PERSONA, QINGXIAO_GREETING, QINGXIAO_PERSONA

PACK_KEEP_TABLES = ("cam_review", "character", "asset")


def _pack_asset_ok(path_str: str) -> bool:
    raw = (path_str or "").replace("\\", "/")
    return bool(raw) and (COMPANION / "assets" / raw).is_file()


def _pack_character_name(name: str, label: str) -> str:
    if name == "qingxiao":
        return "清宵"
    text = (label or name or "").strip()
    if "_by_" in text:
        text = text.split("_by_")[0]
    return text.strip(" _") or name or "角色"


def export_pack_db(src: Path, dst: Path) -> dict:
    """镜头审查 + 默认可选角色 + 资产表（含舞蹈配乐绑定）。不含密钥、聊天、记忆。"""
    import sqlite3
    from datetime import datetime, timezone

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
    finally:
        src_conn.close()
    tables = [
        r[0]
        for r in dst_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    for name in tables:
        if name not in PACK_KEEP_TABLES:
            dst_conn.execute(f'DELETE FROM "{name}"')
    if "asset" in tables:
        gone = [
            row[0]
            for row in dst_conn.execute("SELECT id, path FROM asset")
            if not _pack_asset_ok(row[1])
        ]
        if gone:
            dst_conn.executemany("DELETE FROM asset WHERE id = ?", [(i,) for i in gone])
    if "character" in tables:
        dst_conn.execute(
            "DELETE FROM character WHERE model_asset_id NOT IN "
            "(SELECT id FROM asset WHERE kind = 'model')"
        )
        used = {
            int(r[0])
            for r in dst_conn.execute("SELECT model_asset_id FROM character")
            if r[0] is not None
        }
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
        for row in dst_conn.execute(
            "SELECT id, name, label, path, fmt FROM asset WHERE kind = 'model'"
        ):
            aid, name, label, path, fmt = row
            if (fmt or "").lower() != "pmx" or not _pack_asset_ok(path):
                continue
            if int(aid) in used:
                continue
            qx = name == "qingxiao"
            char_name = _pack_character_name(name, label)
            dst_conn.execute(
                "INSERT INTO character "
                "(name, model_asset_id, persona, greeting, voice, emotion_map, "
                "idle_motion, created_at) VALUES (?, ?, ?, ?, '', '{}', '', ?)",
                (
                    char_name,
                    aid,
                    QINGXIAO_PERSONA if qx else GENERIC_PERSONA.format(name=char_name),
                    QINGXIAO_GREETING if qx else "",
                    now,
                ),
            )
    dst_conn.commit()
    counts = {
        "cam_review": 0,
        "character": 0,
        "asset": 0,
    }
    for key in counts:
        if key in tables:
            counts[key] = int(
                dst_conn.execute(f'SELECT COUNT(*) FROM "{key}"').fetchone()[0]
            )
    dst_conn.execute("VACUUM")
    dst_conn.close()
    return counts


def step_copy_payload(dist_dir: Path) -> None:
    print("\n[5/8] 复制前端、3D 资产、语音模型")
    web = dist_dir / "web"
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(FRONTEND / "dist", web)
    print("  ok web/")

    robocopy(COMPANION / "assets", dist_dir / "assets")

    tools = dist_dir / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    seven_src = None
    for cand in (
        Path(r"D:\BingSoft\7-Zip"),
        Path(r"C:\Program Files\7-Zip"),
        Path(r"C:\Program Files (x86)\7-Zip"),
    ):
        if (cand / "7z.exe").is_file():
            seven_src = cand
            break
    if seven_src:
        for name in ("7z.exe", "7z.dll"):
            src = seven_src / name
            if src.is_file():
                shutil.copy2(src, tools / name)
        print(f"  ok tools/7z.exe ← {seven_src}")
    else:
        print("  skip 7z（没找到 7-Zip，rar 解压可能失败）")

    data_dst = dist_dir / "data"
    data_dst.mkdir(parents=True, exist_ok=True)
    db_src = BACKEND / "data" / "app.db"
    if db_src.is_file():
        n = export_pack_db(db_src, data_dst / "app.db")
        print(
            f"  ok data/app.db（审查 {n['cam_review']} / "
            f"角色 {n['character']} / 资产 {n['asset']}，不含密钥/聊天）"
        )
    else:
        print("  skip app.db（开发库不存在）")
    review_src = BACKEND / "data" / "cam_review.json"
    if review_src.is_file():
        shutil.copy2(review_src, data_dst / "cam_review.json")
        print("  ok data/cam_review.json")

    speech_src = BACKEND / "data" / "speech"
    speech_dst = dist_dir / "data" / "speech"
    speech_dst.mkdir(parents=True, exist_ok=True)
    for name in SPEECH_KEEP:
        src = speech_src / name
        if src.exists():
            print(f"  语音模型 {name} …")
            robocopy(src, speech_dst / name)
        else:
            print(f"  skip {name}")
    for d in ("tmp", "keepsakes", "mem0", "embed"):
        (dist_dir / "data" / d).mkdir(parents=True, exist_ok=True)
    embed_src = BACKEND / "data" / "embed" / "minilm"
    if embed_src.exists():
        print("  embedding MiniLM …")
        robocopy(embed_src, dist_dir / "data" / "embed" / "minilm")
    else:
        print("  skip MiniLM")
    fastembed_src = BACKEND / "data" / "embed" / "fastembed"
    if fastembed_src.exists():
        print("  embedding fastembed cache …")
        robocopy(fastembed_src, dist_dir / "data" / "embed" / "fastembed")
    else:
        print("  skip fastembed cache")

    # 绝不拷开发机 .env：里面是 API Key。目标机自己填设置面板，或旁放一份空模板。
    for leaked in (dist_dir / ".env", data_dst / ".env"):
        if leaked.is_file():
            leaked.unlink()
            print(f"  已删除误带的 {leaked.relative_to(dist_dir)}")
    example = COMPANION / "scripts" / ".env.example"
    if example.is_file():
        shutil.copy2(example, dist_dir / ".env.example")
        print("  ok .env.example（空模板，不含 Key）")


def step_pyinstaller(dist_dir: Path, py: Path) -> None:
    print("\n[6/8] 打包启动器 exe（源码进 exe）")
    run([str(py), "-m", "pip", "install", "-q", "pyinstaller"])
    spec = COMPANION / "build_exe.spec"
    work = WORK_DIR / "pyi"
    work.mkdir(parents=True, exist_ok=True)
    run([
        str(py), "-m", "PyInstaller",
        "--clean", "--noconfirm",
        "--distpath", str(dist_dir),
        "--workpath", str(work),
        str(spec),
    ])
    exe = dist_dir / "CompanionStudio.exe"
    if not exe.is_file():
        raise SystemExit("没有生成 CompanionStudio.exe")
    print(f"  ok {exe}")


def write_readme(dist_dir: Path) -> None:
    print("\n[7/8] 写使用说明")
    text = """小可 AI 本地版
======================

双击 CompanionStudio.exe 会打开自带的 Chromium 窗口（不需要安装 Chrome），
并同时启动前端和后端（和开发环境不是同一套端口）：

  桌面窗口  内嵌 Chromium（electron/ 目录）
  前端页面  http://127.0.0.1:9615
  后端 API  http://127.0.0.1:9610

开发环境仍是 5175 / 8600，两边可以一起开，不会抢端口。

需要：Windows 10+、较新的 NVIDIA 显卡（本地语音合成）。

聊天用的大模型 Key 请在设置面板填写，或在本目录自己放一份 .env
（可参考旁边的 .env.example）。打包不会带开发机密钥。

请勿删除 runtime、app、web、electron、assets、data。
关掉窗口或黑窗即退出前后端。
数据库带镜头审查、默认可选角色，以及舞蹈配乐绑定；不含开发机的聊天记录。
"""
    (dist_dir / "使用说明.txt").write_text(text, encoding="utf-8")


def step_7z(dist_dir: Path) -> Path:
    print("\n[8/8] 打 7z 压缩包")
    logs = dist_dir / "logs"
    if logs.is_dir():
        shutil.rmtree(logs, ignore_errors=True)
    seven = find_7z()
    archive = dist_dir.with_suffix(".7z")
    if archive.exists():
        archive.unlink()
    # 压缩包内保留文件夹，解压后就是 xiaoke_ai_时间戳/
    run([
        str(seven), "a", "-t7z",
        "-mx=3", "-mmt=on",
        str(archive),
        str(dist_dir.name),
    ], cwd=dist_dir.parent)
    if not archive.is_file():
        raise SystemExit("没有生成 7z")
    size_gb = archive.stat().st_size / (1024 ** 3)
    print(f"  ok {archive}  ({size_gb:.2f} GB)")
    return archive


def cleanup_work() -> None:
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    leftover = COMPANION / "build"
    if leftover.exists():
        shutil.rmtree(leftover, ignore_errors=True)


def main() -> None:
    skip_7z = "--skip-7z" in sys.argv
    print("=" * 52)
    print("小可 AI 大打包")
    print("=" * 52)
    py = venv_python()
    print(f"Python: {py}")
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    dist_dir = OUT_ROOT / f"xiaoke_ai_{stamp}"
    dist_dir.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {dist_dir}")
    print(f"（与 games 同级，不进仓库）")
    if skip_7z:
        print("本次跳过 7z 压缩包")

    step_frontend(py)
    step_electron(dist_dir)
    step_copy_runtime(dist_dir, py)
    step_encrypt_app(dist_dir, py)
    step_copy_payload(dist_dir)
    step_pyinstaller(dist_dir, py)
    write_readme(dist_dir)
    archive = None
    if skip_7z:
        print("\n[8/8] 跳过 7z 压缩包")
        logs = dist_dir / "logs"
        if logs.is_dir():
            shutil.rmtree(logs, ignore_errors=True)
    else:
        archive = step_7z(dist_dir)
    cleanup_work()

    print("\n" + "=" * 52)
    print("打包完成")
    print(f"  目录  {dist_dir / 'CompanionStudio.exe'}")
    if archive is not None:
        print(f"  压缩包 {archive}")
        print("把整个文件夹或 7z 拷走即可。")
    else:
        print("  压缩包 （已跳过）")
        print("把整个文件夹拷走即可。")
    print("=" * 52)


if __name__ == "__main__":
    os.chdir(COMPANION)
    main()
