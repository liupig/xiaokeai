"""从模之屋批量搜索并下载待机 / 打招呼 / 互动动作。

用法（在 companion/backend 目录）：
    python scripts/batch_dl_gestures.py              # 搜索 + 下载
    python scripts/batch_dl_gestures.py --search     # 只搜索
    python scripts/batch_dl_gestures.py --resume     # 跳过已完成，继续下
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import Asset  # noqa: E402
from app.services import downloader, settings_store  # noqa: E402
from app.services.catalog import classify_motion  # noqa: E402
from app.services.importer import import_downloaded  # noqa: E402

OUT_DIR = ROOT / "data" / "tmp"
CANDIDATES_PATH = OUT_DIR / "gesture_candidates.json"
PROGRESS_PATH = OUT_DIR / "gesture_progress.json"

SEARCHES = {
    "idle": ["待机", "待機", "站立待机", "闲置动作", "站姿"],
    "greet": ["打招呼", "挥手", "招手", "问好", "挥手再见", "挨拶"],
    "interact": [
        "互动", "比心", "飞吻", "害羞", "思考", "托腮", "叉腰", "点头", "摇头",
        "鼓掌", "歪头", "伸懒腰", "坐下", "坐姿", "说话动作", "鞠躬", "比耶",
        "卖萌", "撩人", "来这边",
    ],
    "pack": ["日常动作", "动作包", "动作合集", "日常动作包", "姿势合集", "动作集"],
}

PACK_KWS = ("动作包", "合集", "pack", "日常动作", "姿势集", "ポーズ集",
            "モーション集", "动作集")
NSFW_KWS = ("r18", "18禁", "色情", "性交", "性爱", "h动作", "nsfw", "里番",
            "裸舞", "高潮", "射精", "推倒")
SKIP_KWS = ("出售", "仅展示", "爱发电", "ifdian", "自用", "密码是", "下载密码",
            "gidle", "(g)-idle", "g-idle", "(g)idle",
            "2253", "抖音快手热门", "格斗", "我的世界", "持枪")

# 每类最多收下多少个（动作包另计）
QUOTAS = {"idle": 20, "greet": 18, "interact": 36, "pack": 14}
DOWNLOAD_GAP = 16         # 两次下载间隔，降低验证码概率
CAPTCHA_WAIT = 180        # 触发图形验证后等待秒数
MAX_CAPTCHA = 6


def load_token() -> str:
    with Session(engine) as s:
        token = (settings_store.get_all(s).get("download") or {}).get("aplaybox_token", "")
    if token:
        return token
    fallback = ROOT / "data" / "tmp" / "set_token.json"
    if fallback.exists():
        data = json.loads(fallback.read_text(encoding="utf-8"))
        return (data.get("download") or {}).get("aplaybox_token", "")
    return ""


def should_skip(text: str) -> bool:
    t = (text or "")
    lower = t.lower()
    if any(k in lower for k in NSFW_KWS):
        return True
    return any(k in t or k.lower() in lower for k in SKIP_KWS)


def is_pack(name: str) -> bool:
    n = (name or "").lower()
    return any(k.lower() in n or k in (name or "") for k in PACK_KWS)


def score_item(item: dict, cat: str) -> float:
    name = item.get("work_name") or ""
    intro = item.get("introduction") or ""
    kws = SEARCHES.get(cat, [])
    s = 0.0
    for kw in kws:
        if kw in name:
            s += 12
        elif kw.lower() in name.lower():
            s += 10
        elif kw in intro:
            s += 3
    if cat != "pack" and is_pack(name):
        s += 8
    dl = item.get("downloads") or 0
    s += min(math.log10(max(dl, 1)), 5) * 2.5
    return s


def already_downloaded_urls() -> set:
    with Session(engine) as s:
        rows = s.exec(select(Asset.source_url).where(Asset.kind == "motion")).all()
    return {u for u in rows if u}


def load_progress() -> dict:
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {"done": [], "error": [], "skipped": []}


def save_progress(p: dict) -> None:
    PROGRESS_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


async def search_all() -> dict:
    client = downloader.AplayboxClient()
    by_uuid: dict = {}
    try:
        for cat, keywords in SEARCHES.items():
            for kw in keywords:
                for page in (1, 2, 3):
                    try:
                        data = await client.search(kw, work_type_id=2, page=page, per_page=20)
                    except Exception as exc:  # noqa: BLE001
                        print(f"  搜索失败 [{cat}/{kw} p{page}]: {exc}")
                        continue
                    for it in data.get("items") or []:
                        uid = it.get("work_uuid")
                        name = it.get("work_name") or ""
                        if not uid or should_skip(name + (it.get("introduction") or "")):
                            continue
                        # 关键词必须出现在标题，避免简介误匹配
                        if kw not in name and kw.lower() not in name.lower():
                            continue
                        rec = by_uuid.setdefault(uid, {**it, "cats": set(), "score": 0})
                        rec["cats"].add(cat)
                        rec["score"] = max(rec["score"], score_item(it, cat))
                    await asyncio.sleep(0.25)
                print(f"  搜完「{kw}」累计 {len(by_uuid)} 条")
    finally:
        await client.close()

    grouped = {"idle": [], "greet": [], "interact": [], "pack": []}
    for rec in by_uuid.values():
        name = rec.get("work_name") or ""
        cats = rec["cats"]
        if "pack" in cats or is_pack(name):
            bucket = "pack"
        elif "idle" in cats:
            bucket = "idle"
        elif "greet" in cats:
            bucket = "greet"
        else:
            bucket = "interact"
        item = {k: v for k, v in rec.items() if k != "cats"}
        item["category"] = bucket
        grouped[bucket].append(item)

    selected = []
    seen = set()
    for cat, quota in QUOTAS.items():
        items = sorted(grouped[cat], key=lambda x: x["score"], reverse=True)
        picked = 0
        for it in items:
            uid = it["work_uuid"]
            if uid in seen:
                continue
            seen.add(uid)
            selected.append(it)
            picked += 1
            if picked >= quota:
                break
        print(f"  {cat}: 候选 {len(items)} → 入选 {picked}")

    CANDIDATES_PATH.write_text(
        json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共入选 {len(selected)} 个作品 → {CANDIDATES_PATH}")
    return {"selected": selected, "grouped_counts": {k: len(v) for k, v in grouped.items()}}


def _import_cb(archive: Path, info: dict, work_name: str, category: str):
    label = work_name.split("_by_")[0].strip()[:40]
    with Session(engine) as s:
        return import_downloaded(
            s, archive, source="aplaybox",
            source_url=f"https://www.aplaybox.com/details/{info['work_type']}/{info['uid']}",
            label=label,
            extra_meta={"category": category or classify_motion(work_name)},
        )


async def download_all(token: str, resume: bool) -> None:
    selected = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    progress = load_progress() if resume else {"done": [], "error": [], "skipped": []}
    done = set(progress["done"])
    existing = already_downloaded_urls()
    captcha_hits = 0
    ok = fail = skip = 0

    for i, item in enumerate(selected, 1):
        uid = item["work_uuid"]
        url = item["url"]
        name = item.get("work_name") or uid
        cat = item.get("category") or "interact"
        print(f"\n[{i}/{len(selected)}] ({cat}) {name}")

        if uid in done or url in existing:
            print("  已有，跳过")
            skip += 1
            continue

        task_id = downloader.create_task(url)

        def make_cb(category: str):
            def cb(archive, info, work_name):
                return _import_cb(archive, info, work_name, category)
            return cb

        await downloader.run_download_task(task_id, url, token, make_cb(cat))
        task = downloader.TASKS[task_id]
        status = task.get("status")
        msg = task.get("message", "")
        print(f"  → {status}: {msg}")

        if status == "done":
            progress["done"].append(uid)
            ok += 1
            n = len(task.get("assets") or [])
            print(f"  导入 {n} 个资产")
        elif "图形验证" in str(msg):
            captcha_hits += 1
            progress["error"].append({"uid": uid, "name": name, "msg": msg})
            fail += 1
            if captcha_hits >= MAX_CAPTCHA:
                print("图形验证次数过多，停止本轮。可用 --resume 稍后再继续。")
                save_progress(progress)
                break
            print(f"  等待 {CAPTCHA_WAIT}s 后继续…")
            await asyncio.sleep(CAPTCHA_WAIT)
        else:
            progress["error"].append({"uid": uid, "name": name, "msg": msg})
            fail += 1

        save_progress(progress)
        await asyncio.sleep(DOWNLOAD_GAP)

    print(f"\n完成：成功 {ok}  失败 {fail}  跳过 {skip}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", action="store_true", help="只搜索不下载")
    parser.add_argument("--resume", action="store_true", help="从进度文件继续下载")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    if not args.resume or not CANDIDATES_PATH.exists():
        print("=== 搜索模之屋动作 ===")
        await search_all()
        if args.search:
            print(f"耗时 {time.time() - t0:.0f}s")
            return

    token = load_token()
    if not token:
        print("没有模之屋 token：请到设置 → 下载里粘贴，或确认 data/tmp/set_token.json")
        sys.exit(1)
    print(f"token 已加载（长度 {len(token)}）")
    print("=== 开始下载 ===")
    await download_all(token, resume=args.resume)
    print(f"总耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
