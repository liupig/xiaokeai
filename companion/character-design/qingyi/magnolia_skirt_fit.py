"""Fit the Magnolia skirt around the seat and transfer each leg's motion to its panels."""
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.interpolate import RegularGridInterpolator

from build_lanxu import PMX
from yuexiao_torso import skin_weights


def ease(t):
    t = np.clip(t, 0., 1.)
    return t*t*(3-2*t)


def hip_envelope(triangles):
    """Outermost skin intersection on each horizontal ray, in PMX coordinates."""
    heights = np.linspace(11.45,15.65,55)
    angles = np.linspace(-np.pi,np.pi,145)
    rays = np.stack((np.sin(angles),-np.cos(angles)),axis=1)
    values = np.zeros((len(heights),len(angles)))
    def cross(a,b):
        return a[...,0]*b[...,1]-a[...,1]*b[...,0]
    for row,y in enumerate(heights):
        tris = triangles[(triangles[:,:,1].min(1)<y)&(triangles[:,:,1].max(1)>=y)]
        hits = []
        for a,b in zip(tris.transpose(1,0,2),np.roll(tris,-1,axis=1).transpose(1,0,2)):
            cut = (a[:,1]<y)!=(b[:,1]<y)
            i = np.flatnonzero(cut)
            point = a[i]+(b[i]-a[i])*((y-a[i,1])/(b[i,1]-a[i,1]))[:,None]
            hits.extend(zip(i,point[:,[0,2]]-[0.,.30]))
        segs = np.array([p for _,p in sorted(hits,key=lambda h:h[0])]).reshape(-1,2,2)
        origin = segs[:,0];edge = segs[:,1]-origin
        den = cross(rays[:,None],edge)
        with np.errstate(divide='ignore',invalid='ignore'):
            distance = cross(origin,edge)/den
            fraction = cross(origin,rays[:,None])/den
        values[row] = np.max(np.where((fraction>=0)&(fraction<=1)&(distance>0),distance,0.),axis=1)
    values[:,:-1]=gaussian_filter1d(values[:,:-1],.75,axis=1,mode='wrap')
    values[:,-1]=values[:,0]
    return RegularGridInterpolator((heights,angles),values,bounds_error=False,fill_value=None)


def fit_skirt(model):
    xyz = np.asarray([v.co for v in model.vertices])
    faces = np.asarray(model.faces)
    bones = {b.name:i for i,b in enumerate(model.bones)}
    groups = {}
    start=0
    for mat in model.materials:
        end=start+mat.vertex_count//3
        groups[mat.name]=faces[start:end]
        start=end
    hip_y = model.bones[bones['左足']].location[1]
    guides=[]
    for side in ('右','左'):
        thigh = bones[side+'足']
        b = PMX['Bone']()
        b.name = b.name_e = 'Magnolia_FrontFold_'+('R' if side=='右' else 'L')
        if b.name in bones:
            raise ValueError('Magnolia skirt is already fitted')
        px,_,pz = model.bones[thigh].location
        b.parent = bones['下半身']
        b.location = (px,hip_y+1.45,pz-.97)
        b.displayConnection = (0.,-.85,0.)
        b.isMovable = b.visible = b.isControllable = False
        b.transform_order = model.bones[thigh].transform_order+1
        b.hasAdditionalRotate = True
        b.additionalTransform = (thigh,.79)
        guides.append(len(model.bones))
        model.bones.append(b)
    # Each skirt grid and its hems were stitched together in dressed().
    # The pendant uses separate metal, enamel and jade slots below the flower.
    cloth=('Moon_PearlHem','Moon_Petal','Moon_Veil','Moon_Silk','Moon_Silver','Moon_Gold',
           'Moon_Celadon','Moon_ChasedMetal','Moon_PearlInlay','Moon_PendantCrystal','Moon_Pearl')
    ids=np.unique(np.concatenate([groups[n].ravel() for n in cloth]))
    x,y,z=xyz[ids].T
    ids=ids[(abs(x)<3.9)&(y<15.62)]
    original=xyz[ids]
    shell=hip_envelope(xyz[groups['Down_Skin']])
    def reshape(p):
        x,y,z=p.T
        a=np.arctan2(x,.30-z)
        r=np.hypot(x,z-.30)
        back=ease((z-.13)/.90)
        seat=np.exp(-((y-13.83)/1.15)**2)
        floor=shell(np.c_[np.clip(y,11.45,15.65),a])+.09+back*(.12+.16*seat)
        gap=.83*.07*np.logaddexp(0,(floor-r+.07)/.07)
        # Keep the layers spaced where the tight underdress crosses the seat.
        gap+=.13*back*seat
        gap*=ease((15.65-y)/.63)*ease((y-11.22)/.76)
        gap+=.17*ease((15.3-y)/1.75)*ease((r-.55)/.68)
        side=ease((abs(x)-.55)/.70)
        gap+=.22*side*np.exp(-((y-14.64)/.68)**2)
        front=ease((.35-z)/.94)
        gap+=front*(.24*np.exp(-((y-13.5)/.73)**2)+.17*np.exp(-((y-11.85)/.70)**2))
        gap+=.12*front*np.exp(-((y-15.25)/.37)**2)
        # Allow the opposite side of the thigh to roll into the panel as the
        # joint reaches full flexion or extends behind the body.
        hip_roll=np.exp(-((abs(x)-.98)/.62)**2)
        gap+=hip_roll*(.12*back*np.exp(-((y-14.77)/.53)**2)
                      +.27*front*np.exp(-((y-12.70)/.64)**2))
        # Preserve space beside the upper thigh when the pelvis turns across
        # the standing leg, especially under the fitted dress's scalloped hem.
        side_room=(.30*np.exp(-((y-13.66)/.86)**2)
                   +.36*np.exp(-((y-12.60)/.90)**2))
        gap+=np.sin(a)**6*side_room
        return p+np.stack((np.sin(a)*gap,np.zeros_like(y),-np.cos(a)*gap),axis=1)
    final=reshape(original)
    jac=np.stack([(reshape(original+axis*.002)-reshape(original-axis*.002))/.004 for axis in np.eye(3)],axis=2)
    normals=np.asarray([model.vertices[i].normal for i in ids])
    # A soft radial clamp can flatten underlapping panels. Keep their local
    # tangential normals well-conditioned while preserving the drawn folds.
    jac=jac*.94+np.eye(3)*.06
    normals=np.linalg.solve(jac.transpose(0,2,1),normals[...,None])[...,0]
    normals/=np.maximum(1.e-9,np.linalg.norm(normals,axis=1,keepdims=True))
    x,y,z=original.T
    left=ease(.5+x/(2.04+.55*ease((y-12.6)/1.8)))
    # The articulated gold frame and jade drop sit on the centre seam.
    # Use the same lateral response across the width of these rigid pieces.
    pendant=(ids>=groups['Moon_ChasedMetal'].min())&(ids<groups['Moon_CuffSetting'].min())&(abs(x)<1.35)&(z<-.53)
    left[pendant]=.5
    gain=.987*ease((hip_y+2.19-y)/1.83)
    rear=ease((z-.35)/1.02)
    gain*=1-.56*rear
    front=ease((.94-z)/1.14)
    leg_ids=(bones['右足D'],bones['左足D'])
    for k,i in enumerate(ids):
        v=model.vertices[i]
        v.co,v.normal=final[k],normals[k]
        if gain[k] < 1.e-5:
            continue
        merged={}
        for b,w in skin_weights(v):
            if w>0 and b>=0: merged[b]=merged.get(b,0.)+w*(1-gain[k])
        for b,guide,f in zip(leg_ids,guides,(1-left[k],left[k])):
            merged[b]=merged.get(b,0.)+f*gain[k]*(1-front[k])
            merged[guide]=f*gain[k]*front[k]
        pairs=sorted(merged.items(),key=lambda item:-item[1])[:4]
        norm=sum(w for _,w in pairs)
        weight=PMX['BoneWeight']()
        weight.type=weight.BDEF4
        weight.bones=[b for b,w in pairs]+[0]*(4-len(pairs))
        weight.weights=[w/norm for _,w in pairs]+[0.]*(4-len(pairs))
        v.weight=weight
