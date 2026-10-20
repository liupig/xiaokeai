#!/usr/bin/env python3
"""Paint the wishing pool, the coin face, and the twelve throwable props.

Props are requested as solid objects on a flat green screen, then keyed to a
transparent PNG. Files already larger than 10KB are left alone, so a rerun
does not spend another image call. The key is read from scripts/.env and is
never printed. Pool and coin images are not keyed.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from generate_tarot_seedream import (  # noqa: E402
    api_key,
    download_image,
    generate_once,
    log,
)

import httpx  # noqa: E402

OUT = SCRIPT_DIR.parent / "assets" / "wish"
ITEMS = OUT / "items"
MODEL = "doubao-seedream-5-0-pro-260628"
SIZE = "2K"

STAGE = (
    "画面里只有这一件东西，四分之三视角，能看出厚度、体积和材质。"
    "物体居中，四周留出空位。背景必须是均匀的纯绿色，接近色值 0,255,0，"
    "不要渐变，不要地面，不要把影子铺在背景上，不要文字，不要数字，不要字母，不要水印，不要边框。"
    "物体本身不要出现绿色。暖光从左上方打下，轮廓有一圈淡淡的冷光。"
    "精细，像一件能被远远扔进池子的实体道具。"
)

JOBS = (
    (
        "pool.png",
        False,
        "一幅正俯视的圆形许愿池，占满画面。池水是深靛蓝，水面有细密的金色涟漪和几片漂浮的莲瓣，"
        "池心一点暖金的光，池沿是一圈细金边。绢本工笔水墨设色，细腻勾线，泥金勾云，清冷雅致。"
        "不要人物，不要文字，不要数字，不要金币堆，不要边框。",
    ),
    (
        "coin.png",
        False,
        "一枚正圆的古金币居中，币面只有一圈细纹和一朵小小的莲，没有文字没有数字。"
        "金币周围是干净的深靛蓝底。绢本工笔，泥金，金属高光。不要文字，不要边框。",
    ),
    ("items/work.png", True, "一只旧皮革公文包，黄铜搭扣，包面有使用过的压痕，斜放，能看见厚度。" + STAGE),
    ("items/phone.png", True, "一只深色金属边框的智能手机，屏幕亮着暖金色的抽象光斑，没有图标。斜放，能看见机身厚度。" + STAGE),
    ("items/computer.png", True, "一台薄金属笔记本电脑，掀开大约四十度，屏幕是暖金色的空画面。能看见转轴和厚度。" + STAGE),
    ("items/bracelet.png", True, "一串木珠和金珠绕成的手串，珠子圆润，中间有穿绳，盘成一圈，有体积。" + STAGE),
    ("items/key.png", True, "一把古铜钥匙，齿和环都清楚，金属有旧包浆和高光，斜放。" + STAGE),
    ("items/letter.png", True, "一封厚信，米白色信封微微鼓起，火漆是暗红色圆印，没有字。能看出纸的厚度。" + STAGE),
    ("items/worry.png", True, "一团能拿在手里的烦恼，像墨色丝线缠成的结，中间夹着几缕金线，有明确的体积和高光。" + STAGE),
    ("items/magnet.png", True, "一块红与银的马蹄磁铁，两端圆润，旁边有几粒细小的金色火星，金属高光清楚。" + STAGE),
    ("items/card.png", True, "一张黑色金属信用卡，斜放，能看见厚度，上面有一枚金色芯片和暗纹，没有数字没有字母。" + STAGE),
    ("items/alarm.png", True, "一座黄铜小闹钟，头顶两个铃，玻璃表面有高光，没有数字，指针是两根细金针。" + STAGE),
    ("items/sock.png", True, "一只织得很细的棉袜，米白和靛蓝的条纹，袜口微微卷起，单独一只，布料有厚度。" + STAGE),
    ("items/meeting.png", True, "一本厚厚的深蓝皮面记事本，夹着一根红丝带，封面没有任何字，能看出书脊的厚度。" + STAGE),
)


def punch_green(path: Path) -> None:
    """把纯绿背景抠成透明，并压掉物体边缘的绿边。"""
    image = Image.open(path).convert("RGBA")
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            red, green, blue, _alpha = pixels[x, y]
            score = green - max(red, blue)
            if score > 36 and green > 80:
                pixels[x, y] = (0, 0, 0, 0)
                continue
            if score > 10 and green >= red and green >= blue:
                alpha = int(max(0, min(255, (1 - (score - 10) / 36) * 255)))
                pixels[x, y] = (red, min(green, max(red, blue)), blue, alpha)
                continue
            if green > max(red, blue) + 8:
                green = max(red, blue) + 8
            pixels[x, y] = (red, green, blue, 255)
    image.save(path, "PNG")


def paint_one(key: str, name: str, prompt: str, keyed: bool) -> str:
    dest = OUT / name
    if dest.is_file() and dest.stat().st_size > 10_000:
        return f"跳过 {name}"
    last = "未知错误"
    for attempt in range(1, 5):
        try:
            with httpx.Client() as client:
                url = generate_once(client, key, prompt, MODEL, SIZE)
                download_image(client, url, dest)
            if keyed:
                punch_green(dest)
            return f"已写入 {dest}"
        except Exception as exc:
            last = str(exc)[:240]
            time.sleep(2 * attempt)
    raise RuntimeError(f"{name}: {last}")


def main() -> None:
    key = api_key()
    OUT.mkdir(parents=True, exist_ok=True)
    ITEMS.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(paint_one, key, name, prompt, keyed) for name, keyed, prompt in JOBS]
        for job in as_completed(jobs):
            log(job.result())


if __name__ == "__main__":
    main()
