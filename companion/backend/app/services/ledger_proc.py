"""账本进程。加密、重放、写库都在这里，不占聊天进程。

标准输出只放一行一个 JSON。日志走标准错误。
"""
from __future__ import annotations

import json
import sys
import threading
import time

_IDLE_SEC = 60


def _ops():
    from . import coins_box

    return {
        "heartbeat": coins_box.heartbeat,
        "grant_talk": coins_box.grant_talk,
        "compact": coins_box.compact,
        "idle_compact": coins_box.idle_compact,
        "balance": coins_box.balance,
        "pay": coins_box.pay,
        "redeem": coins_box.redeem,
        "wish": coins_box.wish,
        "preview": coins_box.preview,
    }


def _idle(box) -> None:
    while True:
        time.sleep(_IDLE_SEC)
        try:
            if box.idle_compact():
                print("[coins] idle fold", file=sys.stderr)
        except Exception as exc:
            print(f"[coins] idle fold skipped: {exc}", file=sys.stderr)


def main() -> None:
    ops = _ops()
    from . import coins_box

    threading.Thread(target=_idle, args=(coins_box,), daemon=True, name="ledger-idle").start()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            ident = int(req.get("id") or 0)
            op = str(req.get("op") or "")
            args = list(req.get("args") or [])
            fn = ops.get(op)
            if fn is None:
                raise coins_box.CoinError("bad_chain")
            result = fn(*args)
            out = {"id": ident, "ok": True, "result": result}
        except coins_box.CoinError as exc:
            code = getattr(exc, "code", None) or (exc.args[0] if exc.args else "bad_chain")
            out = {"id": int(locals().get("ident") or 0), "ok": False, "error": str(code)}
        except Exception as exc:
            print(f"[coins] {exc}", file=sys.stderr)
            out = {"id": int(locals().get("ident") or 0), "ok": False, "error": "bad_chain"}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
