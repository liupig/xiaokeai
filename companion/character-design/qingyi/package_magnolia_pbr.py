"""Package the released Xiaokeai PMX with its UV-matched stage material profile."""
import argparse
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import cv2
import numpy as np
from PIL import Image

from build_lanxu import DESIGN, OUT, PMX
from magnolia_nape_lining import ramp, shorts_hem
from magnolia_neckline_light import apply_neckline_light


SKIN_MAPS = {'Face_':'skin-zones', 'Up_Skin':'upper-skin', 'QingyiTorso':'torso-skin',
             'Down_Skin':'lower-skin', 'QingyiScalp':'nape-zones'}


def facial_zones(xyz):
    x,y,z = xyz.T
    def zone(cx,cy,rx,ry):
        return np.exp(-((abs(x)-cx)/rx)**2-((y-cy)/ry)**2)
    nose = zone(.07,20.43,.15,.105)
    cheek = zone(.48,20.47,.24,.23)
    ear = zone(.79,20.57,.14,.30)
    brow = zone(.12,21.04,.36,.20)
    lip = zone(0,20.20,.20,.065)
    # Red weights warm, grazing backlight. Green controls lobe width. Blue
    # restricts the live highlight to the bridge, lips and upper cheek.
    return np.column_stack((.50*nose+.19*cheek+.95*ear,
                              .75-.39*nose-.27*lip-.12*brow,
                              .68*nose+.23*cheek+.23*brow+.66*lip)).clip(0,1)


def body_zones(xyz, uv, slot):
    x,y,z = xyz.T
    x = abs(x)
    def patch(cx,cy,rx,ry):
        return np.exp(-((x-cx)/rx)**2-((y-cy)/ry)**2)
    shoulder = patch(1.58,18.74,.85,.70)
    clavicle = patch(.68,18.89,.72,.33)
    hands = ramp(5.6,6.7,x)
    forearm = patch(4.9,16.12,1.25,1.12)
    knee = patch(.94,6.74,.82,.78)
    shin = patch(1.03,4.12,.79,2.19)
    thigh = patch(.98,10.55,.84,2.1)
    foot = 1-ramp(.55,2.4,y)
    warmth = .21+.23*hands+.10*knee+.095*shoulder+.12*foot
    rough = .65-.11*clavicle-.09*shoulder-.07*forearm-.08*shin-.06*thigh+.045*hands
    gloss = .34+.25*clavicle+.22*shoulder+.14*forearm+.17*shin+.09*thigh+.11*foot
    weight = 1-ramp(19.55,20.1,y)
    if slot in ('QingyiTorso','Up_Skin'):
        weight *= 1-(1-ramp(1.75,2.2,x))*(1-ramp(15.60,16.05,y))
    if slot=='Down_Skin':
        # The lower atlas also contains the fitted lining. Exclude it, with a
        # curved leg opening matching the garment's inner saddle.
        opening = shorts_hem(x,z)
        weight *= 1-ramp(opening-.12,opening,y)
    if slot=='QingyiScalp':
        # The inner disk is the painted backing for the long hair.
        ring = 1-np.linalg.norm(uv-.5,axis=1)/(124/256)
        weight = .24*ramp(.002,.020,ring)*(1-ramp(.025,.075,ring))
    return np.column_stack((warmth*weight, rough, gloss*weight)).clip(0,1)


def skin_zones(model, slot, triangles, target):
    ids, remap = np.unique(triangles,return_inverse=True)
    xyz = np.asarray([model.vertices[i].co for i in ids])
    uv = np.asarray([model.vertices[i].uv for i in ids])
    values = facial_zones(xyz) if slot=='Face_' else body_zones(xyz,uv,slot)
    texels = uv*512-.5
    raster = np.zeros((512,512,3),np.float32)
    coverage = np.zeros((512,512),np.uint8)
    for corners in remap.reshape(-1,3):
        p = texels[corners]
        lo = np.maximum(np.floor(p.min(0)).astype(int),0)
        hi = np.minimum(np.ceil(p.max(0)).astype(int),511)
        if (lo>hi).any(): continue
        a,b = p[1]-p[0],p[2]-p[0]
        det = a[0]*b[1]-a[1]*b[0]
        if abs(det)<1e-6: continue
        yy,xx = np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
        dx,dy = xx-p[0,0],yy-p[0,1]
        u,v = (dx*b[1]-dy*b[0])/det,(dy*a[0]-dx*a[1])/det
        valid = (u>=0)&(v>=0)&(u+v<=1)
        weights = np.stack([1-u-v,u,v],axis=-1)
        raster[yy[valid],xx[valid]] = weights[valid]@values[corners]
        coverage[yy[valid],xx[valid]] = 1
    # Extend the edge texels before mip generation so UV seams do not show.
    for _ in range(4):
        edge = (cv2.dilate(coverage,None)>coverage)
        raster[edge] = cv2.dilate(raster,None)[edge]
        coverage[edge] = 1
    image = Image.fromarray(np.uint8(np.clip(raster,0,1)*255))
    if slot in ('Up_Skin','QingyiTorso'):
        image = apply_neckline_light(image,xyz,uv,remap.reshape(-1,3),finish=True)
    image.save(target)


def rosette_surface(pigment, target):
    # The strapless rosette has its own projected atlas. Gold, nacre and stone
    # occupy different PMX slots; material ID determines conductor vs dielectric.
    rgb = np.asarray(Image.open(pigment).convert('RGB'),dtype=np.float32)/255
    lum = rgb @ np.array([.2126,.7152,.0722],np.float32)
    relief = cv2.GaussianBlur(lum,(0,0),.85)-cv2.GaussianBlur(lum,(0,0),4.2)
    height = .50 + .88*relief
    rough = .80 - .40*relief + .09*(1-lum)
    packed = np.stack([height,rough,np.ones_like(lum)],axis=-1)
    Image.fromarray(np.uint8(255*np.clip(packed,0,1))).save(target)


def profile():
    recipes = json.loads((DESIGN.parents[2]/'online-demo/frontend/src/yuexiao-finishes.json').read_text('utf-8'))
    for r in recipes:
        slots = r['materials']
        if 'Moon_ChasedMetal' in slots:
            r.update(map='magnolia-filigree', metalness=.93,roughness=.34,env=.96,
                     coat=.14,fill=.06,tint=[.97,.86,.70],bump=.00016)
        elif 'Moon_PearlInlay' in slots:
            r.update(map='magnolia-filigree',metalness=0,roughness=.46,coat=.38,
                     film=.17,env=.60,fill=.14,tint=[.96,.90,.92])
        elif 'Moon_Moonstone' in slots or 'Moon_Celadon' in slots:
            r.update(map='magnolia-filigree',metalness=0,roughness=.30,coat=.40,
                     transmission=.27 if 'Moon_Moonstone' in slots else .12,
                     thickness=.022,env=.84,fill=.075,tint=[.73,.94,.91])
        elif {'MoonHair_Glass','MoonHair_Crystal','Moon_CuffCrystal','Moon_PendantCrystal'} & set(slots):
            r.update(metalness=0,roughness=.29,coat=.44,transmission=.21,
                     thickness=.012,env=.72,fill=.10)
            r.pop('opacity',None)
        elif 'MoonHair_Gilt' in slots or 'Moon_CuffSetting' in slots:
            r.update(env=.78,fill=.095,roughness=.37)
        elif r['map'] in ('fibre','parted-fringe','mantle'):
            r.update(tint=[.68,.64,.70],fill=.10,roughness=.68,sheen=.15,
                     specular=.43,env=.26,bump=r['bump']*.62)
        elif 'MoonHair_Filament' in slots:
            r.update(tint=[.57,.53,.62],fill=.09,opacity=.68,sheen=.03)
    lacquer = dict(materials=['Up_Nail','Down_Nail'],map='',tint=[.86,.79,.82],
                   lacquerBase=[.56,.245,.27],fill=.05,roughness=.40,metalness=0,bump=0,anisotropy=0,sheen=0,
                   sheenTint='#fff1f0',sheenRough=.55,coat=.32,coatRough=.29,
                   specular=.56,env=.42,film=0)
    return {'version':1,'finishes':[*recipes,lacquer],'skinZones':SKIN_MAPS}


def package(source, output, surfaces):
    pmx, = source.glob('*.pmx')
    model = PMX['load'](str(pmx))
    assert model.name=='小可爱' and 'liupig' in model.comment
    tex = surfaces/'textures'
    tex.mkdir(parents=True,exist_ok=True)
    manifest = profile()
    active = {m.name for m in model.materials if m.vertex_count}
    manifest['finishes'] = [r for r in manifest['finishes'] if active.intersection(r['materials'])]
    offset = 0
    assert set(SKIN_MAPS).issubset(active)
    for mat in model.materials:
        end = offset+mat.vertex_count//3
        if mat.name in SKIN_MAPS:
            skin_zones(model,mat.name,model.faces[offset:end],tex/f'yuexiao-{SKIN_MAPS[mat.name]}-finish.png')
        offset = end
    rosette_surface(source/'textures/yuexiao-strapless-filigree.jpg',tex/'yuexiao-magnolia-filigree-finish.png')
    import shutil
    for name in sorted({r['map'] for r in manifest['finishes']} - {'','magnolia-filigree'}):
        filename = 'yuexiao-'+name+'-finish.png'
        shutil.copyfile(OUT/'textures'/filename,tex/filename)
    mapping = surfaces/'xiaokeai-pbr.json'
    mapping.write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),'utf-8')
    originals = [pmx,source/'Readme.txt',*(Path(t.path) for t in model.textures)]
    names = set(SKIN_MAPS.values()) | {r['map'] for r in manifest['finishes'] if r['map']}
    extras = [mapping,*(tex/f'yuexiao-{n}-finish.png' for n in sorted(names))]
    staging = output.with_suffix('.pbr-part')
    try:
        with ZipFile(staging,'w',ZIP_DEFLATED,compresslevel=7) as out:
            for files,root in ((originals,source),(extras,surfaces)):
                for f in files: out.write(f,f.relative_to(root).as_posix())
        with ZipFile(staging) as out:
            assert out.testzip() is None and len(set(out.namelist()))==len(originals)+len(extras)
        os.replace(staging,output)
    finally:
        staging.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source','output','surfaces'): parser.add_argument(name,type=Path)
    args = parser.parse_args()
    package(args.source.resolve(),args.output.resolve(),args.surfaces.resolve())
