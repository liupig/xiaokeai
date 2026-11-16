"""Validate and create contact sheets for the shared-life artwork."""
from pathlib import Path
from PIL import Image, ImageDraw
from generate_life_art import BLUE_PROPS, JOBS, OUT, PROPS

ARTIFACTS = Path(__file__).resolve().parents[1] / 'artifacts' / 'life-art'

def make_sheet(names, output):
    cols, cell_w, cell_h = 4, 256, 200
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell_w, rows * cell_h), '#ede5da')
    draw = ImageDraw.Draw(sheet)
    for i, name in enumerate(names):
        x, y = (i % cols) * cell_w, (i // cols) * cell_h
        path = OUT / name
        if not path.is_file():
            draw.text((x + 8, y + 8), f'MISSING {name}', fill='#b22')
            continue
        with Image.open(path) as source:
            source.load()
            picture = source.convert('RGBA')
            picture.thumbnail((cell_w - 12, cell_h - 30), Image.Resampling.LANCZOS)
            bg = Image.new('RGBA', picture.size, '#d6cec3')
            bg.alpha_composite(picture)
            sheet.paste(bg.convert('RGB'), (x + (cell_w-picture.width)//2, y + 2))
            draw.text((x + 8, y + cell_h - 22), name, fill='#30271f')
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=88)

def main():
    backgrounds = list(JOBS)
    props = [f'{name}.png' for name in [*PROPS, *BLUE_PROPS]]
    errors = []
    for name in backgrounds + props:
        path = OUT / name
        try:
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                if name.endswith('.png') and (img.mode != 'RGBA' or img.getchannel('A').getextrema()[0] > 0):
                    errors.append(f'{name}: missing transparency')
                if min(img.size) < 192:
                    errors.append(f'{name}: too small')
        except Exception as exc:
            errors.append(f'{name}: {type(exc).__name__}')
    make_sheet(backgrounds, ARTIFACTS / 'backgrounds.jpg')
    make_sheet(props, ARTIFACTS / 'props.jpg')
    print(f'checked={len(backgrounds) + len(props)} errors={len(errors)}')
    for error in errors:
        print(error)
    if errors:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
