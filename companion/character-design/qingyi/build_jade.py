"""Build Qingyi's personal-use PMX from the locally supplied character."""
from pathlib import Path
from math import sin, cos, pi, exp
import copy
import runpy
import shutil
from PIL import Image, ImageOps, ImageDraw

root = Path(__file__).resolve().parents[3]
models = root / "online-demo/frontend/public/models"
source = models / "xinyuehu"
out = models / "qingyi-jade"
out.mkdir(exist_ok=True)
pmx = runpy.run_path(str(root / "companion/tools/mmd_tools/core/pmx/__init__.py"))
m = pmx["load"](str(source / "model.pmx"))
m.name = "清漪 · 玉兰"
shutil.copy2(source / "Readme.txt", out / "Readme.txt")
for tex in m.textures:
    src = Path(tex.path)
    dst = out / src.relative_to(source)
    dst.parent.mkdir(exist_ok=True)
    shutil.copy2(src, dst)
    tex.path = str(dst)

def add_texture(name, image):
    path = out / "textures" / name
    image.save(path)
    tex = pmx["Texture"]()
    tex.path = str(path)
    m.textures.append(tex)
    return len(m.textures)-1

palette = {}
def dyed(index, dark, light):
    key = index, dark, light
    if key not in palette:
        src = Image.open(m.textures[index].path).convert("RGBA")
        rgb = ImageOps.colorize(ImageOps.grayscale(src), dark, light)
        rgb.putalpha(src.getchannel("A"))
        palette[key] = add_texture(f"silk-{len(palette)}.png",rgb)
    return palette[key]

# Repaint the face atlas locally, sampling the neighbouring forehead complexion.
import numpy as np
def retouch_skin(index, bounds, sample_offset, name):
    data = np.array(Image.open(m.textures[index].path).convert("RGBA"))
    h,w = data.shape[:2]
    x0,y0,x1,y1 = [round(a*b) for a,b in zip(bounds,(w,h,w,h))]
    if index == 0:
        # Inpaint only the narrow vermilion strokes. A rectangular clone
        # would copy the nearby eyelid and highlight onto the nose bridge.
        import cv2
        skin = data[y0:y1,x0:x1,:3].copy()
        mask = (skin[:,:,1] < 148).astype("uint8") * 255
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9)))
        data[y0:y1,x0:x1,:3] = cv2.inpaint(skin,mask,6,cv2.INPAINT_NS)
        return add_texture(name,Image.fromarray(data))
    yy,xx = np.mgrid[y0:y1,x0:x1]
    edge = np.minimum.reduce([(xx-x0)/(w*.008),(x1-xx)/(w*.008),
                              (yy-y0)/(h*.008),(y1-yy)/(h*.008)])
    mix = np.clip(edge,0,1)[:,:,None]
    if index == 13:
        weight=((xx-x0)/(x1-x0))[:,:,None]
        patch=data[yy,x0,:3]*(1-weight)+data[yy,x1,:3]*weight
    else:
        patch = data[yy,xx+round(sample_offset*w),:3]
    data[y0:y1,x0:x1,:3] = data[y0:y1,x0:x1,:3]*(1-mix)+patch*mix
    return add_texture(name,Image.fromarray(data))

skin_face=retouch_skin(0,(.443,.067,.551,.327),-.095,"clear-forehead.png")
skin_body=retouch_skin(13,(.315,.554,.414,.699),-.08,"clear-neckline.png")
# Fit the transparent decal to the sternum UV island.
path=Path(m.textures[skin_body].path)
painting=Image.open(path).convert("RGBA")
decal=Image.open(Path(__file__).with_name("cloud-phoenix.png")).convert("RGBA")
decal=decal.crop(decal.getchannel("A").getbbox())
w,h=painting.size
decal.thumbnail((round(.134*w),round(.103*h)),Image.LANCZOS)
painting.alpha_composite(decal,(round(.364*w-decal.width/2),round(.600*h)))
painting.save(path)
for i in (0,2,5,6,7,8,9):
    m.materials[i].texture=skin_face
m.materials[30].texture=skin_body
hair_sections = {}
kept = []
face_vertices = set()
offset = 0
for i, mat in enumerate(m.materials):
    n = mat.vertex_count // 3
    triangles = m.faces[offset:offset+n]
    offset += n
    if i in (13, 14, 15, 16, 20):
        for triangle in triangles:
            for index in triangle:
                hair_sections[index] = i
    if i < 13:
        face_vertices.update(v for tri in triangles for v in tri)
    if i in (17,19,23,24,28,29,32,37,40,42,43,44,45,46):
        triangles = []
    if i in (35,36):
        triangles = [tri for tri in triangles if max(m.vertices[v].co[1] for v in tri)<3]
    if i in (21,22,25,26,34):
        mat.texture = dyed(mat.texture, "#112c36", "#b5d8ca")
    if i in (13,15):
        mat.texture = dyed(mat.texture, "#17131e", "#766379")
    if i in (33,20):
        mat.texture = dyed(mat.texture, "#584035", "#f3d991")
    kept.extend(triangles)
    mat.vertex_count = len(triangles)*3
m.faces = kept

for index in face_vertices:
    v = m.vertices[index]
    x,y,z = v.co
    jaw = exp(-((y-18.94)/.36)**2)
    cheek = exp(-((y-19.38)/.3)**2)
    nose = exp(-(x/.17)**2-((y-19.33)/.25)**2)
    eye = exp(-((abs(x)-.51)/.27)**2-((y-19.63)/.13)**2)
    v.co = (x*(1-.095*jaw+.024*cheek), y-.067*jaw+.035*eye, z-.082*nose-.035*jaw)

# Woven skirt atlas with a contrasting centre panel, gold hem and magnolia sprays.
W,H=2048,1024
img=Image.new("RGB",(W,H))
d=ImageDraw.Draw(img)
for x in range(W):
    u=x/W
    panel=abs(u-.5)<.086
    wave=.5+.5*cos(2*pi*24*u)
    base=(87,137,128) if panel else (28,84,85)
    d.line((x,0,x,H),fill=tuple(int(a*(.80+.20*wave)) for a in base))
gold=(211,179,116)
for y in (5,75,80,890,896,978,985):
    d.rectangle((0,y,W,y+2),fill=gold)
d.rectangle((0,9,W,72),fill=(42,65,73))
for x in (846,850,1198,1202):
    d.line((x,0,x,H),fill=gold,width=2)
for i in range(24):
    x=int((i+.5)*W/24)
    y=950
    d.arc((x-35,y-70,x+17,y+10),25,100,fill=gold,width=3)
    for dx,dy in ((0,0),(-12,-12),(10,-17)):
        cx,cy=x+dx,y-22+dy
        d.polygon([(cx,cy+6),(cx-6,cy),(cx-4,cy-12),(cx+2,cy-5),(cx+4,cy)],fill=(225,205,167))
    d.polygon([(x-9,42),(x,32),(x+9,42),(x,52)],outline=gold)
mat=copy.deepcopy(m.materials[21])
mat.name=mat.name_e="Magnolia pleated silk"
mat.texture=add_texture("magnolia-silk.png",img)
mat.diffuse=(1,1,1,1)
mat.sphere_texture_mode=0
mat.enabled_toon_edge=False
m.materials.append(mat)
bones={b.name:i for i,b in enumerate(m.bones)}
rings=[(16.15,1.20,1.08),(15.55,1.13,1.04),(14.7,1.22,1.14),(14,1.35,1.23),(13.3,1.65,1.35),(12,2.12,1.55),(10,2.36,1.67),(8,2.6,1.85),(6,2.85,2.02),(4,3.10,2.22),(2,3.33,2.4),(.75,3.46,2.48)]
N=192
start=len(m.vertices)
for j,(y,rx,rz) in enumerate(rings):
    t=(16.15-y)/15.40
    for k in range(N+1):
        u=k/N
        a=2*pi*u
        fold=(.018+.12*t)*cos(24*a+.28*t)
        v=pmx["Vertex"]()
        v.co=(sin(a)*(rx+fold),y+(.09*cos(24*a) if j==len(rings)-1 else 0),.20+.32*t+cos(a)*(rz+fold))
        v.normal=(sin(a),.12,cos(a))
        v.uv=(u,t)
        w=pmx["BoneWeight"]()
        w.type=w.BDEF4
        leg=min(1,max(0,(13.4-y)/4))
        left=.5+.5*max(-1,min(1,2*sin(a)))
        w.bones=[bones["下半身"],bones["左足"],bones["右足"],bones["腰"]]
        w.weights=[1-leg,left*leg,(1-left)*leg,0]
        v.weight=w
        m.vertices.append(v)
        if j and k:
            b=start+j*(N+1)+k
            m.faces.extend([(b-N-2,b-1,b),(b-N-2,b,b-N-1)])
mat.vertex_count=(len(rings)-1)*N*6
# Keep the original roots, hair cards, UVs and skin weights. Store the exact
# inverse displacement so the wardrobe can also select the original haircut.
restore_hair = pmx["VertexMorph"]("QingyiOriginalHair", "Original hair", 0)
for index, section in hair_sections.items():
    vertex = m.vertices[index]
    x, y, z = vertex.co
    if section in (13, 14):
        drop = max(0, 19.04-y)
        # One lock stays short against the jaw; the opposite lock falls across
        # the shoulder with a soft S curve, tapering naturally in the source UV.
        long_side = x > 0
        dx = (.29*drop+.18*sin(drop*2.1) if long_side else -.10*drop)
        dy = (-1.76 if long_side else -.18)*drop
        dz = (-.54 if long_side else .08)*drop
        # Sweep free fringe tips around the forehead, keeping their roots fixed.
        tip = min(1,max(0,(20.98-y)/1.05))
        forehead = exp(-(x/.96)**4)*exp(-((z+.40)/.85)**4)
        sweep = -.46*tip**1.3*forehead*exp(-((y-19.99)/.50)**4)
        dx += x*(cos(sweep)-1) - (z-.30)*sin(sweep)
        dz += x*sin(sweep) + (z-.30)*(cos(sweep)-1)
        dy += tip*forehead*exp(-((y-19.99)/.59)**4)*(.12+.25*exp(-((x-.46)/.43)**2))
        wing = min(1,max(0,(abs(x)-.78)/1.15))
        dx -= .39*x*wing
        dy -= (.63 if long_side else .40)*wing
    elif section == 20:
        dx,dy,dz = .19,-.24,.23
    else:
        drop = max(0, 18.9-y)
        t = min(1, drop/8.7)
        dx = .80*t + .24*sin(pi*t)
        dy = -.23*drop
        dz = -.72*t
        # Feather the adjustment into the hair at the left rear temple.
        bun = exp(-((x+1.19)/.80)**4-((y-19.94)/1.03)**4-((z-1.28)/1.04)**4)
        dx += bun*(.23-.27*(x+1.19))
        dy += bun*(-.24-.19*(y-19.94))
        dz += bun*.24
    if dx or dy or dz:
        vertex.co = (x+dx, y+dy, z+dz)
        delta = pmx["VertexMorphOffset"]()
        delta.index = index
        delta.offset = (-dx,-dy,-dz)
        restore_hair.offsets.append(delta)
for section in (13,14,15,16):
    m.materials[section].diffuse=(.77,.74,.40,1)
# A recessed crown lining closes sightlines between the separated hair cards.
lining=copy.deepcopy(m.materials[15])
lining.name=lining.name_e="QingyiHairLining"
grain=Image.new("RGB",(512,256))
brush=ImageDraw.Draw(grain)
for row in range(256):
    for col in range(512):
        phase=2*pi*(col/512+row/256*.11)
        strand=.5+.5*cos(31*phase+.32*sin(5*phase))
        value=int(44+8*strand+3*cos(66*phase))
        brush.point((col,row),fill=(value+6,value,value+1))
lining.texture=add_texture("ink-crown.png",grain)
lining.diffuse=(.92,.85,.80,1)
lining.ambient=(.10,.08,.08)
lining.sphere_texture_mode=0
lining.enabled_toon_edge=False
start=len(m.vertices)
for row in range(21):
    for col in range(65):
        a=2*pi*col/64
        b=.001+row/20*(1.58-.66*cos(a))
        normal=(sin(a)*sin(b),cos(b),-cos(a)*sin(b))
        v=pmx["Vertex"]()
        v.co=(.97*normal[0],19.87+1.41*normal[1],.52+1.04*normal[2])
        v.uv=(col/64,row/20)
        v.normal=normal
        v.weight=pmx["BoneWeight"]()
        v.weight.bones=[bones["頭"]]
        m.vertices.append(v)
        if row and col:
            k=len(m.vertices)-1
            m.faces.extend([(k-66,k-1,k),(k-66,k,k-65)])
lining.vertex_count=20*64*6
m.materials.append(lining)
m.morphs.append(restore_hair)
pmx["save"](str(out/"model.pmx"),m,add_uv_count=3)
