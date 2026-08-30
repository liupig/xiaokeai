"""只下载 ZIP 动作包（每个压缩包里往往有多个 VMD）。直链 VPD 已另导入。"""
from __future__ import annotations

import asyncio
import json
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

DETAILS = ROOT / "data" / "tmp" / "candidate_details.json"
PROGRESS = ROOT / "data" / "tmp" / "gesture_progress.json"
GAP = 28
CAPTCHA_WAIT = 240


def load_token() -> str:
    with Session(engine) as s:
        return (settings_store.get_all(s).get("download") or {}).get("aplaybox_token", "")


def existing_urls() -> set:
    with Session(engine) as s:
        return {u for u in s.exec(select(Asset.source_url).where(Asset.kind == "motion")).all() if u}


def import_cb(archive, info, work_name, category):
    label = work_name.split("_by_")[0].strip()[:40]
    with Session(engine) as s:
        return import_downloaded(
            s, archive, source="aplaybox",
            source_url=f"https://www.aplaybox.com/details/{info['work_type']}/{info['uid']}",
            label=label,
            extra_meta={"category": category or classify_motion(work_name)},
        )


async def main() -> None:
    token = load_token()
    if not token:
        raise SystemExit("no token")
    rows = json.loads(DETAILS.read_text(encoding="utf-8"))
    zips = [r for r in rows if r.get("is_zip") and not r.get("is_pose")]
    have = existing_urls()
    progress = json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {"done": []}
    done = set(progress.get("done") or [])
    print(f"ZIP 候选 {len(zips)}，已有 url {len(have)}")
    ok = fail = skip = 0
    captcha = 0
    for i, row in enumerate(zips, 1):
        uid = row["uuid"]
        url = f"https://www.aplaybox.com/details/motion/{uid}"
        name = row.get("name") or uid
        cat = row.get("category") or "interact"
        print(f"\n[{i}/{len(zips)}] ({cat}) {name}")
        if uid in done or url in have:
            print("  已有，跳过")
            skip += 1
            continue
        task_id = downloader.create_task(url)

        def cb(archive, info, work_name, category=cat):
            return import_cb(archive, info, work_name, category)

        await downloader.run_download_task(task_id, url, token, cb)
        task = downloader.TASKS[task_id]
        status, msg = task.get("status"), task.get("message", "")
        print(f"  → {status}: {msg}")
        if status == "done":
            done.add(uid)
            progress["done"] = list(done)
            PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
            ok += 1
            print(f"  导入 {len(task.get('assets') or [])} 个资产")
        elif "图形验证" in str(msg):
            captcha += 1
            fail += 1
            print(f"  验证码，等待 {CAPTCHA_WAIT}s")
            await asyncio.sleep(CAPTCHA_WAIT)
            if captcha >= 5:
                print("验证码过多，结束本轮")
                break
        else:
            fail += 1
        await asyncio.sleep(GAP)
    print(f"\nZIP 完成：成功 {ok} 失败 {fail} 跳过 {skip}")


if __name__ == "__main__":
    asyncio.run(main())
