"""统一路径定义：assets 文件仓库、数据库位置。

开发时：companion/ 为产品根，数据在 backend/data。
打包后：启动器设置 COMPANION_ROOT 为 exe 所在目录，数据在根下 data/。
"""
import os
from pathlib import Path


def _detect() -> tuple[Path, Path, Path]:
    packed = os.environ.get("COMPANION_ROOT")
    if packed:
        root = Path(packed).resolve()
        return root, root / "data", root / "web"
    here = Path(__file__).resolve().parent  # .../app
    pack_root = here.parent
    # 打包目录：和 CompanionStudio.exe / runtime 同级，不依赖环境变量
    if (pack_root / "runtime" / "python.exe").is_file():
        return pack_root, pack_root / "data", pack_root / "web"
    backend_dir = pack_root
    root = backend_dir.parent
    return root, backend_dir / "data", root / "frontend" / "dist"


ROOT_DIR, DATA_DIR, WEB_DIR = _detect()
ASSETS_DIR = ROOT_DIR / "assets"
MODELS_DIR = ASSETS_DIR / "models"
MOTIONS_DIR = ASSETS_DIR / "motions"
CAMERAS_DIR = ASSETS_DIR / "cameras"
AUDIO_DIR = ASSETS_DIR / "audio"
# 舞蹈兜底曲库：动作没绑 BGM 时从这里随机抽。不要放进 audio/，启动时会清掉未绑定文件。
MUSIC_DIR = ASSETS_DIR / "music"
DB_PATH = DATA_DIR / "app.db"
TMP_DIR = DATA_DIR / "tmp"
SPEECH_DIR = DATA_DIR / "speech"
EMBED_DIR = DATA_DIR / "embed"
MINILM_DIR = EMBED_DIR / "minilm"
FASTEMBED_DIR = EMBED_DIR / "fastembed"
KEEPSAKES_DIR = DATA_DIR / "keepsakes"
MEM0_DIR = DATA_DIR / "mem0"
LOGS_DIR = DATA_DIR / "logs"

for d in (MODELS_DIR, MOTIONS_DIR, CAMERAS_DIR, AUDIO_DIR, MUSIC_DIR, DATA_DIR, TMP_DIR, SPEECH_DIR, EMBED_DIR, MINILM_DIR, FASTEMBED_DIR, KEEPSAKES_DIR, MEM0_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)
