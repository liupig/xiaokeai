#!/usr/bin/env python3
"""用火山 Seedream 出一套小可爱界面图标（工笔夜色），再收成图标尺寸。

用法:
  python companion/scripts/generate_ui_icons.py
  python companion/scripts/generate_ui_icons.py --only settings tarot
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from generate_tarot_seedream import (  # noqa: E402
    DEFAULT_MODEL,
    api_key,
    download_image,
    generate_once,
    load_ref_images,
)

REPO = SCRIPT_DIR.parent
RAW_DIR = REPO / "assets" / "ui-icons" / "raw"
OUT_DIR = REPO / "frontend" / "src" / "assets" / "icons"
REF = REPO / "assets" / "tarot" / "samples" / "tarot-sample-17-star.png"

# 最终嵌进按钮的边长。按钮 36px，图标显示约 22px，64 是两倍图。
ICON_PX = 64

STYLE = (
    "应用图标，正方形构图。画风严格模仿参考图：绢本工笔、靛蓝夜色、泥金勾线、"
    "清冷雅致、少量洒金。只学画风，不要画人物、不要画风景、不要复制参考图内容。"
    "画面中央只有一个符号，外轮廓简单闭合，色块不超过四种，线条偏粗，"
    "缩小到三十二像素仍能一眼认出。"
    "背景必须是完全均匀的纯色深靛蓝 RGB(12,14,32)，不要云、不要星空、不要渐变、不要纹理。"
    "不要文字、不要水印、不要边框、不要牌框、不要落款。"
)

ICONS: dict[str, str] = {
    "quick": "符号是一张温和的小面具，细眉弯眼，嘴角浅浅上扬，金线勾轮廓，面色是暖玉白。",
    "review": "符号是一架微微拉开的戏台幕布，幕布后露出两只金色眼睛，像在看镜头。",
    "log": "符号是一卷横向展开的素绢卷轴，绢上只有三道短而粗的金线，像三行记录。",
    "assets": "符号是一只盖子微微打开的描金小木匣，匣身深色，金扣在前。",
    "keepsake": "符号是一只立式小相框，框是泥金，框心是一个侧身人物剪影，剪影留白。",
    "settings": "符号是一枚八齿金齿轮，齿少而粗，正中嵌一颗小小的紫水晶。",
    "cam": "符号是一台横置的电影摄影机，机身是扁长盒子，右侧接一支短镜头筒，镜头朝右。不要照相机，不要圆形大镜头，不要月亮。",
    "film": "符号是一段短胶片，左右齿孔清晰，正中一个金色的三角播放符。",
    "mic": "符号是一只立式小铜话筒，圆头、细杆、圆底座，金线勾边。",
    "tarot": "符号是一张竖立的卡牌，牌面中央一枚金色八角星罗盘，牌面靛蓝，不要任何文字。",
    "code": "符号是一扇小窗，窗内只有三行发光的短金线，像三行字，不要真实字母。",
    "snap": "符号是一台方盒照相机，正面镜头是一轮金边圆月。",
    "rec": "符号是一颗圆润的朱红圆钮，外圈一环金边，像录制键。",
    "send": "符号是一只向前飞的素白纸鹤，翼尖点一点金，姿态简单。",
    "chevron": "符号是一个向下的粗金线折角，像一个展开用的尖角，只有这一道折线，不要别的东西。",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--size", default="2K")
    parser.add_argument("--no-ref", action="store_true")
    args = parser.parse_args()

    names = args.only or list(ICONS)
    unknown = [n for n in names if n not in ICONS]
    if unknown:
        print("未知图标:", ", ".join(unknown), file=sys.stderr)
        sys.exit(1)

    key = api_key()
    refs = None if args.no_ref else load_ref_images([str(REF)])
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    todo = []
    for name in names:
        dest = RAW_DIR / f"{name}.png"
        if dest.is_file() and dest.stat().st_size > 10_000 and not args.force:
            print(f"skip {name}")
            continue
        todo.append(name)

    print(f"待生成 {len(todo)} / {len(names)}  size={args.size}")
    if not todo:
        return

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def one(name: str) -> None:
        prompt = STYLE + ICONS[name]
        dest = RAW_DIR / f"{name}.png"
        with httpx.Client(trust_env=False) as client:
            url = generate_once(client, key, prompt, args.model, args.size, refs)
            download_image(client, url, dest)
        print(f"OK {name} {dest.stat().st_size // 1024}KB", flush=True)

    failed = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(one, n): n for n in todo}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                fut.result()
            except Exception as e:
                failed.append(name)
                print(f"FAIL {name}: {e}", file=sys.stderr, flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
