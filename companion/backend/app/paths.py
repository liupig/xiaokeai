"""统一路径定义：A 包是程序根，B 包是资源根。

开发时：companion/ 为产品根，数据在 backend/data，资产在 companion/assets。
打包后：启动器设置 COMPANION_ROOT 为 A 的 exe 目录；
资源（模型 / 动作 / 歌曲 / ASR / TTS / embedding / PyTorch）在 B。
B 的路径来自环境变量 COMPANION_CONTENT，或 A 目录下的 content.path。
未指定 B 时，若 A 自己带着 data/speech 或 assets/models（旧的一体包），就当 B=A。
"""
import os
import sys
from pathlib import Path

from fastapi.responses import FileResponse
from starlette.responses import PlainTextResponse
from starlette.types import Receive, Scope, Send


CONTENT_MARKER = "xiaoke-content.json"
CONTENT_FILE = "content.path"


def _detect() -> tuple[Path, Path, Path]:
    packed = os.environ.get("COMPANION_ROOT")
    if packed:
        root = Path(packed).resolve()
        return root, root / "data", root / "web"
    here = Path(__file__).resolve().parent  # .../app
    pack_root = here.parent
    if (pack_root / "runtime" / "python.exe").is_file():
        return pack_root, pack_root / "data", pack_root / "web"
    backend_dir = pack_root
    root = backend_dir.parent
    return root, backend_dir / "data", root / "frontend" / "dist"


def _read_content_file(root: Path) -> Path | None:
    p = root / CONTENT_FILE
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8").strip().strip('"').strip("'")
    except OSError:
        return None
    if not text:
        return None
    cand = Path(text)
    if not cand.is_absolute():
        cand = (root / cand).resolve()
    else:
        cand = cand.resolve()
    return cand if cand.is_dir() else None


def looks_like_content(path: Path) -> bool:
    p = path.resolve()
    if not p.is_dir():
        return False
    if (p / CONTENT_MARKER).is_file():
        return True
    if (p / "assets" / "models").is_dir():
        return True
    if (p / "assets" / "motions").is_dir():
        return True
    if (p / "data" / "speech").is_dir() or (p / "speech").is_dir():
        return True
    if (p / "data" / "embed").is_dir() or (p / "embed").is_dir():
        return True
    if (p / "runtime" / "Lib" / "site-packages" / "torch").is_dir():
        return True
    return False


def _monolithic(root: Path) -> bool:
    speech = root / "data" / "speech"
    if speech.is_dir() and any(speech.iterdir()):
        return True
    models = root / "assets" / "models"
    skip = {".gitkeep", "README.txt", "放什么.txt"}
    if models.is_dir() and any(p.name not in skip for p in models.iterdir()):
        return True
    return False


def _sibling_content(app_root: Path) -> Path | None:
    """A 和 B 解压到同一层时自动找到，不用手填路径。"""
    for cand in (app_root.parent / "xiaoke-ai-B", app_root / "xiaoke-ai-B"):
        try:
            p = cand.resolve()
        except OSError:
            continue
        if p.is_dir() and (p / CONTENT_MARKER).is_file():
            return p
    return None


def resolve_content_root(app_root: Path) -> Path | None:
    env = (os.environ.get("COMPANION_CONTENT") or "").strip()
    if env:
        cand = Path(env)
        if not cand.is_absolute():
            cand = (app_root / cand).resolve()
        else:
            cand = cand.resolve()
        if cand.is_dir():
            return cand
    file_path = _read_content_file(app_root)
    if file_path:
        return file_path
    sibling = _sibling_content(app_root)
    if sibling is not None:
        try:
            write_content_path(app_root, sibling)
        except OSError:
            pass
        return sibling
    if _monolithic(app_root):
        return app_root
    return None


def is_packed(app_root: Path | None = None) -> bool:
    root = app_root or ROOT_DIR
    return bool(os.environ.get("COMPANION_ROOT")) or (root / "runtime" / "python.exe").is_file()


def write_content_path(app_root: Path, content: Path) -> None:
    (app_root / CONTENT_FILE).write_text(str(content.resolve()), encoding="utf-8")


def _speech_dir(content: Path, data: Path) -> Path:
    for cand in (content / "data" / "speech", content / "speech"):
        if cand.is_dir():
            return cand
    return content / "data" / "speech" if content != ROOT_DIR else data / "speech"


def _embed_dir(content: Path, data: Path) -> Path:
    for cand in (content / "data" / "embed", content / "embed"):
        if cand.is_dir():
            return cand
    return content / "data" / "embed" if content != ROOT_DIR else data / "embed"


def ml_site_packages(content: Path | None = None) -> Path | None:
    """B（或一体包自己）里的 PyTorch 目录。A 瘦包没有 torch。"""
    roots: list[Path] = []
    if content is not None:
        roots.append(content)
    env = (os.environ.get("COMPANION_CONTENT") or "").strip()
    if env:
        roots.append(Path(env))
    packed = (os.environ.get("COMPANION_ROOT") or "").strip()
    if packed:
        roots.append(Path(packed))
    seen: set[str] = set()
    for root in roots:
        try:
            p = (root / "runtime" / "Lib" / "site-packages").resolve()
        except OSError:
            continue
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        if (p / "torch").is_dir():
            return p
    return None


def attach_ml_runtime(content: Path | None = None) -> Path | None:
    """把 B 里的 torch 挂到 sys.path / PATH，供 Qwen TTS 加载。"""
    sp = ml_site_packages(content)
    if sp is None:
        return None
    text = str(sp)
    if text not in sys.path:
        sys.path.insert(0, text)
    extras = [sp / "torch" / "lib", sp / "nvidia"]
    nvidia = sp / "nvidia"
    if nvidia.is_dir():
        extras.extend(nvidia.glob("*/bin"))
        extras.extend(nvidia.glob("*/lib"))
    prepend: list[str] = []
    for extra in extras:
        if not extra.is_dir():
            continue
        prepend.append(str(extra))
        adder = getattr(os, "add_dll_directory", None)
        if callable(adder):
            try:
                adder(str(extra))
            except OSError:
                pass
    if prepend:
        os.environ["PATH"] = os.pathsep.join(prepend + [os.environ.get("PATH", "")])
    return sp


ROOT_DIR, DATA_DIR, WEB_DIR = _detect()
CONTENT_DIR = resolve_content_root(ROOT_DIR)
attach_ml_runtime(CONTENT_DIR)
_asset_home = (CONTENT_DIR / "assets") if CONTENT_DIR else (ROOT_DIR / "assets")
ASSETS_DIR = _asset_home
MODELS_DIR = ASSETS_DIR / "models"
MOTIONS_DIR = ASSETS_DIR / "motions"
CAMERAS_DIR = ASSETS_DIR / "cameras"
AUDIO_DIR = ASSETS_DIR / "audio"
MUSIC_DIR = ASSETS_DIR / "music"
DB_PATH = DATA_DIR / "app.db"
TMP_DIR = DATA_DIR / "tmp"
SPEECH_DIR = _speech_dir(CONTENT_DIR, DATA_DIR) if CONTENT_DIR else (DATA_DIR / "speech")
EMBED_DIR = _embed_dir(CONTENT_DIR, DATA_DIR) if CONTENT_DIR else (DATA_DIR / "embed")


def current_content_dir() -> Path | None:
    """再读一遍 content.path / 旁边的 B，设置后不用只认启动时的目录。"""
    return resolve_content_root(ROOT_DIR)


def current_speech_dir() -> Path:
    content = current_content_dir()
    if content is None:
        return DATA_DIR / "speech"
    return _speech_dir(content, DATA_DIR)
MINILM_DIR = EMBED_DIR / "minilm"
FASTEMBED_DIR = EMBED_DIR / "fastembed"
KEEPSAKES_DIR = DATA_DIR / "keepsakes"
MEM0_DIR = DATA_DIR / "mem0"
LOGS_DIR = DATA_DIR / "logs"
LOCAL_ASSETS_DIR = ROOT_DIR / "assets"


def content_found() -> dict[str, bool]:
    return {
        "models": MODELS_DIR.is_dir() and any(MODELS_DIR.rglob("*.pmx")),
        "motions": MOTIONS_DIR.is_dir() and any(MOTIONS_DIR.rglob("*.vmd")),
        "cameras": CAMERAS_DIR.is_dir() and any(CAMERAS_DIR.rglob("*.vmd")),
        "music": MUSIC_DIR.is_dir() and any(p.is_file() for p in MUSIC_DIR.rglob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}),
        "speech": SPEECH_DIR.is_dir() and any(SPEECH_DIR.iterdir()),
        "embed": MINILM_DIR.is_dir() or (FASTEMBED_DIR.is_dir() and any(FASTEMBED_DIR.iterdir())),
        "torch": ml_site_packages(CONTENT_DIR) is not None,
    }


def content_status() -> dict:
    found = content_found()
    ok = bool(CONTENT_DIR) and looks_like_content(CONTENT_DIR)
    return {
        "packed": is_packed(),
        "path": str(CONTENT_DIR) if CONTENT_DIR else "",
        "ok": ok,
        "found": found,
    }


def asset_roots() -> list[Path]:
    roots = [ASSETS_DIR.resolve()]
    local = LOCAL_ASSETS_DIR.resolve()
    if local != roots[0]:
        roots.append(local)
    return roots


def resolve_asset_file(rel: str) -> Path | None:
    """B 的 assets 优先，找不到再读 A 自带的塔罗等。"""
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if rel.startswith("assets/"):
        rel = rel[7:]
    if not rel or ".." in Path(rel).parts:
        return None
    for root in asset_roots():
        fp = (root / rel).resolve()
        try:
            fp.relative_to(root)
        except ValueError:
            continue
        if fp.is_file():
            return fp
    return None


def asset_static():
    """兼容旧 mount：内部按 HTTP path 找文件。"""
    class _App:
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                raise RuntimeError("asset_static only handles http")
            rel = (scope.get("path") or "").lstrip("/")
            fp = resolve_asset_file(rel)
            if fp is None:
                await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)
                return
            await FileResponse(fp)(scope, receive, send)
    return _App()


for d in (
    MODELS_DIR, MOTIONS_DIR, CAMERAS_DIR, AUDIO_DIR, MUSIC_DIR,
    DATA_DIR, TMP_DIR, SPEECH_DIR, EMBED_DIR, MINILM_DIR, FASTEMBED_DIR,
    KEEPSAKES_DIR, MEM0_DIR, LOGS_DIR, LOCAL_ASSETS_DIR / "tarot",
):
    d.mkdir(parents=True, exist_ok=True)
