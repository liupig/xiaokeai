#!/usr/bin/env python3
"""火山 Seedream 批量生成塔罗牌面（支持多线程并行）。

用法（PowerShell）:
  $env:ARK_API_KEY='你的key'
  python companion/scripts/generate_tarot_seedream.py --workers 4

可选参数见 --help。已存在的文件默认跳过；网络失败自动重试。
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Windows 控制台避免 GBK 打印报错
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TAROT_DIR = REPO_ROOT / "assets" / "tarot"
LOG_DIR = TAROT_DIR / "_logs"

API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DEFAULT_MODEL = "doubao-seedream-5-0-pro-260628"
DEFAULT_SIZE = "2K"
MAX_RETRIES = 6
RETRY_BASE_SEC = 3.0
DEFAULT_WORKERS = 4

sys.path.insert(0, str(SCRIPT_DIR))
from tarot_manifest import CARDS, TarotCard, prompt_for  # noqa: E402

_print_lock = threading.Lock()
_log_lock = threading.Lock()


def log(msg: str, *, err: bool = False) -> None:
    with _print_lock:
        stream = sys.stderr if err else sys.stdout
        print(msg, file=stream, flush=True)


def load_env_file() -> None:
    env_path = SCRIPT_DIR / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def api_key() -> str:
    load_env_file()
    key = (os.environ.get("ARK_API_KEY") or os.environ.get("VOLC_ARK_API_KEY") or "").strip()
    if not key:
        print("错误：请设置环境变量 ARK_API_KEY，或在 companion/scripts/.env 写入。", file=sys.stderr)
        sys.exit(1)
    return key


def filter_cards(args: argparse.Namespace) -> list[TarotCard]:
    out = list(CARDS)
    if args.only:
        only = set(args.only)
        out = [c for c in out if c.path.split("/")[0].replace(".png", "") in only or c.path in only]
    if args.paths:
        want = set(args.paths)
        out = [c for c in out if c.path in want]
    return out


def should_skip(path: Path, force: bool) -> bool:
    return path.is_file() and path.stat().st_size > 10_000 and not force


def load_ref_images(paths: list[str]) -> list[str]:
    """本地参考图转 base64 data URI。相对路径按仓库 companion 目录解析。"""
    out: list[str] = []
    for p in paths:
        fp = Path(p)
        if not fp.is_absolute():
            fp = (REPO_ROOT / p).resolve()
        if not fp.is_file():
            print(f"错误：参考图不存在: {fp}", file=sys.stderr)
            sys.exit(1)
        mime = mimetypes.guess_type(fp.name)[0] or "image/png"
        b64 = base64.b64encode(fp.read_bytes()).decode("ascii")
        out.append(f"data:{mime};base64,{b64}")
    return out


REF_STYLE_PREFIX = (
    "严格模仿参考图的画风：绢本工笔水墨设色的质感、细腻的勾线、靛蓝夜空底色、"
    "泥金勾云与洒金效果、清冷雅致的配色。只学画风，不要复制参考图的构图和内容。"
    "用这个画风绘制全新画面："
)


def generate_once(
    client: httpx.Client, key: str, prompt: str, model: str, size: str,
    refs: list[str] | None = None,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "response_format": "url",
        "size": size,
        "stream": False,
        "watermark": False,
    }
    if refs:
        payload["image"] = refs[0] if len(refs) == 1 else refs
    resp = client.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180.0,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    items = data.get("data") or []
    if not items:
        raise RuntimeError(f"响应无 data: {json.dumps(data, ensure_ascii=False)[:500]}")
    url = items[0].get("url")
    if not url:
        raise RuntimeError(f"响应无 url: {json.dumps(items[0], ensure_ascii=False)[:300]}")
    return url


def download_image(client: httpx.Client, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with client.stream("GET", url, timeout=120.0, follow_redirects=True) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    tmp.replace(dest)


def generate_with_retry(
    client: httpx.Client,
    key: str,
    card: TarotCard,
    model: str,
    size: str,
    refs: list[str] | None = None,
) -> str:
    prompt = prompt_for(card)
    if refs:
        prompt = REF_STYLE_PREFIX + prompt
    last_err: Exception | None = None
    tag = card.path
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return generate_once(client, key, prompt, model, size, refs)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
            last_err = e
            wait = RETRY_BASE_SEC * (2 ** (attempt - 1))
            log(f"  [{tag}] 网络错误 ({attempt}/{MAX_RETRIES}): {e} — {wait:.0f}s 后重试")
            time.sleep(wait)
        except RuntimeError as e:
            last_err = e
            msg = str(e)
            retryable = any(x in msg for x in ("429", "500", "502", "503", "504", "timeout", "Timeout"))
            if not retryable or attempt >= MAX_RETRIES:
                raise
            wait = RETRY_BASE_SEC * (2 ** (attempt - 1))
            log(f"  [{tag}] API 错误 ({attempt}/{MAX_RETRIES}): {msg[:200]} — {wait:.0f}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"重试耗尽: {last_err}") from last_err


def append_log(log_path: Path, record: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with _log_lock:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_one_card(
    key: str,
    card: TarotCard,
    dest: Path,
    model: str,
    size: str,
    log_path: Path,
    idx: int,
    total: int,
    refs: list[str] | None = None,
) -> tuple[bool, TarotCard, Path, str | None]:
    """单张生成（线程内独立 httpx 客户端）。"""
    log(f"[{idx}/{total}] {card.path} ({card.title})")
    t0 = time.time()
    try:
        # trust_env=False：不走系统/环境变量代理（火山是国内接口，本地代理反而握手失败）
        with httpx.Client(trust_env=False) as client:
            url = generate_with_retry(client, key, card, model, size, refs)
            download_image(client, url, dest)
        elapsed = time.time() - t0
        size_kb = dest.stat().st_size // 1024
        log(f"  OK [{card.path}] {size_kb} KB, {elapsed:.1f}s")
        append_log(log_path, {
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": card.path,
            "title": card.title,
            "status": "ok",
            "bytes": dest.stat().st_size,
            "seconds": round(elapsed, 2),
        })
        return True, card, dest, None
    except Exception as e:
        log(f"  FAIL [{card.path}]: {e}", err=True)
        append_log(log_path, {
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": card.path,
            "title": card.title,
            "status": "fail",
            "error": str(e),
        })
        return False, card, dest, str(e)


def run_batch_parallel(
    key: str,
    queue: list[tuple[TarotCard, Path]],
    model: str,
    size: str,
    log_path: Path,
    workers: int,
    refs: list[str] | None = None,
) -> tuple[int, int, list[tuple[TarotCard, Path]]]:
    ok = fail = 0
    failed: list[tuple[TarotCard, Path]] = []
    total = len(queue)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                run_one_card, key, card, dest, model, size, log_path, i, total, refs,
            ): (card, dest)
            for i, (card, dest) in enumerate(queue, 1)
        }
        for fut in as_completed(futures):
            success, card, dest, _err = fut.result()
            if success:
                ok += 1
            else:
                fail += 1
                failed.append((card, dest))

    return ok, fail, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="火山 Seedream 批量生成塔罗牌面")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    parser.add_argument("--dry-run", action="store_true", help="只打印待生成列表")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--size", default=DEFAULT_SIZE, help="Seedream size，如 2K")
    parser.add_argument("--only", nargs="+", help="只跑某组：major wands cups swords coins root")
    parser.add_argument("--paths", nargs="+", help="只跑指定相对路径，如 major/04-emperor.png")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并行线程数，默认 4")
    parser.add_argument("--rounds", type=int, default=2, help="全部跑完后对失败项再跑几轮")
    parser.add_argument(
        "--ref", nargs="+",
        help="风格参考图（本地路径，图生图模式）。如 assets/tarot/major/00-fool.png",
    )
    args = parser.parse_args()

    if args.workers < 1:
        print("workers 至少为 1", file=sys.stderr)
        sys.exit(1)

    key = api_key()
    refs = load_ref_images(args.ref) if args.ref else None
    cards = filter_cards(args)
    todo: list[tuple[TarotCard, Path]] = []
    for card in cards:
        dest = TAROT_DIR / card.path.replace("/", os.sep)
        if should_skip(dest, args.force):
            continue
        todo.append((card, dest))

    print(f"输出目录: {TAROT_DIR}")
    print(f"模型: {args.model}  size: {args.size}  watermark: false  workers: {args.workers}"
          + (f"  参考图: {len(refs)} 张" if refs else ""))
    print(f"总计 {len(cards)} 张，待生成 {len(todo)} 张，跳过 {len(cards) - len(todo)} 张")

    if args.dry_run:
        for card, dest in todo:
            print(f"  {card.path}  <-  {card.title}")
        return

    if not todo:
        print("没有需要生成的文件。")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"run-{stamp}.jsonl"
    total_ok = total_fail = 0
    failed: list[tuple[TarotCard, Path]] = []

    ok, fail, failed = run_batch_parallel(
        key, todo, args.model, args.size, log_path, args.workers, refs,
    )
    total_ok += ok
    total_fail += fail

    for rnd in range(1, args.rounds + 1):
        retry = [(c, d) for c, d in failed if not should_skip(d, False)]
        if not retry:
            break
        log(f"\n--- 失败重跑 第 {rnd}/{args.rounds} 轮，{len(retry)} 张，workers={args.workers} ---")
        ok, fail, failed = run_batch_parallel(
            key, retry, args.model, args.size, log_path, args.workers, refs,
        )
        total_ok += ok
        # 重跑成功的不再计为最终失败
        total_fail = len(failed)

    remaining = sum(
        1 for c in CARDS
        if not should_skip(TAROT_DIR / c.path.replace("/", os.sep), False)
    )
    print(f"\n完成：本轮成功 {total_ok}，仍缺 {remaining} 张。日志：{log_path}")


if __name__ == "__main__":
    main()
