"""Patterns registered to the approved front and three-quarter character sheet."""
from math import pi
import numpy as np
from PIL import Image
from build_lanxu import TEX
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import distance_transform_edt, gaussian_filter, gaussian_filter1d, map_coordinates, maximum_filter1d
from build_yuexiao import ART, Atelier, curve, jewel_leaf, lattice
from yuexiao_cloth import Patterns, FRONT_CLOTH, cut, front_skirt, rear_skirt, waist_jewel, front_xy

sin,cos=np.sin,np.cos


class SheetForm(Atelier):
    def stone(self,mat,center,scale):
        if not mat.name.startswith('Moon_') or max(scale)>.082:
            return super().stone(mat,center,scale)
        # Seed pearls project to a few pixels in the full-length camera.
        lat=np.linspace(.002,pi-.002,9)[:,None];a=np.linspace(0,2*pi,15)[None,:]
        xyz=np.stack(np.broadcast_arrays(sin(lat)*cos(a),cos(lat),sin(lat)*sin(a)),axis=-1)
        self.grid(mat,np.asarray(center)+xyz*np.asarray(scale))

    def measure_setting(self):
        # The pendant spans several overlapping cloth panels. Seat it on the
        # frontmost finished layer at every height, including below the waist.
        parts=[faces for mat,faces in self.parts.items()
               if mat.name in ('Moon_Petal','Moon_Brocade','Moon_PearlHem','Moon_Veil')]
        coords=np.asarray([v.co for v in self.m.vertices])
        tri=coords[np.vstack(parts)]
        return measured_front_layers(tri,self.torso)


def measured_front_layers(tri,torso):
    tri=tri[(tri[:,:,1].min(1)<16.5)&(tri[:,:,1].max(1)>9.5)&
            (abs(tri[:,:,0]).min(1)<1.35)&(tri[:,:,2].min(1)<-.1)]
    x0,y0,scale=-1.4,9.4,56
    grid=np.full((405,158),np.inf)
    for i in range(8):
        for j in range(8-i):
            p=tri[:,0]+(tri[:,1]-tri[:,0])*(i/7)+(tri[:,2]-tri[:,0])*(j/7)
            x,y=np.rint((p[:,:2]-[x0,y0])*scale).astype(int).T
            ok=(x>=0)&(x<grid.shape[1])&(y>=0)&(y<grid.shape[0])
            np.minimum.at(grid,(y[ok],x[ok]),p[ok,2])
    # Where two cut edges part, the mount continues over the body. A
    # nearest texel from the opposite fold can otherwise form a shelf.
    gy,gx=np.indices(grid.shape,dtype=float)
    h=y0+gy/scale;xx=x0+gx/scale
    width=abs(torso.surface(np.full_like(xx,pi/2),h.clip(13.4,18.55))[...,0])
    under=(h>=13.4)&(abs(xx)<width*.985)
    skin=torso.front_z(xx,h)-.025
    grid[under]=np.minimum(grid[under],skin[under])
    fill=distance_transform_edt(~np.isfinite(grid),return_distances=False,return_indices=True)
    grid=gaussian_filter(grid[tuple(fill)],1.1)
    def depth(x,y):
        xy=np.stack([(y-y0)*scale,(x-x0)*scale])
        return map_coordinates(grid,xy.reshape(2,-1),order=1,mode='nearest').reshape(x.shape)
    return depth


def top(t,pattern,silk,brocade,gold,silver,pearl):
    from yuexiao_jewels import link
    body=t.torso
    first=len(t.m.vertices)
    # One continuous cut on either side of the bias opening. Each horizontal
    # course follows the actual skin. There is no cup or horizontal shelf.
    top_edge=PchipInterpolator([0,.30,.60,.86,1.05,1.25,1.48,1.78,2.12],
        [18.42,18.38,18.24,17.99,17.54,17.12,16.80,16.64,16.47])
    lower_edge=PchipInterpolator([0,.28,.62,1.,1.38,1.77,2.12],
        [14.76,14.98,15.35,15.68,15.90,15.93,15.68])
    cross=PchipInterpolator([14.70,15.10,15.65,16.17,16.64,17.15,17.55,17.99,18.42],
        [-.13,-.21,-.25,-.10,.12,.32,.40,.30,.0])
    for j,s in enumerate((-1,1)):
        v,u=lattice(72,78);az=2.12*u
        y=lower_edge(az)+(top_edge(az)-lower_edge(az))*v
        window=np.clip((y-15.65)/(17.34-15.65),0,1)
        gap=.171*sin(pi*window)**.92
        a=s*az+(cross(y)+s*gap)*(1-u)**1.6
        # A slight longitudinal turn of the silk breaks the highlight at the
        # outer edges while leaving the central chest contour undisturbed.
        flute=sin(pi*u)**.72*sin(pi*v)**.72
        allowance=.059+.032*flute*cos(2*pi*(2.3*u-.62*v))+.010*flute*cos(2*pi*(4.2*u-.75*v))
        points=body.surface(a,y,allowance)
        span=(2.545+.08*points[...,2])/(1604.7*.08)
        py=163+(238-(points[...,1]-1.18/.08+1.17354)/span)/1.27
        cx=np.interp(py,[160,280,350],[525,531.7,533.5])
        px=cx+points[...,0]/(1.27*span)
        # Shade the actual location on each independently cut bodice piece.
        xy=np.stack([px,py],axis=-1)
        uv=pattern.chart(xy,FRONT_CLOTH[j])
        t.grid(brocade,points,flip=s>0,uv=uv)
        t.wire(silver,points[-1],.011,7)
        t.wire(silver,points[0],.014,7)
        if s<0:
            t.wire(silver,points[:,0],.014,7)
        else:
            visible=gap[:,0]>.003
            t.wire(silk,points[visible,0],.012,7)
    # A bias-cut champagne modesty inset sits behind the short almond opening.
    inset=t.material('IllusionBias','silk.jpg',alpha=.51)
    v,u=lattice(29,16);y=15.61+1.78*v
    a=cross(y)+(2*u-1)*(.026+.178*sin(pi*v)**.91)
    t.grid(inset,body.surface(a,y,.025),flip=True)
    # Open-back halter straps are sewn to the same body surface as the front.
    for s in (-1,1):
        v,u=lattice(64,15)
        y=18.41-3.58*v
        mid=2.63-.53*sin(pi*v)+.46*v*v
        half=.27+.145*sin(pi*v)-.19*v**2
        a=s*(mid+(2*u-1)*half)
        p=body.surface(a,y,.073)
        sheet=cut([(1079,147),(1072,170),(1069,199),(1073,228),(1082,258),(1093,289)],
                  [(1090,148),(1084,169),(1080,196),(1083,219),(1094,249),(1097,288)],64,15)
        uv=pattern.chart(sheet)
        t.grid(brocade,p,flip=s<0,uv=uv)
        t.wire(silver,p[:,0],.012,7);t.wire(silk,p[:,-1],.015,7)
    for s in (-1,1):
        v,u=lattice(18,55);a=s*(.020+u*(pi-.020))
        y=18.235+(.16+.33*(1-np.exp(-(a/.65)**2)))*v+.030*(1-cos(a))
        collar=body.surface(a,y,.058+.024*sin(pi*v))
        swatch=cut([(522,162),(518,158),(516,152),(511,146)],
                   [(526,162),(524,156),(521,151),(514,146)],18,55)
        t.grid(brocade,collar,flip=s>0,uv=pattern.chart(swatch))
        t.wire(silver,collar[-1],.013,7);t.wire(silver,collar[:,0],.009,6)
    c=body.surface(0.,18.30,.075)
    up=np.array([0.,1.,0.]);right=np.array([1.,0.,0.])
    for s in (-1,1):
        p=c+[.090*s,.025,-.025]
        link(t,gold,p,right,up,.068,.050,.010)
        t.stone(pearl,p+[0,0,-.014],(.046,.035,.027))
    link(t,gold,c+[0,0,-.036],right,up,.034,.032,.008)
    tail=curve([c,c+[.010,-.077,-.027],c+[.017,-.16,-.035]],np.linspace(0,1,13))
    t.wire(gold,tail,.006,5)
    t.stone(pearl,tail[-1],(.015,.024,.014))
    c=body.surface(pi,14.92,.09)
    t.stone(gold,c,(.15,.11,.040));t.stone(pearl,c+[0,0,.034],(.07,.08,.045))
    for s in (-1,1):
        for h,dx in ((.20,.13),(-.04,.22)):
            tip=c+[s*dx,h,.08]
            jewel_leaf(t,pearl,gold,c,tip,[1,0,0],.051,.024)
        q=np.linspace(0,1,25)
        chain=c+np.stack([s*(.09+.08*sin(pi*q)), -.60*q, .033+.10*q],axis=-1)
        t.wire(gold,chain,.012,6);t.stone(pearl,chain[-1],(.037,.061,.031))
    body.bind_cloth(t.m.vertices[first:])


def fit_streamer(panel, skin, bezel, shoulder, wrist, side, short):
    """Seat the silk on the clasp, then clear the measured arm section at each fold."""
    axis=np.array([.811*side,-.585,0.])
    axis/=np.linalg.norm(axis)
    outward=np.array([-side*axis[1],side*axis[0],0.])
    front=np.array([0.,0.,-1.])
    v=np.linspace(0.,1.,len(panel))
    u=np.linspace(0.,1.,panel.shape[1])
    # The small loop and the long fall are sewn to neighbouring arcs of the
    # lower rim. Preserve each cut edge's orientation as it leaves the metal.
    phi=(.74*pi if short else .45*pi)+(u-.5)*(.27*pi if short else .36*pi)
    root=np.stack([np.interp(phi,np.linspace(0,2*pi,len(bezel)),xyz) for xyz in bezel.T],axis=-1)
    if np.linalg.norm(root[::-1]-panel[0]) < np.linalg.norm(root-panel[0]):
        root=root[::-1]
    fade=np.clip(1-v/(.26 if short else .115),0,1)
    result=panel+(fade*fade*(3-2*fade))[:,None,None]*(root-panel[0])

    # Only the arm on this side can constrain the cut. Keep the original
    # twist of a row by moving both hems and its centre by the same amount.
    skin=skin[(side*skin[:,:,0]).min(1)>1.45]-shoulder
    lateral=skin@outward
    skin=skin[(lateral.min(1)<1.15)&(lateral.max(1)>-1.15)]
    # The trailing edge passes the fingertips. Allow room for the hand to
    # turn about the wrist while the loose silk follows the forearm bone.
    pivot=wrist-shoulder
    hand=skin[((skin-pivot)@axis).min(1)>-.08]
    if not short and len(hand):
        local=hand-pivot
        swept=[skin]
        for bend_axis in (axis,front,outward):
            for angle in (-.48,.48):
                swept.append(pivot+local*cos(angle)+np.cross(bend_axis,local)*sin(angle)
                             +(local@bend_axis)[...,None]*bend_axis*(1-cos(angle)))
        skin=np.concatenate(swept)
    station=skin@axis
    smin,smax=station.min(1),station.max(1)
    lower=np.clip((v-.18)/.22,0,1) if not short else np.zeros_like(v)
    wrist_turn=np.clip((v-.37)/.21,0,1) if not short else np.zeros_like(v)
    directions=outward+(.47*(1-lower)+1.05*wrist_turn**2*(3-2*wrist_turn))[:,None]*front
    directions/=np.linalg.norm(directions,axis=1,keepdims=True)
    required=np.zeros_like(v)
    for j,(row,direction) in enumerate(zip(result-shoulder,directions)):
        along=row@axis
        lo,hi=along.min()-.012,along.max()+.012
        active=(smin<=hi)&(smax>=lo)
        if not active.any():
            continue
        faces,heights=skin[active],station[active]
        samples=[faces[(heights>=lo)&(heights<=hi)]]
        for a,b in ((0,1),(1,2),(2,0)):
            for plane in (lo,hi):
                cross=(heights[:,a]<plane)!=(heights[:,b]<plane)
                t=(plane-heights[cross,a])/(heights[cross,b]-heights[cross,a])
                samples.append(faces[cross,a]+t[:,None]*(faces[cross,b]-faces[cross,a]))
        section=np.concatenate(samples)
        if len(section):
            clearance=.033+.067*lower[j]
            required[j]=max(0.,(section@direction).max()+clearance-(row@direction).min())
    # Feather a correction into the neighbouring folds without reducing
    # the clearance at a tight turn. The root stays seated on the clasp.
    drift=np.maximum(required,gaussian_filter1d(maximum_filter1d(required,7),2.0))
    enter=np.clip(v/(.055 if short else .023),0,1)
    drift*=enter*enter*(3-2*enter)
    return result+(directions*drift[:,None])[:,None,:]


def streamers(t,pattern,gauze,silk,silver,gold,pearl):
    from yuexiao_jewels import articulated_chain, stone_cut
    enamel=t.material('LilacEnamel','pattern.jpg')
    setting=t.material('CuffSetting','arm-clasp.jpg')
    cabochon=t.material('CuffCrystal','arm-clasp.jpg')
    wrist_stone=t.material('BraceletCrystal','jewels.jpg')
    with Image.open(ART) as art:
        art.crop((418,217,452,257)).resize((238,280),Image.BICUBIC).convert('RGB').save(TEX/'yuexiao-arm-clasp.jpg',quality=98,subsampling=0)
    cursor=0;arm_faces=[];nail_faces=[]
    for mat in t.m.materials:
        count=mat.vertex_count//3
        if 'Skin' in mat.name:arm_faces.extend(t.m.faces[cursor:cursor+count])
        if mat.name=='Up_Nail':nail_faces.extend(t.m.faces[cursor:cursor+count])
        cursor+=count
    points=np.asarray([vertex.co for vertex in t.m.vertices])
    skin=points[np.asarray(arm_faces)]
    sleeve_skin=points[np.asarray(arm_faces+nail_faces)]
    for s in (-1,1):
        t.mode='arm+' if s>0 else 'arm-'
        axis=np.array([.811*s,-.585,0]);out=np.array([.585*s,.811,0]);z=np.array([0,0,1.])
        c=np.array([2.39*s,16.83,.83])
        def circlet(center,angles):
            # Take an oblique section through the standing mesh, giving the
            # band a real oval wrist/arm section instead of a circular hoop.
            axes=np.stack([out,z,axis],axis=1)
            tri=(skin-center)@axes
            tri=tri[(tri[:,:,2].min(1)<0)&(tri[:,:,2].max(1)>=0)&
                    (np.abs(tri[:,:,0]).min(1)<.68)&(np.abs(tri[:,:,1]).min(1)<.7)]
            ends=[]
            for j in range(3):
                p,q=tri[:,j],tri[:,(j+1)%3]
                k=np.flatnonzero((p[:,2]<0)!=(q[:,2]<0))
                f=-p[k,2]/(q[k,2]-p[k,2])
                ends.extend(zip(k,p[k,:2]+(q[k,:2]-p[k,:2])*f[:,None]))
            seg=np.array([p for k,p in sorted(ends,key=lambda hit:hit[0])]).reshape(-1,2,2)
            local=(seg.min(axis=(0,1))+seg.max(axis=(0,1)))*.5
            a=seg[:,0]-local;e=seg[:,1]-seg[:,0]
            ray=np.stack([cos(angles),sin(angles)],axis=-1)[:,None,:]
            def cross(p,q):return p[...,0]*q[...,1]-p[...,1]*q[...,0]
            with np.errstate(divide='ignore',invalid='ignore'):
                den=cross(ray,e);dist=cross(a,e)/den;f=cross(a,ray)/den
            r=np.min(np.where((dist>0)&(f>=0)&(f<=1),dist,np.inf),axis=1)
            if not np.isfinite(r).all():raise ValueError('Unclosed skin section at cuff')
            p=local+(r+.019)[:,None]*ray[:,0]
            return center+p[:,0,None]*out+p[:,1,None]*z
        ring=circlet(c,np.linspace(0,2*pi,59))
        t.wire(silver,ring-.024*axis,.015,7)
        t.wire(gold,ring+.020*axis,.017,7)
        theta=2*pi*54/58
        n=cos(theta)*out+sin(theta)*z
        cp=ring[54].copy()+.050*n
        def cuff_surface(turn,axial,rise):
            # A saddle follows the cut arm section. The near and far rims
            # turn in different directions over the round of the bicep.
            knots=np.linspace(0,2*pi,len(ring))
            path=np.stack([np.interp(turn%(2*pi),knots,r) for r in ring.T],axis=-1)
            norm=cos(turn)[...,None]*out+sin(turn)[...,None]*z
            return path+axial[...,None]*axis+(rise+.038)[...,None]*norm
        # A pierced, pearl-set clasp on the outside of the bicep, visible
        # from both the front and rear quarter. The central opening exposes the arm.
        v,u=lattice(7,64);phi=2*pi*u
        rr=.71+.29*v
        top=cuff_surface(theta+.68*rr*cos(phi),.341*rr*sin(phi),.029*sin(pi*v)+.016)
        xy=np.stack([435.0+8.1*rr*cos(phi),235.1+10.6*rr*sin(phi)],axis=-1)
        t.grid(setting,top,uv=(xy-[418,217])/[34,40])
        t.wire(gold,top[0],.010,6);t.wire(silver,top[-1],.011,6)
        for ang in [.32,1.0,1.56,2.21,2.84,4.03,5.44]:
            at=cuff_surface(theta+.61*cos(ang),.311*sin(ang),np.array(.045))
            t.stone(pearl,at,(.021,.030,.022))
        rr,turn=lattice(13,40);turn*=2*pi
        disk=cuff_surface(theta+.49*rr*cos(turn),.244*rr*sin(turn),.014+.032*(1-rr*rr))
        sample=np.stack([435.0+5.1*rr*cos(turn),235.1+7.3*rr*sin(turn)],axis=-1)
        t.grid(cabochon,disk,uv=(sample-[418,217])/[34,40])
        t.wire(gold,disk[-1],.009,6)
        # The enamel leaf and the little folded ribbon have independent
        # roots below the hoop instead of growing from the upper-arm axis.
        xy=cut([(432,232),(426,230),(419,226),(414,218),(410,204)],
               [(437,229),(435,221),(427,214),(416,211),(410,204)],28,13)
        uv=pattern.chart(xy);vv,uu=lattice(28,13)
        pp=cp+(435-xy[...,0:1])*.031*out+(xy[...,1:2]-235)*.014*axis
        pp+=(.042+.078*sin(pi*uu)*sin(pi*vv))[...,None]*n
        t.grid(enamel,pp,uv=uv);t.wire(silver,pp[:,0],.007,6)
        t.wire(silver,pp[:,-1],.006,6)
        shoulder=np.array(t.m.bones[t.bones[('左' if s>0 else '右')+'腕']].location)
        elbow=np.array(t.m.bones[t.bones[('左' if s>0 else '右')+'ひじ']].location)
        wrist=np.array(t.m.bones[t.bones[('左' if s>0 else '右')+'手首']].location)
        down=1.15-np.arctan2(shoulder[1]-elbow[1],abs(elbow[0]-shoulder[0]))
        angle=-s*down
        rot=np.array([[cos(angle),-sin(angle),0],[sin(angle),cos(angle),0],[0,0,1]])
        cuff_pos=(cp-shoulder)@rot.T+shoulder
        # Trace the falling length in the relaxed pose, then rotate back to
        # the PMX bind pose. Normal arm/elbow weights still drive the silk.
        for short in [False,True]:
            if short:
                left=[(430,246),(425,253),(413,264),(405,272),(403,279),(408,283),(414,280),(423,269)]
                right=[(438,244),(440,251),(437,256),(433,262),(430,267),(426,274),(424,274),(423,269)]
            else:
                left=[(429,246),(420,269),(412,290),(401,310),(382,324),(366,335),(360,352),
                      (361,366),(348,375),(327,385),(322,403),(323,419),(328,433),(327,447),(317,462),
                      (309,477),(306,493),(306,515),(311,533),(321,548),(323,561),(322,569)]
                right=[(437,247),(430,270),(422,295),(413,315),(402,332),(395,348),(386,359),
                       (370,371),(356,375),(350,387),(347,408),(345,425),(343,443),(339,454),(333,462),
                       (328,477),(327,496),(327,515),(328,532),(329,549),(329,559),(322,569)]
            if s>0:
                def opposite(line):
                    return [(float(2*np.interp(y,[240,380,500,570],[519.6,509.,496.,491.])-x),
                             240+(y-240)*.951) for x,y in line]
                left,right=opposite(left),opposite(right)
            xy=cut(left,right,71,19);vv,uu=lattice(71,19)
            uv=pattern.chart(xy,chiffon=True)
            atlas_pivot=np.array([434.7 if s<0 else 604.5,235.2])
            shift=cuff_pos-front_xy(*atlas_pivot,cuff_pos[2])
            drape=(.25*sin(3.5*pi*vv+.3)-.26*vv+.23*vv*sin(pi*uu))
            if short:drape=.13*sin(pi*vv)-.12*vv
            zz=cuff_pos[2]+drape+.17*(2*uu-1)*sin(3.3*pi*vv)
            posed=front_xy(xy[...,0],xy[...,1],zz)
            posed+=shift*(1-.28*vv[...,None])
            # Clear the front of the bicep before the ribbon turns back
            # toward the wrist. Its small upper loop sits on the bezel.
            posed[...,2]-=(.45 if short else .53)*np.sin(pi*np.clip(vv/(1 if short else .55),0,1))**.75
            posed[...,0]+=s*(.092 if short else .125)*np.sin(pi*np.clip(vv/.48,0,1))
            pp=(posed-shoulder)@rot+shoulder
            pp=fit_streamer(pp,sleeve_skin,top[-1],shoulder,wrist,s,short)
            t.grid(gauze,pp,uv=uv)
            t.wire(silver,pp[:,0],.007,6);t.wire(silk,pp[:,-1],.008,6)
            if not short:
                end=pp[-1,9]
                chain=end+np.linspace(0,.42,16)[:,None]*(np.array([0.,-1,0])@rot)
                t.wire(gold,chain,.009,6)
                for j,rad in [(1,.058),(7,.035),(15,.049)]:
                    t.stone(pearl,chain[j],(rad,rad*1.27,rad*.84))
        # Fine wrist chain and two drop pearls, as in the front view.
        wc=np.array([6.08*s,14.24,.86]);tt=np.linspace(0,2*pi,39)
        bracelet=circlet(wc,tt)
        for d in [-.029,.029]:
            t.wire(gold,bracelet+d*axis,.010,6)
        for j in range(0,38,2):
            side=cos(tt[j])*out+sin(tt[j])*z
            around=-sin(tt[j])*out+cos(tt[j])*z
            stone_cut(t,wrist_stone,bracelet[j]+.013*side,around,axis,side,
                      (.043,.027,.018),'wrist',np.array([369.,426.]),[1.7,1.1])
        forearm=wc-1.01*axis
        fine=circlet(forearm,tt)+.080*cos(tt+.5)[:,None]*axis
        articulated_chain(t,gold,fine,z,.061,.006)
        q=np.linspace(0,1,25)
        line=fine[28]+(.47*q)[:,None]*axis+(.11*sin(pi*q))[:,None]*out-.056*q[:,None]*z
        articulated_chain(t,silver,line,-z,.078,.006)
        sweep=curve([fine[18],fine[18]+.19*axis+.043*out,line[12]],q)
        articulated_chain(t,gold,sweep,-z,.071,.006)
        for i in (4,11,18,24):
            r=.043 if i==24 else .026
            stone_cut(t,wrist_stone,line[i],out,-axis,-z,(r,r*1.55,r*.76),
                      'wrist',np.array([403.,409.]),[1.3,2.1],True)
    t.mode='body'


def dressed(t,m):
    from yuexiao_jewels import articulated_chain, link
    silk,petal,gauze,gold,silver,pearl=m
    pattern=Patterns()
    brocade=t.material('Brocade','pattern.jpg')
    veil=t.material('Veil','organza.png',alpha=.48)
    top(t,pattern,silk,brocade,gold,silver,pearl)
    skirt_start=len(t.m.vertices)
    front_skirt(t,pattern,silk,petal,veil,silver)
    rear_skirt(t,pattern,silk,petal,veil,silver)
    t.torso.bind_cloth(t.m.vertices[skirt_start:],waist_transition=(13.23,13.78))
    chain_start=len(t.m.vertices)
    for s in (-1,1):
        a=np.linspace(0,1.46,54)*s
        h=15.03+.89*(abs(a)/1.46)**1.75
        t.wire(gold,t.torso.surface(a,h,.088),.010,6)
        for j in (6,12,19):t.stone(pearl,t.torso.surface(a[j],h[j],.10),(.047,.049,.035))
        # The chain rises from the setting to the underside of the bodice,
        # leaving an actual wedge of skin visible above the basque.
        a=s*np.linspace(.17,1.46,51)
        h=15.01+.91*(sin(abs(a))/sin(1.46))**1.42
        p=t.torso.surface(a,h,.095)
        t.wire(gold,p,.010,7)
        t.stone(pearl,p[-1],(.044,.059,.038))
        for j in (7,15,23,31,39):t.stone(pearl,p[j],(.035,.039,.025))
        # In the rear view the crossed straps end in a curved sash with a
        # side clasp. Its pearl sprigs and chain sit outside the rear gores.
        v,u=lattice(16,64);a=s*(1.43+(pi-1.43)*u)
        h=14.68+.23*sin(pi*u)+.11*u+(.29+.08*sin(2*pi*u))*v
        band=t.torso.surface(a,h,.064+.016*(1-v)+.008*cos(3*pi*v))
        t.grid(silk,band,flip=s<0)
        t.wire(silver,band[-1],.014,7);t.wire(gold,band[0],.013,7)
        angle=s*2.08
        c=t.torso.surface(angle,15.04,.097)
        n=np.array([sin(angle),0,-cos(angle)]);tan=np.array([cos(angle),0,sin(angle)]);up=np.array([0,1,0])
        brooch=c+.032*n
        for dx,dy,r in [(0,.12,.051),(-.105,.092,.028),(.082,.136,.026),(.022,-.01,.042),(-.035,-.113,.029)]:
            bud=brooch+dx*tan+dy*up
            t.wire(gold,curve([brooch-.10*up,bud-.039*up,bud],np.linspace(0,1,12)),.009,6)
            link(t,gold,bud,tan,up,r*1.12,r*1.27,.007)
            t.stone(pearl,bud+.018*n,(r,r*1.18,r))
        for sign in (-1,1):
            base=brooch-.05*up
            tip=base+.149*sign*tan-.16*up+.021*n
            jewel_leaf(t,pearl,gold,base,tip,tan,.033,.017,openwork=True)
        q=np.linspace(0,1,50);a=s*(2.08+.56*q)
        h=15.04-.91*q-.24*sin(pi*q)
        drop=t.torso.surface(a,h,.087+.15*q)
        drop+=(c-drop[0])*(1-q[:,None])
        articulated_chain(t,gold,drop,n,.064,.007)
        for j in (9,21,33,47):t.stone(pearl,drop[j],(.027,.041,.026))
    t.torso.bind_cloth(t.m.vertices[chain_start:])
    t.jewel_surface=t.measure_setting()
    setting_start=len(t.m.vertices)
    waist_jewel(t,gold,silver,pearl)
    t.torso.bind_cloth(t.m.vertices[setting_start:],waist_transition=(13.23,13.78))
    streamers(t,pattern,gauze,silk,silver,gold,pearl)
    pattern.save()


def waves(t,hair,groom):
    from yuexiao_hair import mantle, strip_uv
    t.mode='hair'
    # The nape ends inside the inner sections, above the first open curl.
    v,u=lattice(35,64);a=2*pi*u
    w=(.75+.12*sin(pi*v))*(1-.992*v**2)
    p=np.stack([w*sin(a),20.12-3.77*v,1.07+.65*v+.39*(1-.992*v*v)*cos(a)],-1)
    t.grid(hair,p,uv=strip_uv(0,.5+.49*sin(a),v))
    mantle(t,t.material('Mantle','mantle.jpg',hair=True),groom.fibres,groom.filament)
    for sign in (-1,1):
        # Trace the two prominent side sweeps from the three-quarter view.
        # One leaves an open loop near the shoulder blade. The longer sweep
        # returns behind it and rolls back upwards just above the belt.
        outer=[(.63,20.50,.75),(.92,19.88,.82),(1.01,19.19,1.03),
               (1.14,18.50,1.37),(1.30,17.97,1.96),(1.51,17.65,2.37),
               (1.64,17.16,2.63),(1.65,16.65,2.70),(1.49,16.29,2.60),
               (1.30,16.21,2.42),(1.20,16.40,2.29)]
        lower=[(.55,20.48,.91),(.80,19.84,1.22),(1.01,19.05,1.38),
               (1.07,18.28,1.55),(1.23,17.62,1.89),(1.47,17.07,2.22),
               (1.59,16.52,2.66),(1.46,15.90,2.90),(1.17,15.27,2.73),
               (1.07,14.67,2.30),(1.24,14.15,2.13),(1.45,13.77,2.35),
               (1.56,13.63,2.69),(1.50,13.76,2.94),(1.34,14.01,3.00)]
        for j,path in enumerate([outer,lower]):
            pts=np.array(path);t0=np.linspace(0,1,len(pts))
            pts[:,0]=sign*(pts[:,0]+.08*sign*sin(4*t0)*t0)
            pts[:,1]+=.28*sign*t0**2
            pts[:,2]+=.12*sign*t0
            groom.sweep(pts,[.026,.155,.236,.213,.137,.061,.004],.094,
                        (sign*.84,0,.58),2 if j==0 else 1,sign*(.09+.34*j))
            # An escaped filament shares the root, then describes a longer
            # ellipse at the released end. Do not multiply the whole curl.
            fly=pts.copy()
            fly[:,0]+=sign*(.12*sin(pi*t0)+.19*t0**2)
            fly[:,1]+=.22*sin(2.35*pi*t0)*t0
            fly[:,2]+=.16*t0+.22*sin(2*pi*t0)*t0
            groom.sweep(fly,[.004,.021,.035,.039,.027,.012,.001],.011,
                        (sign*.57,0,.82),2)
        # A short inner side-lock gives the ear a soft border in profile.
        short=np.array([(.81,20.30,.11),(.98,19.98,.13),(.96,19.57,.17),
                        (.88,19.20,.16),(.85,18.89,.09),(.88,18.66,-.08),(.96,18.56,-.16)])
        short[:,0]*=sign
        groom.sweep(short,[.025,.115,.16,.105,.072,.031,.002],.053,(sign*.86,0,-.42),1)
        # Face-framing lengths hug the cheek, break over the clavicle and
        # taper over the bodice. The inner and outer tips return differently.
        pts=np.array([(.75,20.36,-.025),(.95,19.91,-.075),(.94,19.40,-.17),
                      (.85,18.94,-.25),(.88,18.50,-.34),(1.03,18.08,-.42),
                      (1.23,17.78,-.65),(1.28,17.48,-.81),(1.19,17.19,-1.02),
                      (1.04,16.96,-1.15),(.96,16.69,-1.22),(1.00,16.43,-1.25),
                      (1.10,16.28,-1.22)])
        h=np.linspace(0,1,len(pts))
        pts[:,0]=sign*(pts[:,0]+.083*sign*sin(1.4*pi*h))
        pts[:,1]+=.19*sign*h*h
        groom.sweep(pts,[.025,.108,.186,.166,.098,.047,.003],.084,(sign*.32,0,-1),2,sign*.22)
        for j in range(2):
            fine=pts.copy()
            fine[:,0]+=sign*((-.12 if j==0 else .13)*sin(pi*h)+(.09-.23*j)*h**2)
            fine[:,1]+=(.33*j-.15)*h*h
            fine[:,2]-=.032+.028*j
            groom.sweep(fine,[.008,.043,.056-.02*j,.044,.030,.012,.001],.018,
                        (sign*.21,0,-1),1+j)
    t.mode='head'
