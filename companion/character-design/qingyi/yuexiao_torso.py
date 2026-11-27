"""Reconstruct the missing torso between the donor's actual skin boundaries."""
import copy
from collections import defaultdict

import cv2
import numpy as np
import triangle
from PIL import Image
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree

from build_lanxu import PMX, TEX


def smooth(x):
    x = np.clip(x, 0, 1)
    return x*x*(3-2*x)


# Width, centre depth and rib-cage radius in horizontal sections of the
# original armature. The soft tissue is placed separately over the ribs.
levels = [12.9,13.4,13.85,14.25,14.66,14.96,15.32,15.72,16.05,16.4,16.75,17.12,17.48,17.82,18.15,18.50]
width = PchipInterpolator(levels,[1.60,1.42,1.15,.98,.92,.93,.99,1.09,1.19,1.29,1.36,1.43,1.50,1.38,.56,.34])
centre = PchipInterpolator(levels,[.22,.09,0,-.055,-.07,-.06,-.03,.015,.085,.16,.25,.39,.53,.65,.69,.65])
depth = PchipInterpolator(levels,[.97,.84,.72,.65,.64,.65,.69,.74,.80,.86,.89,.86,.77,.66,.49,.39])


def radius(a,y):
    w,d=width(y),depth(y)
    base=w*d/np.hypot(d*np.sin(a),w*np.cos(a))
    # Two broad upper slopes and a rounded lower turn, blending into the
    # sternum and axilla without cutting a transverse groove into the chest.
    elevation=y-16.46
    vertical=np.exp(-(elevation/np.where(elevation>0,.83,.62))**2)
    lobes=np.exp(-((a-.58)/.52)**2)+np.exp(-((a+.58)/.52)**2)
    return base+.54*vertical*lobes


def surface_point(a,y):
    r=radius(a,y)
    return np.stack([r*np.sin(a),y,centre(y)-r*np.cos(a)],axis=-1)


def surface_normal(a,y):
    da=surface_point(a+.003,y)-surface_point(a-.003,y)
    dy=surface_point(a,y+.003)-surface_point(a,y-.003)
    n=np.cross(dy,da)
    return n/np.maximum(np.linalg.norm(n,axis=-1,keepdims=True),1e-9)


def complexion(a,y):
    # Match the low-frequency lighting baked into the neck/shoulder atlas.
    # The falloff beneath the rib cage follows the new surface normal.
    n=surface_normal(a,y)
    tone=6*n[...,1]-12*np.maximum(-n[...,1],0)-3*abs(np.sin(a))**2
    tone-=3*np.exp(-((y-15.9)/.48)**2)*np.maximum(np.cos(a),0)
    return np.clip([245,221,220]+tone[...,None]*[.72,1.13,1.10],0,255)


def clear_arm_ink(image):
    # Two islands on the 2048px upper-body UV atlas carry the same red motif:
    # the dorsal forearm and the back of the hand on the viewer's left.
    for x, y, right, bottom in [(1372, 0, 1512, 309), (855, 1855, 975, 2033)]:
        rgb = image[y:bottom, x:right, :3]
        r, g, b = rgb.astype(np.float32).transpose(2, 0, 1)
        chroma = r-(g+b)/2
        base = cv2.morphologyEx(chroma, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21,21)))
        core = (chroma-base > 27) & (chroma > 54)
        if not core.any():
            continue
        distance = cv2.distanceTransform((~core).astype(np.uint8), cv2.DIST_L2, 5)
        ink = (distance < 5) & (chroma-base > 3)
        if y == 0:
            # One hairline reaches the edge of the forearm's UV chart.
            ink[:22, 58:67] |= (chroma-base)[:22, 58:67] > 2
        mask = cv2.dilate(ink.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5)))
        inside = mask.astype(bool)
        fill = cv2.inpaint(rgb.copy(), mask, 4, cv2.INPAINT_NS).astype(np.float32)
        # Relax to the surrounding painted skin gradient across each narrow stroke.
        kernel = np.array([[0,.25,0],[.25,0,.25],[0,.25,0]], np.float32)
        for _ in range(100):
            updated = cv2.filter2D(fill, -1, kernel)[inside]
            error = np.max(np.abs(updated-fill[inside]))
            fill[inside] = updated
            if error < .012:
                break
        rgb[inside] = np.rint(fill[inside]).astype(np.uint8)


def blend_donor_skin(m,mat,faces,p,upper,t):
    path=m.textures[mat.texture].path if upper else TEX/'yuexiao-lining.png'
    im=np.array(Image.open(path).convert('RGBA'));h,w=im.shape[:2]
    colors=np.zeros((h,w,3),np.uint8);amount=np.zeros((h,w),np.uint8)
    x,y,z=p.T
    fade=smooth((17.76-y)/.70)*smooth((1.79-abs(x))/.40) if upper else smooth((y-13.47)/.43)
    ids=np.unique(faces)
    elig=ids[(fade[ids]>0)&(y[ids]>13.45)&(y[ids]<17.76)]
    keep=np.zeros(len(p),bool);keep[elig]=True
    selected=faces[np.any(keep[faces],axis=1)]
    local=np.unique(selected);coords=np.array([m.vertices[i].uv for i in local])*[w-1,h-1]
    a=np.arctan2(x[local],centre(y[local])-z[local])
    swatch=complexion(a,np.clip(y[local],13.,17.85))
    for tri in np.searchsorted(local,selected):
        uv=coords[tri];lo=np.maximum(0,np.floor(uv.min(0)).astype(int))
        hi=np.minimum([w-1,h-1],np.ceil(uv.max(0)).astype(int))
        if np.any(hi<lo):continue
        b,c=uv[1:]-uv[0];det=b[0]*c[1]-b[1]*c[0]
        if abs(det)<1e-8:continue
        yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];xx=xx-uv[0,0];yy=yy-uv[0,1]
        u=(xx*c[1]-yy*c[0])/det;v=(b[0]*yy-b[1]*xx)/det
        bary=np.stack([1-u-v,u,v],axis=-1);inside=bary.min(axis=-1)>=-.003
        sl=np.s_[lo[1]:hi[1]+1,lo[0]:hi[0]+1];blend=np.uint8(np.clip(bary@fade[local[tri]],0,1)*255)
        take=inside&(blend>=amount[sl])
        colors[sl][take]=np.clip((bary@swatch[tri])[take],0,255)
        amount[sl][take]=blend[take]
    kernel=np.ones((5,5),np.uint8)
    pad=cv2.dilate(amount,kernel);outside=amount==0
    colors[outside]=cv2.dilate(colors,kernel)[outside];amount[outside]=pad[outside]
    alpha=amount[...,None]/255
    im[:,:,:3]=im[:,:,:3]*(1-alpha)+colors*alpha
    name='yuexiao-upper-skin.png' if upper else 'yuexiao-lining.png'
    if upper:
        clear_arm_ink(im)
    Image.fromarray(im).save(TEX/name)
    if upper:mat.texture=t.tex(name)


def boundary(faces,points,upper):
    # UV seams duplicate PMX vertices. Weld for boundary identification only.
    ids=np.unique(faces); coords,ix,inv=np.unique(np.round(points[ids],4),axis=0,return_index=True,return_inverse=True)
    f=inv[np.searchsorted(ids,faces)]
    e=np.sort(np.vstack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
    edges,n=np.unique(e,axis=0,return_counts=True)
    adj=defaultdict(list)
    for a,b in edges[n==1]:
        adj[a].append(b);adj[b].append(a)
    pool=set(adj)
    while pool:
        start=next(iter(pool));prev=None;node=start;loop=[]
        while node in pool:
            pool.remove(node);loop.append(node)
            nxt=next(k for k in adj[node] if k!=prev)
            prev,node=node,nxt
        ring=coords[loop]
        if 13.9 < ring[:,1].min() < 15.1 and abs(ring[:,0]).max()<1.45 and len(loop)>12:
            if (ring[:,1].max()>16)==upper:
                return ids[ix[np.asarray(loop)]]
    raise ValueError('Torso seam missing from donor')


def skin_weights(v):
    w=v.weight
    if w.type==w.BDEF1:return [(w.bones[0],1.)]
    if w.type==w.BDEF2:return list(zip(w.bones,[w.weights[0],1-w.weights[0]]))
    if w.type==w.SDEF:return list(zip(w.bones,[w.weights.weight,1-w.weights.weight]))
    return list(zip(w.bones,w.weights))


def pack_weights(row,bones):
    idx=np.argsort(row)[-4:][::-1]; vals=np.maximum(row[idx],0)
    vals/=vals.sum()
    w=PMX['BoneWeight']();w.type=w.BDEF4;w.bones=bones[idx].tolist();w.weights=vals.tolist()
    return w


class Torso:
    def __init__(self,t):
        m=t.m
        p=np.array([v.co for v in m.vertices]);start=0;skin={}
        for mat in m.materials:
            end=start+mat.vertex_count//3
            if mat.name in ('Up_Skin','Down_Skin'):
                skin[mat.name]=np.asarray(m.faces[start:end])
            start=end
        upper=boundary(skin['Up_Skin'],p,True);lower=boundary(skin['Down_Skin'],p,False)
        rims=np.r_[upper,lower]
        orig=p.copy()
        for mat,faces in skin.items():
            ids=np.unique(faces)
            ids=ids[(p[ids,1]>13.0)&(p[ids,1]<17.68)&(np.abs(p[ids,0])<1.78)]
            x,y,z=p[ids].T
            a=np.arctan2(x,centre(y)-z)
            strength=smooth((y-13.0)/.65)*smooth((17.68-y)/.72)*smooth((1.78-abs(x))/.40)
            r=np.hypot(x,centre(y)-z)
            r+=strength*(radius(a,y)-r)
            p[ids,0]=r*np.sin(a);p[ids,2]=centre(y)-r*np.cos(a)
            for i in ids:m.vertices[i].co=p[i]

        # Triangulate a periodic annulus in angle/height space. Its two
        # constrained rings are the donor edges, including the re-entrant
        # arcs at the axillae. Preserve every edge and its original weights.
        y=p[rims,1];a=np.arctan2(p[rims,0],centre(y)-p[rims,2])
        rho=1.+.42*(y-14)
        uv=np.c_[rho*np.cos(a),rho*np.sin(a)]
        loops=[np.arange(len(upper)),len(upper)+np.arange(len(lower))]
        segments=np.vstack([np.c_[l,np.roll(l,-1)] for l in loops])
        mesh=triangle.triangulate(dict(vertices=uv,segments=segments,holes=[[0,0]]),'pYa0.0025Q')
        xy=mesh['vertices']; faces=mesh['triangles'].astype(int)
        edges=np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1)
        edges,count=np.unique(edges,axis=0,return_counts=True)
        if set(map(tuple,edges[count==1]))!=set(map(tuple,np.sort(segments,axis=1))):
            raise ValueError('Sewing the torso altered a donor boundary')
        y=14+(np.linalg.norm(xy,axis=1)-1)/.42
        a=np.arctan2(xy[:,1],xy[:,0]);r=radius(a,y)
        q=np.c_[r*np.sin(a),y,centre(y)-r*np.cos(a)]
        nb=len(rims);q[:nb]=p[rims]
        # Harmonic interpolation propagates the original rig across the
        # inserted faces, with exact Dirichlet weights on both skin seams.
        left,right=edges.T;w=1/np.linalg.norm(q[left]-q[right],axis=1).clip(.01)
        graph=coo_matrix((np.r_[w,w],(np.r_[left,right],np.r_[right,left])),shape=(len(q),len(q))).tocsr()
        lap=diags(np.asarray(graph.sum(axis=1)).ravel())-graph
        active=np.array(sorted({b for i in rims for b,v in skin_weights(m.vertices[i]) if v>0}))
        bw=np.zeros((nb,len(active)))
        for i,idx in enumerate(rims):
            for b,v in skin_weights(m.vertices[idx]):
                if v>0:bw[i,np.searchsorted(active,b)]+=v
        interior=spsolve(lap[nb:,nb:].tocsc(), -lap[nb:,:nb]@bw)
        new=np.arange(len(m.vertices),len(m.vertices)+len(q)-nb)
        for pos,weights in zip(q[nb:],interior):
            v=PMX['Vertex']();v.co=pos;v.weight=pack_weights(weights,active);v.edge_scale=0
            m.vertices.append(v)
        ix=np.r_[rims,new]
        tri=q[faces];cr=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        mid=tri.mean(axis=1);out=mid-np.c_[np.zeros(len(mid)),mid[:,1],centre(mid[:,1])]
        reverse=np.einsum('ij,ij->i',cr,out)>0
        faces[reverse]=faces[reverse,::-1]
        patch=ix[faces]
        donor=next(o for o in m.materials if o.name=='Up_Skin')
        mat=copy.deepcopy(donor);mat.name=mat.name_e='QingyiTorso'
        extent=2.4
        uvs=.5+xy/(2*extent)
        axis=((np.arange(640)+.5)/640-.5)*2*extent
        ax,az=np.meshgrid(axis,axis)
        atlas_y=np.clip(14+(np.hypot(ax,az)-1)/.42,13.,17.7)
        shade=complexion(np.arctan2(az,ax),atlas_y)
        Image.fromarray(shade.astype(np.uint8)).save(TEX/'yuexiao-torso.png')
        mat.texture=t.tex('yuexiao-torso.png');t.parts[mat]=patch.tolist()
        positions=np.vstack([p,q[nb:]])
        body_faces=np.vstack([*skin.values(),patch])
        # Recompute smooth normals across the graft and coincident UV seams.
        tr=positions[body_faces]; n=np.cross(tr[:,2]-tr[:,0],tr[:,1]-tr[:,0])
        touched=np.unique(body_faces)
        _,inv=np.unique(np.round(positions[touched],4),axis=0,return_inverse=True)
        accum=np.zeros((inv.max()+1,3))
        for col in body_faces.T:np.add.at(accum,inv[np.searchsorted(touched,col)],n)
        accum/=np.linalg.norm(accum,axis=1,keepdims=True).clip(1.e-12)
        x,y,z=positions[touched].T
        region=(y>13.02)&(y<17.68)&(abs(x)<1.77)
        x,y,z=x[region],y[region],z[region]
        a=np.arctan2(x,centre(y)-z)
        fit=smooth((y-13.)/.65)*smooth((17.68-y)/.72)*smooth((1.78-abs(x))/.40)
        # The torso bridges dense and sparse donor rings. Use the normal
        # of its designed surface to avoid skinny seam triangles darkening
        # an otherwise continuous waist or rib contour under grazing light.
        normal=accum[inv[region]]*(1-fit[:,None])+surface_normal(a,y)*fit[:,None]
        normal/=np.maximum(np.linalg.norm(normal,axis=1,keepdims=True),1.e-9)
        for i,n in zip(touched[region],normal):m.vertices[i].normal=n
        # PMX assigns UVs per vertex. Split only the atlas boundary and
        # copy its skinned position, normal and weights exactly.
        atlas_ids=[]
        for i,atlas_uv in zip(rims,uvs[:nb]):
            v=copy.copy(m.vertices[i]);v.uv=atlas_uv
            atlas_ids.append(len(m.vertices));m.vertices.append(v)
        for i,atlas_uv in zip(new,uvs[nb:]):m.vertices[i].uv=atlas_uv
        t.parts[mat]=np.r_[atlas_ids,new][faces].tolist()
        for part in m.materials:
            if part.name in skin:
                blend_donor_skin(m,part,skin[part.name],p,part.name=='Up_Skin',t)
        # Keep corrective shapes consistent where an existing vertex moved.
        # The donor's facial and hairstyle keys do not share torso vertices.
        moved=set(np.flatnonzero(np.linalg.norm(p-orig,axis=1)>1.e-7))
        if any(o.index in moved and np.linalg.norm(o.offset)>1.e-6
               for morph in m.morphs if morph.type_index()==1 for o in morph.offsets):
            raise ValueError('An active donor shape also modifies the fitted torso')
        local=touched[(positions[touched,1]>13.25)&(positions[touched,1]<18.65)&(abs(positions[touched,0])<1.85)]
        self.tree=cKDTree(positions[local]);self.ids=local
        self.paint_bones=np.array(sorted({b for i in local for b,w in skin_weights(m.vertices[i]) if w>0}))
        self.paint=np.zeros((len(local),len(self.paint_bones)))
        for row,i in enumerate(local):
            for b,w in skin_weights(m.vertices[i]):
                if w>0:self.paint[row,np.searchsorted(self.paint_bones,b)]+=w
        self.measure(tr)

    def bind_cloth(self,vertices,waist_transition=None):
        if waist_transition:
            lo,hi=waist_transition
            vertices=[v for v in vertices if v.co[1]>lo]
        if not vertices:
            return
        points=np.asarray([v.co for v in vertices])
        d,idx=self.tree.query(points,k=6)
        mix=1/np.maximum(d,.018)**2
        rows=np.einsum('ij,ijk->ik',mix/mix.sum(axis=1,keepdims=True),self.paint[idx])
        for v,row in zip(vertices,rows):
            bones=self.paint_bones
            if waist_transition and v.co[1]<hi:
                mix=float(smooth((v.co[1]-lo)/(hi-lo)))
                previous=skin_weights(v)
                bones=np.union1d(bones,[b for b,w in previous if w>0])
                merged=np.zeros(len(bones))
                merged[np.searchsorted(bones,self.paint_bones)]=mix*row
                for b,w in previous:
                    if w>0:merged[np.searchsorted(bones,b)]+=(1-mix)*w
                row=merged
            v.weight=pack_weights(row,bones)

    def measure(self,tri):
        self.heights=np.linspace(13.4,18.55,138)
        self.angles=np.linspace(-np.pi,np.pi,256,endpoint=False)
        a=self.angles; rays=np.c_[np.sin(a),-np.cos(a)]
        tri=tri[(tri[:,:,1].max(1)>13.38)&(tri[:,:,1].min(1)<18.57)&(abs(tri[:,:,0]).min(1)<1.86)]
        def cross(x,z):return x[...,0]*z[...,1]-x[...,1]*z[...,0]
        table=[]
        for y in self.heights:
            ring=tri[(tri[:,:,1].min(1)<=y)&(tri[:,:,1].max(1)>y)]
            endpoints=[]
            for i in range(3):
                l,r=ring[:,i],ring[:,(i+1)%3]
                sel=(l[:,1]>y)!=(r[:,1]>y)
                k=np.flatnonzero(sel)
                pts=l[k]+(r[k]-l[k])*((y-l[k,1])/(r[k,1]-l[k,1]))[:,None]
                endpoints.extend(zip(k,pts[:,[0,2]]-[0,centre(y)]))
            ends=np.array([p for k,p in sorted(endpoints,key=lambda item:item[0])]).reshape(-1,2,2)
            point=ends[:,0];edge=ends[:,1]-point
            den=cross(rays[:,None],edge)
            with np.errstate(invalid='ignore',divide='ignore'):
                dist=cross(point,edge)/den; frac=cross(point[None],rays[:,None])/den
            dist=np.min(np.where((dist>.10)&(frac>=0)&(frac<=1),dist,np.inf),axis=1)
            table.append(np.where(np.isfinite(dist),dist,radius(a,y)))
        rad=gaussian_filter(table,(1.3,1.8),mode=('nearest','wrap'))
        self.rad=np.column_stack([rad,rad[:,0]])
        samples=self.surface(np.linspace(-np.pi/2,np.pi/2,181)[None,:],self.heights[:,None])
        self.front_x=np.linspace(-1.8,1.8,181)
        rows=[]
        for ring in samples:
            ix=np.argsort(ring[:,0])
            rows.append(np.interp(self.front_x,ring[ix,0],ring[ix,2]))
        self.front=np.asarray(rows)

    def front_z(self,x,y):
        rows=(y-self.heights[0])/(self.heights[1]-self.heights[0])
        cols=(x-self.front_x[0])/(self.front_x[1]-self.front_x[0])
        coords=np.stack([rows,cols])
        return map_coordinates(self.front,coords.reshape(2,-1),order=1,mode='nearest').reshape(rows.shape)

    def surface(self,a,y,ease=0.):
        a,y=np.broadcast_arrays(a,y);rows=(y-self.heights[0])/(self.heights[1]-self.heights[0])
        cols=(a+np.pi)*len(self.angles)/(2*np.pi)
        # Padding the periodic axis allows the closed back seam to sample the
        # same physical surface on both sides of the atlas.
        c=np.stack([np.clip(rows,0,len(self.heights)-1),cols%len(self.angles)])
        shape=c.shape[1:];rad=map_coordinates(self.rad,c.reshape(2,-1),order=1,mode='nearest').reshape(shape)+ease
        return np.stack([rad*np.sin(a),y,centre(y)-rad*np.cos(a)],axis=-1)
