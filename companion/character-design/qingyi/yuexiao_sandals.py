"""Last and straps of the pearl sandals, fitted to the existing arched feet."""
from copy import deepcopy
import cv2
import numpy as np
from PIL import Image
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

from build_yuexiao import lattice
from yuexiao_jewels import chart, stone_cut
from build_lanxu import TEX


def remove_painted_straps():
    # The donor skin has metallic strokes baked into its calf and instep UVs.
    # Only fill the old strokes on the Yuexiao copy with their adjacent skin.
    file=TEX/'yuexiao-lining.png'
    image=np.array(Image.open(file).convert('RGBA'))
    rgb=image[:,:,:3].copy()
    _,g,b=rgb.astype('int16').transpose(2,0,1)
    h,w=g.shape
    x,y=np.meshgrid(np.arange(w)*850/w,np.arange(h)*850/h)
    area=((x>652)&(x<841)&(y>406)&(y<766))|((x>754)&(x<826)&(y>766)&(y<800))
    seeds=((g-b>8)&area).astype('uint8')
    brush=cv2.dilate(seeds,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(13,13)))
    image[:,:,:3]=cv2.inpaint(rgb,brush,5,cv2.INPAINT_NS)
    Image.fromarray(image).save(file)


def sandals(t):
    m=t.m;cursor=0
    for mat in m.materials:
        count=mat.vertex_count//3
        if mat.name=='Down_Skin':
            faces=np.asarray(m.faces[cursor:cursor+count]);break
        cursor+=count
    ids=np.unique(faces)
    points=np.array([m.vertices[i].co for i in ids])
    low=points[:,1]<8.2
    tree=cKDTree(points[low]);donor=ids[low]
    tris=points[np.searchsorted(ids,faces)]
    tris=tris[(tris[:,:,0].min(1)>.35)&(tris[:,:,1].max(1)<8.5)]

    # Intersect horizontal stations of the foot with rays from its centre.
    # This keeps the ankle wrap against the skin around the heel and instep.
    def section(y,a):
        tr=tris[(tris[:,:,1].min(1)<=y)&(tris[:,:,1].max(1)>y)]
        ends=[]
        for j in range(3):
            p,q=tr[:,j],tr[:,(j+1)%3]
            k=np.flatnonzero((p[:,1]>y)!=(q[:,1]>y))
            mix=((y-p[k,1])/(q[k,1]-p[k,1]))[:,None]
            ends.extend(zip(k,(p[k]+mix*(q[k]-p[k]))[:,[0,2]]))
        arr=np.array([v for i,v in sorted(ends,key=lambda kv:kv[0])]).reshape(-1,2,2)
        centre=(arr.min(axis=(0,1))+arr.max(axis=(0,1)))*.5
        ray=np.array([np.sin(a),-np.cos(a)])
        b,e=arr[:,0]-centre,arr[:,1]-arr[:,0]
        def cross(x,y):return x[...,0]*y[...,1]-x[...,1]*y[...,0]
        with np.errstate(divide='ignore',invalid='ignore'):
            den=cross(ray,e);r=cross(b,e)/den;f=cross(b,ray)/den
        radii=r[(r>0)&(f>=0)&(f<=1)]
        if not len(radii):raise ValueError('No skin at the sandal strap')
        x,z=centre+(radii.min()+.025)*ray
        return [x,y,z]

    satin=t.material('SandalSatin',color=(.86,.76,.77))
    sole=t.material('SandalSole','jewels.jpg')
    gold=t.material('SandalGold',color=(.80,.65,.48))
    counter=t.material('SandalCounter','jewels.jpg')
    heel_metal=t.material('SandalHeelMetal','jewels.jpg')
    pearl=t.material('SandalPearl',color=(.94,.87,.85))
    crystal=t.material('SandalCrystal','jewels.jpg')
    dark_tip=t.material('SandalHeelTip',color=(.32,.22,.18))
    first=len(m.vertices)
    levels=[-.69,-.63,-.49,-.28,-.02,.20,.42,.66,.92,1.15,1.34,1.49,1.58]
    half=PchipInterpolator(levels,[.018,.179,.315,.411,.449,.429,.379,.314,.296,.320,.314,.209,.013])
    mid=PchipInterpolator(levels,[1.05,1.065,1.097,1.144,1.195,1.220,1.232,1.23,1.22,1.205,1.19,1.18,1.18])
    base=PchipInterpolator(levels,[.021,.012,.010,.010,.010,.015,.103,.375,.565,.744,.875,1.00,1.05])
    foot=tris[tris[:,:,1].min(1)<1.65]
    def plantar(x,z,top=False):
        local=foot[(foot[:,:,0].min(1)<=x)&(foot[:,:,0].max(1)>=x)&
                   (foot[:,:,2].min(1)<=z)&(foot[:,:,2].max(1)>=z)]
        e=local[:,1]-local[:,0];f=local[:,2]-local[:,0];w=np.array([x,0,z])-local[:,0]
        det=e[:,0]*f[:,2]-e[:,2]*f[:,0]
        with np.errstate(divide='ignore',invalid='ignore'):
            l=(w[:,0]*f[:,2]-w[:,2]*f[:,0])/det;n=(e[:,0]*w[:,2]-e[:,2]*w[:,0])/det
        heights=(local[:,0,1]+l*e[:,1]+n*f[:,1])[(l>=0)&(n>=0)&(l+n<=1)]
        return (heights.max() if top else heights.min()) if len(heights) else np.nan
    stations=np.linspace(levels[0],levels[-1],91)
    underside=np.array([plantar(mid(z),z) for z in stations])
    hit=np.isfinite(underside)
    curved=np.interp(stations,stations[hit],underside[hit])
    # Let the small margins beyond the toe and heel follow the last itself.
    curved=np.where(hit,.95*curved+.05*base(stations),base(stations))
    curved=gaussian_filter1d(curved,2.1,mode='nearest')
    ball=np.clip((stations-.13)/.23,0,1)
    curved=base(stations)*(1-ball)+curved*ball
    bed_height=PchipInterpolator(stations,np.maximum(.004,curved+.005))
    v,u=lattice(69,26);z=levels[0]+(levels[-1]-levels[0])*v;d=2*u-1
    for s in (-1,1):
        def mirror(p):
            p=np.array(p,copy=True);p[...,0]*=s;return p
        bed=np.stack([mid(z)+d*half(z),bed_height(z)+.023*d*d,z],axis=-1)
        bottom=bed.copy();bottom[...,1]=np.maximum(-.017,bed[...,1]-.068)
        sole_uv=chart('heel',np.stack([997.5+5.*u+4.*(1-v),958.+5.5*u+5.*(1-v)],axis=-1))
        t.grid(satin,mirror(bed),flip=s>0);t.grid(sole,mirror(bottom),flip=s<0,uv=sole_uv)
        rim=np.concatenate([bed[:,0],bed[-1,1:],bed[-2::-1,-1],bed[0,-2::-1]])
        underside=rim.copy();underside[:,1]=np.maximum(-.017,underside[:,1]-.068)
        t.grid(satin,mirror(np.stack([rim,underside],axis=1)),flip=s<0)
        t.wire(gold,mirror(rim),.012,7)

        # The back of the heel grows out of the sole into a raked stiletto.
        v1,u1=lattice(36,32);a=2*np.pi*u1
        rx=np.interp(v1,[0,.13,.27,.55,.83,1],[.191,.131,.078,.038,.029,.031])
        rz=rx*np.interp(v1,[0,.25,1],[1.11,1.15,1.03])
        zc=1.315+.164*v1+.093*np.sin(np.pi*v1)
        heel_z=zc+rz*np.sin(a)
        crown_y=bed_height(1.315+.191*1.11*np.sin(a))-.044
        p=np.stack([1.197+rx*np.cos(a),crown_y*(1-v1)-.013*v1,heel_z],axis=-1)
        image_y=903+54*v1
        left_rail=np.interp(image_y,[903,912,922,940,957],[983.2,984.4,985.9,985.5,984.8])
        right_rail=np.interp(image_y,[903,912,922,940,957],[1000.,997.1,994.4,990.5,987.6])
        image_x=left_rail+(right_rail-left_rail)*(.5+.49*np.sin(a-.35))
        t.grid(heel_metal,mirror(p),flip=s>0,uv=chart('heel',np.stack([image_x,image_y],axis=-1)))
        t.grid(dark_tip,mirror(np.stack([p[-1],p[-1]-[0,.010,0]])),flip=s>0)
        t.wire(gold,mirror(p[-2]),.006,6)

        def band(points, facing, halfwidth, rise=.012):
            # An oval, edge-rolled strap lies flat against the arch. Its
            # broad polished face and turned edge catch different highlights.
            tang=np.gradient(points,axis=0)
            tang/=np.linalg.norm(tang,axis=1,keepdims=True).clip(1e-7)
            norm=np.broadcast_to(facing,points.shape).copy()
            norm-=np.sum(norm*tang,axis=1)[:,None]*tang
            norm/=np.linalg.norm(norm,axis=1,keepdims=True).clip(1e-7)
            across=np.cross(tang,norm)
            a=np.linspace(0,2*np.pi,11)[None,:,None]
            ribbon=points[:,None]+np.asarray(halfwidth).reshape(-1,1,1)*np.cos(a)*across[:,None]+rise*np.sin(a)*norm[:,None]
            t.grid(gold,mirror(ribbon),flip=s<0)

        # A U-shaped quarter follows the heel from both sides of the shank.
        # Its raised topline frames the skin above the flared stiletto head.
        vq,uq=lattice(12,52)
        turn=-1.57-3.14*uq
        lower=.51+.54*np.sin(np.pi*uq)**.72
        upper=.62+.88*np.sin(np.pi*uq)**.82
        level=lower+(upper-lower)*vq
        quarter=np.array([section(h,a) for h,a in zip(level.ravel(),turn.ravel())]).reshape(*level.shape,3)
        uv=chart('heel',np.stack([1000+4.8*(2*uq-1),897.5-9*vq+3*np.cos(2*np.pi*uq)],axis=-1))
        t.grid(counter,mirror(quarter[:5]),flip=s>0,uv=uv[:5])
        for station in (1,-2):
            t.wire(gold,mirror(quarter[4:,station]),.013,6)
        # Keep the opening open, with a metallic topline and two thin stays.
        normal=np.stack([np.sin(turn[-1]),np.zeros(turn.shape[1]),-np.cos(turn[-1])],axis=-1)
        band(quarter[-1],normal,.022,.009)
        def welt_return(point,side,reach,width):
            # A strap is captured between the insole and outsole, below the
            # side of the foot. The hand-over never ends halfway up the skin.
            z0=np.clip(point[2]+reach,-.22,1.14)
            edge=np.array([mid(z0)+side*half(z0),bed_height(z0)+.015,z0])
            w=np.linspace(0,1,21)[:,None]
            guide=point+(edge-point)*w
            guide[:,0]+=side*.045*np.sin(np.pi*w[:,0])
            band(guide,[float(side),0.,0.],width,.009)
        for j,side in ((0,-1),(-1,1)):
            welt_return(quarter[-1,j],side,.14,.022)

        # A fine strap follows the real foot's upper surface at the toe joints.
        q=np.linspace(-1,1,55);zz=-.278+.065*q+.055*(1-q*q)
        px=mid(zz)+q*half(zz)*.98
        top_y=[]
        for xx,zz0 in zip(px,zz):
            surface=plantar(xx,zz0,top=True)
            top_y.append(surface+.017 if np.isfinite(surface) else bed_height(zz0)+.028)
        # Bridge the spaces between toes with one continuous leather
        # band. The vamp is supported by the highest toe on each side.
        toe_y=np.asarray(top_y)
        arch=np.maximum(0,1-q*q)**.56
        amp=np.max((toe_y-bed_height(zz))[abs(q)<.72]/arch[abs(q)<.72])
        toe_y=bed_height(zz)+.018+amp*arch
        line=np.c_[px,toe_y,zz]
        band(line,[0.,1.,0.],.032,.011)
        vamp_tip=line[len(q)//2]
        # The two leaves of the anklet bow out around the ankle, then cross
        # on its front. The inner side continues over the heel as a sling.
        q=np.linspace(0,1,65)
        brooch_angle=.19
        stops=[0,.24,.51,.69,.84,1]
        top_angle=-.42
        heights=PchipInterpolator(stops,[1.07,1.44,1.97,2.32,2.51,2.70])(q)
        for hand in (-1,1):
            angles=[.12,-.91,-1.60,-1.69,-1.38,top_angle] if hand<0 else [.26,.93,1.44,1.51,1.04,top_angle]
            a=PchipInterpolator(stops,angles)(q)
            norm=np.stack([np.sin(a),0*q,-np.cos(a)],axis=-1)
            path=np.array([section(y,ang) for y,ang in zip(heights,a)])
            path+=(.009+.083*np.sin(np.pi*q)**1.5)[:,None]*norm
            band(path,norm,.026-.004*np.cos(2*np.pi*q),.010)
            if hand==1:
                angle=top_angle-1.30*np.pi*q
                filament=np.array([section(y,ang) for y,ang in zip(2.70+4.0*q,angle)])
                filament+=(path[-1]-filament[0])*(1-q[:,None])**3
                t.wire(gold,mirror(filament),.013*(1-.66*q),6)
            a=hand*(1.47*(1-q)+brooch_angle*hand*q)
            h=.26+.82*q
            lower=np.array([section(y,ang) for y,ang in zip(h,a)])
            band(lower,np.stack([np.sin(a),0*q,-np.cos(a)],axis=-1),.019,.009)
            welt_return(lower[0],hand,-.105,.019)
        a=PchipInterpolator(stops,[-np.pi,-2.73,-2.29,-1.90,-1.42,top_angle])(q)
        level=PchipInterpolator(stops,[1.50,1.72,2.04,2.25,2.45,2.70])(q)
        normals=np.stack([np.sin(a),0*q,-np.cos(a)],axis=-1)
        backstrap=np.array([section(y,ang) for y,ang in zip(level,a)])+.013*normals
        backstrap[0]=quarter[-1,len(quarter[-1])//2];backstrap[-1]=path[-1]
        band(backstrap,normals,.018,.008)
        c=np.asarray(section(1.09,brooch_angle))
        spine=np.array([section(y,ang) for y,ang in zip(.36+.73*q,.09+.10*q)])
        lead=np.linspace(0,1,19)[:,None]
        footline=vamp_tip+(spine[0]-vamp_tip)*lead
        for i,(xx,_,zz) in enumerate(footline):
            sy=plantar(xx,zz,top=True)
            if np.isfinite(sy):footline[i,1]=max(footline[i,1],sy+.023)
        band(np.vstack([footline[:-1],spine]),[0.,.45,-1.],.016,.008)
        left=np.array([s,0.,0.]);up=np.array([0.,.94,.34]);normal=np.array([0.,.34,-.94])
        mount=mirror(c)+.017*normal
        for j,(dx,dy,w,h) in enumerate([(-.105,.080,.044,.088),(.092,.107,.045,.090),(-.082,-.065,.039,.071),(.081,-.047,.041,.081),(0.,.169,.032,.069),(0.,-.155,.030,.060)]):
            theta=[-.63,.48,-.85,.66,.06,0][j]
            axis=np.cos(theta)*up+np.sin(theta)*left
            across=np.cos(theta)*left-np.sin(theta)*up
            centre=mirror(section(1.09+dy,brooch_angle+dx/.37))+.017*normal
            stone_cut(t,crystal,centre,across,axis,normal,(w,h,.032),'vamp',np.array([489.+dx*26,927.-dy*27]),[1.7,2.3],True)
            b=np.linspace(0,2*np.pi,23)
            t.wire(gold,centre+w*.80*np.cos(b)[:,None]*across+h*np.sin(b)[:,None]*axis,.0065,5)
            t.wire(gold,np.linspace(mount,centre,8),.010,6)
        t.stone(pearl,mount+.035*normal,(.047,.057,.033))
    _,nearest=tree.query([v.co for v in m.vertices[first:]])
    for v,i in zip(m.vertices[first:],donor[nearest]):v.weight=deepcopy(m.vertices[i].weight)
