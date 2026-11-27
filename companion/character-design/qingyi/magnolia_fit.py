"""Transfer the approved skin to PMX and draft the satin against its bound surface."""
import copy
import numpy as np
from scipy.spatial import cKDTree

from build_torso_base import SKIN,prepared_skin
from yuexiao_torso import Torso,centre,pack_weights,skin_weights,smooth


def attach_skin(model,groups,rise):
    data=prepared_skin(model)
    ids=data['ids'];count=np.count_nonzero(ids>=0)
    skin=np.concatenate([groups[n] for n in SKIN])
    children=data['faces'].reshape(-1,4,3)
    corners=np.stack((children[:,0,0],children[:,1,1],children[:,2,2]),axis=1)
    mids=np.stack((children[:,0,1],children[:,1,2],children[:,2,0]),axis=1)
    if not np.array_equal(ids[corners],skin) or not np.isclose(data['rise'],rise):
        raise ValueError('Approved skin does not correspond to this PMX')
    p=data['coords'];hh=p[:,1]-rise
    split=(hh>14.45)&(hh<18.28)&(abs(p[:,0])<2.82)
    use=np.flatnonzero(split&(ids<0))
    remap=ids.copy();remap[use]=np.arange(len(use))+len(model.vertices)
    ends=np.zeros((len(ids),2),int)
    for j in range(3):ends[mids[:,j]]=corners[:,[j,(j+1)%3]]
    # A PMX point carries its own UV. Subdivide independently on each UV
    # island, including the additional texture coordinates on the donor.
    new_edges={}
    for k in use:
        i,j=ids[ends[k]]
        a,b=model.vertices[i],model.vertices[j]
        v=copy.copy(a)
        v.uv=data['uv'][k]
        v.additional_uvs=((np.asarray(a.additional_uvs)+np.asarray(b.additional_uvs))*.5).tolist()
        v.edge_scale=(a.edge_scale+b.edge_scale)*.5
        model.vertices.append(v)
        new_edges.setdefault(i,[]).append(remap[k]);new_edges.setdefault(j,[]).append(remap[k])
    for morph in model.morphs:
        if morph.type_index() not in (1,3,4,5,6,7):continue
        changes={}
        for off in morph.offsets:
            for j in new_edges.get(off.index,()):
                changes[j]=changes.get(j,0.)+.5*np.asarray(off.offset)
        for j,delta in changes.items():
            off=type(morph.offsets[0])();off.index=j;off.offset=delta
            morph.offsets.append(off)
    names={bone.name:i for i,bone in enumerate(model.bones)}
    skin_points=data['sculpt']
    h=skin_points[:,1]-rise
    angle=abs(np.arctan2(skin_points[:,0],centre(np.clip(h,13.4,18.55))-skin_points[:,2]))
    bust=smooth((h-15.45)/.44)*smooth((17.95-h)/.42)*smooth((1.32-angle)/.34)
    # Fair the donor's spring paint across chart boundaries. The old cage
    # alternates between rib and spring weights on neighbouring triangles,
    # producing peaks through the silk when the spine bends.
    src_bones,src_weights=data['bones'],data['weights']
    paint_ids=np.flatnonzero((h>15.1)&(h<18.22)&(abs(skin_points[:,0])<2.1))
    palette=np.unique(src_bones[paint_ids][src_weights[paint_ids]>0])
    dense=np.zeros((len(paint_ids),len(palette)))
    ir,jc=np.nonzero(src_weights[paint_ids]>0)
    np.add.at(dense,(ir,np.searchsorted(palette,src_bones[paint_ids[ir],jc])),src_weights[paint_ids[ir],jc])
    tree=cKDTree(skin_points[paint_ids])
    distances,neighbors=tree.query(skin_points[paint_ids],k=80)
    mix=np.exp(-.5*(distances/.14)**2)
    mix/=mix.sum(axis=1,keepdims=True)
    fair=np.einsum('ij,ijk->ik',mix,dense[neighbors])
    fair=dense+(fair-dense)*bust[paint_ids,None]
    paint_index=np.full(len(ids),-1,int)
    paint_index[paint_ids]=np.arange(len(paint_ids))
    supports={}
    for name,b in names.items():
        if name.startswith('ZSpring_Spine_') and name.endswith(('_L','_R')):
            segment='F02' if name.startswith(('ZSpring_Spine_F02','ZSpring_Spine_F03')) else 'F01'
            supports[b]=names['ZSpring_Spine_'+segment+name[-2:]]
        elif name.startswith(('Bone_Omuscle01','Bone_Clavicle01')) or name=='上半身1':
            supports[b]=names['上半身2']
    for k in np.r_[np.arange(count),use]:
        v=model.vertices[remap[k]]
        v.co=data['sculpt'][k];v.normal=data['sculpt_normals'][k]
        if k>=count or data['axilla_fade'][k]>0 or bust[k]>0:
            w=data['weights'][k];bones=data['bones'][k]
            if bust[k]>0 and paint_index[k]>=0:
                w=fair[paint_index[k]];bones=palette
            # These auxiliary skin joints follow the upper chest in the
            # character's built-in actions. Pool them before PMX's four-slot
            # reduction so a small change cannot drop the upper-arm influence.
            if np.count_nonzero(w)>4 or bust[k]>0:
                compact={}
                for b,weight in zip(bones,w):
                    if weight<=0:continue
                    bone=model.bones[b]
                    # Use the same two spring joints per cup across adjacent
                    # skin and cloth triangles. Hard four-weight truncation
                    # otherwise alternates between the rib and spring in a bow.
                    mix=bust[k] if b in supports else 0.
                    if mix:
                        support=supports[b]
                        compact[support]=compact.get(support,0.)+weight*mix
                        weight*=1-mix
                    if weight<=0:continue
                    if bone.name.startswith(('Bone_Omuscle01','Bone_Clavicle01')):b=bone.parent
                    compact[b]=compact.get(b,0.)+weight
                bones=np.array([*compact,0,0,0,0]);w=np.array([*compact.values(),0.,0.,0.,0.])
            v.weight=pack_weights(w,bones)
    # Split triangles sharing a selected edge on both sides of the boundary.
    # This keeps neck, hands and all neighbouring costume charts sewn as before.
    batches={n:[] for n in SKIN}
    for i,(tri,edge) in enumerate(zip(corners,mids)):
        keep=split[edge];n=keep.sum()
        if n==3:tris=children[i]
        elif n==0:tris=[tri]
        elif n==1:
            j=np.flatnonzero(keep)[0];a,b,c=np.roll(tri,-j);m=edge[j]
            tris=[[a,m,c],[m,b,c]]
        else:
            j=(np.flatnonzero(~keep)[0]+1)%3;a,b,c=np.roll(tri,-j);m,t=np.roll(edge,-j)[:2]
            tris=[[m,b,t],[a,m,t],[a,t,c]]
        batches[SKIN[data['surface'][4*i]]].extend(remap[np.asarray(tris)].tolist())
    for name,faces in batches.items():groups[name]=np.asarray(faces,np.int32)
    return np.asarray([v.co for v in model.vertices])-[0,rise,0]


class DressForm(Torso):
    def __init__(self,model,coords,faces):
        self.measure(coords[faces])
        tri=coords[faces]
        mid=tri.mean(axis=1)
        h=mid[:,1];a=np.arctan2(mid[:,0],centre(np.clip(h,13.4,18.55))-mid[:,2])
        r=np.hypot(mid[:,0],centre(np.clip(h,13.4,18.55))-mid[:,2])
        surface=self.surface(a,np.clip(h,13.4,18.55))
        fitted=np.hypot(surface[:,0],centre(np.clip(h,13.4,18.55))-surface[:,2])
        keep=(h>13.75)&(h<17.95)&(abs(r-fitted)<.21)
        faces=faces[keep]
        self.ids,compact=np.unique(faces,return_inverse=True)
        self.tri=compact.reshape(-1,3)
        q=coords[self.ids]
        angle=np.arctan2(q[:,0],centre(q[:,1])-q[:,2])
        self.points=q
        self.polar=np.stack([angle[self.tri],q[self.tri,1]],axis=-1)
        self.polar[:,:,0]=np.unwrap(self.polar[:,:,0],axis=1)
        centres=self.polar.mean(axis=1)
        self.tree=cKDTree(np.vstack([centres+[phase,0] for phase in (-2*np.pi,0,2*np.pi)]))
        rows=[skin_weights(model.vertices[i]) for i in self.ids]
        self.palette=np.array(sorted({b for row in rows for b,w in row if w>0}))
        self.weights=np.zeros((len(q),len(self.palette)))
        for i,row in enumerate(rows):
            for b,w in row:
                if w>0:self.weights[i,np.searchsorted(self.palette,b)]+=w

    def anchors(self,a,h):
        query=np.c_[((a.ravel()+np.pi)%(2*np.pi))-np.pi,h.ravel()]
        _,hits=self.tree.query(query,k=24)
        ix=hits%len(self.tri)
        planes=self.polar[ix].copy()
        planes[:,:,:,0]+=((hits//len(self.tri))-1)[:,:,None]*2*np.pi
        p,b,c=np.moveaxis(planes,2,0);u=b-p;v=c-p;t=query[:,None]-p
        def cross(x,y):return x[...,0]*y[...,1]-x[...,1]*y[...,0]
        den=cross(u,v);den=np.where(abs(den)<1e-11,np.inf,den)
        s=cross(t,v)/den;l=cross(u,t)/den
        bary=np.stack([1-s-l,s,l],axis=-1)
        score=np.maximum(-bary.min(2),0.)
        score[~np.isfinite(den)]=1e6
        best=score.argmin(1);i=np.arange(len(best))
        weights=np.clip(bary[i,best],0,1);weights/=weights.sum(1,keepdims=True)
        return self.tri[ix[i,best]],weights

    def cloth_surface(self,a,h,gap):
        a,h=np.broadcast_arrays(a,h)
        hit,weights=self.anchors(a,h)
        skin=np.einsum('ij,ijk->ik',weights,self.points[hit]).reshape(a.shape+(3,))
        sa,ca=np.sin(a),np.cos(a)
        radial=np.stack([sa,np.zeros_like(a),-ca],axis=-1)
        draft=self.surface(a,h)
        da=self.surface(a+.007,h)-self.surface(a-.007,h)
        dh=self.surface(a,h+.012)-self.surface(a,h-.012)
        n=np.cross(dh,da);n/=np.linalg.norm(n,axis=-1,keepdims=True).clip(1e-9)
        # Measure a normal allowance, including on the changing pitch under
        # the bust. A radial-only allowance pinches at the lower turn.
        clearance=gap/abs((n*radial).sum(-1)).clip(.32,1)
        correction=np.maximum(((skin-draft)*radial).sum(-1),0.)
        return draft+(clearance+correction)[...,None]*radial

    def bind_at(self,model,ids,coords):
        for batch in np.array_split(np.asarray(ids),max(1,(len(ids)+3999)//4000)):
            q=coords[batch]
            a=np.arctan2(q[:,0],centre(q[:,1])-q[:,2])
            hit,bary=self.anchors(a,q[:,1])
            rows=np.einsum('ij,ijk->ik',bary,self.weights[hit])
            for i,row in zip(batch,rows):model.vertices[i].weight=pack_weights(row,self.palette)
