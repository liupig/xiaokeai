"""Build linear height, roughness and metal masks in the costume's registered UVs."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def surface(rgb, woven):
    value = rgb @ np.array([.2126, .7152, .0722], dtype=np.float32)
    fine = cv2.GaussianBlur(value, (0, 0), .75)
    detail = fine - cv2.GaussianBlur(value, (0, 0), 4.5)
    if woven:
        # The chart U axis crosses a piece, V runs from its top to its hem.
        y, x = np.indices(value.shape)
        warp = np.cos(2*np.pi*(x/5.8 + .14*np.sin(y/17)))
        pick = np.cos(2*np.pi*(y/4.2 + x/17))
        relief = .50 + 1.8*detail + .056*warp + .023*pick
        rough = .83 - 2.6*detail - .052*warp
        metal = np.zeros_like(value)
    else:
        # Neutral seed pearls and blue-green stone are separate from the
        # champagne edges and engraved shadow in the original setting.
        r, g, b = rgb.transpose(2, 0, 1)
        warm = np.clip((r-b-.010)*6 + (g-b)*2.4, 0, 1)
        shadow = np.clip((.69-fine)*2.7, 0, 1)
        metal = np.clip(.26 + .69*warm + .46*shadow, .2, 1)
        relief = .50 + detail*1.65
        rough = .76 + shadow*.19 - warm*.10 - 1.65*detail
    return np.uint8(255*np.clip(np.stack([relief, rough, metal], axis=2), 0, 1))


def bake_finishes(directory):
    def read(name):
        return np.asarray(Image.open(directory / f'yuexiao-{name}.jpg').convert('RGB'), dtype=np.float32)/255
    atlas = read('pattern')
    packed = np.empty(atlas.shape, dtype=np.uint8)
    # The blue channel for textiles holds the measured low-frequency studio
    # response. Correct only the pigment, so the live specular lobe still moves.
    field = np.asarray(Image.open(Path(__file__).with_name('yuexiao-studio-response.png')).convert('L'))
    # Do filtering separately so height and roughness never bleed across cuts.
    for y in range(0, atlas.shape[0], 256):
        for x in range(0, atlas.shape[1], 512):
            tile = np.s_[y:y+256, x:x+512]
            packed[tile] = surface(atlas[tile], True)
            packed[tile][:,:,:2] &= 252
            patch = field[y//8:(y+256)//8, x//8:(x+512)//8]
            packed[tile][:,:,2] = cv2.resize(patch, (512, 256), interpolation=cv2.INTER_LINEAR)
    def save(name, data):
        # Keep the three data channels independent through compression.
        Image.fromarray(data).save(directory / f'yuexiao-{name}-finish.png', optimize=True)
    save('cloth', packed)
    for name in ('filigree', 'arm-clasp'):
        save(name, surface(read(name), False))


if __name__ == '__main__':
    bake_finishes(Path(__file__).resolve().parents[3] / 'online-demo/frontend/public/models/qingyi-jade/textures')
