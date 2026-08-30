"""统一路径定义：assets 文件仓库、数据库位置。"""
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
ASSETS_DIR = ROOT_DIR / "assets"
MODELS_DIR = ASSETS_DIR / "models"
MOTIONS_DIR = ASSETS_DIR / "motions"
CAMERAS_DIR = ASSETS_DIR / "cameras"
AUDIO_DIR = ASSETS_DIR / "audio"
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
TMP_DIR = DATA_DIR / "tmp"
SPEECH_DIR = DATA_DIR / "speech"
KEEPSAKES_DIR = DATA_DIR / "keepsakes"
MEM0_DIR = DATA_DIR / "mem0"

for d in (MODELS_DIR, MOTIONS_DIR, CAMERAS_DIR, AUDIO_DIR, DATA_DIR, TMP_DIR, SPEECH_DIR, KEEPSAKES_DIR, MEM0_DIR):
    d.mkdir(parents=True, exist_ok=True)
