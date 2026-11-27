"""A low side knot sculpted on Qingyi's existing weighted hair and UV charts."""
import copy
from math import atan, cos, exp, pi, sin
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from liuting_texture import contact_charts, paint_silk
from liuting_crown import attach_crown, fit_crown, paint_crown, raster_map


def smooth(t):
    t = min(1., max(0., t))
    return t*t*(3-2*t)


def shape_fringe_ends(model, original):
    mat = next(m for m in model.materials if m.name=="Hair_Bangs")
    start = sum(m.vertex_count for m in model.materials[:model.materials.index(mat)])//3
    faces = np.asarray(model.faces[start:start+mat.vertex_count//3])
    ids = np.unique(faces)
    coords = np.array([model.vertices[i].co+original.get(i,np.zeros(3)) for i in ids])
    points, weld = np.unique(np.round(coords,5),axis=0,return_inverse=True)
    triangles = weld[np.searchsorted(ids,faces)]
    edges = np.vstack([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]])
    x,y,z = points.T
    cut = 19.96
    fringe = (abs(x)<.73)&(z<-.35)&(y<cut)&(y>19.48)
    edges = edges[fringe[edges].all(axis=1)]
    graph = coo_matrix((np.ones(len(edges)),edges.T),shape=(len(points),len(points)))
    _,groups = connected_components(graph,directed=False)
    shifts = np.zeros_like(points)
    # Below the brow-level cut each native blade is a separate island. Pull
    # its free end toward its own centreline, leaving its attached rim intact.
    for group in np.where(np.bincount(groups)>=5)[0]:
        selected = groups==group
        tips = points[selected]
        low = min(tips[:,1])
        q = np.clip((cut-tips[:,1])/max(cut-low,.12),0,1)**2
        c = np.median(tips[tips[:,1]<np.quantile(tips[:,1],.33)+.001],axis=0)
        taper = np.clip((.74-abs(tips[:,0]))/.10,0,1)*q
        shifts[selected,0] = taper*(.68*(c[0]-tips[:,0])-.038)
        shifts[selected,2] = taper*(.48*(c[2]-tips[:,2])-.014)
        shifts[selected,1] = -q*(.043+.045*cos(22*c[0]))
    return dict(zip(ids,shifts[weld]))


def comb(co, section):
    x, y, z = co
    if section.startswith("Hair_Bangs"):
        # Draw the temple fans back around the ears, keeping volume at their
        # roots. Carry a swept fringe along an arc on the forehead.
        wing = max(0., abs(x)-.80)
        tucked = wing-.22*atan(wing/.28)
        side = 1 if x>0 else -1
        turn = -.37*smooth((21.0-y)/1.05)*exp(-((z+.48)/.64)**4-((y-20.03)/.69)**4)
        xx = x*cos(turn)-(z-.32)*sin(turn)-side*tucked
        zz = .32+x*sin(turn)+(z-.32)*cos(turn)+.95*tucked
        lift = .27*exp(-((x-.30)/.40)**2)+.065
        yy = y-.35*tucked+lift*exp(-((y-19.92)/.48)**2-((z+.56)/.47)**4)
        yy += .055*sin(11*x+.5)*exp(-((y-19.82)/.23)**2-((z+.55)/.42)**2)
        xx += side*.085*exp(-((abs(x)-.72)/.17)**2-((y-19.58)/.27)**2)
        fringe_tip = exp(-((y-19.84)/.32)**2-((z+.58)/.34)**4)
        yy += fringe_tip*(.11*exp(-((x-.32)/.17)**2)-.085*exp(-((x+.25)/.13)**2))
        xx -= .075*fringe_tip*exp(-((x+.18)/.34)**2)
        # The native fan ends at the knot. Open its middle away from the
        # temple, keeping the short tips and their painted glints together.
        if x < -.82:
            reach = min(1.,(-x-.82)/1.46)
            arch = sin(pi*reach**.80)**1.5
            tuck = smooth((reach-.46)/.53)
            xx -= .45*arch-.17*tuck
            yy += .62*smooth(reach/.70)+.12*arch+.03*tuck
            zz += .22*tuck-.15*arch
            # Turn the fan's cross-section around the head as its tangent
            # swings back. The painted upper blade passes over the underfold.
            cross = z-np.interp(-x,[.82,1.08,1.32,1.55,1.8,2.1,2.28],
                                    [.02,.06,.24,.57,.88,1.08,1.115])
            roll = smooth((reach-.02)/.40)
            xx += .78*cross*roll
            zz -= .38*cross*roll
            yy += .12*cross*roll
        # One temple lock brushes the collarbone, with a longer arc across
        # the opposite shoulder. Roots remain at their bind-pose positions.
        drop = max(0.,18.91-y)
        if side<0:
            yy += .29*drop
            xx += .05*drop-.11*sin(2.8*drop)*smooth(drop/.65)
            zz += .32*drop
        else:
            fall = smooth(drop/1.92)
            yy -= .84*drop
            xx += .21*drop+.18*sin(2.6*drop)*smooth(drop/.65)
            xx -= .32*fall*(x-.67)
            zz -= .42*drop-.06*sin(3.4*drop)
        return (xx,yy,zz)

    # The original braid, knot, glints and hairpin travel together. The
    # long outer locks descend from the same gathered section.
    knot = (1. if section=="Cloth_Hairpin" else
            smooth((-x-.21)/.59)*smooth((z-.52)/.53)*smooth((y-18.3)/.95)
            *(1-.66*smooth((y-20.15)/.62)))
    tail = smooth((19.72-y)/1.1)*smooth((-x-.19)/.44)*smooth((z-.76)/.49)
    drop = max(0.,19.43-y)
    t = smooth(drop/9.8)
    xx = x+knot*(.22+.06*(y-19.98))+tail*(.21+.75*t-.30*sin(2*np.pi*t))
    yy = y+knot*(-.54+.10*(z-1.65)-.08*(y-20.0))-tail*(.39+.12*drop)
    zz = z+knot*(.14-.08*(y-20.0))+tail*(.10-.72*t)
    if tail and y<18.8:
        # Fan adjacent locks out from their shared tie, then let them settle
        # into different endpoints. Work about the centre of each cross-section.
        height = [9.6,11.4,13.0,14.5,15.6,16.8,18.0,18.8]
        cx = np.interp(y,height,[-2.78,-2.35,-1.77,-1.63,-1.42,-1.01,-.96,-1.06])
        cz = np.interp(y,height,[3.44,3.82,3.40,2.82,2.17,1.64,1.55,1.43])
        dx,dz = x-cx,z-cz
        released = tail*smooth((18.8-y)/2.8)
        angle = .48*sin(1.38*pi*t)
        width = 1.28+.33*sin(pi*t)
        xx += released*((width*cos(angle)-1)*dx-sin(angle)*dz-.16*sin(2*pi*t))
        zz += released*(.58*sin(angle)*dx-.24*dz-.22*sin(pi*t))
        yy -= released*(.14*drop+smooth((13-y)/2.6)*(.37*dx-.28*dz))
    return (xx,yy,zz)


def finish_temple(paint, model, original):
    # The lower face of the native splayed fan was painted nearly black.
    # Its turned section is exposed beside the bun and needs a satin half-tone.
    mat = next(m for m in model.materials if m.name == "Hair_Bangs")
    first = sum(m.vertex_count for m in model.materials[:model.materials.index(mat)])//3
    faces = np.asarray(model.faces[first:first+mat.vertex_count//3])
    ids = np.unique(faces)
    xyz = np.array([model.vertices[i].co+original.get(i,np.zeros(3)) for i in ids])
    uv = np.array([model.vertices[i].uv for i in ids])
    tris = np.searchsorted(ids,faces)
    relevant = ((xyz[tris,0].min(axis=1)<-1.08) & (xyz[tris,1].mean(axis=1)>19.12) &
                (xyz[tris,1].mean(axis=1)<20.35))
    img = np.asarray(paint).copy()
    base = img[:,:,:3].astype(np.float32)
    shape = np.array(paint.size)
    for tri in tris[relevant]:
        mapped = raster_map(uv[tri]*shape-.5,xyz[tri][:,[0,2]],shape)
        if mapped is None:
            continue
        y,x,coords = mapped
        width,z = -coords[:,0],coords[:,1]
        blend = np.clip((width-1.01)/.36,0,1)
        across = z-np.interp(width,[1.,1.32,1.55,1.8,2.1],[.04,.24,.57,.88,1.08])
        phase = 24*across+.8*np.sin(4*width)
        shade = np.clip((61-base[y,x,0])/41,0,1)
        lift = blend*shade*(22+4.5*np.cos(phase)+1.5*np.cos(phase*5.2))
        img[y,x,:3] = np.uint8(np.clip(base[y,x]+lift[:,None]*[1.,.94,1.03],0,255))
    return Image.fromarray(img)


def add_liuting(model, pmx, directory):
    # QingyiOriginalHair is the existing inverse sculpt back to the artist's
    # original hair. Reuse it without reading or extracting another mesh.
    restore = next(m for m in model.morphs if m.name=="QingyiOriginalHair")
    original = {o.index:np.asarray(o.offset) for o in restore.offsets}
    tips = shape_fringe_ends(model,original)
    style = pmx["VertexMorph"]("QingyiLiutingHair", "Liuting hairstyle", 0)
    cursor = 0
    seen = set()
    for mat in model.materials:
        end = cursor+mat.vertex_count//3
        if mat.name.startswith("Hair_") or mat.name=="Cloth_Hairpin":
            ids = {i for tri in model.faces[cursor:end] for i in tri}
            for i in sorted(ids-seen):
                co = np.asarray(model.vertices[i].co)
                new = comb(co+original.get(i,0)+tips.get(i,0),mat.name)
                offset = pmx["VertexMorphOffset"]()
                offset.index = i
                offset.offset = np.asarray(new)-co
                style.offsets.append(offset)
            seen.update(ids)
        cursor = end
    model.morphs.append(style)
    # Keep the painted gradients, including the fine tonal changes within a
    # lock. Both charts use one ink wash. The two highlight atlases stay
    # independent, exactly as in the local reference.
    colors = np.array([(16,16,22),(25,24,32),(36,33,43),(52,48,57),
                       (78,71,81),(113,104,111),(155,143,144)])
    levels = [0,66,113,151,180,211,255]
    palette = {}
    by_name = {mat.name:mat for mat in model.materials}
    crown = fit_crown(model, original, comb)
    texture = directory/"textures/liuting-crown-repair.png"
    attach_crown(model,pmx,crown,texture)
    shadows = contact_charts(model,{o.index:o.offset for o in style.offsets})
    for name, chart in (("Hair_Bangs","Bangs_EX.png"),("Hair_Back","Hair_EX.png")):
        source = Image.open(directory/"textures"/chart).convert("RGBA")
        path = directory/"textures"/("liuting-"+chart)
        painted = paint_silk(source,shadows[name],levels,colors)
        if name == "Hair_Bangs":
            painted = finish_temple(painted, model, original)
        painted.save(path)
        palette[name] = path
    paint_crown(crown,palette["Hair_Back"],texture)
    # The fox-ear attachment sites are open in the reference. Close their
    # sightlines with the existing fitted lining, painting the flow toward
    # the nape in the same tonal range as the surrounding native locks.
    v,u = np.mgrid[0:512,0:1024]/np.array([511.,1023.])[:,None,None]
    gather = u-.28*np.sin(2*np.pi*u)*v**1.26
    flow = 2*np.pi*(10*gather+.12*np.sin(6*np.pi*gather+1.3*v))
    ridges = .5+.5*np.cos(flow+.35*np.sin(2*flow))
    fibres = (np.cos(8*flow+.9*np.sin(3*flow+v))
              +.55*np.cos(19*flow+.7*np.sin(2*flow+2*v)))
    crown_shadow = np.asarray(Image.fromarray(shadows["QingyiHairLining"]).resize((1024,512),Image.BILINEAR))
    tone = 177+21*ridges+3*fibres-10*(1-ridges)**4+8*np.sin(np.pi*v)-22*crown_shadow
    under = np.stack([np.interp(tone,levels,c) for c in colors.T],axis=2)
    path = directory/"textures/liuting-crown.png"
    Image.fromarray(under.astype("uint8")).save(path)
    palette["QingyiHairLining"] = path
    for name, path in palette.items():
        tex = pmx["Texture"]()
        tex.path = str(path)
        model.textures.append(tex)
        mat = copy.deepcopy(by_name[name])
        mat.name = mat.name_e = "Liuting_"+name
        mat.texture = len(model.textures)-1
        mat.diffuse = (1.,1.,1.,1.)
        mat.ambient = (.11,.10,.13)
        mat.vertex_count = 0
        model.materials.append(mat)
    # Bake this wardrobe state for Blender, preserving the source skeleton,
    # expressions, weights and costume.
    edit = pmx["load"](str(directory/"model.pmx"))
    first = 0
    for mat in edit.materials:
        if mat.name == "Cloth_Hairpin":
            del edit.faces[first:first+mat.vertex_count//3]
            mat.vertex_count = 0
            break
        first += mat.vertex_count//3
    for o in style.offsets:
        edit.vertices[o.index].co = np.asarray(edit.vertices[o.index].co)+o.offset
    attach_crown(edit,pmx,crown,texture)
    for mat in edit.materials:
        if mat.name in palette:
            tex = pmx["Texture"]()
            tex.path = str(palette[mat.name])
            mat.texture = len(edit.textures)
            edit.textures.append(tex)
            mat.diffuse = (1.,1.,1.,1.)
            mat.ambient = (.11,.10,.13)
        elif mat.name in ("Hair_Back+","Hair_Bangs+"):
            mat.diffuse = (.50,.48,.50,1.)
    edit.morphs = [m for m in edit.morphs if m.name!="QingyiOriginalHair"]
    pmx["save"](str(Path(tempfile.gettempdir())/"qingyi-liuting-edit.pmx"),edit,add_uv_count=3)
