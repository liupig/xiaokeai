#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""xiaoke.ai 打包：A 程序包 + B 资源包。

用法（在 companion 目录，用后端 venv 的 Python）：
    python build_exe.py              # 只打 A（代码 + 运行时，日常迭代）
    python build_exe.py --content    # 只打 B（模型 / 动作 / 歌曲 / 语音权重）
    python build_exe.py --all        # A 和 B 都打
    python build_exe.py --skip-7z    # 只出目录，不打 7z

产物不进仓库：A 在 games 同级 xiaoke-ai-A-时间戳/，B 固定为 xiaoke-ai-B/。
一体包（旧）：python build_exe.py --full  → xiaoke-ai-时间戳/（代码+资源打一起）。
"""
from __future__ import annotations

import compileall
import json
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

# games 仓库根；产物默认放到它的上一级（与 games 同级），避免撑爆仓库。
# 盘空间不够时：set XIAOKE_OUT=H:\xiaoke-ai-packs
GAMES_ROOT = COMPANION.parent
OUT_ROOT = Path(os.environ.get("XIAOKE_OUT") or GAMES_ROOT.parent)
WORK_DIR = OUT_ROOT / "_xiaoke-ai_work"
EXE_NAME = "xiaoke-ai.exe"

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
    for pat in ("xiaoke-ai-A-*", "xiaoke-ai-*", "xiaoke_ai_*"):
        for p in OUT_ROOT.glob(pat):
            if not p.is_dir():
                continue
            if p.name.startswith("xiaoke-ai-B"):
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
    print("\n[3/8] 复制 Python 运行时")
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
            "gradio", "opencv", "scipy", "sklearn", "pandas", "matplotlib",
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


CONTENT_ASSET_DIRS = ("models", "motions", "cameras", "audio", "music")

# 本地 Qwen TTS 要的 CUDA / PyTorch，放进 B，A 只留瘦 Python。
ML_DIR_NAMES = {
    "torch", "torchaudio", "torchvision", "torchgen", "triton", "functorch", "nvidia",
}
ML_NAME_PREFIXES = ("torch-", "torchaudio-", "torchvision-", "triton", "nvidia-")


def _is_ml_name(name: str) -> bool:
    n = name.lower()
    if n in ML_DIR_NAMES:
        return True
    return n.startswith(ML_NAME_PREFIXES)


def ml_entries(site_packages: Path) -> list[Path]:
    if not site_packages.is_dir():
        return []
    return [p for p in site_packages.iterdir() if _is_ml_name(p.name)]


def strip_build_junk(root: Path) -> int:
    """运行时不需要 .lib / .pdb（torch 里 dnnl.lib 就有 2GB）。"""
    n = 0
    if not root.is_dir():
        return 0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".lib", ".pdb", ".a"}:
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
    return n


def copy_ml_runtime(src_sp: Path, dest_sp: Path) -> int:
    entries = ml_entries(src_sp)
    if not entries:
        print("  skip ML runtime（源里没有 torch）")
        return 0
    dest_sp.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in entries:
        dst = dest_sp / src.name
        if src.is_dir():
            robocopy(src, dst)
        else:
            shutil.copy2(src, dst)
        n += 1
        print(f"  ok ML {src.name}")
    junk = strip_build_junk(dest_sp)
    print(f"  推理库 → {dest_sp}（{n} 项，去掉 {junk} 个编译文件）")
    return n


def remove_ml_runtime(site_packages: Path) -> int:
    n = 0
    for p in ml_entries(site_packages):
        name = p.name
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.is_file():
            p.unlink(missing_ok=True)
        n += 1
        print(f"  已从 A 去掉 {name}")
    return n


def find_ml_source(*prefer: Path) -> Path | None:
    cands: list[Path] = []
    cands.extend(p for p in prefer if p is not None)
    prev = latest_pack_dir()
    if prev is not None:
        cands.append(prev / "runtime" / "Lib" / "site-packages")
    cands.append(OUT_ROOT / "xiaoke-ai-B" / "runtime" / "Lib" / "site-packages")
    cands.append(BACKEND / ".venv" / "Lib" / "site-packages")
    try:
        cands.append(base_prefix(venv_python()) / "Lib" / "site-packages")
    except Exception:
        pass
    seen: set[str] = set()
    for sp in cands:
        key = str(sp.resolve()) if sp.exists() else str(sp)
        if key in seen:
            continue
        seen.add(key)
        if (sp / "torch").is_dir():
            return sp
    return None


# 开发机 conda/venv 里有、发行版用不到的库（产品代码未 import）。
# 不要删 scipy：qwen-tts → librosa 启动就要它，上次精简后打包版 TTS 直接加载失败。
RUNTIME_DROP_NAMES = {
    "gradio", "gradio_client", "safehttpx",
    "cv2", "opencv_python", "opencv_contrib_python",
    "sklearn", "pandas", "matplotlib", "mpl_toolkits",
    "contourpy", "cycler", "kiwisolver", "fonttools", "fontTools",
    "mistral_common", "openai_harmony", "outlines", "outlines_core",
    "timm", "pythonwin",
    "IPython", "jupyter", "jupyter_client", "jupyter_core",
    "notebook", "nbconvert", "nbformat", "nbclient",
    "vllm", "ray",
}
RUNTIME_DROP_PREFIXES = (
    "gradio", "opencv", "scikit_learn", "scikit-learn",
    "sklearn", "pandas", "matplotlib",
    "mistral_common", "openai_harmony", "outlines", "timm",
    "jupyter", "ipython", "notebook", "nbconvert",
    "vllm", "ray",
)


def _is_drop_name(name: str) -> bool:
    n = name.lower()
    if n.startswith("~"):
        return True
    if n in {x.lower() for x in RUNTIME_DROP_NAMES}:
        return True
    for pfx in RUNTIME_DROP_PREFIXES:
        if n == pfx or n.startswith(pfx + "-") or n.startswith(pfx + "_"):
            return True
    return False


def strip_unused_site_packages(site_packages: Path) -> int:
    """删掉开发环境残留（gradio / opencv / sklearn 等），产品跑起来不需要。"""
    if not site_packages.is_dir():
        return 0
    n = 0
    freed = 0
    for p in list(site_packages.iterdir()):
        if not _is_drop_name(p.name):
            continue
        try:
            if p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        freed += f.stat().st_size
                shutil.rmtree(p, ignore_errors=True)
            elif p.is_file():
                freed += p.stat().st_size
                p.unlink(missing_ok=True)
            n += 1
            print(f"  去掉无关库 {p.name}")
        except OSError as exc:
            print(f"  skip {p.name}（{exc}）")
    print(f"  共去掉 {n} 项无关库（约 {freed / (1024 ** 2):.0f} MB）")
    return n


# qwen-tts → librosa 必依赖。开发机常靠 Anaconda 带一份，venv 里没有；
# 打包运行时是独立 Python，不补上就会 ModuleNotFoundError。
TTS_KEEP_PACKAGES = ("scipy", "numba", "llvmlite")


def ensure_tts_python_deps(dest_sp: Path) -> None:
    print("  检查 TTS Python 依赖")
    cands: list[Path] = [BACKEND / ".venv" / "Lib" / "site-packages"]
    try:
        cands.append(base_prefix(venv_python()) / "Lib" / "site-packages")
    except Exception:
        pass
    prev = latest_pack_dir()
    if prev is not None:
        cands.append(prev / "runtime" / "Lib" / "site-packages")
    for name in TTS_KEEP_PACKAGES:
        if (dest_sp / name).is_dir():
            print(f"  ok {name}")
            continue
        src_root = next((sp for sp in cands if (sp / name).is_dir()), None)
        if src_root is None:
            raise SystemExit(
                f"A 运行时缺少 {name}，Qwen TTS 无法加载。"
                f"请先执行：backend\\.venv\\Scripts\\pip install {name}"
            )
        robocopy(src_root / name, dest_sp / name)
        for info in src_root.glob(f"{name}-*.dist-info"):
            if info.is_dir():
                robocopy(info, dest_sp / info.name)
        print(f"  补上 {name} ← {src_root}")
        if not (dest_sp / name).is_dir():
            raise SystemExit(f"没能把 {name} 拷进 A 运行时")


def smoke_packed_tts_import(dist_dir: Path) -> None:
    """打包机上用 A 的独立 Python + B 的 torch 试 import，缺库当场失败。"""
    py = dist_dir / "runtime" / "python.exe"
    b_sp = OUT_ROOT / "xiaoke-ai-B" / "runtime" / "Lib" / "site-packages"
    if not py.is_file():
        print("  skip TTS import 冒烟（还没有 runtime python）")
        return
    code = (
        "import os, sys\n"
        f"sp = r'{b_sp}'\n"
        "sys.path.insert(0, sp)\n"
        "lib = os.path.join(sp, 'torch', 'lib')\n"
        "if os.path.isdir(lib) and hasattr(os, 'add_dll_directory'):\n"
        "    os.add_dll_directory(lib)\n"
        "from librosa.filters import mel\n"
        "import qwen_tts\n"
        "from qwen_tts import Qwen3TTSModel\n"
        "print('TTS_IMPORT_OK')\n"
    )
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    print("  TTS import 冒烟…")
    r = subprocess.run([str(py), "-c", code], env=env, capture_output=True, text=True)
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0 or "TTS_IMPORT_OK" not in out:
        raise SystemExit(f"打包后 TTS 无法 import：\n{out[-2400:]}")
    print("  ok TTS import 冒烟")


def slim_a_runtime(dist_dir: Path) -> None:
    """A 去掉 torch / CUDA（放到 B），再删开发残留和编译垃圾。"""
    print("\n[3b/8] 精简 A 运行时")
    src_sp = dist_dir / "runtime" / "Lib" / "site-packages"
    if (src_sp / "torch").is_dir():
        staged = WORK_DIR / "ml" / "Lib" / "site-packages"
        copy_ml_runtime(src_sp, staged)
        b_sp = OUT_ROOT / "xiaoke-ai-B" / "runtime" / "Lib" / "site-packages"
        copy_ml_runtime(src_sp, b_sp)
        marker = OUT_ROOT / "xiaoke-ai-B" / "xiaoke-content.json"
        if not marker.is_file():
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(
                json.dumps({"name": "xiaoke-ai-B", "kind": "content", "version": 1}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
        remove_ml_runtime(src_sp)
    else:
        print("  A 里没有 torch（已在 B 或不需要）")
    strip_unused_site_packages(src_sp)
    ensure_tts_python_deps(src_sp)
    smoke_packed_tts_import(dist_dir)
    junk = strip_build_junk(dist_dir / "runtime")
    print(f"  A runtime 去掉编译文件 {junk} 个")


def _copy_tools_7z(dist_dir: Path) -> None:
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


def step_copy_payload(dist_dir: Path) -> None:
    """A 包：前端、塔罗牌面、空数据目录。大资源去 B。"""
    print("\n[5/8] 复制前端与轻量资源（不含模型 / 语音权重）")
    web = dist_dir / "web"
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(FRONTEND / "dist", web)
    print("  ok web/")

    tarot = COMPANION / "assets" / "tarot"
    if tarot.is_dir():
        robocopy(tarot, dist_dir / "assets" / "tarot")
    else:
        (dist_dir / "assets" / "tarot").mkdir(parents=True, exist_ok=True)

    _copy_tools_7z(dist_dir)

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
    for d in ("tmp", "keepsakes", "mem0", "speech", "embed"):
        (dist_dir / "data" / d).mkdir(parents=True, exist_ok=True)

    for leaked in (dist_dir / ".env", data_dst / ".env", dist_dir / "content.path"):
        if leaked.is_file():
            leaked.unlink()
            print(f"  已删除误带的 {leaked.relative_to(dist_dir)}")
    example = COMPANION / "scripts" / ".env.example"
    if example.is_file():
        shutil.copy2(example, dist_dir / ".env.example")
        print("  ok .env.example（空模板，不含 Key）")


def step_copy_payload_full(dist_dir: Path) -> None:
    """旧一体包：A 的轻量文件 + 全部大资源。"""
    step_copy_payload(dist_dir)
    print("\n[5b/8] 一体包：再拷模型 / 动作 / 语音权重")
    for name in CONTENT_ASSET_DIRS:
        src = COMPANION / "assets" / name
        if src.exists():
            robocopy(src, dist_dir / "assets" / name)
        else:
            print(f"  skip assets/{name}")
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


def step_copy_content(dist_dir: Path) -> None:
    """B 包：模型、动作、镜头、歌曲、ASR / TTS / embedding。"""
    print("\n[*] 复制资源包 B")
    marker = {"name": "xiaoke-ai-B", "kind": "content", "version": 1}
    (dist_dir / "xiaoke-content.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("  ok xiaoke-content.json")
    for name in CONTENT_ASSET_DIRS:
        src = COMPANION / "assets" / name
        if src.exists():
            robocopy(src, dist_dir / "assets" / name)
        else:
            print(f"  skip assets/{name}")
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
    print("  PyTorch / CUDA …")
    src = find_ml_source(WORK_DIR / "ml" / "Lib" / "site-packages")
    if src is not None:
        copy_ml_runtime(src, dist_dir / "runtime" / "Lib" / "site-packages")
    else:
        print("  skip torch（找不到源，打 A 或一体包时会带上）")


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
    exe = dist_dir / EXE_NAME
    for legacy_name in ("Xiaoke.exe", "CompanionStudio.exe"):
        legacy = dist_dir / legacy_name
        if not exe.is_file() and legacy.is_file():
            legacy.rename(exe)
    if not exe.is_file():
        raise SystemExit(f"没有生成 {EXE_NAME}")
    print(f"  ok {exe}")


def write_readme_a(dist_dir: Path) -> None:
    print("\n[7/8] 写使用说明（A）")
    text = """xiaoke.ai 程序包 A
======================

这是可运行的程序（代码 + 瘦 Python + 窗口）。
角色、动作、歌曲、离线语音、记忆向量和 PyTorch/CUDA 在资源包 B。

第一次打开：设置 → 资源包 → 选 B 的目录（里面有 xiaoke-content.json），
关掉窗口再打开。路径记在本目录的 content.path，换 A 不用重选。

双击 xiaoke-ai.exe 打开自带 Chromium 窗口：

  前端  http://127.0.0.1:5211
  后端  http://127.0.0.1:5201

需要：Windows 10+。本地 Qwen TTS 建议有 NVIDIA 显卡。
聊天 Key 在设置面板填，或自己放 .env（参考 .env.example）。

请勿删除 runtime、app、web、electron。
"""
    (dist_dir / "使用说明.txt").write_text(text, encoding="utf-8")


def write_readme_full(dist_dir: Path) -> None:
    print("\n[7/8] 写使用说明（一体包）")
    text = """xiaoke.ai 本地版（一体包）
======================

双击 xiaoke-ai.exe 会打开自带的 Chromium 窗口（不需要安装 Chrome），
并同时启动前端和后端：

  前端页面  http://127.0.0.1:5211
  后端 API  http://127.0.0.1:5201

本目录已含角色、动作、歌曲和离线语音权重，不用再选资源包。

需要：Windows 10+、较新的 NVIDIA 显卡（本地语音合成）。
聊天 Key 在设置面板填，或自己放 .env（参考 .env.example）。

请勿删除 runtime、app、web、electron、assets、data。
"""
    (dist_dir / "使用说明.txt").write_text(text, encoding="utf-8")


def write_readme_b(dist_dir: Path) -> None:
    print("\n[*] 写使用说明（B）")
    text = """xiaoke.ai 资源包 B
======================

这是大资源，一般不用重打：

  assets/models     角色模型
  assets/motions    动作
  assets/cameras    镜头
  assets/audio      动作自带音频
  assets/music      舞蹈兜底曲库
  data/speech       SenseVoice + Qwen3-TTS
  data/embed        记忆用 MiniLM / fastembed
  runtime/Lib/.../torch   本地 Qwen TTS 用的 PyTorch / CUDA

解压后，在程序包 A 的设置 → 资源包里填本目录路径。
看到 xiaoke-content.json 就说明选对了。
"""
    (dist_dir / "使用说明.txt").write_text(text, encoding="utf-8")


def step_7z(dist_dir: Path) -> Path:
    print("\n[8/8] 打 7z 压缩包")
    logs = dist_dir / "logs"
    if logs.is_dir():
        shutil.rmtree(logs, ignore_errors=True)
    seven = find_7z()
    archive = dist_dir.with_suffix(".7z")
    # 先写到不跟目录同名的临时包。旧的 .7z 成功后再换，避免 7z 多线程
    # 在 Windows 上打不开源文件，或把 xiaoke-ai-B 目录冲掉。
    tmp = dist_dir.parent / f"{dist_dir.name}.part.7z"
    if tmp.exists():
        tmp.unlink()
    run([
        str(seven), "a", "-t7z",
        "-mx=3", "-mmt=1",
        str(tmp),
        str(dist_dir.name),
    ], cwd=dist_dir.parent)
    if not tmp.is_file() or tmp.stat().st_size < 1024:
        raise SystemExit("没有生成 7z")
    if not dist_dir.is_dir():
        raise SystemExit(f"压缩后源目录消失：{dist_dir}")
    if archive.exists():
        archive.unlink()
    tmp.replace(archive)
    size_gb = archive.stat().st_size / (1024 ** 3)
    print(f"  ok {archive}  ({size_gb:.2f} GB)")
    return archive


def cleanup_work() -> None:
    for d in (WORK_DIR, OUT_ROOT / "_xiaoke_ai_work"):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    leftover = COMPANION / "build"
    if leftover.exists():
        shutil.rmtree(leftover, ignore_errors=True)


def _archive(dist_dir: Path, skip_7z: bool) -> Path | None:
    if skip_7z:
        print("\n[8/8] 跳过 7z 压缩包")
        logs = dist_dir / "logs"
        if logs.is_dir():
            shutil.rmtree(logs, ignore_errors=True)
        return None
    return step_7z(dist_dir)


def build_a(py: Path, skip_7z: bool) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    dist_dir = OUT_ROOT / f"xiaoke-ai-A-{stamp}"
    dist_dir.mkdir(parents=True, exist_ok=True)
    print(f"A 输出: {dist_dir}")
    step_frontend(py)
    step_electron(dist_dir)
    step_copy_runtime(dist_dir, py)
    slim_a_runtime(dist_dir)
    step_encrypt_app(dist_dir, py)
    step_copy_payload(dist_dir)
    step_pyinstaller(dist_dir, py)
    write_readme_a(dist_dir)
    archive = _archive(dist_dir, skip_7z)
    print(f"  A 目录  {dist_dir / EXE_NAME}")
    if archive is not None:
        print(f"  A 压缩包 {archive}")
    return dist_dir


def build_full(py: Path, skip_7z: bool) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    dist_dir = OUT_ROOT / f"xiaoke-ai-{stamp}"
    dist_dir.mkdir(parents=True, exist_ok=True)
    print(f"一体包输出: {dist_dir}")
    step_frontend(py)
    step_electron(dist_dir)
    step_copy_runtime(dist_dir, py)
    junk = strip_build_junk(dist_dir / "runtime")
    print(f"  一体包 runtime 去掉编译文件 {junk} 个")
    strip_unused_site_packages(dist_dir / "runtime" / "Lib" / "site-packages")
    ensure_tts_python_deps(dist_dir / "runtime" / "Lib" / "site-packages")
    step_encrypt_app(dist_dir, py)
    step_copy_payload_full(dist_dir)
    step_pyinstaller(dist_dir, py)
    write_readme_full(dist_dir)
    archive = _archive(dist_dir, skip_7z)
    print(f"  一体包目录  {dist_dir / EXE_NAME}")
    if archive is not None:
        print(f"  一体包压缩包 {archive}")
    return dist_dir


def build_b(skip_7z: bool) -> Path:
    dist_dir = OUT_ROOT / "xiaoke-ai-B"
    dist_dir.mkdir(parents=True, exist_ok=True)
    print(f"B 输出: {dist_dir}")
    step_copy_content(dist_dir)
    write_readme_b(dist_dir)
    archive = _archive(dist_dir, skip_7z)
    print(f"  B 目录  {dist_dir}")
    if archive is not None:
        print(f"  B 压缩包 {archive}")
    return dist_dir


def main() -> None:
    skip_7z = "--skip-7z" in sys.argv
    want_full = "--full" in sys.argv
    only_b = ("--content" in sys.argv or "--b" in sys.argv) and "--all" not in sys.argv and not want_full
    want_b = only_b or "--all" in sys.argv
    want_a = (not only_b and not want_full) or "--all" in sys.argv
    if want_full:
        want_a = False
        want_b = False
    label = "一体包" if want_full else ("A+B" if want_a and want_b else "B" if want_b else "A")
    print("=" * 52)
    print("xiaoke.ai 打包  " + label)
    print("=" * 52)
    py = venv_python()
    print(f"Python: {py}")
    if skip_7z:
        print("本次跳过 7z 压缩包")
    if want_full:
        build_full(py, skip_7z)
    if want_a:
        build_a(py, skip_7z)
    if want_b:
        build_b(skip_7z)
    cleanup_work()
    print("\n" + "=" * 52)
    print("打包完成")
    print("=" * 52)


if __name__ == "__main__":
    os.chdir(COMPANION)
    main()
