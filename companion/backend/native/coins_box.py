"""金币黑盒。

界面只能做三件事：按地址和金额转账、导入交易串、读余额。
盒子里有一条从同一个创世块长出来的哈希链。挂机和转账都是往后接一块，
余额只由这条链重放出来。各台电脑不连网、不对齐，所以各有各的分叉。
挂机大约每 10 分钟接一块。闲时把旧明细收成一块快照：
余额和已经花过的票号留在快照里，更早的明细删掉。票号不过期，否则同一张票能再收一次。
挂机只是把上一枚并进下一枚，被并掉的编号不进已花名单，名单不再按心跳变长。
账本整份加密。改一个字节就校验失败，盒子作废。转到黑洞地址就是销毁。

编译时要两把编译密钥一起盖章，缺一把就不成立。封账本也要两把密钥一起派生，缺一把打不开。
账本拆在两个加密文件和数据库四条记录里，六处互相咬住，改不齐就作废。
两把公共密钥写进每个正式版本，标明这是哪一条链。盖章对不上的包，三个入口都不工作。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..paths import DATA_DIR, DB_PATH

# 下面八行由打包脚本按两把编译密钥和两把封账密钥填上。源码里是空的，自己编译盖不上章。
_PUB = ""  # STAMP_PUB
_PUB2 = ""  # STAMP_PUB2
_STAMP = ""  # STAMP_SIG
_STAMP2 = ""  # STAMP_SIG2
_PEPPER_MASK = ""  # STAMP_MASK
_PEPPER_HIDDEN = ""  # STAMP_HIDDEN
_PEPPER2_MASK = ""  # STAMP_MASK2
_PEPPER2_HIDDEN = ""  # STAMP_HIDDEN2
_STAMP_OK = False


def _hidden(mask_hex: str, hidden_hex: str) -> bytes:
    try:
        mask = bytes.fromhex(mask_hex)
        hidden = bytes.fromhex(hidden_hex)
    except ValueError as exc:
        raise CoinError("unofficial") from exc
    if len(mask) != 16 or len(hidden) != 16:
        raise CoinError("unofficial")
    return bytes(left ^ right for left, right in zip(hidden, mask))


def _pepper() -> bytes:
    return _hidden(_PEPPER_MASK, _PEPPER_HIDDEN)


def _pepper2() -> bytes:
    return _hidden(_PEPPER2_MASK, _PEPPER2_HIDDEN)


def _chain_id() -> str:
    raw = bytes.fromhex(_PUB) + bytes.fromhex(_PUB2)
    return hashlib.sha256(b"xiaoke-chain/2|" + raw).hexdigest()


def _official() -> None:
    global _STAMP_OK
    if _STAMP_OK:
        return
    pub = (_PUB or "").strip().lower()
    pub2 = (_PUB2 or "").strip().lower()
    stamp = (_STAMP or "").strip().lower()
    stamp2 = (_STAMP2 or "").strip().lower()
    if pub == pub2 or not _HEX64.match(pub) or not _HEX64.match(pub2):
        raise CoinError("unofficial")
    if not _HEX128.match(stamp) or not _HEX128.match(stamp2):
        raise CoinError("unofficial")
    try:
        msg = f"xiaokeai-box/3|{pub}|{pub2}|{_pepper().hex()}|{_pepper2().hex()}|{_GENESIS}".encode()
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub)).verify(bytes.fromhex(stamp), msg)
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub2)).verify(bytes.fromhex(stamp2), msg)
    except (CoinError, InvalidSignature, ValueError):
        raise CoinError("unofficial")
    _STAMP_OK = True


_MAGIC = b"XK3"
_MAGIC_V2 = b"XK2"
_SEAL = DATA_DIR / "wallet.seal"
_KNOT = DATA_DIR / "wallet.knot"
_KNOT_MAGIC = b"XK4"
_DB = DB_PATH
_LOCK = threading.Lock()
_ADDR = re.compile(r"^[0-9a-f]{64}$")
_OUT = re.compile(r"^[0-9a-f]{64}:[0-9]{1,3}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX128 = re.compile(r"^[0-9a-f]{128}$")
_GENESIS = hashlib.sha256(b"xiaoke-chain/1|genesis").hexdigest()
BURN = "00" * 32

# 心跳改成 10 分钟一次。间隔再长才算人走了，这一段不发币。
_BREAK_MS = 900_000
_SKEW_MS = 2_000
# 明细上限。写账时到了就收成一块 check。闲时更早收，避免账本在聊天时变长。
_FOLD_AT = 32
_IDLE_FOLD_AT = 4
_BASE_PER_MIN_MILLI = 2_000
_HOUR = 60 * 60 * 1000
_TIERS = (
    (30 * 60 * 1000, 10),
    (60 * 60 * 1000, 15),
    (2 * _HOUR, 20),
    (4 * _HOUR, 30),
    (8 * _HOUR, 50),
    (16 * _HOUR, 80),
    (24 * _HOUR, 120),
)


class CoinError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _now_ms() -> int:
    return int(time.time() * 1000)


_LABEL = b"xiaokeai-box/4"


def _keys() -> Tuple[bytes, bytes]:
    left = _pepper()
    right = _pepper2()
    if left == right:
        raise CoinError("unofficial")
    master = hashlib.sha256(left + right + _LABEL).digest()
    enc = hmac.new(master, b"enc", hashlib.sha256).digest()
    mac = hmac.new(master, b"mac", hashlib.sha256).digest()
    return enc, mac


def _priv_raw(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _pub_hex(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return raw.hex()


def _key_from(priv_hex: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))


def _tx_msg(sender: str, inputs: List[str], recipient: str, amount: int, tip: str) -> bytes:
    return (
        f"xiaoke-chain/2|tx|{_chain_id()}|{sender}|{','.join(inputs)}|{recipient}|{amount}|{tip}"
    ).encode()


def _txid(msg: bytes) -> str:
    return hashlib.sha256(msg).hexdigest()


def _canon(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def _pack_tx(sender: str, inputs: List[str], recipient: str, amount: int, sig: bytes, tip: str) -> str:
    payload = {
        "v": 3,
        "ch": _chain_id(),
        "frm": sender,
        "in": inputs,
        "to": recipient,
        "amt": amount,
        "sig": sig.hex(),
        "tip": tip,
    }
    token = base64.urlsafe_b64encode(_canon(payload).encode()).decode().rstrip("=")
    return "XKTX3." + token


def _unpack_tx(text: str) -> Dict[str, Any]:
    raw_text = (text or "").strip()
    prefix = "XKTX3."
    if not raw_text.startswith(prefix):
        raise CoinError("bad_note")
    token = raw_text[len(prefix):]
    token += "=" * ((4 - len(token) % 4) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(token))
        sender = str(data["frm"]).lower()
        recipient = str(data["to"]).lower()
        amount = int(data["amt"])
        inputs = [str(item).lower() for item in data["in"]]
        sig = bytes.fromhex(str(data["sig"]))
        tip = str(data.get("tip") or "").lower()
        chain = str(data.get("ch") or "").lower()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise CoinError("bad_note")
    if chain != _chain_id():
        raise CoinError("foreign")
    if not _ADDR.match(sender) or not _ADDR.match(recipient) or amount <= 0:
        raise CoinError("bad_note")
    if not inputs or len(inputs) != len(set(inputs)) or any(not _OUT.match(item) for item in inputs):
        raise CoinError("bad_note")
    if inputs != sorted(inputs) or len(sig) != 64 or not _HEX64.match(tip):
        raise CoinError("bad_note")
    msg = _tx_msg(sender, inputs, recipient, amount, tip)
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(sender)).verify(sig, msg)
    except (InvalidSignature, ValueError):
        raise CoinError("bad_note")
    return {
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "inputs": inputs,
        "sig": sig,
        "tip": tip,
        "msg": msg,
        "txid": _txid(msg),
    }


def _tenths(streak_ms: int) -> int:
    for limit, tenths in _TIERS:
        if streak_ms < limit:
            return tenths
    over = streak_ms - 24 * _HOUR
    blocks = over // (12 * _HOUR)
    return 120 + blocks * 40


_GPU_AT = 0.0
_GPU_GB = 0.0
_WISH_PER_DAY = 50
_TOKENS_PER_COIN = 4_000
_TOKEN_CAP = 200_000


def _vram_gb() -> float:
    global _GPU_AT, _GPU_GB
    now = time.time()
    if _GPU_AT and now - _GPU_AT < 300:
        return _GPU_GB
    best = 0.0
    smi = shutil.which("nvidia-smi")
    if smi:
        kwargs: Dict[str, Any] = {
            "args": [smi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            "capture_output": True,
            "text": True,
            "timeout": 4,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            out = subprocess.run(**kwargs)
        except (OSError, subprocess.TimeoutExpired):
            out = None
        if out is not None and out.returncode == 0:
            for line in (out.stdout or "").splitlines():
                try:
                    best = max(best, float(line.strip().split()[0]) / 1024.0)
                except (ValueError, IndexError):
                    continue
    _GPU_AT = now
    _GPU_GB = best
    return best


def _gpu_tenths() -> int:
    gb = _vram_gb()
    if gb <= 0:
        return 10
    if gb < 4:
        return 12
    if gb < 8:
        return 15
    if gb < 12:
        return 20
    if gb < 16:
        return 26
    return 34


def _credit(streak_ms: int, elapsed_ms: int) -> int:
    if elapsed_ms <= 0:
        return 0
    return (
        elapsed_ms * _BASE_PER_MIN_MILLI * _tenths(streak_ms) * _gpu_tenths()
        // 6_000_000
    )


def _blank(raw: bytes, now: int) -> Dict[str, Any]:
    key = Ed25519PrivateKey.from_private_bytes(raw)
    return {
        "v": 2,
        "priv": raw.hex(),
        "addr": _pub_hex(key),
        "streak_ms": 0,
        "last_ms": now,
        "mint_n": 0,
        "tip": _GENESIS,
        "height": 0,
        "chain": [],
        "utxo": [],
        "used": [],
        "seen": [],
    }


def _fresh(now: int) -> Dict[str, Any]:
    return _blank(_priv_raw(Ed25519PrivateKey.generate()), now)


def _key_ok(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    try:
        raw = bytes.fromhex(str(state.get("priv") or ""))
        if len(raw) != 32:
            return False
        if _pub_hex(Ed25519PrivateKey.from_private_bytes(raw)) != state.get("addr"):
            return False
        int(state.get("streak_ms"))
        int(state.get("last_ms"))
        int(state.get("mint_n"))
    except (TypeError, ValueError):
        return False
    return True


def _utxo_sane(state: Dict[str, Any]) -> bool:
    try:
        used = set(state.get("used") or [])
        if not isinstance(state.get("utxo"), list) or not isinstance(state.get("seen") or [], list):
            return False
        for utxo in state["utxo"]:
            if not _OUT.match(str(utxo.get("id") or "")) or int(utxo.get("amt") or 0) <= 0:
                return False
            if utxo["id"] in used:
                return False
    except (TypeError, ValueError):
        return False
    return True


def _block_hash(index: int, prev: str, when: int, tx: Dict[str, Any]) -> str:
    raw = f"{index}|{prev}|{when}|{_canon(tx)}".encode()
    return hashlib.sha256(raw).hexdigest()


def _links_ok(state: Dict[str, Any]) -> bool:
    chain = state.get("chain")
    if not isinstance(chain, list):
        return False
    prev = _GENESIS
    for index, block in enumerate(chain, 1):
        try:
            when = int(block["time"])
            tx = block["tx"]
            if int(block["i"]) != index or block["prev"] != prev:
                return False
            if block["hash"] != _block_hash(index, prev, when, tx):
                return False
        except (KeyError, TypeError, ValueError):
            return False
        prev = block["hash"]
    return state.get("tip") == prev and int(state.get("height") or 0) == len(chain)


def _append(state: Dict[str, Any], tx: Dict[str, Any], now: int) -> None:
    prev = state.get("tip") or _GENESIS
    index = int(state.get("height") or 0) + 1
    digest = _block_hash(index, prev, now, tx)
    state.setdefault("chain", []).append({
        "i": index,
        "prev": prev,
        "time": now,
        "tx": tx,
        "hash": digest,
    })
    state["tip"] = digest
    state["height"] = index
    state["v"] = 2


def _materialize(state: Dict[str, Any]) -> None:
    utxo: List[Dict[str, Any]] = []
    index: Dict[str, Dict[str, Any]] = {}
    used: List[str] = []
    seen: List[str] = []

    def add(item: Dict[str, Any]) -> None:
        index[item["id"]] = item
        utxo.append(item)

    def drop(ids: List[str]) -> None:
        nonlocal utxo
        gone = set(ids)
        have = set(used)
        for item in gone:
            if item not in index:
                raise CoinError("bad_chain")
            if item not in have:
                used.append(item)
                have.add(item)
            del index[item]
        utxo = [row for row in utxo if row["id"] not in gone]

    for block in state.get("chain") or []:
        tx = block["tx"]
        kind = tx.get("k")
        if kind == "check":
            utxo = []
            index = {}
            used = list(tx.get("used") or [])
            seen = list(tx.get("seen") or [])
            for item in tx.get("outs") or []:
                add({"id": item["id"], "amt": int(item["amt"]), "src": item.get("src") or "mint"})
        elif kind == "mint":
            # 挂机是把上一枚并进下一枚。被并掉的编号不是别人转来的票，
            # 不进 used，否则每次心跳多留一个永久编号，账本会一直涨。
            if tx.get("drop"):
                gone = set(tx["drop"])
                for item in gone:
                    if item not in index:
                        raise CoinError("bad_chain")
                    del index[item]
                utxo = [row for row in utxo if row["id"] not in gone]
            add({"id": tx["id"], "amt": int(tx["amt"]), "src": "mint"})
        elif kind == "pay":
            drop(list(tx["ins"]))
            if int(tx.get("chg") or 0) > 0:
                add({"id": f"{tx['txid']}:1", "amt": int(tx["chg"]), "src": "change"})
            if tx["txid"] not in seen:
                seen.append(tx["txid"])
        elif kind == "in":
            have = set(used)
            for item in tx["ins"]:
                if item not in have:
                    used.append(item)
                    have.add(item)
            add({"id": f"{tx['txid']}:0", "amt": int(tx["amt"]), "src": "in"})
            if tx["txid"] not in seen:
                seen.append(tx["txid"])
        else:
            raise CoinError("bad_chain")
    state["utxo"] = utxo
    state["used"] = used
    state["seen"] = seen


def _upgrade(state: Dict[str, Any]) -> None:
    outs = [
        {"id": row["id"], "amt": int(row["amt"]), "src": row.get("src") or "mint"}
        for row in state.get("utxo") or []
    ]
    tx = {
        "k": "check",
        "outs": outs,
        "used": list(state.get("used") or []),
        "seen": list(state.get("seen") or []),
    }
    state["chain"] = []
    state["tip"] = _GENESIS
    state["height"] = 0
    _append(state, tx, int(state.get("last_ms") or 0))
    _materialize(state)


def _seal(payload: bytes) -> bytes:
    enc, mac_key = _keys()
    tag = hmac.new(mac_key, payload, hashlib.sha256).digest()
    nonce = os.urandom(12)
    ct = AESGCM(enc).encrypt(nonce, payload + tag, _MAGIC)
    return _MAGIC + nonce + ct


def _unseal(blob: bytes) -> Optional[bytes]:
    if len(blob) < len(_MAGIC) + 12 + 16 or not blob.startswith(_MAGIC):
        return None
    enc, mac_key = _keys()
    nonce = blob[len(_MAGIC):len(_MAGIC) + 12]
    try:
        body = AESGCM(enc).decrypt(nonce, blob[len(_MAGIC) + 12:], _MAGIC)
    except Exception:
        return None
    if len(body) < 32:
        return None
    payload, tag = body[:-32], body[-32:]
    expect = hmac.new(mac_key, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expect):
        return None
    return payload


def _core(state: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in state.items() if not str(key).startswith("_w")}


def _digest(state: Dict[str, Any]) -> bytes:
    raw = json.dumps(_core(state), separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(raw).digest()


def _secret(digest: bytes, gen: int, salt: bytes) -> bytes:
    _, mac_key = _keys()
    msg = b"xiaokeai-box/6|" + digest + gen.to_bytes(8, "big") + salt
    return hmac.new(mac_key, msg, hashlib.sha256).digest()


def _bind(index: int, gen: int, digest: bytes, share: bytes, nxt: bytes) -> str:
    _, mac_key = _keys()
    msg = f"{index}|{gen}|".encode() + digest + b"|" + share + nxt
    return hmac.new(mac_key, msg, hashlib.sha256).hexdigest()


def _slot_id(index: int) -> str:
    _, mac_key = _keys()
    return hmac.new(mac_key, f"xiaokeai-box/slot/{index}".encode(), hashlib.sha256).hexdigest()[:24]


def _row_mac(slot: str, gen: int, share: str, bind: str, ring: str) -> str:
    _, mac_key = _keys()
    msg = f"{slot}|{gen}|{share}|{bind}|{ring}".encode()
    return hmac.new(mac_key, msg, hashlib.sha256).hexdigest()


def _split(secret: bytes) -> List[bytes]:
    shares = [os.urandom(32) for _ in range(5)]
    folded = secret
    for share in shares:
        folded = bytes(left ^ right for left, right in zip(folded, share))
    shares.append(folded)
    return shares


def _db():
    con = sqlite3.connect(str(_DB), timeout=5)
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        "CREATE TABLE IF NOT EXISTS kx_slot ("
        "slot TEXT PRIMARY KEY, n INTEGER NOT NULL, p TEXT NOT NULL, "
        "q TEXT NOT NULL, r TEXT NOT NULL, s TEXT NOT NULL)"
    )
    return con


def _slots_ready() -> bool:
    try:
        con = _db()
        try:
            found = 0
            for index in range(2, 6):
                row = con.execute(
                    "SELECT slot FROM kx_slot WHERE slot = ?",
                    (_slot_id(index),),
                ).fetchone()
                if row is not None:
                    found += 1
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            raise CoinError("busy") from exc
        return False
    return found == 4


def _write_slots(gen: int, shares: List[bytes], binds: List[str], rings: List[str]) -> None:
    try:
        con = _db()
        try:
            with con:
                for index in range(2, 6):
                    slot = _slot_id(index)
                    share = shares[index].hex()
                    bind = binds[index]
                    ring = rings[index]
                    mac = _row_mac(slot, gen, share, bind, ring)
                    con.execute(
                        "INSERT INTO kx_slot(slot, n, p, q, r, s) VALUES(?,?,?,?,?,?) "
                        "ON CONFLICT(slot) DO UPDATE SET "
                        "n = excluded.n, p = excluded.p, q = excluded.q, "
                        "r = excluded.r, s = excluded.s",
                        (slot, gen, share, bind, ring, mac),
                    )
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            raise CoinError("busy") from exc
        raise CoinError("bad_chain") from exc


def _read_slots(gen: int) -> Optional[List[Tuple[bytes, str, str]]]:
    try:
        con = _db()
        try:
            found: List[Tuple[bytes, str, str]] = []
            for index in range(2, 6):
                slot = _slot_id(index)
                row = con.execute(
                    "SELECT n, p, q, r, s FROM kx_slot WHERE slot = ?",
                    (slot,),
                ).fetchone()
                if row is None or int(row[0]) != gen:
                    return None
                share, bind, ring, mac = str(row[1]), str(row[2]), str(row[3]), str(row[4])
                if not hmac.compare_digest(mac, _row_mac(slot, gen, share, bind, ring)):
                    return None
                found.append((bytes.fromhex(share), bind, ring))
        finally:
            con.close()
    except (sqlite3.OperationalError, ValueError) as exc:
        if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
            raise CoinError("busy") from exc
        return None
    return found


def _replace(path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as handle:
        handle.write(blob)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _witness_ok(state: Dict[str, Any]) -> bool:
    try:
        gen = int(state["_wgen"])
        salt = bytes.fromhex(str(state["_wsalt"]))
        shares = [bytes.fromhex(str(state["_wshare"]))]
        binds = [str(state["_wbind"])]
        rings = [str(state["_wring"])]
    except (KeyError, TypeError, ValueError):
        return False
    try:
        knot_raw = _unseal_with(_KNOT.read_bytes(), _KNOT_MAGIC)
    except OSError:
        return False
    if knot_raw is None:
        return False
    try:
        knot = json.loads(knot_raw)
        if int(knot["g"]) != gen or str(knot["s"]) != salt.hex():
            return False
        digest = _digest(state)
        if bytes.fromhex(str(knot["d"])) != digest:
            return False
        shares.append(bytes.fromhex(str(knot["p"])))
        binds.append(str(knot["q"]))
        rings.append(str(knot["r"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    rows = _read_slots(gen)
    if rows is None:
        return False
    for share, bind, ring in rows:
        shares.append(share)
        binds.append(bind)
        rings.append(ring)
    if len(shares) != 6:
        return False
    for index in range(6):
        nxt = shares[(index + 1) % 6]
        if binds[index] != _bind(index, gen, digest, shares[index], nxt):
            return False
        if rings[index] != hashlib.sha256(shares[index] + nxt).hexdigest():
            return False
    folded = bytes(32)
    for share in shares:
        folded = bytes(left ^ right for left, right in zip(folded, share))
    return hmac.compare_digest(folded, _secret(digest, gen, salt))


def _publish(state: Dict[str, Any]) -> None:
    for key in ("_wlegacy", "_wsalt", "_wshare", "_wbind", "_wring"):
        state.pop(key, None)
    gen = int(state.pop("_wgen", 0) or 0) + 1
    digest = _digest(state)
    salt = os.urandom(16)
    shares = _split(_secret(digest, gen, salt))
    binds = []
    rings = []
    for index in range(6):
        nxt = shares[(index + 1) % 6]
        binds.append(_bind(index, gen, digest, shares[index], nxt))
        rings.append(hashlib.sha256(shares[index] + nxt).hexdigest())
    state["_wgen"] = gen
    state["_wsalt"] = salt.hex()
    state["_wshare"] = shares[0].hex()
    state["_wbind"] = binds[0]
    state["_wring"] = rings[0]
    knot = {
        "g": gen,
        "d": digest.hex(),
        "s": salt.hex(),
        "p": shares[1].hex(),
        "q": binds[1],
        "r": rings[1],
    }
    _write_slots(gen, shares, binds, rings)
    _replace(_KNOT, _seal_with(
        json.dumps(knot, separators=(",", ":"), sort_keys=True).encode(),
        _KNOT_MAGIC,
    ))
    _replace(_SEAL, _seal(json.dumps(state, separators=(",", ":"), sort_keys=True).encode()))


def _seal_with(payload: bytes, magic: bytes) -> bytes:
    enc, mac_key = _keys()
    tag = hmac.new(mac_key, magic + payload, hashlib.sha256).digest()
    nonce = os.urandom(12)
    ct = AESGCM(enc).encrypt(nonce, payload + tag, magic)
    return magic + nonce + ct


def _unseal_with(blob: bytes, magic: bytes) -> Optional[bytes]:
    if len(blob) < len(magic) + 12 + 16 or not blob.startswith(magic):
        return None
    enc, mac_key = _keys()
    nonce = blob[len(magic):len(magic) + 12]
    try:
        body = AESGCM(enc).decrypt(nonce, blob[len(magic) + 12:], magic)
    except Exception:
        return None
    if len(body) < 32:
        return None
    payload, tag = body[:-32], body[-32:]
    expect = hmac.new(mac_key, magic + payload, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expect):
        return None
    return payload


def _read() -> Optional[Dict[str, Any]]:
    try:
        blob = _SEAL.read_bytes()
    except OSError:
        return None
    payload = _unseal(blob)
    if payload is None:
        return None
    try:
        state = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not _key_ok(state):
        return None
    try:
        version = int(state.get("v") or 1)
    except (TypeError, ValueError):
        return None
    legacy = "_wgen" not in state
    if legacy and (_KNOT.exists() or _slots_ready()):
        return None
    if not legacy and not _witness_ok(state):
        return None
    if version < 2 or "chain" not in state:
        if not _utxo_sane(state):
            return None
        if legacy:
            state["_wlegacy"] = 1
        return state
    if not _links_ok(state):
        return None
    try:
        _materialize(state)
    except (CoinError, KeyError, TypeError, ValueError):
        return None
    if legacy:
        state["_wlegacy"] = 1
    return state


def _fold(state: Dict[str, Any], now: int, limit: int = 0) -> bool:
    """把已经重放出来的余额收成一块快照。已用票号原样留下。"""
    chain = state.get("chain") or []
    need = int(limit or _FOLD_AT)
    if len(chain) < need:
        return False
    outs = []
    for row in state.get("utxo") or []:
        amt = int(row.get("amt") or 0)
        if amt <= 0:
            continue
        outs.append({
            "id": str(row["id"]),
            "amt": amt,
            "src": row.get("src") or "mint",
        })
    tx = {
        "k": "check",
        "outs": outs,
        "used": list(state.get("used") or []),
        "seen": list(state.get("seen") or []),
    }
    state["chain"] = []
    state["tip"] = _GENESIS
    state["height"] = 0
    _append(state, tx, int(now))
    _materialize(state)
    return True


def _load(now: int) -> Tuple[Dict[str, Any], bool]:
    state = _open()
    return state, _fold(state, now)


def _write(state: Dict[str, Any]) -> None:
    _fold(state, int(state.get("last_ms") or _now_ms()))
    _publish(state)


def _migrate_v2(now: int) -> Optional[Dict[str, Any]]:
    try:
        blob = _SEAL.read_bytes()
    except OSError:
        return None
    if len(blob) != len(_MAGIC_V2) + 32 + 8 + 32 or not blob.startswith(_MAGIC_V2):
        return None
    off = len(_MAGIC_V2)
    raw = blob[off:off + 32]
    seq = int.from_bytes(blob[off + 32:off + 40], "big")
    seal_mac = blob[off + 40:off + 72].hex()
    try:
        con = sqlite3.connect(str(DB_PATH), timeout=2)
        try:
            row = con.execute(
                "SELECT balance_milli, streak_ms, last_tick_ms, seq, nonce, address, mac "
                "FROM coin_wallet WHERE id = 1"
            ).fetchone()
            notes = [item[0] for item in con.execute("SELECT txid FROM coin_note ORDER BY txid")]
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            raise CoinError("busy") from exc
        return None
    if row is None:
        return None
    balance, streak, last, row_seq, nonce, address, row_mac = row
    notes_hash = hashlib.sha256("|".join(str(item) for item in notes).encode()).hexdigest()
    msg = (
        f"{int(row_seq)}|{int(balance)}|{int(streak)}|{int(last)}"
        f"|{int(nonce)}|{address}|{notes_hash}"
    ).encode()
    mac_key = hmac.new(_pepper(), raw, hashlib.sha256).digest()
    mac = hmac.new(mac_key, msg, hashlib.sha256).hexdigest()
    try:
        pub = _pub_hex(Ed25519PrivateKey.from_private_bytes(raw))
    except ValueError:
        return None
    intact = (
        int(row_seq) > 0
        and int(row_seq) == seq
        and mac == (row_mac or "")
        and mac == seal_mac
        and address == pub
    )
    if not intact:
        return None
    state = _blank(raw, now)
    state["streak_ms"] = max(0, int(streak))
    state["last_ms"] = int(last)
    if int(balance) > 0:
        _mint(state, int(balance), now)
    return state


def _open() -> Dict[str, Any]:
    state = _read()
    if state is not None:
        if int(state.get("v") or 1) < 2 or "chain" not in state:
            _upgrade(state)
            _write(state)
            return state
        if state.pop("_wlegacy", None):
            _write(state)
        return state
    now = _now_ms()
    existed = False
    try:
        existed = _SEAL.exists()
    except OSError:
        existed = False
    if existed:
        migrated = _migrate_v2(now)
        if migrated is not None:
            _write(migrated)
            return migrated
        print("[coins] ledger rejected", file=sys.stderr)
    state = _fresh(now)
    _write(state)
    return state


def _balance(state: Dict[str, Any]) -> int:
    return sum(int(utxo["amt"]) for utxo in state["utxo"])


def _wish_day(now: int) -> str:
    stamp = time.localtime(now / 1000)
    return f"{stamp.tm_year:04d}-{stamp.tm_mon:02d}-{stamp.tm_mday:02d}"


def _wish_used(state: Dict[str, Any], now: int) -> int:
    day = _wish_day(now)
    if state.get("wish_day") == day:
        return max(0, int(state.get("wish_n") or 0))
    last = int(state.get("wish_ms") or 0)
    if last > 0 and _wish_day(last) == day:
        return 1
    return 0


def _wish_left(state: Dict[str, Any], now: int) -> int:
    return max(0, _WISH_PER_DAY - _wish_used(state, now))


def _secs_to_midnight(now: int) -> int:
    stamp = time.localtime(now / 1000)
    passed = stamp.tm_hour * 3600 + stamp.tm_min * 60 + stamp.tm_sec
    return max(1, 86400 - passed)


def _view(state: Dict[str, Any], gained: int) -> Dict[str, Any]:
    tenths = _tenths(int(state["streak_ms"]))
    gpu = _gpu_tenths()
    balance = _balance(state)
    return {
        "balance_milli": balance,
        "balance": balance // 1000,
        "multiplier": tenths / 10,
        "gpu": gpu / 10,
        "vram_gb": round(_vram_gb(), 1),
        "per_min": 2 * (tenths / 10) * (gpu / 10),
        "streak_sec": int(state["streak_ms"]) // 1000,
        "gained_milli": gained,
        "wish_left": _wish_left(state, _now_ms()),
        "wish_sec": 0 if _wish_left(state, _now_ms()) > 0 else _secs_to_midnight(_now_ms()),
        "address": state["addr"],
    }


def _estimate_tokens(text: str) -> int:
    cjk = 0
    other = 0
    for ch in text or "":
        if ord(ch) > 127:
            cjk += 1
        elif not ch.isspace():
            other += 1
    return cjk + (other + 3) // 4


def grant_talk(prompt: str, reply: str, billed: int = 0) -> Dict[str, Any]:
    """对话消耗。有接口账单就用账单，否则按中文约 1 字 1 token、英文约 4 字 1 token 估算。"""
    _official()
    tokens = int(billed or 0)
    if tokens <= 0:
        tokens = _estimate_tokens(prompt) + _estimate_tokens(reply)
    tokens = max(0, min(tokens, _TOKEN_CAP))
    with _LOCK:
        now = _now_ms()
        state, folded = _load(now)
        left = int(state.get("token_left") or 0) + tokens
        milli = left * 1000 // _TOKENS_PER_COIN
        state["token_left"] = left - milli * _TOKENS_PER_COIN // 1000
        if milli > 0:
            _mint(state, milli, now)
        if tokens > 0 or folded:
            _write(state)
        out = _view(state, milli if milli > 0 else 0)
        out["tokens"] = tokens
        return out


# Wish pool. The coin amount is decided only inside this extension.
#
# Each wish draws 3 distinct props from the bag below. The tuple is
# (id, gag, low tenths, high tenths). Serious props (work, phone, computer,
# bracelet, key, letter) roll about 0.9–1.3. Gag props (worry, magnet, card,
# alarm, sock, meeting) roll about 1.2–2.4, so the same base pays more.
# Each prop rolls its own coefficient from os.urandom. The same trio never
# pays the same amount twice.
#
# Base is 2–12 coins, or 30 coins when a 16-bit roll is divisible by 20
# (about 1 in 20). One coin is 1000 milli. The three coefficients are summed
# as tenths and the base is scaled by that sum / 30, which is the average of
# three 1.0 coefficients. The result is rounded to a whole coin and clamped
# to 1–80 coins. The HTTP layer may narrate that integer; it cannot change it.
#
# wish_n is today's count. The local calendar day allows 50 wishes.
# wish_total is the lifetime count and is what memory stores.
_WISH_BAG = (
    ("work", False, 10, 12),
    ("phone", False, 10, 12),
    ("computer", False, 10, 13),
    ("bracelet", False, 9, 12),
    ("key", False, 9, 12),
    ("letter", False, 9, 12),
    ("worry", True, 14, 22),
    ("magnet", True, 13, 21),
    ("card", True, 15, 24),
    ("alarm", True, 12, 20),
    ("sock", True, 12, 19),
    ("meeting", True, 14, 23),
)


def _wish_throws() -> tuple:
    """Pick 3 distinct props and a fresh coefficient for each."""
    bag = list(_WISH_BAG)
    picks = []
    for _ in range(3):
        pick = int.from_bytes(os.urandom(2), "big") % len(bag)
        picks.append(bag.pop(pick))
    throws = []
    total = 0
    for item_id, gag, lo, hi in picks:
        span = max(1, hi - lo + 1)
        tenths = lo + (int.from_bytes(os.urandom(2), "big") % span)
        total += tenths
        throws.append({"id": item_id, "k": tenths / 10, "gag": bool(gag)})
    return throws, total


def wish() -> Dict[str, Any]:
    """Mint one wish. Returns the whole-coin drop and the three thrown props."""
    _official()
    with _LOCK:
        now = _now_ms()
        state, _folded = _load(now)
        used = _wish_used(state, now)
        if used >= _WISH_PER_DAY:
            raise CoinError("wished")
        throws, ksum = _wish_throws()
        roll = int.from_bytes(os.urandom(2), "big")
        if roll % 20 == 0:
            base = 30_000
        else:
            base = 2_000 + (roll % 11) * 1_000
        raw = base * ksum // 30
        drop = ((raw + 500) // 1_000) * 1_000
        if drop < 1_000:
            drop = 1_000
        if drop > 80_000:
            drop = 80_000
        state["wish_day"] = _wish_day(now)
        state["wish_n"] = used + 1
        state["wish_total"] = int(state.get("wish_total") or 0) + 1
        state["wish_ms"] = now
        _mint(state, drop, now)
        _write(state)
        out = _view(state, drop)
        out["drop_milli"] = drop
        out["throws"] = throws
        out["wish_times"] = int(state["wish_total"])
        return out


def _mint(state: Dict[str, Any], amount: int, now: int) -> None:
    if amount <= 0:
        return
    old = [utxo for utxo in state["utxo"] if utxo.get("src") == "mint"]
    folded = sum(int(utxo["amt"]) for utxo in old) + amount
    state["mint_n"] = int(state["mint_n"]) + 1
    msg = (
        f"xiaoke-chain/1|mint|{state['addr']}|{state['mint_n']}|{folded}|{now}"
    ).encode()
    txid = _txid(msg)
    _append(state, {
        "k": "mint",
        "id": f"{txid}:0",
        "amt": folded,
        "drop": [utxo["id"] for utxo in old],
    }, now)
    _materialize(state)


def _tick(state: Dict[str, Any], now: int) -> Tuple[int, bool]:
    gained = 0
    gap = now - int(state["last_ms"])
    if gap < -_SKEW_MS:
        return 0, False
    if gap > _BREAK_MS:
        state["streak_ms"] = 0
        state["last_ms"] = now
        return 0, True
    if gap <= 0:
        return 0, False
    gained = _credit(int(state["streak_ms"]), gap)
    if gained <= 0:
        return 0, False
    _mint(state, gained, now)
    state["streak_ms"] = int(state["streak_ms"]) + gap
    state["last_ms"] = now
    return gained, True


def _select(state: Dict[str, Any], amount: int) -> Tuple[List[Dict[str, Any]], int]:
    rows = sorted(state["utxo"], key=lambda utxo: (-int(utxo["amt"]), utxo["id"]))
    picked: List[Dict[str, Any]] = []
    total = 0
    for utxo in rows:
        picked.append(utxo)
        total += int(utxo["amt"])
        if total >= amount:
            return picked, total
    raise CoinError("funds")


def _transfer(state: Dict[str, Any], recipient: str, amount: int, now: int) -> str:
    if not _ADDR.match(recipient):
        raise CoinError("bad_address")
    if recipient == state["addr"]:
        raise CoinError("self")
    if amount <= 0:
        raise CoinError("bad_amount")
    picked, total = _select(state, amount)
    inputs = sorted(utxo["id"] for utxo in picked)
    tip = state.get("tip") or _GENESIS
    msg = _tx_msg(state["addr"], inputs, recipient, amount, tip)
    sig = _key_from(state["priv"]).sign(msg)
    txid = _txid(msg)
    _append(state, {
        "k": "pay",
        "txid": txid,
        "ins": inputs,
        "chg": total - amount,
        "to": recipient,
        "amt": amount,
    }, now)
    _materialize(state)
    return _pack_tx(state["addr"], inputs, recipient, amount, sig, tip)


def _import(state: Dict[str, Any], parsed: Dict[str, Any], now: int) -> int:
    if parsed["recipient"] == BURN or parsed["recipient"] != state["addr"]:
        raise CoinError("not_yours")
    if parsed["txid"] in set(state["seen"]):
        raise CoinError("spent")
    used = set(state["used"])
    if any(item in used for item in parsed["inputs"]):
        raise CoinError("spent")
    outpoint = f"{parsed['txid']}:0"
    if any(utxo["id"] == outpoint for utxo in state["utxo"]) or outpoint in used:
        raise CoinError("spent")
    _append(state, {
        "k": "in",
        "txid": parsed["txid"],
        "ins": parsed["inputs"],
        "amt": parsed["amount"],
    }, now)
    _materialize(state)
    return parsed["amount"]


def heartbeat() -> Dict[str, Any]:
    _official()
    with _LOCK:
        now = _now_ms()
        state, folded = _load(now)
        gained, dirty = _tick(state, now)
        if dirty or folded:
            _write(state)
        return _view(state, gained)


def compact() -> bool:
    """链超长时收成一块快照。余额和已花票号不变，只删掉更早的明细。"""
    _official()
    with _LOCK:
        now = _now_ms()
        state, folded = _load(now)
        if not folded:
            return False
        _write(state)
        return True


def idle_compact() -> bool:
    """闲时收明细。正在记账就让开，余额和已花票号不动。"""
    _official()
    if not _LOCK.acquire(blocking=False):
        return False
    try:
        now = _now_ms()
        state = _open()
        if not _fold(state, now, _IDLE_FOLD_AT):
            return False
        _publish(state)
        return True
    finally:
        _LOCK.release()


def balance() -> int:
    _official()
    with _LOCK:
        return _balance(_open())


def pay(recipient: str, amount_milli: int) -> Dict[str, Any]:
    _official()
    recipient = (recipient or "").strip().lower()
    with _LOCK:
        now = _now_ms()
        state, _folded = _load(now)
        note = _transfer(state, recipient, int(amount_milli), now)
        _write(state)
        out = _view(state, 0)
        out["note"] = note
        return out


def redeem(note_text: str) -> Dict[str, Any]:
    _official()
    parsed = _unpack_tx(note_text)
    with _LOCK:
        now = _now_ms()
        state, _folded = _load(now)
        got = _import(state, parsed, now)
        _write(state)
        out = _view(state, 0)
        out["from"] = parsed["sender"]
        out["received_milli"] = got
        return out


_LADDER_SEC = (
    0,
    30 * 60,
    60 * 60,
    2 * 3600,
    4 * 3600,
    8 * 3600,
    16 * 3600,
    24 * 3600,
    36 * 3600,
    48 * 3600,
)


def _next_edge_ms(streak_ms: int) -> int:
    for sec in _LADDER_SEC:
        edge = sec * 1000
        if streak_ms < edge:
            return edge
    over = streak_ms - 24 * _HOUR
    step = 12 * _HOUR
    return 24 * _HOUR + (over // step + 1) * step


def earned_milli(seconds: int) -> int:
    left = max(0, seconds) * 1000
    streak = 0
    total = 0
    for _ in range(80):
        if left <= 0:
            break
        step = min(left, _next_edge_ms(streak) - streak)
        if step <= 0:
            break
        total += _credit(streak, step)
        streak += step
        left -= step
    return total


def ladder() -> list:
    rows = []
    for index in range(len(_LADDER_SEC) - 1):
        start = _LADDER_SEC[index]
        end = _LADDER_SEC[index + 1]
        tenths = _tenths(start * 1000)
        rows.append({
            "from_sec": start,
            "until_sec": end,
            "multiplier": tenths / 10,
            "per_min": 2 * tenths / 10,
        })
    return rows


def preview(seconds: int) -> Dict[str, Any]:
    _official()
    seconds = max(0, min(int(seconds), 48 * 3600))
    tenths = _tenths(seconds * 1000)
    gpu = _gpu_tenths()
    return {
        "sec": seconds,
        "multiplier": tenths / 10,
        "gpu": gpu / 10,
        "vram_gb": round(_vram_gb(), 1),
        "per_min": 2 * (tenths / 10) * (gpu / 10),
        "earned_milli": earned_milli(seconds),
        "ladder": ladder(),
    }
