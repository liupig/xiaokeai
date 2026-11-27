"""Build a separate rigged half-up style using the original character's PMX skeleton."""
import copy
import runpy
import tempfile
from math import pi, sin, cos, exp
from pathlib import Path

import numpy as np
import cv2
from PIL import Image
from liuting_hair import add_liuting
from fengguan import add_pmx_regalia

design = Path(__file__).resolve().parent
root = design.parents[2]
out = root/"online-demo/frontend/public/models/qingyi-jade"
pmx = runpy.run_path(str(root/"companion/tools/mmd_tools/core/pmx/__init__.py"))
m = pmx["load"](str(out/"model.pmx"))
bones = {b.name:i for i,b in enumerate(m.bones)}
V = np.array

# Strand direction follows our UV chart, including across the rolled bun.
# Broad bands describe hair locks; the finer fibres remain in the texture.
atlas=out/"textures/lingyun-silk.png"
original=np.array(Image.open(design/"lingyun-hair-albedo.png").convert("RGB"),dtype=float)
# Adapt the painted albedo to the low-key lighting of the PMX stage.
ink=np.clip(original*V((1.12,1.20,1.32))+V((12,12,14)),0,255)
Image.fromarray(ink.astype("uint8")).save(atlas)
tex=pmx["Texture"]()
tex.path=str(atlas)
m.textures.append(tex)

def material(name,color,texture=-1):
    a=copy.deepcopy(m.materials[0])
    a.name=a.name_e="Lingyun_"+name
    a.texture=texture
    a.diffuse=(*color,1)
    a.ambient=(.20,.18,.20)
    a.specular=(.10,.09,.11)
    a.shininess=48
    a.enabled_toon_edge=False
    a.is_double_sided=True
    a.sphere_texture_mode=0
    a.sphere_texture=-1
    a.vertex_count=0
    a.toon_texture=m.materials[0].toon_texture
    a.is_shared_toon_texture=m.materials[0].is_shared_toon_texture
    return a

hair=material("Ink",(.96,.96,.99),len(m.textures)-1)
# The source bangs have hand-painted layers and a fitted hairline. Repaint
# that chart in chestnut ink to match the loosely pinned lengths.
source = pmx["load"](str(out.parent/"xinyuehu"/"model.pmx"))
bangs = next(mat for mat in source.materials if mat.name == "Hair_Bangs")
paint = Image.open(source.textures[bangs.texture].path).convert("RGBA")
value = np.array(paint.convert("L"),dtype=np.float32)/255
stops = [0,.30,.58,.82,1.]
palette = np.array([(22,20,24),(37,32,35),(52,44,45),(73,61,59),(101,84,77)])
# Comb fine fibres along the painted locks using their local texture gradient.
# Following the chart in image space also respects rotated UV islands.
guide = cv2.GaussianBlur(value,(0,0),3)
gx,gy = cv2.Sobel(guide,-1,1,0),cv2.Sobel(guide,-1,0,1)
orientation = .5*np.arctan2(cv2.GaussianBlur(2*gx*gy,(0,0),7),
                            cv2.GaussianBlur(gx*gx-gy*gy,(0,0),7))
tx,ty = -np.sin(orientation),np.cos(orientation)
y_grid,x_grid = np.indices(value.shape,dtype=np.float32)
noise = np.random.default_rng(28).normal(0,1,value.shape).astype(np.float32)
strands = noise.copy()
for distance in range(1,15):
    for sign in (1,-1):
        strands += cv2.remap(noise,x_grid+sign*tx*distance,y_grid+sign*ty*distance,
                             cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
strands = (strands/29)*13
rgba = np.dstack([np.interp(value,stops,palette[:,i])+strands for i in range(3)] + [np.array(paint.getchannel("A"))])
fringe_color = out/"textures/tea-fringe.png"
Image.fromarray(np.uint8(np.clip(rgba,0,255))).save(fringe_color)
tex = pmx["Texture"]()
tex.path = str(fringe_color)
m.textures.append(tex)
forelocks=material("Painted_forelocks",(.98,.98,.98),len(m.textures)-1)
ivory=material("White_nephrite",(.96,.86,.72))
gold=material("Pale_gold",(.68,.47,.23))
green=material("Celadon",(.23,.47,.39))
# Long lengths dissolve into separate fine tips rather than terminating
# around the rim of the underlying volume.
h,w=ink.shape[:2]
vv,uu=np.mgrid[0:h,0:w]/V([h-1,w-1])[:,None,None]
wave=uu+.006*np.sin(pi*vv)*np.cos(4*pi*uu)
edge=.85+.105*(.5+.5*np.cos(2*pi*13*wave))**.65+.025*np.sin(2*pi*67*wave)
fade=np.clip((edge-vv)/.10,0,1)
length_atlas=out/"textures/lingyun-lengths.png"
Image.fromarray(np.dstack((ink.astype("uint8"),(fade*255).astype("uint8")))).save(length_atlas)
length_texture=pmx["Texture"]()
length_texture.path=str(length_atlas)
m.textures.append(length_texture)
lengths=material("Loose_lengths",(.98,.98,1),len(m.textures)-1)
parts={mat:[] for mat in (hair,forelocks,green,gold,ivory,lengths)}
head=bones["頭"]
spine=bones["上半身2"]

def unit(v):
    return v/max(1e-8,np.linalg.norm(v))

def surface(shape, rows,cols,mat=hair, across=1, inward=False,weighted=False):
    start=len(m.vertices)
    coords=np.array([[shape(i/rows,j/cols) for j in range(cols+1)] for i in range(rows+1)])
    along=np.gradient(coords,axis=0)
    across_vectors=np.gradient(coords,axis=1)
    normals=np.cross(along,across_vectors)
    if inward: normals*=-1
    for i,row in enumerate(coords):
        for j,co in enumerate(row):
            v=pmx["Vertex"]()
            v.co=co
            v.normal=unit(normals[i,j])
            v.uv=(j/cols*across,i/rows)
            w=pmx["BoneWeight"]()
            chest=float(np.clip((19-co[1])/2.3,0,1)) if weighted else 0
            if chest:
                w.type=w.BDEF2
                w.bones=[spine,head]
                w.weights=[chest*chest*(3-2*chest)]
            else:
                w.bones=[head]
            v.weight=w
            m.vertices.append(v)
            if i and j:
                k=start+i*(cols+1)+j
                for tri in ((k-cols-2,k-1,k),(k-cols-2,k,k-cols-1)):
                    parts[mat].append(tri if inward else tri[::-1])

# Two contiguous panels begin at the curved scalp part and flow around the ears.
# Their front and back boundaries form continuous, intentionally asymmetrical hairlines.
def sheet(s,t,u):
    lat=1.15-2.45*u
    part=-.22+.16*u
    start=unit(V((part,cos(lat),-sin(lat))))
    az=1.30+(pi-1.30)*u
    end=V((s*sin(az),-.32-.59*sin(pi*u*.7),-cos(az)))
    end=unit(end)
    n=unit((1-t)*start+ t*end + V((s*.26*sin(pi*t)*sin(pi*u),
            .12*sin(pi*t)*sin(pi*u),-.10*sin(pi*t)*(1-u)**3)))
    # soft lifted roots on both sides of the part, descending to a thin hairline
    roll=.07*sin(pi*t)**.8+.020*(.5+.5*cos(2*pi*(7*u+.17*t)))*sin(pi*t)
    edge=.010*sin(6*pi*t+.3*s)*(1-u)**9
    return V(((.95+roll)*n[0],19.88+(1.23+roll)*n[1]+edge,.49+(.96+roll)*n[2]))

for s in (-1,1):
    surface(lambda t,u:sheet(s,t,u),48,76,hair,inward=(s>0))

def spline(points,t):
    p=np.asarray(points)
    pos=min(t*(len(p)-1),len(p)-1-1e-8)
    i=int(pos); f=pos-i
    a,b,c,d=p[np.clip([i-1,i,i+1,i+2],0,len(p)-1)]
    return .5*(2*b+(c-a)*f+(2*a-5*b+4*c-d)*f*f+(3*b-a-3*c+d)*f**3)

def ribbon(points,width,depth,mat=hair,weighted=False,turn=0,roll=.0,rows=38,across=1):
    # Parallel transported cross-sections avoid twists at a horizontal tangent.
    guide=np.asarray([spline(points,t) for t in np.linspace(0,1,rows+1)])
    tangents=[unit(d) for d in np.gradient(guide,axis=0)]
    ref=V((0.,0.,-1.))
    basis=[]
    for tangent in tangents:
        ref=unit(ref-np.dot(ref,tangent)*tangent)
        basis.append((unit(np.cross(ref,tangent)),ref))
    def shape(t,u):
        i=round(t*rows)
        h,k=basis[i]
        angle=2*pi*u
        taper=.009+.991*sin(pi*t)**.53
        q=turn*t+roll
        a,b=cos(q)*h+sin(q)*k,-sin(q)*h+cos(q)*k
        return guide[i]+taper*(width*cos(angle)*a+depth*sin(angle)*b)
    surface(shape,rows,20,mat,across,inward=True,weighted=weighted)

# Unbroken underlayer behind the neck. Fluting continues into the staggered ends.
def fall(t,u):
    a=2*pi*u
    tips=.60*cos(5*a+.5)+.31*cos(9*a)+.18*sin(3*a)
    y=20.18-(8.39+tips)*t
    width=.35+.85*sin(pi*t*.84)+.29*t
    ripple=.08*cos(12*a+.85*sin(5*t))+.035*cos(23*a)
    sway=.31*sin(2*pi*t-.5)*t+.12*t
    thickness=.31+.11*sin(pi*t)
    return (sway+sin(a)*(width+ripple)*(1-.72*t**3),
            y,.82+.40*(1-exp(-8*t))+.74*sin(pi*t*.83)+.24*t+(thickness+ripple)*cos(a))
surface(fall,65,144,lengths,across=3,weighted=True)

# Individually textured locks for the swept fringe, temples and long underlayer.
lock_image=Image.open(design/"silk-lock.png").convert("RGBA")
alpha=lock_image.getchannel("A")
lock_image=lock_image.crop(alpha.point(lambda a:255 if a>32 else 0).getbbox())
lock_image.thumbnail((768,2048), Image.LANCZOS)
pixels=np.asarray(lock_image).copy()
pixels[:,:,:3]=np.clip(pixels[:,:,:3]*V((1.13,1.18,1.26))+V((12,12,14)),0,255)
# PMX viewers can repeat both UV axes. Feather the atlas borders so a
# neighbouring root texel cannot leave a horizontal mark below the tip.
t,u=np.mgrid[0:pixels.shape[0],0:pixels.shape[1]]
border=np.minimum.reduce((t/16,(pixels.shape[0]-1-t)/16,u/5,(pixels.shape[1]-1-u)/5))
pixels[:,:,3]=(pixels[:,:,3]*np.clip(border,0,1)).astype("uint8")
lock_atlas=out/"textures/lingyun-fringe.png"
Image.fromarray(pixels).save(lock_atlas)
tex=pmx["Texture"]()
tex.path=str(lock_atlas)
m.textures.append(tex)
fringe=material("Feathered_fringe",(.98,.97,1),len(m.textures)-1)
parts[fringe]=[]

def lock(points,width,depth=.04,angle=0,twist=0,weighted=False,flip=False):
    # A shallow camber catches light on the middle of the lock. The edges
    # and tips are supplied by the strand atlas rather than a pointed tube.
    def shape(t,u):
        centre=spline(points,t)
        tangent=unit(spline(points,min(1,t+.002))-spline(points,max(0,t-.002)))
        a=angle+twist*t
        facing=V((sin(a),0,-cos(a)))
        lateral=unit(np.cross(tangent,facing))
        d=(1-2*u) if flip else (2*u-1)
        span=width*(.62+.38*sin(pi*t)**.6)
        return centre+span*d*lateral+depth*(1-d*d)*facing
    surface(shape,46,18,fringe,weighted=weighted,inward=flip)

# Use the source construction of the fringe and its fine tapered cheek locks.
# Fold the wing tips down and sweep the part to one side on the skull.
offset = sum(mat.vertex_count for mat in source.materials[:source.materials.index(bangs)])//3
bang_faces = source.faces[offset:offset+bangs.vertex_count//3]
indices = {}
for tri in bang_faces:
    for idx in tri:
        if idx in indices:
            continue
        vertex = copy.deepcopy(source.vertices[idx])
        x,y,z = vertex.co
        ax = abs(x)
        low = max(0,18.86-y)
        # At the ear, a turning lock follows a quarter-circle toward the
        # nape. Its length is preserved in depth instead of splaying out.
        wing = max(0,ax-.83)
        gate = exp(-((y-19.9)/.82)**4)
        turn = min(1,wing/.72)*1.30*gate
        xx = x-np.sign(x)*wing*(1-cos(turn))
        yy = y-wing*.66*gate
        zz = z+wing*sin(turn)*.91
        fringe_band = exp(-((y-20.02)/.53)**4-((z+.55)/.48)**4)
        sweep = -.19*fringe_band*exp(-((x+.06)/.63)**2)
        xx += sweep
        yy += fringe_band*(.08+.22*exp(-((x-.17)/.43)**2))
        zz -= .042*fringe_band
        if low:
            if x<0:
                yy += .47*low
                xx += .07*low
            else:
                yy -= .70*low
                xx += .18*low
                zz -= .36*low
        vertex.co = (xx,yy,zz)
        w = pmx["BoneWeight"]()
        chest = min(1.,max(0.,(18.9-yy)/2.2))
        if chest:
            w.type = w.BDEF2
            w.bones = [spine,head]
            w.weights = [chest*chest*(3-2*chest)]
        else:
            w.bones = [head]
        vertex.weight = w
        indices[idx] = len(m.vertices)
        m.vertices.append(vertex)
    parts[forelocks].append(tuple(indices[i] for i in tri))

# Two fine locks cross the opening in the source fringe. The width narrows
# continuously to a point to avoid a blunt fringe when seen in profile.
def part_lock(points,width):
    def shape(t,u):
        centre = spline(points,t)
        tangent = spline(points,min(1,t+.002))-spline(points,max(0,t-.002))
        across = unit(np.cross(tangent,V((0.,0.,-1.))))
        d = 2*u-1
        envelope = sin(pi*t)**.6*(1-t)**.35
        return centre+width*envelope*d*across+V((0,0,-.024*envelope*(1-d*d)))
    surface(shape,48,14,hair,across=.35)

part_lock([(.10,20.99,-.22),(.15,20.80,-.43),(.19,20.61,-.56),
           (.20,20.41,-.63),(.16,20.23,-.66),(.09,20.08,-.65),
           (-.01,19.96,-.57)],.17)
part_lock([(.035,20.92,-.30),(.09,20.70,-.49),(.11,20.48,-.62),
           (.085,20.31,-.68),(.025,20.16,-.68),(-.060,20.05,-.63)],.048)

# Lower, off-centre French twist crossing the nape, with an underlying
# cushion so the outer silhouette cannot read as an open ring.
def pleat(t,u):
    b=.001+(pi-.002)*t
    a=2*pi*u
    ribs=.028*cos(7*a+2.8*b)*sin(b)
    return (-.24+.71*sin(b)*cos(a)+.14*cos(b),
            20.10+.57*cos(b)+.10*sin(b)*cos(a),
            1.25+(.53+ribs)*sin(b)*sin(a))
surface(pleat,38,84,hair)
for s in (-1,1):
    ribbon([(.86*s,19.86,.45),(.91*s,19.88,.81),(.71*s,20.01,1.25),
            (.39*s,20.11,1.58),(.04*s-.15,20.21,1.73),
            (-.37*s-.12,20.36,1.57),(-.38*s,20.48,1.26)],
            .19,.062,turn=.8*s,rows=44,across=.60)
# Feathered rear layers fall on different arcs and terminate at different
# heights. The shorter side layers expose the taper of the central lengths.
for i in range(11):
    q=(i-5)/5
    a=q*pi*.48
    side=sin(a)
    back=cos(a)
    end=10.55+1.63*abs(q)**1.6+.31*sin(3*i)
    lock([(.44*side,20.02,1.32+.22*back),(.82*side,19.23,1.33+.38*back),
          (1.10*side,17.75,1.62+.54*back),(1.25*side+.11,16.05,1.65+.65*back),
          (1.39*side,14.30+.21*q,1.75+.62*back),
          (1.13*side-.20,12.81+.48*q*q,1.76+.62*back),
          (.91*side+.19*sin(2*i),end,1.93+.41*back)],
          .36-.08*abs(q),.045,angle=pi-.88*a,twist=.20*q,weighted=True,flip=i%2==0)

# Brushed pale gold pin carries a lanceolate jade leaf with a raised
# midrib. Tilt the leaf outwards so the carving is legible in profile.
ribbon([(-.92,19.87,1.38),(-.26,20.10,1.41),(.53,20.37,1.26),
        (1.16,20.59,.95)],.030,.032,gold)
def leaf(t,u):
    d=u*2-1
    width=.088*sin(pi*t)**.87
    return (.81+.54*t-.11*d*width,20.43+.30*t+.075*sin(pi*t)+width*d,
            1.04-.35*t+.10*t*t-.048*sin(pi*t)*(1-d*d))
surface(leaf,24,12,green)
ribbon([(.84,20.46,1.01),(1.01,20.61,.88),(1.20,20.70,.79),(1.34,20.73,.78)],
       .008,.010,gold)
def second_leaf(t,u):
    d=2*u-1
    return (.96+.17*t+.044*d*sin(pi*t),20.57+.28*t,
            .95-.10*t-.035*sin(pi*t)*(1-d*d))
surface(second_leaf,18,8,green)
def bead(t,u):
    a=2*pi*u
    b=.001+(pi-.002)*t
    return (1.08+.047*sin(b)*cos(a),20.02+.065*cos(b),.95+.045*sin(b)*sin(a))
ribbon([(1.06,20.58,.94),(1.09,20.41,.95),(1.08,20.20,.95),(1.08,20.08,.95)],
       .009,.010,gold)
surface(bead,15,24,ivory)
original_count=len(m.materials)
for mat,faces in parts.items():
    mat.vertex_count=len(faces)*3
    m.faces.extend(faces)
    m.materials.append(mat)
add_liuting(m,pmx,out)
add_pmx_regalia(m,pmx)
pmx["save"](str(out/"lingyun.pmx"),m,add_uv_count=3)

# Same asset, with wardrobe alternatives excluded from the artist's Blender scene.
offset=0
active=[]
for i,mat in enumerate(m.materials):
    count=mat.vertex_count//3
    if mat.name.startswith("Fengguan_") or mat.name == "Liuting_Crown" or (i<original_count and (mat.name.startswith("Hair_") or mat.name in ("Cloth_Hairpin","QingyiHairLining"))):
        mat.vertex_count=0
    else:
        active.extend(m.faces[offset:offset+count])
    offset+=count
m.faces=active
pmx["save"](str(Path(tempfile.gettempdir())/"qingyi-lingyun-edit.pmx"),m,add_uv_count=3)
