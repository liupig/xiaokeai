"""用本地 .env 里的两把编译密钥给黑盒盖章，再编译成扩展模块。缺一把就打不出官方版本。"""
import hashlib
import os
import shutil
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from Cython.Build import cythonize
from setuptools import Extension, setup

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT.parent.parent / "scripts" / ".env"
PUB_FILE = ROOT / "chain.pub"
SOURCE = ROOT / "coins_box.py"
STAGED = ROOT / "sealed" / "coins_box.py"
GENESIS = hashlib.sha256(b"xiaoke-chain/1|genesis").hexdigest()


def _fields(path: Path) -> dict:
    found = {}
    if not path.is_file():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        found[key.strip()] = value.strip().lower()
    return found


def _load():
    if not ENV_FILE.is_file():
        sys.exit("缺少 companion/scripts/.env。编译密钥要写在这个本地文件里。")
    if not PUB_FILE.is_file():
        sys.exit("缺少公共密钥 native/chain.pub。")
    secret = _fields(ENV_FILE)
    public = _fields(PUB_FILE)
    priv_hex = secret.get("COIN_BOX_PRIV", "")
    priv2_hex = secret.get("COIN_BOX_PRIV2", "")
    pepper_hex = secret.get("COIN_BOX_PEPPER", "")
    pepper2_hex = secret.get("COIN_BOX_PEPPER2", "")
    if len(priv_hex) != 64 or len(priv2_hex) != 64 or priv_hex == priv2_hex:
        sys.exit("companion/scripts/.env 里的两把编译密钥不完整。")
    if len(pepper_hex) != 32 or len(pepper2_hex) != 32 or pepper_hex == pepper2_hex:
        sys.exit("companion/scripts/.env 里的两把封账密钥不完整。")
    try:
        priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
        priv2 = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv2_hex))
        pepper = bytes.fromhex(pepper_hex)
        pepper2 = bytes.fromhex(pepper2_hex)
    except ValueError:
        sys.exit("companion/scripts/.env 里的密钥不是有效的十六进制。")
    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    pub2 = priv2.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    if public.get("pub") != pub or public.get("pub2") != pub2:
        sys.exit("编译密钥和公共密钥不是一对。")
    if public.get("pepper_sha256") != hashlib.sha256(pepper).hexdigest():
        sys.exit(".env 里的第一把封账密钥和公共密钥登记的不一致。")
    if public.get("pepper2_sha256") != hashlib.sha256(pepper2).hexdigest():
        sys.exit(".env 里的第二把封账密钥和公共密钥登记的不一致。")
    return priv, priv2, pepper, pepper2, pub, pub2


def _stamp_msg(pub: str, pub2: str, pepper: bytes, pepper2: bytes) -> bytes:
    return f"xiaokeai-box/3|{pub}|{pub2}|{pepper.hex()}|{pepper2.hex()}|{GENESIS}".encode()


def _raw_hex(key: Ed25519PrivateKey) -> str:
    return key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()


def _stage(pub: str, pub2: str, pepper: bytes, pepper2: bytes, priv: Ed25519PrivateKey, priv2: Ed25519PrivateKey) -> None:
    mask = os.urandom(16)
    hidden = bytes(left ^ right for left, right in zip(pepper, mask))
    mask2 = os.urandom(16)
    hidden2 = bytes(left ^ right for left, right in zip(pepper2, mask2))
    msg = _stamp_msg(pub, pub2, pepper, pepper2)
    stamp = priv.sign(msg).hex()
    stamp2 = priv2.sign(msg).hex()
    text = SOURCE.read_text(encoding="utf-8")
    replacements = {
        '_PUB = ""  # STAMP_PUB': f'_PUB = "{pub}"  # STAMP_PUB',
        '_PUB2 = ""  # STAMP_PUB2': f'_PUB2 = "{pub2}"  # STAMP_PUB2',
        '_STAMP = ""  # STAMP_SIG': f'_STAMP = "{stamp}"  # STAMP_SIG',
        '_STAMP2 = ""  # STAMP_SIG2': f'_STAMP2 = "{stamp2}"  # STAMP_SIG2',
        '_PEPPER_MASK = ""  # STAMP_MASK': f'_PEPPER_MASK = "{mask.hex()}"  # STAMP_MASK',
        '_PEPPER_HIDDEN = ""  # STAMP_HIDDEN': f'_PEPPER_HIDDEN = "{hidden.hex()}"  # STAMP_HIDDEN',
        '_PEPPER2_MASK = ""  # STAMP_MASK2': f'_PEPPER2_MASK = "{mask2.hex()}"  # STAMP_MASK2',
        '_PEPPER2_HIDDEN = ""  # STAMP_HIDDEN2': f'_PEPPER2_HIDDEN = "{hidden2.hex()}"  # STAMP_HIDDEN2',
    }
    for old, new in replacements.items():
        if old not in text:
            sys.exit("源码里找不到盖章位置，拒绝编译。")
        text = text.replace(old, new, 1)
    leaked = (pepper.hex(), pepper2.hex(), _raw_hex(priv), _raw_hex(priv2))
    if any(item and item in text for item in leaked):
        sys.exit("盖章结果把密钥原文写进了源码，已中止。")
    STAGED.parent.mkdir(parents=True, exist_ok=True)
    STAGED.write_text(text, encoding="utf-8")


def _cleanup() -> None:
    shutil.rmtree(ROOT / "sealed", ignore_errors=True)
    shutil.rmtree(ROOT.parent / "build", ignore_errors=True)


def main() -> None:
    priv, priv2, pepper, pepper2, pub, pub2 = _load()
    _cleanup()
    _stage(pub, pub2, pepper, pepper2, priv, priv2)
    try:
        setup(
            ext_modules=cythonize(
                [Extension("app.services.coins_box", ["native/sealed/coins_box.py"])],
                compiler_directives={"language_level": "3"},
                build_dir="native/sealed/c",
            ),
            script_args=["build_ext", "--build-lib", "."],
        )
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
