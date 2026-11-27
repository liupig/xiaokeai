"""Build the magnolia half-crown and fork in Blender and PMX from one sculpt."""
from math import cos, pi, sin
import copy
from pathlib import Path
from tinglan import sculpt

import numpy as np


# Linear colour for both the Blender studio and the live PBR materials.
FINISHES = {
    "Gold": ((.68,.345,.087), .74, .32),
    "Wire": ((.88,.565,.229), .77, .24),
    "Recess": ((.32,.144,.054), .58, .38),
    "Carving": ((.96,.96,.90), .055, .46),
    "Celadon": ((.069,.350,.321), .20, .22),
    "Pearl": ((.93,.855,.705), .14, .23),

}


ARTWORK = Path(__file__).resolve().parents[3]/'online-demo/frontend/public/models/qingyi-jade/textures/tinglan-carving.png'


def unit(v):
    return v / np.maximum(np.linalg.norm(v,axis=-1,keepdims=True),1e-10)


def spline(points, count):
    points = np.asarray(points,float)
    t = np.linspace(0,len(points)-1,count)
    i = np.minimum(t.astype(int),len(points)-2)
    f = (t-i)[:,None]
    a,b,c,d = points[np.clip([i-1,i,i+1,i+2],0,len(points)-1)]
    return b+.5*f*((c-a)+f*((2*a-5*b+4*c-d)+f*(3*b-a-3*c+d)))


class Piece:
    def __init__(self, name):
        self.name = name
        self.parts = {k:[] for k in FINISHES}

    def shell(self, finish, rings, uv=None):
        rings = np.asarray(rings)
        centre = rings.mean(axis=1)
        outward = rings-centre[:,None]
        across = np.roll(rings,-1,axis=1)-np.roll(rings,1,axis=1)
        normal = unit(np.cross(across,np.gradient(rings,axis=0)))
        # Retain the silhouette and the normals of the sculpt while dropping
        # intermediate sections on straight shanks, veins and feather shafts.
        tolerance = min(.0032,.18*np.linalg.norm(outward,axis=2).max())
        keep = {0,len(rings)-1}
        pending = [(0,len(rings)-1)]
        while pending:
            lo,hi = pending.pop()
            if hi-lo <= 1:
                continue
            t = np.arange(1,hi-lo)[:,None,None]/(hi-lo)
            error = np.linalg.norm(rings[lo+1:hi]-((1-t)*rings[lo]+t*rings[hi]),axis=2).max(axis=1)
            if error.max() > tolerance:
                cut = lo+1+int(error.argmax())
                keep.add(cut)
                pending.extend([(lo,cut),(cut,hi)])
        take = sorted(keep)
        rings,centre,normal,outward = rings[take],centre[take],normal[take],outward[take]
        rows,cols,_ = rings.shape
        idx = np.arange(rows*cols).reshape(rows,cols)
        a,b = idx[:-1].ravel(),np.roll(idx[:-1],-1,axis=1).ravel()
        faces = np.vstack([np.column_stack([a,b,b+cols]),np.column_stack([a,b+cols,a+cols])])
        if (normal*outward).sum()<0:
            normal *= -1
            faces = faces[:,::-1]
        # Seal both ends. Each pole has its own normal instead of averaging
        # bevelled front facets with the underside of a setting.
        caps = []
        for row,direction in [(0,-1),(-1,1)]:
            ring = idx[row]
            cap = np.column_stack([ring,np.roll(ring,-1),np.full(cols,rows*cols+len(caps))])
            cap_normal = unit(centre[1]-centre[0] if row==0 else centre[-1]-centre[-2])*direction
            if np.dot(np.cross(rings[row,1]-rings[row,0],centre[row]-rings[row,0]),cap_normal)<0:
                cap = cap[:,::-1]
            caps.append(cap_normal)
            faces = np.vstack([faces,cap])
        pos = np.vstack([rings.reshape(-1,3),centre[[0,-1]]])
        if uv is None:
            uv = np.zeros((len(pos),2))
        else:
            uv = np.asarray(uv)[take]
            uv = np.vstack([uv.reshape(-1,2),uv[[0,-1]].mean(axis=1)])
        self.parts[finish].append((pos,np.vstack([normal.reshape(-1,3),caps]),faces,uv))

    def wire(self, centre, radius, finish="Wire", sides=6):
        centre = np.asarray(centre,float)
        tangent = unit(np.gradient(centre,axis=0))
        # Transport the cross section through the turns of the cloud scrolls.
        ref = np.eye(3)[np.argmin(abs(tangent[0]))]
        axes = []
        for v in tangent:
            ref = unit(ref-np.dot(ref,v)*v)
            axes.append(ref)
        axes = np.array(axes)
        ang = np.arange(sides)*2*pi/sides
        radius = np.broadcast_to(radius,(len(centre),))[:,None,None]
        rings = centre[:,None]+radius*(axes[:,None]*np.cos(ang)[None,:,None]+
                                       np.cross(tangent,axes)[:,None]*np.sin(ang)[None,:,None])
        self.shell(finish,rings)

    def merged(self):
        for mat,parts in self.parts.items():
            if not parts:
                continue
            v,n,f,texcoords = [],[],[],[]
            count = 0
            for pos,norm,faces,uv in parts:
                texcoords.append(uv)
                v.append(pos); n.append(norm); f.append(faces+count)
                count += len(pos)
            yield mat,np.vstack(v),np.vstack(n),np.vstack(f),np.vstack(texcoords)


def circlet(a):
    # Fitted around the eight native crown panels. The rear left seat comes
    # down with the side knot; its opposite side clears the temple braid.
    y = np.interp(np.mod(a,2*pi),np.deg2rad(np.arange(0,361,15)),
        [21.17,21.09,21.065,21.015,20.944,20.926,20.921,21.012,21.046,21.076,
         21.097,21.12,21.142,21.093,20.995,20.81,20.784,20.825,20.90,20.939,
         20.938,21.049,21.093,21.166,21.17])
    return np.stack([.90*np.sin(a),y,-.59+.88*np.cos(a)],axis=-1)


def make_regalia():
    return sculpt(Piece, spline, circlet)


def add_pmx_regalia(model,pmx):
    bone = pmx["BoneWeight"]()
    bone.bones = [next(i for i,b in enumerate(model.bones) if b.name=="頭")]
    batches = {k:[] for k in FINISHES}
    axis = np.array([1.,1.,-1.])
    for piece in make_regalia():
        for finish,pos,norm,faces,uv in piece.merged():
            start = len(model.vertices)
            for p,n,texcoord in zip(pos*axis,norm*axis,uv):
                v = pmx["Vertex"]()
                v.co,v.normal,v.weight,v.edge_scale,v.uv = p,n,bone,0.,texcoord
                model.vertices.append(v)
            batches[finish].extend((faces[:,::-1]+start).tolist())
    texture = pmx["Texture"]()
    texture.path = str(ARTWORK)
    atlas = next((i for i,t in enumerate(model.textures) if Path(t.path)==ARTWORK),len(model.textures))
    if atlas==len(model.textures):
        model.textures.append(texture)
    for finish,faces in batches.items():
        if not faces:
            continue
        mat = copy.deepcopy(model.materials[0])
        mat.name = mat.name_e = "Fengguan_"+finish
        rgb,metal,rough = FINISHES[finish]
        mat.diffuse,mat.ambient = (*rgb,1.),tuple(.20*c for c in rgb)
        mat.specular,mat.shininess = (.6,.52,.38),32/rough
        mat.texture = mat.sphere_texture = mat.toon_texture = -1
        mat.texture = atlas if finish=='Carving' else -1
        mat.sphere_texture_mode = 0
        mat.is_shared_toon_texture = mat.enabled_toon_edge = mat.is_double_sided = False
        mat.vertex_count = 3*len(faces)
        model.faces.extend(faces)
        model.materials.append(mat)


def add_blender_regalia(bpy,armature):
    palette = {}
    for key,(rgb,metal,rough) in FINISHES.items():
        mat = bpy.data.materials.new("Fengguan_"+key)
        mat.diffuse_color = (*rgb,1.)
        mat.use_nodes = True
        shader = mat.node_tree.nodes.get("Principled BSDF")
        for k,val in [("Base Color",(*rgb,1.)),("Metallic",metal),("Roughness",rough)]:
            shader.inputs[k].default_value = val
        if key=="Carving":
            image = mat.node_tree.nodes.new("ShaderNodeTexImage")
            image.image = bpy.data.images.load(str(ARTWORK),check_existing=True)
            mat.node_tree.links.new(image.outputs["Color"],shader.inputs["Base Color"])
            shader.inputs["Subsurface Weight"].default_value = .065
            shader.inputs["Subsurface Scale"].default_value = .0014
        palette[key] = mat
    for piece in make_regalia():
        pos,faces,indices,norm,uv = [],[],[],[],[]
        for slot,(key,v,n,f,texcoords) in enumerate(piece.merged()):
            faces.extend((f+len(pos)).tolist())
            pos.extend((v[:,[0,2,1]]*[.08,-.08,.08]).tolist())
            norm.extend((n[:,[0,2,1]]*[1,-1,1]).tolist())
            indices.extend([slot]*len(f))
            uv.extend(texcoords)
        mesh = bpy.data.meshes.new(piece.name)
        mesh.from_pydata(pos,[],faces)
        for k in piece.parts:
            if piece.parts[k]:
                mesh.materials.append(palette[k])
        layer = mesh.uv_layers.new(name="Carving")
        texcoords = np.asarray(uv,dtype=np.float32)
        texcoords[:,1] = 1-texcoords[:,1]
        layer.data.foreach_set("uv",texcoords[np.asarray(faces).ravel()].ravel())
        mesh.polygons.foreach_set("material_index",indices)
        mesh.polygons.foreach_set("use_smooth",[True]*len(faces))
        mesh.normals_split_custom_set_from_vertices(norm)
        ob = bpy.data.objects.new(piece.name,mesh)
        armature.users_collection[0].objects.link(ob)
        ob.parent = armature
        group = ob.vertex_groups.new(name="頭")
        group.add(list(range(len(pos))),1.,"REPLACE")
        ob.modifiers.new("随头部骨骼","ARMATURE").object = armature
