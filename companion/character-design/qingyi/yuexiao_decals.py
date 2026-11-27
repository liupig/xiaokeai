"""Fit the magnolia expression artwork to Xiaokeai's existing facial morph UVs."""
import json
from pathlib import Path

from PIL import Image, ImageOps


ART = Path(__file__).with_name("expression-decals")
EMOTES = "yuexiao-magnolia-emotes.png"
CHEEKS = "yuexiao-magnolia-cheeks.png"
# Row-major order of the painted sheet. The decal planes and iris shells
# sample slightly different UV rectangles even when their atlas cells line up.
with (ART / "stickers.json").open(encoding="utf-8") as manifest:
    SPRITES = [(s["morph"], s["label"], *s["rect"]) for s in json.load(manifest) if "rect" in s]


# Card centres relative to the active cheek overlay's vertical midpoint.
# Width and height describe the whole sampled quad, in the model's PMX units.
TEMPLE_CARDS = {
    "#":   (-1.13, 1.35, -.78, .90, .90),
    "#2":  (1.09, 1.34, -.86, .93, .93),
    "？":  (1.25, 1.31, -.52, .98, .98),
    "！":  (1.25, 1.36, -.54, .97, .97),
    "ZZZ": (-1.27, 1.41, -.46, 1.00, 1.00),
    "汗":  (.79, .21, -.65, .71, .71),
    "はちゅ": (-1.24, 1.06, -.67, .92, .92),
    "惊":  (1.16, 1.54, -.55, 1.02, 1.02),
    "……": (1.23, 1.08, -.54, 1.06, .46),
}


def fit_temple_cards(model):
    morphs = {m.name: m for m in model.morphs}
    cheek = morphs["FaceRed"].offsets
    heights = [model.vertices[o.index].co[1] + o.offset[1] for o in cheek]
    middle = (min(heights) + max(heights)) / 2
    for name, (x, y, z, width, height) in TEMPLE_CARDS.items():
        corners = morphs[name].offsets
        if len(corners) != 4:
            raise ValueError(f"Expected a four-corner facial decal for {name}")
        u, v = zip(*(model.vertices[o.index].uv for o in corners))
        for o in corners:
            vert = model.vertices[o.index]
            du = (vert.uv[0] - min(u)) / (max(u)-min(u)) - .5
            dv = (vert.uv[1] - min(v)) / (max(v)-min(v)) - .5
            target = (x + width*du, middle + y - height*dv, z)
            o.offset = tuple(value-base for value, base in zip(target, vert.co))


def fit_emotes():
    atlas = Image.new("RGBA", (2048, 2048))
    with Image.open(ART / "magnolia-emote-sheet.png") as sheet:
        sheet = sheet.convert("RGBA")
    sprites = {}
    for index, (morph, _, u, v, width, height) in enumerate(SPRITES):
        row, col = divmod(index, 4)
        box = tuple(round(n*size/4) for n, size in (
            (col, sheet.width), (row, sheet.height),
            (col+1, sheet.width), (row+1, sheet.height)))
        tile = sheet.crop(box)
        alpha = tile.getchannel("A").point(lambda a: a if a >= 10 else 0)
        # Cheek powder is translucent on skin. The symbol decals retain
        # their firmer edges so punctuation and eye highlights read at a distance.
        if morph in ("照れ", "照れ2"):
            alpha = alpha.point(lambda a: round(a * .58))
        tile.putalpha(alpha)
        tile = tile.crop(alpha.getbbox())
        sprites[morph] = tile
        if morph == "照れ":
            # U increases toward the nose on both cheek cards.
            tile = ImageOps.mirror(tile)
        scale = min(width*atlas.width/tile.width, height*atlas.height/tile.height)
        stamp = tile.resize((round(tile.width*scale), round(tile.height*scale)), Image.LANCZOS)
        anchor = (round(u*atlas.width-stamp.width/2), round(v*atlas.height-stamp.height/2))
        atlas.alpha_composite(stamp, anchor)
    return atlas, sprites


def fit_cheeks(source):
    """Replace the fitted blush island and preserve the separate native details."""
    with Image.open(source) as im:
        cheeks = im.convert("RGBA")
    with Image.open(ART / "magnolia-blush-uv.png") as im:
        blush = im.convert("RGBA")
    if cheeks.size != blush.size or cheeks.size != (1024, 1024):
        raise ValueError("Unexpected cheek UV atlas size")
    cheeks.paste((0, 0, 0, 0), (0, 275, 1024, 700))
    cheeks.alpha_composite(blush)
    return cheeks


def bind_expression_art(model, directory):
    fit_temple_cards(model)
    materials = {m.name: m for m in model.materials}
    atlas, _ = fit_emotes()
    atlas.save(directory / EMOTES)
    cheeks = model.textures[materials["Face+"].texture]
    fit_cheeks(cheeks.path).save(directory / CHEEKS)
    model.textures[materials["Facial"].texture].path = str(directory / EMOTES)
    cheeks.path = str(directory / CHEEKS)
