"""Generate original Shared Time UI artwork with the existing Ark configuration."""
from pathlib import Path

import httpx
from PIL import Image

from generate_tarot_seedream import api_key, download_image, generate_once
from generate_wish_art import punch_green


OUT = Path(__file__).resolve().parents[1] / 'assets' / 'journey'
MODEL = 'doubao-seedream-5-0-pro-260628'
JOBS = {
    'hero.jpg': (
        '宽横向构图，一本打开的精装共同相册放在右侧木质书桌上，相册里是温暖的共同生活插画，'
        '旁边有两杯热茶、一朵小花、手写信和一支画笔，左侧保留完整安静的深暖棕色墙面供界面标题排版。'
        '温柔手绘动画电影质感，细腻笔触，奶油色纸张、暖琥珀灯光、少量泥金细节，'
        '高级、克制、亲密、像一本会逐渐写满的时光册。不要人物、不要文字、不要水印、不要边框。'
    ),
    'empty-gifts.png': (
        '一本合上的暖棕色精装相册，封面只有细金花纹，旁边是一只奶油白信封和一朵粉色小花，'
        '完整居中，精致温暖的动画电影道具插画，纯绿色背景 #00ff00，四周留白，'
        '不要人物、不要文字、不要水印、不要边框。'
    ),
}


def main():
    key = api_key()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, prompt in JOBS.items():
        path = OUT / name
        if path.exists():
            print(f'{name}: already exists')
            continue
        with httpx.Client(trust_env=False) as client:
            url = generate_once(client, key, prompt, MODEL, '2K')
            download_image(client, url, path)
        if name.endswith('.png'):
            punch_green(path)
            with Image.open(path) as image:
                image.thumbnail((640, 640), Image.Resampling.LANCZOS)
                image.save(path, optimize=True)
        else:
            with Image.open(path) as image:
                image.convert('RGB').save(path, format='JPEG', quality=93)
        print(f'{name}: generated')


if __name__ == '__main__':
    main()
