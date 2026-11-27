"""Root-to-tip fibre maps and layered hair cards for the two-view 小可爱 style."""
from math import pi

import cv2
import numpy as np
from PIL import Image
from scipy.interpolate import CubicHermiteSpline, PchipInterpolator
from scipy.ndimage import distance_transform_edt, gaussian_filter, gaussian_filter1d, map_coordinates

from build_lanxu import DESIGN, TEX


# Outer ridge and inner hairline of each curtain on the approved 1536px sheet.
# Both charts start at the part. Their V axis follows the direction of growth.
WINGS = [
    ([(519,18),(506,18),(493,24),(483,34),(477,47),(473,62),(467,78),(460,87),(456,91)],
     [(519,53),(516,55),(512,61),(508,71),(503,80),(495,89),(483,96),(468,98),(456,91)]),
    ([(519,18),(532,18),(544,23),(553,30),(559,40),(564,54),(570,67),(577,78),(580,84)],
     [(519,53),(523,55),(528,61),(533,73),(539,80),(550,87),(563,90),(575,90),(580,84)])]


def wing_coordinates(side, v, u):
    high,low=WINGS[side]
    def rail(points):
        return PchipInterpolator(np.linspace(0,1,len(points)),points,axis=0)(v)
    return rail(high)*(1-u[...,None])+rail(low)*u[...,None]


def strand_detail(flow,v,seed,groups):
    # Break broad studio highlights into irregular clusters large enough to
    # survive texture filtering. Individual shafts inside each cluster vary
    # in width, value and phase as they twist through the light.
    rng=np.random.default_rng(seed)
    def band(n,smoothing,coords):
        values=gaussian_filter1d(rng.normal(size=n),smoothing)
        values/=max(values.std(),1e-6)
        return np.interp(coords,np.linspace(-.12,1.12,n),values)
    track=flow+.005*np.sin(5*v+17*flow)+.002*np.sin(12*v-23*flow)
    bunch=band(groups*6,1.4,track)
    shaft=band(groups*25,.66,track+.0015*np.sin(8*v+34*track))
    return np.clip(bunch,-2.0,2.0)*(.73+.27*np.cos(7*v+21*flow))+shaft*.45


def bake_wings(art):
    # Only hair texels enter the chart. Extend pigment at the occluded
    # temple from the neighbouring hairs before sampling the flower area.
    region = art[12:103,449:585]
    outline = [(519,18),(508,18),(495,23),(485,31),(478,41),(475,50),(476,57),
               (477,65),(475,70),(470,78),(464,84),(458,90),(467,96),
               (478,96),(488,92),(498,82),(505,75),(509,65),(513,53),
               (516,50),(522,50),(526,56),(531,69),(536,75),(545,82),
               (555,87),(564,89),(576,87),(577,83),(569,73),(563,66),
               (558,58),(553,50),(551,42),(553,37),(548,32),(539,25),(530,21)]
    mask=np.zeros(region.shape[:2],np.uint8)
    cv2.fillPoly(mask,[np.int32(outline)-[449,12]],1)
    mask[(region[...,0]-region[...,1]<8)|(region[...,2]>region[...,0]-1)] = 0
    near=distance_transform_edt(mask==0,return_distances=False,return_indices=True)
    safe=region[tuple(near)]
    # The dark centre line is made by the lifted roots meeting, while the
    # studio lighting supplies the moving highlight over that volume.
    h,w=896,480
    v,u=np.mgrid[:h,:w]/np.array([h-1,w-1])[:,None,None]
    paint,relief=[],[]
    for side in range(2):
        xy=wing_coordinates(side,v[:,0,None],u)
        coord=[xy[...,1]-12,xy[...,0]-449]
        sample=np.stack([map_coordinates(safe[...,k],coord,order=1,mode='nearest') for k in range(3)],-1)
        rng=np.random.default_rng(732+side)
        noise=gaussian_filter1d(rng.normal(size=1200),1.)
        along=u + .015*np.sin(7*v+4*u)+.035*np.sin(3*v)*np.sin(pi*u)
        thread=np.interp(along,np.linspace(-.1,1.1,len(noise)),noise)
        value=(sample-np.array([155,126,138]))*1.04+[147,119,129]
        locks=gaussian_filter1d(rng.normal(size=350),2)
        grooves=np.interp(along,np.linspace(-.1,1.1,len(locks)),locks)
        strands=strand_detail(along,v,1917+side,27)
        value+=(thread*8.2+grooves*9+7.4*strands)[...,None]
        paint.append(np.uint8(np.clip(value,0,255)))
        ridges=(sample.mean(-1)-gaussian_filter(sample.mean(-1),[7,8]))*.019
        relief.append(surface_map(thread+.48*strands,ridges,v))
    Image.fromarray(np.hstack(paint)).save(TEX/'yuexiao-parted-fringe.jpg',quality=96,subsampling=0)
    Image.fromarray(np.hstack(relief)).save(TEX/'yuexiao-parted-fringe-finish.png')


def surface_map(thread,relief,v):
    height=np.clip(.5+.105*thread+.085*relief,0,1)
    rough=np.clip(.71+.055*np.sin(4*v)+.045*thread-.038*relief,.48,.94)
    return np.uint8(255*np.stack([height,rough,np.zeros_like(height)],-1))


def bake_fibres():
    # Each strip has its own parting, length distribution and groups of hairs.
    # Keep colour in transparent texels to avoid black seams in distant mips.
    width, height = 512, 1536
    v = np.linspace(0., 1., height)
    row = np.arange(height)
    u = np.linspace(0., 1., width)[None, :]
    solid, cards, finish = [], [], []
    art=np.asarray(Image.open(DESIGN/'qingyi-yueluo-concept.png').convert('RGB'),float)
    bake_wings(art)
    bake_mantle(art)
    for tile in range(4):
        rng = np.random.default_rng(4097 + tile)
        part = u + .035*np.sin(5*v[:, None]+tile+5*u) + .019*np.sin(9*v[:, None]-3*u)
        profile = gaussian_filter1d(rng.normal(size=width), 9)
        profile = profile / profile.std()
        group = np.interp(part, u.ravel(), profile)
        fine = gaussian_filter1d(rng.normal(size=width), 1.3)
        fine /= fine.std()
        fibre = np.interp(part, u.ravel(), fine)
        # Sample down a continuous, unobscured lock on the return view.
        # Retain the violet at the ear and the rose in the lower curl.
        guide=[(1049,103,4),(1043,140,6),(1037,165,6),(1033,191,7),
               (1029,210,10),(1022,229,9),(1008,247,8),(995,266,6),
               (992,286,5),(997,304,5),(1000,322,6),(998,343,5),(1007,358,4)]
        xy=smooth_path(np.array(guide)[:,:2],v)
        radius=np.interp(v,np.linspace(0,1,len(guide)),np.array(guide)[:,2])
        xx=xy[:,0,None]+(u-.5)*2*radius[:,None]
        yy=np.broadcast_to(xy[:,1,None],xx.shape)
        sample=np.stack([map_coordinates(art[...,k],[yy,xx],order=1) for k in range(3)],-1)
        pigment=np.array([[131,105,117],[153,127,139],[170,146,154],[159,121,137.]])[tile]
        gradient=(v**1.4)[:,None,None]*np.array([24.,9.,9.])
        focus=[.32,.53,.49,.62][tile]+.11*np.sin(5*v[:,None]+tile)
        ridge=np.exp(-((u-focus)/.205)**2)
        channel=np.exp(-((u-focus-.30)/.12)**2)
        satin=(12+6*np.cos(8*v[:,None]+tile))*ridge-14*channel
        recorded=sample-gaussian_filter(sample,(95,57,0))
        field=pigment+gradient+.75*np.clip(recorded,-19,20)
        strands=strand_detail(part,v[:,None],3201+tile,22)
        field+=(3.6*group+3.2*fibre+satin+7.3*strands)[...,None]
        finish.append(surface_map(fibre*.65+.40*strands,group*.36+ridge,v[:,None]))
        veil = np.zeros((height, width), np.float32)
        ink = np.zeros_like(veil)
        # Lay overlapping tapered hairs in families with a common bend. Each
        # family's ends separate before individual threads dissolve at the tip.
        for family, start in enumerate(np.linspace(.105, .895, 15)):
            phase = rng.uniform(-pi, pi)
            drift = rng.uniform(-.037, .037)
            travel = .038*np.sin(5.6*v+phase) + .019*np.sin(10*v+2*phase)
            travel += drift*v + (start-.5)*(.10*np.sin(pi*v) - .23*v**3)
            length = rng.uniform(.79, 1.04) - .14*abs(2*start-1)
            if family in (6,8):
                length = .994
            family_tone = rng.normal(0, 8)
            for _ in range(18):
                lateral = rng.normal(0, .022)
                twist = rng.uniform(-pi, pi)
                stop = np.clip(length+rng.normal(0,.052), .52, .997)
                spread = lateral*(.71 + .54*v) + .009*np.sin(7*v+twist)
                path = (start+travel+spread)*width
                emerge = rng.uniform(-.010,.056)
                r = rng.uniform(1.15,2.65)*np.clip((stop-v)/.10, 0, 1)**.7
                r *= np.clip((v-emerge)/.055,0,1)**.8
                shade = .46*family_tone+rng.normal(0, 4)
                ix = np.floor(path).astype(int)
                for k in range(-4, 5):
                    col = np.clip(ix+k, 0, width-1)
                    coverage = np.clip(r+.52-abs(ix+k-path),0,1) * (v<stop) * (v>emerge)
                    weight = coverage*rng.uniform(.75,.96)
                    veil[row, col] += weight
                    ink[row, col] += weight*shade
        value = ink/np.maximum(veil, .001)
        rgb = np.uint8(np.clip(field+value[..., None], 0, 255))
        alpha = np.uint8(255*np.clip(veil, 0, 1))
        solid.append(np.uint8(np.clip(field,0,255)))
        cards.append(np.dstack([rgb,alpha]))
    Image.fromarray(np.hstack(solid)).save(TEX/'yuexiao-fibre-base.jpg',quality=96,subsampling=0)
    Image.fromarray(np.hstack(cards)).save(TEX/'yuexiao-fibre-cards.png',compress_level=6)
    Image.fromarray(np.hstack(finish)).save(TEX/'yuexiao-fibre-finish.png')


def strip_uv(tile, cross, length):
    # Leave a gutter on both sides; the PMX reader handles its UV convention.
    return np.stack(np.broadcast_arrays((tile+.005+.99*cross)/4, length), axis=-1)


def unit(x):
    return x/np.maximum(np.linalg.norm(x, axis=-1, keepdims=True),1e-9)


def smooth_path(guides, v):
    p = np.asarray(guides, float)
    knots = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))]
    knots /= knots[-1]
    deriv = np.gradient(p, knots, axis=0)
    return CubicHermiteSpline(knots,p,deriv)(v)


def frame(line, facing, angle):
    # Transport the frame through the curl. A fixed projection becomes
    # singular when the tip turns back toward the root.
    tangent = unit(np.gradient(line,axis=0))
    ref = np.asarray(facing,float)
    out = np.empty_like(line)
    out[0] = unit(ref-tangent[0]*np.dot(ref,tangent[0]))
    for i in range(1,len(line)):
        a,b = tangent[i-1:i+1]
        axis = np.cross(a,b)
        n = out[i-1]
        transported = n+np.cross(axis,n)+np.cross(axis,np.cross(axis,n))/max(1+np.dot(a,b),1e-6)
        goal = ref-b*np.dot(ref,b)
        out[i] = unit(transported + .055*goal)
    lateral = unit(np.cross(tangent,out))
    c,s = np.cos(angle)[:,None],np.sin(angle)[:,None]
    return lateral*c+out*s, out*c-lateral*s


def sample_chart(chart, along, across):
    rows,cols=chart.shape[:2]
    row,col=np.broadcast_arrays(np.clip(along,0,1)*(rows-1),np.clip(across,0,1)*(cols-1))
    r=np.minimum(row.astype(int),rows-2);c=np.minimum(col.astype(int),cols-2)
    dr=(row-r)[...,None];dc=(col-c)[...,None]
    upper=chart[r,c]*(1-dc)+chart[r,c+1]*dc
    lower=chart[r+1,c]*(1-dc)+chart[r+1,c+1]*dc
    return upper*(1-dr)+lower*dr


def single_hairs(t,mat,section,flip,count,rng,reach):
    # Real tapered, triangular-section fibres survive both the PMX export
    # and the editable Blender import, including when viewed edge-on.
    across=np.gradient(section,axis=1)
    along=np.gradient(section,axis=0)
    normals=unit(np.cross(across,along))*(-1 if flip else 1)
    samples=41 if reach>.15 else 29
    v=np.linspace(0,1,samples)
    q=np.linspace(0,2*pi,4)[None,:]
    for k in range(count):
        root=rng.uniform(.015,.25)
        stop=rng.uniform(.87,.995)
        a=root+(stop-root)*v
        lane=(k+rng.uniform(.17,.83))/count
        lane+=.09*np.sin(v*rng.uniform(4.,8.)+rng.uniform(-pi,pi))*np.sin(pi*v)
        line=sample_chart(section,a,lane)
        outward=unit(sample_chart(normals,a,lane))
        lateral=unit(sample_chart(across,a,lane))
        lift=rng.uniform(.0017,.009)*np.sin(pi*v)**.7
        release=np.clip((v-.59)/.41,0,1)**1.65
        line+=outward*(lift+release*reach*rng.uniform(.08,.33))[:,None]
        line+=lateral*(release*reach*rng.uniform(-.77,.77))[:,None]
        line+=unit(np.gradient(line,axis=0))*(release*reach*rng.uniform(.24,1.05))[:,None]
        direction=unit(np.gradient(line,axis=0))
        side=unit(np.cross(direction,outward))
        normal=unit(np.cross(side,direction))
        r=rng.uniform(.0013,.0032)*np.interp(v,[0,.08,.58,.85,1],[.10,.91,1,.72,.028])
        p=line[:,None]+r[:,None,None]*(side[:,None]*np.cos(q)[...,None]+normal[:,None]*np.sin(q)[...,None])
        tile=int(rng.choice([0,1,1,2,3]))
        t.grid(mat,p,flip=True,uv=strip_uv(tile,.48+.24*np.cos(q),a[:,None]))


def divide_surface(t,mat,filament,surface,uv,flip,count,seed,fringe=False):
    # Retain a continuous part at the scalp, then let each child release
    # from its parent wave at its own length, width and depth.
    rng=np.random.default_rng(seed)
    splits=np.r_[0.,np.cumsum(rng.uniform(.75,1.25,count))]
    splits/=splits[-1]
    rows=57 if fringe else 84
    a=np.linspace(0,1,rows)[:,None];c=np.linspace(-1,1,9)[None,:]
    finish=np.clip((a-(.53 if fringe else .32))/(.47 if fringe else .68),0,1)
    envelope=np.sin(pi*a)**.8
    # Shared boundary drift keeps the roots watertight even where the
    # individual lanes curve away from the original straight UV columns.
    boundaries=splits[None,:]+(.13/count)*np.sin(6*a+8*splits[None,:])*envelope*np.sin(pi*splits)
    for k in range(count):
        start,end=boundaries[:,k:k+1],boundaries[:,k+1:k+2]
        mid=.5*(start+end);spread=.5*(end-start)
        trim=rng.uniform(.002,.060 if fringe else .13)
        if k==count//2:trim=.001
        h=a-trim*finish**1.7
        cut=finish**1.55
        lane=mid+spread*c*(1-(.94 if fringe else .91)*cut)
        points=sample_chart(surface,h,lane)
        chart=sample_chart(uv,h,lane)
        side=unit(np.gradient(points,axis=1))
        normal=unit(np.cross(side,np.gradient(points,axis=0)))*(-1 if flip else 1)
        width=np.linalg.norm(points[:,-1]-points[:,0],axis=1)[:,None]
        arc=np.maximum(0,1-c*c)
        loft=width*(.15 if fringe else .20)*arc*(.13+.87*envelope)
        variation=rng.uniform(-1,1)
        direction=unit(np.gradient(points,axis=0))
        drift=finish**1.85
        release=(.095 if fringe else .27)*variation
        points+=normal*(loft+drift*(.011 if fringe else .060)*variation)[...,None]
        points+=side*(drift*release)[...,None]
        advance=rng.uniform(-.042,.085) if fringe else rng.uniform(-.17,.20)
        points+=direction*(drift*advance)[...,None]
        t.grid(mat,points,flip=flip,uv=chart)
        if not fringe:
            # The rounded reverse stays visible inside a turned lock.
            inside=points-normal*(width*.33*arc)[...,None]
            t.grid(mat,inside,flip=not flip,uv=chart)
        single_hairs(t,filament,points,flip,5 if fringe else 7,rng,.085 if fringe else .23)


def mantle(t,mat,fibres,filament):
    # The dorsal shell starts at the crown itself. Each section follows
    # the same spherical scalp through the occiput before falling freely.
    # At the waist the five sections have a rounded underside of their own.
    rows=122
    v=np.linspace(0,1,rows)[:,None]
    free=np.clip((v-.19)/.81,0,1)
    cuts=[-1,-.68,-.24,.17,.63,1]
    edges=[]
    for j,(lo,hi) in enumerate(zip(cuts,cuts[1:])):
        c=np.linspace(0,1,33)[None,:];s=lo+(hi-lo)*c
        split=np.clip((free-.45)/.55,0,1)**1.25
        u=s+(lo+(hi-lo)*.49-s)*(.982*split**2.25)
        angle=u*1.57
        bend=.012+np.minimum(1,v/.19)*1.55
        onset=np.sin(.5*pi*np.clip(free/.31,0,1))**2
        w=1.035+.35*np.sin(pi*free*.87)
        x=w*np.sin(bend)*np.sin(angle)
        top=19.98+1.463*np.cos(bend)
        h=top-7.23*free+split*(.46*u*u+.31*np.sin(j*1.91))
        z=.48+1.103*np.sin(bend)*np.cos(angle)
        z+=.84*np.sin(free*pi*.83)+1.51*np.abs(u)**1.9*np.sin(.5*pi*np.clip(free/.40,0,1))**1.7
        x+=onset*(.38*np.sin(9.4*free+1.95*u)+.14*np.sin(14*free-.9*u))
        z+=onset*(.37*np.cos(9.6*free+2.30*u)+.10*np.sin(14.3*free-2*u))
        camber=np.sin(pi*c)
        finish=1-split**3
        # A shallow longitudinal rib grows into a folded oval, then closes
        # down to a pointed tip. Both sides of the curl remain fully modelled.
        crest=camber*(.017*np.sin(bend)+.24*onset)*finish
        tilt=.98*np.sin(5.4*free+.7*j)*onset
        x+=crest*np.sin(tilt)+.31*split*np.sin(5*free+j)
        z+=crest*np.cos(tilt)+.15*split*np.sin(j*2.12)
        z+=(c-.5)*np.sin(7*free+.86*j)*split**.75*finish*.52
        h-=.18*split*camber*finish
        uv=np.stack(np.broadcast_arrays(.002+.996*(s+1)/2,.001+.998*v),-1)
        points=np.stack(np.broadcast_arrays(x,h,z),-1)
        edges.append((points[:,0],points[:,-1]))
        divide_surface(t,mat,filament,points,uv,True,[5,6,6,6,5][j],802+j)
        # Hair remains dense over the shoulder blades. An inset layer
        # fills the narrow sightlines between locks, then tapers away
        # to leave air between the individual ends below the waist.
        a=np.linspace(.21,.91+.027*np.sin(3*j+1),65)[:,None]
        c=np.linspace(-1,1,15)[None,:]
        taper=np.clip((a-.63)/(a[-1]-.63),0,1)
        b=.51+.475*c*(1-.99*taper**1.65)+.035*np.sin(8*a+j)
        inset=sample_chart(points,a,b)
        behind=unit(np.cross(np.gradient(inset,axis=1),np.gradient(inset,axis=0)))
        inset+=behind*(.05+.12*a)[...,None]
        t.grid(mat,inset,flip=True,uv=sample_chart(uv,a,b))
        # Loose ends share the exact tangents of the piece they grow from.
        # They release below the crest, where a little air shows through.
        a=np.linspace(.52,1,62)[:,None];norm=(a-.52)/.48
        edge=np.linspace(-1,1,7)[None,:]
        for k,(center,span) in enumerate([(.16,.036),(.71,.049),(.87,.033)]):
            across=center+span*edge+.035*np.sin(8*a+k)
            mm=np.stack(np.broadcast_arrays(np.clip(across,0,1)*32,
                                            a*(rows-1)),-1).astype('float32')
            loose=cv2.remap(points.astype('float32'),mm,None,cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
            release=norm**2.1
            loose[...,0]+=release*(.06+.13*k)*(-1 if (j+k)%2 else 1)+.042*edge*release
            loose[...,2]+=.009+.11*release*np.sin(8*a+k)
            loose[...,1]+=release*(.22-.19*k)
            t.grid(fibres,loose,flip=True,uv=strip_uv(1+(j+k)%2,.5+.5*edge,norm))
    # A lower, softer layer is visible between the two central forks. It
    # shares their upper path and turns up inside the otherwise open tips.
    start=rows//2
    a=np.linspace(0,1,rows-start)[:,None];c=np.linspace(-1,1,13)[None,:]
    for j in (1,2):
        line=(edges[j][1][start:]+edges[j+1][0][start:])*.5
        bias=-1 if j==1 else 1
        line[:,0]+=bias*(.14*np.sin(2*pi*a[:,0])+.07*a[:,0])
        line[:,1]+=.39*a[:,0]**2
        line[:,2]-=.24+.08*np.sin(pi*a[:,0])
        width=.13*np.sin(pi*np.minimum(.997,.045+.95*a))**.77
        p=np.broadcast_to(line[:,None,:],(len(a),c.size,3)).copy()
        p[...,0]+=width*c
        p[...,2]+=.066*(1-c*c)*(1-a)
        uv=np.stack(np.broadcast_arrays((1+cuts[j+1])*.5+.035*c,.50+.495*a),-1)
        divide_surface(t,mat,filament,p,uv,True,3,944+j)


def bake_mantle(art):
    rows,cols=1536,1200
    v,u=np.mgrid[:rows,:cols]/np.array([rows-1,cols-1])[:,None,None]
    stream=u+.032*np.sin(pi*v)*np.sin(9.7*v+4.2*u)+.007*np.sin(16*v+7*u)
    rng=np.random.default_rng(508)
    def noise(n,blur):
        field=gaussian_filter1d(rng.normal(size=n),blur)
        return np.interp(stream,np.linspace(-.07,1.07,n),field/field.std())
    grain=noise(1850,1.1)
    group=noise(420,4.6)
    # Read the smoke-rose to blush gradation along the actual side fall.
    # Median samples keep nearby skin, jewellery and background off the hair.
    spine=[(1064,29),(1046,109),(1042,147),(1032,195),(1018,231),
           (1000,253),(992,276),(1003,304),(1006,333),(1008,361)]
    xy=PchipInterpolator(np.linspace(0,1,len(spine)),spine,axis=0)(v[:,0])
    swatches=np.stack([art[np.clip((xy[:,1]+dy).astype(int),0,art.shape[0]-1),
                           np.clip((xy[:,0]+dx).astype(int),0,art.shape[1]-1)]
                      for dx in (-4,-2,0,2,4) for dy in (-3,0,3)])
    hue=gaussian_filter1d(np.median(swatches,axis=0),54,axis=0)
    base=np.array([153.,127.,138.])+v[...,None]**1.26*[39.,18.,17.]
    base+=.48*(hue-hue.mean(0))[...,None,:]
    # The five turns have broad unequal colour fields; soft occlusion in
    # the valleys stays on the surface when the directional light moves.
    phase=2*pi*(4.48*stream+.24*np.sin(6*v+4*u)+.10*np.sin(9*u-3*v))
    flank=(.5+.5*np.cos(phase))**1.45
    seam=np.exp(-((np.sin(.5*phase+.035))/.19)**2)
    strands=strand_detail(stream,v,861,79)
    tone=27*flank-13*seam+8.3*group+4.2*grain+10.5*strands
    tone+=8*np.sin(10*v+7*u)*np.sin(pi*v)
    rgb=base+tone[...,None]
    Image.fromarray(np.uint8(np.clip(rgb,0,255))).save(TEX/'yuexiao-mantle.jpg',quality=96,subsampling=0)
    Image.fromarray(surface_map(.76*grain+.21*group+.48*strands,flank-group*.14,v)).save(TEX/'yuexiao-mantle-finish.png')


class Groom:
    def __init__(self, atelier, body, fibres, filament):
        self.t = atelier
        self.body = body
        self.fibres = fibres
        self.filament = filament
        self.index = 0

    def sweep(self, pts, widths, thickness, facing, tile, roll=0.):
        seed = self.index + 127
        self.index += 1
        rng = np.random.default_rng(seed)
        phase = rng.uniform(0,2*pi)
        v = np.linspace(0,1,67)
        line = smooth_path(pts,v)
        turn = roll + .55*np.sin(1.65*pi*v+phase) + .16*np.sin(3*pi*v-phase)
        wide,out = frame(line,facing,turn)
        w = PchipInterpolator([0,.12,.37,.72,.89,.97,1],widths)(v)
        deep = thickness*np.interp(v,[0,.12,.60,.90,1],[.16,1,.82,.42,.012])
        # Fine perimeter locks consist entirely of cutout cards. The curved
        # body of each larger lock narrows into its feathered ends.
        major = max(widths) >= .105
        if major:
            count=5 if max(widths)>.175 else 4
            borders=np.r_[0.,np.cumsum(rng.uniform(.8,1.2,count))]
            borders=2*borders/borders[-1]-1
            q=np.linspace(0,2*pi,9)[None,:]
            for k,(lo,hi) in enumerate(zip(borders,borders[1:])):
                mid=(lo+hi)*.5
                a=np.linspace(0,rng.uniform(.88,1.),59)
                x=np.interp(a,v,w);z=np.interp(a,v,deep)
                ax=unit(np.stack([np.interp(a,v,col) for col in wide.T],axis=1))
                no=unit(np.stack([np.interp(a,v,col) for col in out.T],axis=1))
                release=np.clip((a/a[-1]-.42)/.58,0,1)
                taper=np.clip((1-a/a[-1])/.23,.008,1)
                drift=.075*np.sin(6*a+.87*k)*np.sin(pi*a)+mid
                lateral=drift*x+release**1.6*max(widths)*(mid*.68+rng.uniform(-.45,.45))
                offset=np.sqrt(np.maximum(0,1-drift**2))*.51*z+release**1.3*rng.uniform(-.032,.042)
                center=smooth_path(pts,a)+lateral[:,None]*ax+offset[:,None]*no
                radius=(hi-lo)*.54*x*taper
                thick=np.minimum(z*.66,radius*.72)
                p=center[:,None]+(radius[:,None]*np.cos(q))[...,None]*ax[:,None]
                p+=(thick[:,None]*np.sin(q))[...,None]*no[:,None]
                uv=strip_uv(tile,.5+.44*np.clip(mid+.5*(hi-lo)*np.cos(q),-1,1),a[:,None])
                self.t.grid(self.body,p,flip=True,uv=uv)
                # The outward half of this oval anchors the individual hairs.
                single_hairs(self.t,self.filament,p[:,:5],True,4,rng,.14)

        # A continuous cambered body carries the reflection. Reserve the
        # cutouts for the two feathered edges and split ends of each section.
        layers = [(-.84,.17,.18),(.80,.15,.22)] if major else [(0.,1.0,.50)]
        for i,(part,span,lift) in enumerate(layers):
            # Stratified ribbons wrap either side of the core. Vary the length,
            # curvature and direction of release independently at the ends.
            end = rng.uniform(.94,1.)
            h = v*end
            center = smooth_path(pts,h)
            ax = np.stack([np.interp(h,v,a) for a in wide.T],axis=1)
            no = np.stack([np.interp(h,v,a) for a in out.T],axis=1)
            hw = np.interp(h,v,w)
            depth = np.interp(h,v,deep)
            swing = np.sin(2.3*pi*v+phase+i)*(.12+.13*v)
            fan = np.clip((v-.61)/.39,0,1)**1.4
            finish = rng.uniform(-1,1)*fan*max(widths)*.68
            offset = (part+swing)*hw+finish
            rib = span*(hw + .11*max(widths)*fan)*(1+.09*np.sin(5*v+i))
            cols = np.linspace(-1,1,7)[None,:]
            x = offset[:,None]+rib[:,None]*cols
            # Arched sections, rather than a stack of flat planes, turn the
            # highlights toward and away from the light around each wave.
            convex = lift + .89*(1-cols**2)-(.78*part)*cols
            convex = convex + .13*np.cos(2.5*pi*cols + .65*np.sin(5*v[:,None]+i))
            relief = depth[:,None]*convex
            p = center[:,None]+x[...,None]*ax[:,None]+relief[...,None]*no[:,None]
            self.t.grid(self.fibres,p,uv=strip_uv(tile,(cols+1)/2,v[:,None]))


def crown_chart(sign):
    v,a=np.mgrid[0:53,0:89]/np.array([52,88])[:,None,None]
    a=a*pi
    b=v*(1.11+.99*(1-np.cos(a))/2+.38*np.sin(a)**2)+.0008
    # Turn the underside of the original cap down behind the temples and
    # in towards the nape. Its upper rows still sit under the swept fringe.
    def ease(x):
        x=np.clip(x,0,1)
        return x*x*(3-2*x)
    rear=ease((a-.72)/.93)
    lower=ease((v-.56)/.44)*rear
    b+=lower*(.18+.026*np.cos(7*a)+.014*np.sin(11*a))
    nx,ny,nz=np.sin(b)*np.sin(a),np.cos(b),-np.sin(b)*np.cos(a)
    axis=np.arctan2(nz,ny)
    bank=.035*np.exp(-((nx-.14)/.12)**2)-.012*np.exp(-(nx/.044)**2)
    bank*=np.clip(1.4-axis,0,1)
    bank+=.044*np.exp(-(nx/.13)**2-((axis+.23)/.37)**2)
    bank*=1-ease((axis+.04)/.22)
    bank+=.020*nx**3*np.cos(13*b-2.5*a-.8*np.sin(a))*np.sin(b)**2
    p=np.stack([sign*nx*(1.015+bank-.085*lower),19.98+ny*(1.43+bank),
                .48+nz*(1.07+bank)+.065*lower],-1)
    across=np.clip((axis+1.4)/4.15,0,1)
    along=np.arcsin(np.clip(nx,0,1))/(pi/2)
    # Flow downward through the underlayer instead of folding the strand map
    # back over itself on its way to the new hairline.
    comb=ease((v-.22)/.48)*ease((a-.52)/.70)
    across=across*(1-comb)+(.075+.84*a/pi+.03*v)*comb
    along=along*(1-comb)+(.13+.84*v)*comb
    return p,strip_uv(1,across,along)


def parted_crown(t, cap, fringe, groom):
    t.mode='head'
    for sign in (-1,1):
        p,uv=crown_chart(sign)
        t.grid(cap,p,flip=sign<0,uv=uv)
        nape_wisps(t,cap,p,uv,sign)
    v,u=np.mgrid[:76,:39]/np.array([75,38])[:,None,None]
    for side,sgn in enumerate((-1,1)):
        xy=wing_coordinates(side,v[:,0,None],u)
        x=(xy[...,0]-519)*.0233
        x=np.sign(x)*(np.minimum(abs(x),.82)+.76*np.maximum(0,abs(x)-.82))
        y=18.59+(135-xy[...,1])*.024
        fraction=np.clip(abs(x)/1.38,0,1)
        hull=.48-1.07*np.sqrt(np.maximum(.038,1-(x/1.015)**2-((y-19.98)/1.43)**2))
        face=.43-1.13*np.sqrt(np.maximum(.052,1-(x/1.18)**2-((y-19.98)/1.51)**2))-.48*fraction**3
        f=np.clip(u/.51,0,1)
        blend=1-(1-f*f*(3-2*f))*(1-fraction**3)
        # Lift the curtain at its root, then curl its outer lip back towards
        # the temple as on the concept. Only the last few fibres clear it.
        arch=np.sin(pi*u)*np.sin(pi*np.clip(v*1.35,0,1))
        bank=np.exp(-((abs(x)-.145)/.13)**2)*np.sin(u*pi*.82)
        flute=np.sin(pi*v)**.74*np.sin(pi*u)**.80
        relief=.018*np.cos(5.8*pi*u+.89*np.sin(4*v))+.007*np.cos(13*pi*u-.84*v)
        z=hull*(1-blend)+face*blend-.101*arch-.060*bank-.012-flute*relief
        y+=.052*arch+.037*bank
        uv=np.stack([(side+.002+.996*u)/2,.001+.998*v],-1)
        p=np.stack([x,y,z],-1)
        divide_surface(t,fringe,groom.filament,p,uv,side==0,11,1127+side,fringe=True)
        # Fine brow-grazing forelocks sit behind the swept wing at their
        # roots. Stagger the tips and let skin show between their ends.
        a=np.linspace(0,1,53)[:,None];c=np.linspace(-1,1,11)[None,:]
        for j,(mid,end,offset) in enumerate([(.147,.235,.095),(.239,.36,.022),(.35,.51,.064)]):
            end+=.034*side
            pts=np.array([[.053*sgn,20.73,-.422],[.109*sgn,20.58,-.513],
                          [mid*sgn,20.39,-.568],[(mid+.032)*sgn,20.18,-.577],
                          [(end-.024)*sgn,19.98+offset,-.558],[end*sgn,19.68+offset,-.519]])
            if side: pts[:,1]+=.037
            line=smooth_path(pts,a[:,0])
            width=np.interp(a[:,0],[0,.18,.45,.72,.91,1],[.018,.052,.063,.047,.019,.004])
            pos=np.broadcast_to(line[:,None,:],(len(a),c.size,3)).copy()
            pos[...,0]+=c*width[:,None]
            pos[...,2]+=.023*c**2 + .021*j
            pos[...,1]+=.041*c*sgn*a
            t.grid(groom.fibres,pos,uv=strip_uv(1,.5+c*.5,a))
        # Separate only the last hairs along the turned lip from the main
        # curtain; their roots share its sampled surface and colour.
        for k in range(3):
            f=np.linspace(.36+.035*k,1,48)[:,None]
            c=np.linspace(-1,1,7)[None,:]
            g=.90+.03*k+.095*c+.042*np.sin(f*pi*1.4)
            mm=np.stack(np.broadcast_arrays(np.clip(g,0,1)*(p.shape[1]-1),
                                            f*(p.shape[0]-1)),-1).astype('float32')
            wisp=cv2.remap(p.astype('float32'),mm,None,cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
            end=((f-f[0])/(1-f[0]))**2
            wisp[...,0]+=sgn*end*(.045+.032*k)
            wisp[...,1]-=end*(.045+.020*k)
            wisp[...,2]+=.012-.018*end
            t.grid(groom.fibres,wisp,flip=side==0,uv=strip_uv(1+(k%2),.5+.5*c,(f-f[0])/(1-f[0])))


def nape_wisps(t, cap, chart, uv, sign):
    # Short locks emerge from beneath the cap with its own UVs and finish
    # in slender, swept points against the neck on either side.
    h=np.linspace(0,1,30)[:,None]
    c=np.linspace(-1,1,7)[None,:]
    rng=np.random.default_rng(217+sign)
    for mid in np.linspace(.32,.69,19)+rng.uniform(-.005,.005,19):
        lane=mid+rng.uniform(.0045,.009)*c*(1-.985*h**2)+rng.uniform(.026,.052)*h**1.5
        grow=.86+.14*h
        pts=sample_chart(chart,grow,lane)
        radial=unit((pts-[0,19.98,.48])/[1.015,1.43,1.07])
        tangent=unit(pts-sample_chart(chart,grow-.012,lane))
        pts+=radial*(-.019+.028*h+.004*(1-c*c)*np.sin(pi*h))[...,None]
        pts+=tangent*(rng.uniform(.06,.17)*h**2)[...,None]
        pts[...,2]+=.095*h**2
        t.grid(cap,pts,flip=sign<0,uv=sample_chart(uv,grow,lane))
