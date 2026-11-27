"""Paint strand groups on the native charts, with contact baked from the finished coiffure."""
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import cv2
import numpy as np
from PIL import Image


def contact_charts(model, offsets):
    faces = {}
    start = 0
    for material in model.materials:
        end = start+material.vertex_count//3
        if material.name in ("Hair_Bangs","Hair_Back","QingyiHairLining","Liuting_Crown"):
            faces[material.name] = np.asarray(model.faces[start:end],dtype=np.int32)
        start = end
    all_faces = np.concatenate(list(faces.values()))
    ids = np.unique(all_faces)
    vertices = [model.vertices[i] for i in ids]
    positions = np.array([v.co for v in vertices])+np.array([offsets.get(i,(0,0,0)) for i in ids])
    triangles = np.searchsorted(ids,all_faces)
    normals = np.array([v.normal for v in vertices])
    # Refit the outward ray hemisphere on the rotated and tapered sections.
    ab = positions[triangles[:,1]]-positions[triangles[:,0]]
    ac = positions[triangles[:,2]]-positions[triangles[:,0]]
    geometric = np.cross(ab,ac)
    orientation = np.sum(geometric*normals[triangles[:,0]],axis=1)
    geometric[orientation<0] *= -1
    smooth = np.zeros_like(normals)
    for corner in triangles.T:
        np.add.at(smooth,corner,geometric)
    smooth /= np.maximum(np.linalg.norm(smooth,axis=1,keepdims=True),1e-9)
    uv = np.array([v.uv for v in vertices])
    here = Path(__file__).resolve().parent
    bundled = sorted((here.parents[1]/"tools/blender").glob("*/blender.exe"))
    blender = str(bundled[-1]) if bundled else shutil.which("blender")
    with TemporaryDirectory() as temp:
        mesh = Path(temp)/"hair.npz"
        out = Path(temp)/"contact.npy"
        np.savez(mesh,positions=positions,normals=smooth+.35*normals,triangles=triangles)
        subprocess.run([blender,"-b","--python-exit-code","1","-P",
                        str(here/"bake_liuting_shadows.py"),"--",str(mesh),str(out)],check=True)
        contact = np.load(out)
    return {name: paint_contact(uv,contact,np.searchsorted(ids,tris))
            for name,tris in faces.items() if name != "Liuting_Crown"}


def paint_contact(uv, contact, triangles):
    # Accumulate overlapping UV islands instead of letting the last triangle
    # overwrite its neighbours. Ignore unused texels when padding the seams.
    size = 768
    sums = np.zeros((size,size),np.float32)
    counts = np.zeros_like(sums)
    points = np.clip(uv,0,1)*(size-1)
    for indices in triangles:
        tri = points[indices]
        x0,y0 = np.floor(tri.min(axis=0)).astype(int)
        x1,y1 = np.ceil(tri.max(axis=0)).astype(int)+1
        mask = np.zeros((y1-y0,x1-x0),np.uint8)
        cv2.fillConvexPoly(mask,np.int32(np.rint((tri-[x0,y0])*16)),1,shift=4)
        sums[y0:y1,x0:x1] += mask*contact[indices].mean()
        counts[y0:y1,x0:x1] += mask
    return cv2.GaussianBlur(sums,(0,0),1.7)/np.maximum(cv2.GaussianBlur(counts,(0,0),1.7),1e-7)


def comb_grain(luma, seed, step, iterations):
    guide = cv2.GaussianBlur(luma,(0,0),2.5)
    gx,gy = cv2.Sobel(guide,-1,1,0),cv2.Sobel(guide,-1,0,1)
    angle = .5*np.arctan2(cv2.GaussianBlur(2*gx*gy,(0,0),9),
                          cv2.GaussianBlur(gx*gx-gy*gy,(0,0),9))
    field = np.dstack([-np.sin(angle),np.cos(angle)])
    y,x = np.indices(luma.shape,dtype=np.float32)
    noise = np.random.default_rng(seed).standard_normal(luma.shape).astype(np.float32)
    noise = cv2.GaussianBlur(noise,(0,0),.65)
    fibres = noise.copy()
    for sign in (-1,1):
        px,py = x.copy(),y.copy()
        previous = field*sign
        for _ in range(iterations):
            direction = cv2.remap(field,px,py,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
            # The texture tangent has no intrinsic sign. Orient each sample
            # with the preceding step to follow a bend through the braid.
            reverse = direction[:,:,0]*previous[:,:,0]+direction[:,:,1]*previous[:,:,1]<0
            direction[reverse] *= -1
            px += step*direction[:,:,0]
            py += step*direction[:,:,1]
            fibres += cv2.remap(noise,px,py,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
            previous = direction
    return fibres/max(float(fibres.std()),1e-6)


def paint_silk(source, contact, levels, colors):
    luma = np.asarray(source.convert("L"),dtype=np.float32)
    size = source.size
    small = cv2.resize(luma,None,fx=.40,fy=.40,interpolation=cv2.INTER_AREA)
    locks = cv2.resize(comb_grain(small,91,1.55,22),size,interpolation=cv2.INTER_CUBIC)
    strands = comb_grain(luma,54,1.4,21)
    contact = cv2.resize(contact,size,interpolation=cv2.INTER_LINEAR)
    broad = cv2.GaussianBlur(luma,(0,0),16)
    sheen = np.clip((luma-105)/92,.15,1)
    contact = cv2.GaussianBlur(contact,(0,0),3.5)
    value = (luma+.48*(luma-broad) + sheen*(3.0*locks+2.4*strands)
             - 49*contact**.8)
    rgb = [np.interp(value,levels,column) for column in colors.T]
    return Image.fromarray(np.uint8(np.dstack(rgb+[np.asarray(source.getchannel("A"))])))
