"""Prepare Xiaokeai's bare, rig-compatible body cage for a separate sculpt study."""
from pathlib import Path
from tempfile import gettempdir

import numpy as np
from scipy.interpolate import CubicSpline, LinearNDInterpolator, RectBivariateSpline
from scipy.ndimage import gaussian_filter, gaussian_filter1d

from build_lanxu import OUT, PMX
from yuexiao_torso import centre, depth, radius, skin_weights, smooth, width


SKIN = ('Up_Skin', 'Down_Skin', 'QingyiTorso')
STUDY = Path(gettempdir())/'xiaokeai-torso-base.npz'


def body_data(filename,model=None):
    if model is None:
        model=PMX['load'](str(OUT/filename))
    batches={}
    first=0
    for mat in model.materials:
        last=first+mat.vertex_count//3
        if mat.name in SKIN:
            batches[mat.name]=np.asarray(model.faces[first:last],dtype=np.int32)
        if mat.name=='Moon_Brocade':
            first_top=np.min(model.faces[first:last])
        first=last
    faces=np.concatenate([batches[n] for n in SKIN])
    ids=np.unique(faces)
    q=np.array([model.vertices[i].co for i in ids])
    data=dict(coords=q,ids=ids,faces=np.searchsorted(ids,faces),
              normals=np.asarray([model.vertices[i].normal for i in ids]))
    if filename=='yuexiao.pmx':
        weights=np.zeros((len(q),4))
        bones=np.zeros((len(q),4),np.int32)
        for j,i in enumerate(ids):
            for k,(bone,w) in enumerate(skin_weights(model.vertices[i])):
                weights[j,k]=w;bones[j,k]=bone
        data.update(rise=model.vertices[first_top].co[1]-14.76,
                    names=np.asarray([b.name for b in model.bones]),
                    weights=weights,bones=bones,
                    uv=np.asarray([model.vertices[i].uv for i in ids]),
                    surface=np.repeat(np.arange(len(SKIN)),[len(batches[n]) for n in SKIN]))
    return data


def sculpt(donor, rise):
    # Draft the unsupported form on the donor ribcage. Its forward volume
    # reaches its broadest section below mid-height, then runs out over the
    # pectoral plane. The medial and lateral roots finish at different levels.
    x,y,z=donor.T
    h=y-rise
    section=np.clip(h,12.9,18.5)
    c=centre(section)
    a=np.arctan2(x,c-z)
    angle=abs(a)
    levels=[15.02,15.30,15.49,15.65,15.85,16.08,16.30,16.51,16.78,
            17.04,17.30,17.55,17.79,18.03,18.18]
    fullness=[0,.014,.085,.27,.63,.91,1.,.975,.87,.70,.48,.265,.102,.016,0]
    sections=CubicSpline(levels,fullness,bc_type=((1,0.),(1,0.)))
    medial=.12*np.exp(-(angle/.34)**2)
    axillary=.32*smooth((angle-.85)/.55)
    # A slight difference in settling is carried by the surface, not by
    # the skeleton or by moving one entire side of the chest.
    station=h-(medial+axillary+.115)*(1-smooth((h-16.1)/.82))+.021*np.tanh(x/.35)
    volume=np.maximum(sections(np.clip(station,levels[0],levels[-1])),0)
    peak=.62+.085*smooth((h-16.37)/1.06)
    def mass(distance):
        breadth=.565+.080*np.tanh(distance/.33)
        # A broad lower pole turns across the rib cage without producing
        # two pointed highlights when the character is viewed head-on.
        exponent=2.14+.16*np.exp(-((h-16.15)/.50)**2)
        return np.exp(-np.abs(distance/breadth)**exponent)
    lobes=mass(a-peak)+mass(-a-peak)
    tail=.095*np.exp(-((angle-1.04)/.34)**2-((h-(16.64+.70*(angle-1.0)))/.83)**2)
    rib=width(section)*depth(section)/np.hypot(depth(section)*np.sin(a),width(section)*np.cos(a))
    # The tissue projects both forward from the chest wall and around the
    # ribs. A purely radial displacement flares the breasts toward the arms.
    soft=(.91+.009*np.tanh(x/.45))*volume*lobes
    change=rib+.60*soft+tail-radius(a,section)
    # Keep the donor landmarks at the collar, under the arm and at the waist.
    # Use a smooth mask on actual positions to keep the donor's separate arm
    # islands out of the fit on horizontal sections that cross the humerus.
    mask=(smooth((h-15.07)/.37)*(1-smooth((h-17.70)/.49))*
          (1-smooth((angle-1.27)/.30))*(1-smooth((abs(x)-1.65)/.39)))
    side=change*np.sin(a)
    front=change*np.cos(a)+.40*soft
    return donor+np.stack([side*mask,np.zeros_like(y),-front*mask],axis=1)


class ReferenceBodiceForm:
    """Fit the two outlines on the supplied 1536 × 1024 strapless sheet."""

    angle=np.deg2rad(113)
    px_per_unit=44.
    # Front outer satin edges, sampled where the edge separates from
    # the upper arm. The centre and waist/shoulder anchors register the view.
    front_y=np.array([201,205,210,216,222,228,234,240,246,252,257,261])
    front_left=np.array([473,465,461,458,456,456,457,458,460,463,466,470])
    front_right=np.array([570,579,583,586,588,589,589,588,586,583,580,576])
    # The second camera shows the back and the outside profile together.
    # Stop at the bottom of the cup, above the bow and upper arm.
    side_y=np.array([188,191,194,197,200,203,206,209,212,215,218,221,224,
                     227,230,233,236,239,242,245,248,251,254,257,260])
    side_right=np.array([1142,1148,1153,1157,1161,1166,1169,1172,1174,1176,
                         1178,1179,1180,1180,1180,1180,1179,1179,1177,1176,
                         1174,1172,1169,1165,1159])

    def __init__(self,points,rise):
        self.rise=rise
        h=points[:,1]-rise
        c=centre(np.clip(h,12.9,18.5))
        a=np.arctan2(points[:,0],c-points[:,2])
        # Sample the actual anterior skin, including its departures from the
        # drafted rib cage near the clavicle. Exclude the separate arm charts.
        use=(h>15.0)&(h<18.1)&(abs(a)<1.60)&(abs(points[:,0])<1.78)
        coords=np.c_[abs(a[use]),h[use]]
        r=np.hypot(points[use,0],c[use]-points[use,2])
        sample=LinearNDInterpolator(coords,r)
        heights=np.linspace(15.1,17.84,150)
        aa,hh=np.meshgrid(np.linspace(0,1.47,150),heights)
        rr=sample(aa,hh)
        rr=np.where(np.isfinite(rr),rr,radius(aa,hh))
        self.skin_residual=RectBivariateSpline(heights,aa[0],
            gaussian_filter(rr-radius(aa,hh),(5.5,4.0),mode='nearest'))
        grid=np.stack([rr*np.sin(aa),hh+rise,centre(hh)-rr*np.cos(aa)],axis=-1)
        base=sculpt(grid.reshape(-1,3),rise).reshape(grid.shape)
        side,forward,wx,wz=self.adjustments(aa,hh)
        xx=base[:,:,0]+side
        zz=-base[:,:,2]+forward
        fy=166.+(18.-heights)*self.px_per_unit
        sy=168.+(18.-heights)*self.px_per_unit
        # Allow for the satin thickness. The outer arc at the top is the
        # neckline, not the full body width; release that constraint there.
        target_w=(np.interp(fy,self.front_y,self.front_right-self.front_left)/2-1.)/self.px_per_unit
        target_p=(np.interp(sy,self.side_y,self.side_right)-1103.5-1.4)/self.px_per_unit
        fw=smooth((fy-201)/13)*smooth((265-fy)/7)
        sw=smooth((sy-185)/9)*smooth((266-sy)/8)
        cs,ss=-np.cos(self.angle),np.sin(self.angle)
        def envelope_fit(base,direction,target):
            # The point on the envelope can move between angular samples as
            # its curvature changes. Solve the maximum of all sampled rays.
            lo=np.full_like(target,-.38);hi=np.full_like(target,.48)
            for _ in range(20):
                mid=(lo+hi)/2
                too_big=(base+mid[:,None]*direction).max(axis=1)>target
                hi=np.where(too_big,mid,hi);lo=np.where(too_big,lo,mid)
            return (hi+lo)/2
        lateral=gaussian_filter1d(fw*envelope_fit(xx,wx,target_w),10.)
        projected=cs*(xx+wx*lateral[:,None])+ss*zz
        anterior=gaussian_filter1d(sw*envelope_fit(projected,ss*wz,target_p),9.0)
        self.lateral=CubicSpline(heights,lateral,bc_type='clamped')
        self.anterior=CubicSpline(heights,anterior,bc_type='clamped')
        self.limits=heights[[0,-1]]

    @staticmethod
    def adjustments(a,h):
        # Bring the upper-inner surfaces together above the centre of the
        # bodice, leaving a soft trough as the sternum approaches the waist.
        def lobes(c,w):
            return np.exp(-((a-c)/w)**2)+np.exp(-((a+c)/w)**2)
        upper=np.exp(-((h-16.91)/.63)**2)
        gather=np.exp(-((h-16.67)/.60)**2)
        inward=-np.tanh(a/.20)*(.045*upper+.095*gather)*lobes(.40,.38)
        # Each upper pole rises toward its own centre and rolls away toward
        # the sternum and axilla. This shapes the skin exposed above the satin.
        arch=17.18-.43*((np.hypot(a,.045)-.61)/.67)**2
        roll=(.095*upper*lobes(.34,.34)+
              .14*np.exp(-((h-arch)/.48)**2)*lobes(.58,.56))
        side=np.sin(a)*lobes(1.18,.39)
        front=lobes(.57,.52)+.12*lobes(.96,.46)
        return inward,roll,side,front

    def __call__(self,points):
        h=points[:,1]-self.rise
        a=np.arctan2(points[:,0],centre(np.clip(h,12.9,18.5))-points[:,2])
        sampled=np.clip(h,*self.limits)
        inward,roll,wx,wz=self.adjustments(a,h)
        mask=(smooth((h-15.14)/.33)*smooth((17.96-h)/.30)*
              smooth((1.58-abs(a))/.16)*smooth((1.94-abs(points[:,0]))/.25))
        result=sculpt(points,self.rise)
        result[:,0]+=mask*(inward+wx*self.lateral(sampled))
        result[:,2]-=mask*(roll+wz*self.anterior(sampled))
        return result

    def skin_normals(self,points,donor_normals):
        normals=sculpt_normals(points,donor_normals,self)
        h=points[:,1]-self.rise
        a=np.arctan2(points[:,0],centre(np.clip(h,12.9,18.5))-points[:,2])
        weight=(smooth((h-15.15)/.36)*smooth((17.85-h)/.35)*
                smooth((1.48-abs(a))/.25)*smooth((1.81-abs(points[:,0]))/.25))
        use=weight>0
        a,h=a[use],h[use]
        def surface(angle,level):
            r=radius(angle,level)+self.skin_residual.ev(level,abs(angle))
            return self(np.c_[r*np.sin(angle),level+self.rise,centre(level)-r*np.cos(angle)])
        # Evaluate the tangents of the fitted sheet directly on the skin.
        # The normal at a skin seam must not depend on a neighbouring UV
        # island's edge lengths or on how a PMX normal extends off-surface.
        da=surface(a+.008,h)-surface(a-.008,h)
        dh=surface(a,h+.012)-surface(a,h-.012)
        n=np.cross(dh,da)
        n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-8)
        normals[use]+=(n-normals[use])*weight[use,None]
        return normals/np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-8)


def sculpt_normals(points,normals,deform):
    # Transport the donor's authored skin normals through the actual shape
    # change. This keeps the fine clavicle and the sewn chart boundaries
    # continuous even where the PMX has very differently sized triangles.
    delta=.0008
    gradients=[]
    for axis in np.eye(3)*delta:
        gradients.append((deform(points+axis)-deform(points-axis))/(2*delta))
    inverse_transpose=np.stack(gradients,axis=1)
    result=np.linalg.solve(inverse_transpose,normals[...,None])[...,0]
    return result/np.maximum(np.linalg.norm(result,axis=1,keepdims=True),1e-8)


def refine_skin(donor,sculpted,normals):
    # One edge point per chart edge. Preserve the original cage points;
    # additional samples round the silhouette between them. UV seams still
    # share the same spatial edge when the Blender cage is welded.
    f=donor['faces']
    edge_list=np.sort(f[:,[0,1,1,2,2,0]].reshape(-1,2),axis=1)
    edges,inverse=np.unique(edge_list,axis=0,return_inverse=True)
    a,b=edges.T
    def mean(v):return (v[a]+v[b])*.5
    def extended(v,mid):return np.concatenate([v,mid])
    def unit(v):return v/np.maximum(np.linalg.norm(v,axis=1,keepdims=True),1e-8)
    mid=mean(donor['coords'])
    h=mid[:,1]-donor['rise']
    angle=np.arctan2(mid[:,0],centre(np.clip(h,12.9,18.5))-mid[:,2])
    mask=(smooth((h-15.10)/.45)*(1-smooth((h-17.6)/.55))*
          (1-smooth((abs(angle)-1.27)/.30))*(1-smooth((abs(mid[:,0])-1.65)/.39)))
    def round_edge(points,shading):
        delta=points[b]-points[a]
        def normal_component(n):return (delta*n).sum(1)[:,None]*n
        bend=(normal_component(shading[b])-normal_component(shading[a]))/8
        return mean(points)+mask[:,None]*bend
    new_mid=round_edge(sculpted,normals)
    count=len(mid)
    all_bones=np.concatenate([donor['bones'][a],donor['bones'][b]],axis=1)
    all_weights=np.concatenate([donor['weights'][a],donor['weights'][b]],axis=1)*.5
    # Combine identical influences from either endpoint before truncation.
    for j in range(1,8):
        same=all_bones[:,:j]==all_bones[:,j,None]
        duplicate=same.any(axis=1)
        rows=np.flatnonzero(duplicate)
        all_weights[rows,same[rows].argmax(axis=1)]+=all_weights[rows,j]
        all_weights[rows,j]=0
    strongest=np.argsort(-all_weights,axis=1,kind='stable')[:,:4]
    weights=np.take_along_axis(all_weights,strongest,axis=1)
    weights/=weights.sum(axis=1,keepdims=True)
    edge_ids=inverse.reshape(-1,3)+len(sculpted)
    i,j,k=f.T;ij,jk,ki=edge_ids.T
    donor.update(coords=extended(donor['coords'],mid),uv=extended(donor['uv'],mean(donor['uv'])),
                 bones=extended(donor['bones'],np.take_along_axis(all_bones,strongest,axis=1)),
                 weights=extended(donor['weights'],weights),ids=np.r_[donor['ids'],np.full(count,-1)],
                 faces=np.stack([i,ij,ki,ij,j,jk,ki,jk,k,ij,jk,ki],axis=1).reshape(-1,3),
                 surface=np.repeat(donor['surface'],4))
    return dict(sculpt=extended(sculpted,new_mid),sculpt_normals=extended(normals,unit(mean(normals))))


def prepared_skin(model=None):
    donor=body_data('yuexiao.pmx',model)
    # Store the cage, bind data and source vertex identity. UV islands are
    # stitched in Blender with corner UVs retained on either side of a seam.
    coords=donor['coords']
    form=ReferenceBodiceForm(coords,donor['rise'])
    new=form(coords)
    normals=form.skin_normals(coords,donor['normals'])
    shapes=refine_skin(donor,new,normals)
    from torso_surface import finish_skin
    finish_skin(donor,shapes)
    del donor['normals']
    return dict(**shapes,**donor)


def build():
    np.savez_compressed(STUDY,**prepared_skin())


if __name__=='__main__':
    build()
