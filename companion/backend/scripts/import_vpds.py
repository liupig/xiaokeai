"""下载候选里的直链 VPD，转成 VMD 并入库（不走下载接口，无验证码）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from sqlmodel import Session

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import engine  # noqa: E402
from app.services.importer import import_single_file  # noqa: E402
from app.services.vpd_to_vmd import convert_file  # noqa: E402
from app.paths import TMP_DIR  # noqa: E402

DETAILS = ROOT / "data" / "tmp" / "candidate_details.json"


def main() -> None:
    rows = json.loads(DETAILS.read_text(encoding="utf-8"))
    headers = {
        "Referer": "https://www.aplaybox.com/",
        "Origin": "https://www.aplaybox.com",
        "User-Agent": "Mozilla/5.0",
    }
    ok = skip = fail = 0
    with httpx.Client(headers=headers, timeout=60, trust_env=False, follow_redirects=True) as http:
        for row in rows:
            url = (row.get("content") or "").strip()
            if not url.lower().endswith(".vpd"):
                continue
            name = row.get("name") or "pose"
            cat = row.get("category") or "interact"
            print(f"VPD  {name}")
            try:
                resp = http.get(url)
                resp.raise_for_status()
                raw_name = unquote(Path(urlparse(url).path).name)
                src = TMP_DIR / raw_name
                src.write_bytes(resp.content)
                dest = TMP_DIR / (src.stem + ".vmd")
                convert_file(src, dest)
                with Session(engine) as s:
                    created = import_single_file(
                        s, dest, source="aplaybox",
                        source_url=f"https://www.aplaybox.com/details/motion/{row['uuid']}",
                        label=name[:40],
                        extra_meta={"category": cat, "from_vpd": True},
                    )
                print(f"  → 导入 {len(created)}：{created[0].label if created else '?'}")
                ok += 1
                src.unlink(missing_ok=True)
                dest.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                print(f"  → 失败 {exc}")
                fail += 1
    print(f"完成 VPD：成功 {ok} 失败 {fail} 跳过 {skip}")


if __name__ == "__main__":
    main()
