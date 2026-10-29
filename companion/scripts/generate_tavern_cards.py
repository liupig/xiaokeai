#!/usr/bin/env python3
"""用火山 Seedream 出魅影酒馆的分牌：萝莉、少女、御姐各六张，外加牌背。

魅和影沿用现成的 mei.png、ying.png，这里不重画。
少女第一张直接复制现在的 girl.png。其余都以它为画风参考。

用法（在 companion 目录的上一级，或任意处）:
  python companion/scripts/generate_tavern_cards.py
已有的大图默认跳过。密钥读 companion/.env 的 ARK_API_KEY，不写进命令行。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
OUT = ROOT / "assets" / "tavern"
API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DEFAULT_MODEL = "doubao-seedream-5-0-pro-260628"
MAX_RETRIES = 5
_print_lock = threading.Lock()

TAIL = (
    "竖构图 2:3，人物居中，上下留一点空。"
    "画面里不要任何文字、字母、数字、水印、签名、边框。"
    "不要真人照片，不要3D瓷娃娃，不要Q版婴儿。"
)
STYLE = (
    "严格模仿参考图的画风：清透的日系动漫插画、细腻发丝、明亮的眼睛、干净的线。"
    "只学画风，不要复制参考图的脸、衣服、姿势和背景。"
)

LOLI = (
    "浅粉色系的洛丽塔少女，和参考图同一种日系动漫少女，年龄感与参考图接近。"
    "完全着装的洋装，蕾丝、缎带、蓬裙盖到膝下。不是瓷娃娃，不是婴儿，不是Q版大头，不是真人。"
    "主色只有浅粉、奶油白和一点点樱花。不要蓝天，不要黄衣，不要冷色银蓝。"
)
LADY = (
    "冷色系的成年动漫女性，猫眼三姐妹那样：细长上挑的眼睛，利落，气场稳，带一点笑。"
    "画风仍是参考图那种清透日系动漫，不要照片，不要娃娃，不要幼态圆脸。"
    "主色只有银、冰青、午夜蓝、薰衣草灰。不要浅粉，不要黄衣，不要蓝天暖光。"
    "衣服完整，领口扣好，不裸露。"
)
GIRL = (
    "和参考图同一种晴空动漫少女：蓝天、柠檬黄外套、白裙、蜂蜜金头发，清甜元气。"
    "姿势、表情和构图必须和参考图不同。不要浅粉洛丽塔，不要冷色夜景，不要照片。"
)

CARDS = [
    {"path": "loli-1.png", "prompt": LOLI + "浅粉双马尾，大蝴蝶结，抱一束浅粉玫瑰，站在玻璃花房里。" + TAIL},
    {"path": "loli-2.png", "prompt": LOLI + "侧坐在白色窗台，缎带礼帽，手里一杯草莓奶油，裙摆铺开。" + TAIL},
    {"path": "loli-3.png", "prompt": LOLI + "回眸，编发盘着粉花，多层蛋糕裙，蕾丝手套，身后是樱花。" + TAIL},
    {"path": "loli-4.png", "prompt": LOLI + "提着裙摆向前走，短而卷的浅粉发，珍珠项链，背景是柔和的浅粉光。" + TAIL},
    {"path": "loli-5.png", "prompt": LOLI + "坐在花藤秋千上，裙摆像一朵打开的花，发间别着小粉花。" + TAIL},
    {"path": "loli-6.png", "prompt": LOLI + "低头整理袖口蕾丝，长直的浅粉发，一手撑着蕾丝阳伞。" + TAIL},
    {"path": "girl-2.png", "prompt": GIRL + "跳起来去够一枝白花，黄外套扬起，马尾向上，满是蓝天。" + TAIL},
    {"path": "girl-3.png", "prompt": GIRL + "骑着浅色自行车回眸，黄衣白裙，晴空和飞着的云。" + TAIL},
    {"path": "girl-4.png", "prompt": GIRL + "坐在草地上笑，黄开衫搭在肩上，白云很低。" + TAIL},
    {"path": "girl-5.png", "prompt": GIRL + "正跑过来，马尾横着甩开，柠檬黄外套，蓝天白云。" + TAIL},
    {"path": "girl-6.png", "prompt": GIRL + "靠着白色栏杆，黄背心配白裙，海风，背后是蓝天。" + TAIL},
    {"path": "lady-1.png", "prompt": LADY + "银白长直发，冰蓝色修身长外套，侧身回望，身后是冷月。" + TAIL},
    {"path": "lady-2.png", "prompt": LADY + "午夜蓝高领长裙，栗色长发被冷光打成灰蓝，手里一支细长的黑伞。" + TAIL},
    {"path": "lady-3.png", "prompt": LADY + "薰衣草灰的短发，银色耳坠，冷白衬衫和深蓝背心，站在夜窗前。" + TAIL},
    {"path": "lady-4.png", "prompt": LADY + "墨蓝长裙，冷金细链，高马尾，微微俯视，背景是冷色城市灯。" + TAIL},
    {"path": "lady-5.png", "prompt": LADY + "银灰盘发，冰蓝披肩，坐着，眼神锐利，嘴角一点笑。" + TAIL},
    {"path": "lady-6.png", "prompt": LADY + "午夜蓝风衣，利落短发，猫眼，雨夜，霓虹只有冷青和银。" + TAIL},
    {
        "path": "mei.png",
        "prompt": (
            "大王，魅影酒馆的女馆主，一张脸就要认出来。"
            "和参考图同一种清透日系动漫画风，但不要金发，不要黄衣，不要浅粉洛丽塔，不要银发御姐。"
            "浓密的暗紫色长卷发，额心一条细金链垂到眉心，眼尾一颗泪痣，笑着却把人看穿。"
            "黑纱只搭在发间，眼睛完全露出来。深紫与赤金的高领礼服，金线绣着飞蛾，领口扣到喉，不裸露。"
            "一手举着暗红色的水晶杯，杯沿停着一只发光的幻影飞蛾。背景是烛火和金粉。"
            "平面插画铺满四边，正对观者，不要透视，不要立体盒子，不要白边。"
            + TAIL
        ),
    },
    {
        "path": "ying.png",
        "prompt": (
            "小王，暗夜侍者，不是第三位美人。和参考图同一种清透日系动漫画风。"
            "中性、瘦、年轻。窄脸尖下巴，短而乱的墨色头发，一只眼睛被光削亮，另一只沉在影子里，眉毛挑起，坏笑。"
            "银半面具推到额角，没有戴上。墨色短外套扣到喉，银扣。"
            "侧身像刚从暗处闪出来，食指竖在唇边。背景是夜巷和一盏将灭的纸灯。只有银、墨、冷蓝。"
            "不要长裙，不要长卷发，不要紫金馆主，不要浅粉，不要黄衣，不要照片。"
            "平面插画铺满四边，正对观者，不要透视，不要立体盒子，不要白边。"
            + TAIL
        ),
    },
    {
        "path": "back.png",
        "force": True,
        "prompt": (
            "一张正对观者的平面插画，没有任何透视，不要立体铁盒，不要厚度，不要桌子，不要白边，"
            "图案铺满画面的四条边。"
            "一列三行，用极细的金线分成三格，融成同一幅画："
            "上格浅粉洛丽塔动漫少女的半身，中格银蓝冷色御姐的半身，下格蓝天黄衣动漫少女的半身。"
            "花瓣和光穿过金线。画风和参考图一样的清透日系动漫。"
            "不要文字，不要字母，不要水印，不要面具。"
        ),
    },
]


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def load_env() -> None:
    for env_path in (SCRIPT_DIR / ".env", ROOT / ".env"):
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def api_key() -> str:
    load_env()
    key = (os.environ.get("ARK_API_KEY") or os.environ.get("VOLC_ARK_API_KEY") or "").strip()
    if not key:
        print("缺少 ARK_API_KEY", file=sys.stderr)
        sys.exit(1)
    return key


def ref_uri() -> str:
    import base64
    import mimetypes

    fp = OUT / "girl.png"
    mime = mimetypes.guess_type(fp.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(fp.read_bytes()).decode('ascii')}"


def generate_once(client: httpx.Client, key: str, prompt: str, model: str, size: str, ref: str | None) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "response_format": "url",
        "size": size,
        "stream": False,
        "watermark": False,
    }
    if ref:
        payload["image"] = ref
        prompt = STYLE + prompt
        payload["prompt"] = prompt
    resp = client.post(
        API_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=180.0,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    items = data.get("data") or []
    if not items or not items[0].get("url"):
        raise RuntimeError(f"无图: {json.dumps(data, ensure_ascii=False)[:400]}")
    return items[0]["url"]


def ensure_png(dest: Path) -> None:
    raw = dest.read_bytes()
    if not raw.startswith(b"\xff\xd8\xff"):
        return
    try:
        from PIL import Image
    except ImportError:
        log(f"{dest.name} 仍是 JPEG")
        return
    im = Image.open(dest).convert("RGB")
    im.save(dest, "PNG")


def download(client: httpx.Client, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with client.stream("GET", url, timeout=120.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    tmp.replace(dest)


def one(card: dict, key: str, model: str, size: str, force: bool, ref: str) -> str:
    dest = OUT / card["path"]
    if dest.is_file() and dest.stat().st_size > 10_000 and not force and not card.get("force"):
        log(f"跳过 {card['path']}")
        return "skip"
    last = "未知"
    with httpx.Client() as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                url = generate_once(client, key, card["prompt"], model, size, ref)
                download(client, url, dest)
                ensure_png(dest)
                log(f"好了 {card['path']} ({dest.stat().st_size} bytes)")
                return "ok"
            except Exception as exc:
                last = str(exc)[:240]
                wait = 3 * (2 ** (attempt - 1))
                log(f"{card['path']} 第 {attempt} 次失败：{last} — {wait}s 后再试")
                time.sleep(wait)
    raise RuntimeError(f"{card['path']} 失败：{last}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--size", default="1664x2496")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    key = api_key()
    src = OUT / "girl.png"
    if not src.is_file():
        print("缺少画风参考 assets/tavern/girl.png", file=sys.stderr)
        sys.exit(1)
    (OUT / "girl-1.png").write_bytes(src.read_bytes())
    ref = ref_uri()
    cards = CARDS
    if args.only:
        want = set(args.only)
        cards = [c for c in cards if c["path"].split(".")[0] in want or c["path"] in want]
    OUT.mkdir(parents=True, exist_ok=True)
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(one, card, key, args.model, args.size, args.force, ref): card for card in cards}
        for fut in as_completed(futs):
            card = futs[fut]
            try:
                fut.result()
            except Exception as exc:
                failed.append(card["path"])
                log(f"放弃 {card['path']}：{exc}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
