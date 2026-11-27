"""Cut the visible silk, chiffon and metalwork from the approved costume sheet."""
from math import pi
import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
from build_lanxu import TEX, shell
from build_yuexiao import ART, curve, lattice
from yuexiao_torso import centre, smooth


def cut(left, right, rows=64, cols=28):
    v, u = lattice(rows, cols)
    a, b = (curve(line, v[:, 0])[:, None] for line in (left, right))
    return a * (1-u[..., None]) + b * u[..., None]


def outline(xy):
    return np.concatenate([xy[:, 0], xy[-1, 1:], xy[-2::-1, -1], xy[0, -2:0:-1]])


class Patterns:
    def __init__(self):
        self.art = np.array(Image.open(ART).convert('RGB'))
        self.atlas = Image.new('RGB', (2048, 2048))
        self.organ = Image.new('RGBA', (2048, 2048), (223,211,229,0))
        self.used = 0

    def chart(self, xy, visible=None, holes=(), chiffon=False, pale_silk=False):
        # Each chart contains one material only. Hidden weave is continued
        # from the nearest surviving section of this same piece.
        tw, th = 512, 256
        if self.used >= 32:
            raise ValueError('Too many cloth charts')
        x0, y0 = np.floor(xy.min(axis=(0, 1)) - 4).astype(int)
        x1, y1 = np.ceil(xy.max(axis=(0, 1)) + 5).astype(int)
        origin = np.array([x0, y0])
        art = self.art[y0:y1, x0:x1]
        def polygon(points):
            return np.rint(np.asarray(points)-origin).astype('int32')
        mask = np.zeros(art.shape[:2], 'uint8')
        cv2.fillPoly(mask, [polygon(visible if visible is not None else outline(xy))], 255)
        for poly in holes:
            cv2.fillPoly(mask, [polygon(poly)], 0)
        if pale_silk:
            # The basque passes in front of both hair and grey backdrop.
            # Reject those occluders before extending silk into the seam.
            rgb=art.astype(int)
            mask[(rgb.max(axis=2)<158) | (rgb[...,0]-rgb[...,2]>28)]=0
        mask = cv2.erode(mask, np.ones((3, 3), 'uint8'))
        if not np.any(mask):
            raise ValueError('Empty cloth patch at ' + str(origin))
        dist, nearest = distance_transform_edt(mask == 0, return_indices=True)
        clean = art[tuple(nearest)]
        smooth = cv2.GaussianBlur(clean, (0, 0), 3.5)
        blend = np.clip((dist-1)/6, 0, 1)[..., None]
        clean = np.uint8(clean*(1-blend) + smooth*blend)
        f = cv2.resize((xy-origin).astype('float32'), (tw-6, th-6), interpolation=cv2.INTER_CUBIC)
        rgb = cv2.remap(clean, f[...,0], f[...,1], cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        if not chiffon:
            rgb=cv2.addWeighted(rgb,1.29,cv2.GaussianBlur(rgb,(0,0),2.6),-.29,0)
        if chiffon:
            # Separate thread colour and optical coverage. A dark fold in
            # the source increases transparency instead of painting grey
            # studio pixels onto the arm when it moves across the body.
            linear = ((rgb.astype(float)/255 + .055)/1.055)**2.4
            observed=linear @ np.array([.2126,.7152,.0722])
            intrinsic=np.array([.77,.68,.83])
            opacity=np.clip((observed-.144)/(.71-.144),.18,.78)
            estimate=(linear-.144*(1-opacity[...,None]))/opacity[...,None]
            fibre=np.clip(.73*intrinsic+.27*estimate,.16,.96)
            rgb=np.uint8(np.clip((1.055*fibre**(1/2.4)-.055)*255,0,255))
            alpha=np.uint8(255*np.clip(opacity/.58,.28,1))
        rgb = cv2.copyMakeBorder(rgb, 3, 3, 3, 3, cv2.BORDER_REPLICATE)
        x, y = self.used % 4 * tw, self.used // 4 * th
        self.used += 1
        self.atlas.paste(Image.fromarray(rgb), (x, y))
        if chiffon:
            tile=Image.fromarray(rgb)
            tile.putalpha(Image.fromarray(cv2.copyMakeBorder(alpha,3,3,3,3,cv2.BORDER_REPLICATE)))
            self.organ.paste(tile,(x,y))
        v, u = lattice(xy.shape[0]-1, xy.shape[1]-1)
        return np.stack([(x+3.5+(tw-7)*u)/2048, (y+3.5+(th-7)*v)/2048], axis=-1)

    def save(self):
        self.atlas.save(TEX/'yuexiao-pattern.jpg', quality=98, subsampling=0)
        self.organ.save(TEX/'yuexiao-organza.png')
        from yuexiao_finish import bake_finishes
        bake_finishes(TEX)


# Front bodice. The hair falls across both outside edges of the sample.
FRONT_CLOTH = [
 [(523,167),(530,171),(541,185),(538,199),(529,212),(521,231),(517,247),(521,253),(513,257),(498,259),(496,264),(475,256),(480,247),(484,235),(482,225),(477,215),(475,209),(477,201),(491,190),(507,180)],
 [(544,189),(555,194),(565,199),(574,205),(575,211),(570,218),(564,229),(564,236),(569,231),(574,223),(581,218),(582,232),(579,245),(575,257),(562,264),(551,270),(549,260),(538,259),(534,249),(527,252),(532,239),(539,222),(544,203)]
]


def front_xy(px, py, z):
    """Register drafted stations in the frontal fitting view, compensating
    the perspective change across the depth of a folded piece."""
    px, py, z = np.broadcast_arrays(px, py, z)
    center = np.interp(py, [160, 280, 350, 500], [525, 531.7, 533.5, 535])
    span = (2.545 + .08*z) / (1604.7 * .08)
    x = (px-center) * 1.27 * span
    y = 1.18/.08 - 1.17354 + (430 - 192 - (py-163)*1.27)*span
    return np.stack([x, y, z], axis=-1)


# The rails go from the outer edge to the inner edge. Each side follows
# its own drawing; the figure in the sheet turns slightly at the waist.
FRONT = {
 'train': [
 ([(471,334),(449,364),(423,403),(402,437),(386,460),(392,470),(405,479),(401,491),(402,500),(394,515),(397,525),(417,533),(431,542),(430,549),(420,557),(414,563)],
  [(486,333),(469,365),(454,398),(451,434),(447,461),(444,480),(441,493),(440,505),(441,518),(441,531),(440,541),(437,548),(433,554),(426,559),(419,562),(414,563)]),
 ([(577,332),(598,360),(617,390),(634,424),(650,450),(655,462),(651,469),(641,476),(639,484),(642,495),(646,509),(641,516),(622,523),(612,532),(609,541),(613,550),(620,557)],
  [(565,333),(579,368),(590,400),(594,433),(596,461),(596,476),(596,484),(598,494),(600,507),(601,521),(601,532),(602,539),(604,545),(608,550),(612,553),(616,555),(620,557)])],
 'ivoryWing': [
 ([(508,305),(495,327),(478,359),(459,391),(446,428),(440,459),(444,474),(449,479),(455,484),(456,490),(454,498)],
  [(524,305),(519,332),(509,360),(507,395),(504,431),(500,455),(493,469),(484,475),(467,481),(455,487),(454,498)]),
 ([(548,306),(564,331),(578,360),(594,389),(605,422),(614,454),(616,470),(613,478),(611,483),(615,486),(615,495)],
  [(535,306),(542,331),(549,364),(557,397),(568,431),(580,456),(583,470),(588,478),(602,482),(612,485),(615,495)])],
 'wrap': [
 ([(504,292),(489,312),(468,337),(450,372),(431,410),(416,449),(401,480)],
  [(531,293),(534,323),(531,357),(524,391),(504,421),(462,448),(401,480)]),
 ([(555,292),(570,311),(587,334),(598,361),(611,389),(624,428),(637,474)],
  [(534,293),(533,323),(540,357),(549,388),(566,420),(595,449),(637,474)])],
 'apron': [
 ([(507,293),(497,311),(490,330),(480,354),(470,384),(463,408)],
  [(531,293),(535,316),(534,344),(524,363),(493,386),(463,408)]),
 ([(556,293),(568,311),(580,335),(593,362),(605,390),(617,405)],
  [(534,293),(533,316),(534,344),(548,365),(581,387),(617,405)])],
 'hip': [
 ([(495,281),(483,282),(477,287),(480,298),(478,308),(471,320),(456,341),(438,375),(429,387)],
  [(528,279),(518,292),(510,311),(498,327),(487,343),(471,359),(454,372),(439,381),(429,387)]),
 ([(561,281),(574,282),(578,289),(575,300),(578,312),(585,321),(597,337),(603,352),(612,373)],
  [(538,279),(548,292),(554,309),(566,325),(578,341),(590,352),(601,362),(607,369),(612,373)])]
}

# Clean sampling windows for the white centre. The pendant has its own
# UVs and relief, so it must never appear in the silk underneath.
PENDANT = [(524,317),(543,318),(541,338),(544,350),(544,362),(553,371),(555,396),(549,410),(542,429),(542,454),(546,477),(544,505),(528,505),(528,479),(530,451),(528,430),(516,409),(510,398),(510,378),(522,359),(527,348)]
FLOWER = [(490,308),(496,288),(510,283),(510,263),(524,268),(533,242),(540,260),(550,254),(550,276),(569,283),(576,307),(571,313),(559,307),(549,298),(552,317),(543,314),(543,328),(535,341),(522,326),(519,316),(510,323),(512,303),(504,310)]


def fit_waist(t, points, ease, angle=None):
    """Seat the waistband on the measured skin and release it over the hips."""
    h=points[...,1]
    sample=np.clip(h,t.torso.heights[0],t.torso.heights[-1])
    if angle is None:
        angle=np.arctan2(points[...,0],centre(sample)-points[...,2])
    target=t.torso.surface(angle,sample,ease)
    # Continue the lowest measured section with the change in hip girth.
    # This avoids a vertical cylinder where the waist meets the loose skirt.
    hip=shell(angle,np.minimum(h,sample))-shell(angle,sample)
    # The front fall has a longer, gentler release than the gathers over
    # the seat. A short transition here produces a bulge below the rosette.
    forward=np.clip(np.cos(angle),0,1)
    low=11.55-1.5*forward
    high=13.62+.73*forward
    blend=smooth((h-low)/(high-low))
    for axis in (0,2):
        points[...,axis]+=blend*(target[...,axis]+hip[...,axis]-points[...,axis])
    return points


def front_skirt(t, pattern, silk, petal, gauze, silver):
    ivory = t.material('PearlHem','pattern.jpg')
    lining = cut([(505,414),(502,435),(500,450),(497,464)],[(527,413),(525,434),(524,450),(521,471)])
    iv = pattern.chart(lining)
    # Sew a full satin underskirt. Its front edge turns up behind the
    # scalloped facing, while the rear gathers open into a short fan.
    v,u = lattice(48,144); a = (u-.5)*2*pi
    back = (1-np.cos(a))*.5
    hem = 10.82-.29*back + .105*np.cos(11*a) + .085*np.sin(5*a)
    h=14.97+(hem-14.97)*v
    h+=(.06+.15*np.maximum(np.cos(a),0)**3)*(1-smooth(v/.31))
    p = shell(a,h,.029+.045*v,(.022+.081*v**1.8)*np.cos(11*a+.4*v))
    p[...,0] *= .92+.07*back
    # Close the top on the waist, keeping the original armature.
    fit_waist(t,p,.031,a)
    t.grid(ivory,p,uv=iv[0,0]+(iv[-1,-1]-iv[0,0])*np.stack([abs(2*((u*8)%1)-1),v],axis=-1))
    t.wire(silk,p[-1],.008,6)
    station=[273,290,310,335,365,405,448,480,524,565]
    radius=[1.30,1.53,1.75,2.03,2.39,2.88,3.43,3.62,3.65,3.61]
    front=[.99,1.04,1.10,1.20,1.34,1.39,1.44,1.45,1.42,1.41]
    def fabric(xy, offset, index):
        xx, yy = xy[...,0], xy[...,1]
        v,u = lattice(xy.shape[0]-1,xy.shape[1]-1)
        radius_x=np.interp(yy,station,radius)
        r=np.clip(front_xy(xx,yy,0)[...,0]/radius_x,-.997,.997)
        turn=np.sqrt(1-r*r)
        z=.22 - (.22+np.interp(yy,station,front))*turn
        z -= offset*(.36+.64*turn)
        z -= (np.sin(pi*v)**.65)*(.062*np.cos(2*pi*(1.19*u+.14*v))+.027*np.sin(2*pi*(2.7*u-.26*v)))
        if index=='train':
            z += .49*v*np.sin(2.9*pi*v+.30*u)+.17*np.sin(pi*u)
        if index=='ivoryWing':
            z += .16*v**4*np.sin(2*pi*u+.32)
        p=front_xy(xx,yy,z)
        hy=np.clip(p[...,1],t.torso.heights[0],t.torso.heights[-1])
        depth=centre(hy)-t.torso.surface(np.zeros_like(hy),hy)[...,2]
        angle=np.arctan2(p[...,0],np.maximum(depth*turn,.014))
        # Millimetres separate the sewn layers. Keep their original full
        # depth in the unsupported petals below the upper hip.
        ease=.053+offset*.115+.0025*np.sin(pi*v)*np.cos(2*pi*u)
        return fit_waist(t,p,ease,angle)
    # Front satin falls in three lobes, with a second, shorter scallop
    # visible just behind the raised corners.
    for layer,(xs,ys,off) in enumerate([
      ([453,463,481,497,515,534,551,568,583,602,610],[470,477,481,473,479,481,478,473,479,479,470],.08),
      ([453,466,485,494,497,504,515,525,534,547,555,568,576,582,591,605,614],[472,485,477,470,463,469,474,482,487,482,476,471,468,463,478,483,472],.17)]):
        v,u=lattice(45,100)
        ends=curve(list(zip(xs,ys)),u[0])[None]
        xy=np.stack([532+(ends[...,0]-532)*(.27+.73*v),302+(ends[...,1]-302)*v],axis=-1)
        mask=[(511,394),(523,383),(543,389),(563,393),(573,427),(580,461),(573,466),(563,471),(551,475),(536,484),(522,479),(513,471),(503,467),(502,455),(505,426)]
        uv=pattern.chart(xy,mask,[PENDANT])
        p=fabric(xy,off,'satin')
        t.grid(ivory,p,uv=uv)
        t.wire(silk,p[-1],.012,7)
        if layer:
            q=p[-1].copy();q[:,1]+=.023;q[:,2]-=.009
            t.wire(silver,q,.006,6)
    pieces={name:[cut(*rails) for rails in pair] for name,pair in FRONT.items()}
    trims={'train':-.11,'ivoryWing':.26,'wrap':.38,'apron':.49,'hip':.52}
    for name, pair in pieces.items():
        for i, xy in enumerate(pair):
            holes=[PENDANT,FLOWER]
            for higher in list(pieces)[list(pieces).index(name)+1:]:
                holes.append(outline(pieces[higher][i]))
            uv=pattern.chart(xy, holes=holes, chiffon=name=='train', pale_silk=name=='hip')
            p=fabric(xy,trims[name],name)
            mat=gauze if name=='train' else ivory if name=='ivoryWing' else petal
            t.grid(mat,p,flip=i==0,uv=uv)
            # A single fine cord follows the bias. Double outlining every
            # edge turns layered silk into a conspicuous wire cage.
            t.wire(silver,p[:,-1],.009 if name in ('wrap','apron') else .006,6)
            if name=='train':t.wire(silk,p[:,0],.009,6)
            if name=='ivoryWing':
                rim=p[38:,-1].copy()
                t.wire(silk,rim,.016,8)
                inner=p[38:,-4].copy()
                lift=np.sin(np.linspace(0,pi,len(rim)))**.7
                lip=(rim+inner)*.5
                lip[:,1]+=.031*lift;lip[:,2]-=.043*lift
                t.grid(ivory,np.stack([inner,lip,rim],axis=1),flip=i==0,uv=uv[38:,[-4,-2,-1]])
    # A diagonally couched braid secures the basque. Two small silk flowers
    # emerge from the braid on the hip, just above its turned-over tip.
    for side in [-1,1]:
        seam=[(499,302),(491,310),(485,316),(476,322),(468,326),(457,333)]
        def side_xy(xy):
            xy=xy.copy()
            if side>0:xy[...,0]=1063-xy[...,0]+np.interp(xy[...,1],[302,344],[0,-.8])
            return xy
        ctr=curve(seam,np.linspace(0,1,42))
        strip=side_xy(np.stack([ctr+[-.45,-.35],ctr+[.45,.35]],axis=1))
        points=fabric(strip,.55,'hip')
        t.wire(silver,points[:,0],.014,7)
        for j in (5,13,22,30,39):
            t.stone(silk,points[j,0]+[0,0,-.014],(.035,.035,.027))
        for cx,cy,size in [(456,334,1.),(450.7,342,.71)]:
            for angle in np.arange(5)*2*pi/5+.38:
                v,u=lattice(12,8)
                along=4.4*size*v;cross=2.0*size*np.sin(pi*v)**.65*(2*u-1)
                x=cx+np.cos(angle)*along-np.sin(angle)*cross
                y=cy+np.sin(angle)*along+np.cos(angle)*cross
                xy=side_xy(np.stack([x,y],axis=-1))
                p=fabric(xy,.57,'hip')
                p[...,2]-=.037*np.sin(pi*u)*np.sin(pi*v)
                t.grid(ivory,p,uv=iv[0,0]+(iv[-1,-1]-iv[0,0])*np.stack([u,v],axis=-1))
            t.stone(silver,p[0,4]+[0,0,-.038],(.036,.034,.024))

def rear_skirt(t, pattern, silk, petal, gauze, silver):
    # The rear has a continuous scalloped fan and two longer overturned
    # gores. They are cut on different grain lines, with an actual return
    # on the hem rather than a pale stripe painted across a flat cone.
    rear_satin = cut([(1075,330),(1060,357),(1046,398),(1034,441),(1030,460)],
                     [(1086,329),(1081,355),(1075,397),(1067,435),(1063,459)])
    satin_uv=pattern.chart(rear_satin)
    for sign in [-1,1]:
        v,u=lattice(51,60);a=sign*(1.35+(pi-1.35)*u)
        hem=10.65+.13*np.cos(9*a)+.10*np.cos(14*a+.22)
        h=15.02+(hem-15.02)*v
        fold=(.012+.09*v**1.65)*np.cos(2*pi*(4.1*u-.16*v))
        p=shell(a,h,.05+.14*v,fold)
        fit_waist(t,p,.054,a)
        uv=satin_uv[0,0]+(satin_uv[-1,-1]-satin_uv[0,0])*np.stack([u,v],axis=-1)
        t.grid(petal,p,flip=sign<0,uv=uv)
    # Reconstruct each visible return on the near half of a hip section.
    # The second side is sewn around the opposite hip in the same way.
    view=-2.15
    right=np.array([np.cos(view), np.sin(view)])
    normal=np.array([np.sin(view), -np.cos(view)])
    def fit(xy,lift,roll):
        v,u=lattice(xy.shape[0]-1,xy.shape[1]-1)
        xx,yy=xy[...,0],xy[...,1]
        levels=[293,308,335,370,410,455,486,530,570]
        rx=np.interp(yy,levels,[1.15,1.32,1.65,2.03,2.43,2.83,2.98,2.96,2.96])
        rz=np.interp(yy,levels,[1.14,1.24,1.39,1.59,1.81,2.04,2.15,2.18,2.19])
        cz=np.interp(yy,levels,[.03,.05,.12,.19,.27,.37,.40,.40,.40])
        # Solve the ray/ellipse intersection at each drafted station.
        depth=0.
        for i in range(4):
            span=(2.545-.08*depth)/(1604.7*.08)
            screen=(xx-1090)*1.21*span
            bx=screen*right[0];bz=screen*right[1]-cz
            aa=(normal[0]/rx)**2+(normal[1]/rz)**2
            bb=bx*normal[0]/rx**2+bz*normal[1]/rz**2
            cc=(bx/rx)**2+(bz/rz)**2-1
            depth=(-bb+np.sqrt(np.maximum(bb*bb-aa*cc,.003)))/aa
            depth+=lift*(.36+.64*v)+.073*np.sin(pi*v)*np.cos(2*pi*(u*1.2-.22*v))
            depth+=roll*v**1.9*np.sin(3*pi*v+1.2*u)
        span=(2.545-.08*depth)/(1604.7*.08)
        screen=(xx-1090)*1.21*span
        h=1.18/.08-1.17354+(80-1.27*(yy-296))*span
        p=np.stack([screen*right[0]+depth*normal[0],h,screen*right[1]+depth*normal[1]],axis=-1)
        return fit_waist(t,p,.061+.105*lift)
    # The visible lower edge sweeps are independent from the upper side seams.
    def panel(rows,mat,visible,lift,roll=.0,chiffon=False):
        v,u=lattice(62,39)
        xy=curve(rows,v[:,0])
        xy=xy[:,None,:2]*(1-u[...,None])+xy[:,None,2:]*u[...,None]
        uv=pattern.chart(xy,visible,chiffon=chiffon)
        p=fit(xy,lift,roll)
        for sign in [1,-1]:
            q=p.copy();q[...,0]*=sign
            t.grid(mat,q,flip=sign<0,uv=uv)
            t.wire(silk,q[-1],.009,6)
            t.wire(silver,q[:,0],.007,6)
            t.wire(silk,q[:,-1],.011 if chiffon else .008,6)
            if chiffon:
                # Doubled organza in the diagonal rolled hem has more
                # optical depth than the single layer across the thigh.
                start=len(q)//2
                outer=q[start:,-1];inner=q[start:,-4]
                width=np.sin(np.linspace(0,pi,len(outer)))**.66
                inner=outer+(inner-outer)*width[:,None]
                crown=(outer+inner)*.5+.033*width[:,None]*np.array([sign*normal[0],0,normal[1]])
                facing=np.stack([outer,crown,inner],axis=1)
                t.grid(mat,facing,flip=sign<0,uv=uv[start:,[-1,-2,-4]])
    panel([(1081,312,1092,309),(1068,344,1090,342),(1039,379,1083,386),
           (1011,422,1073,430),(990,468,1065,463),(983,500,1057,484),
           (985,510,1049,502),(997,517,1048,516),(1008,531,1048,531),
           (1020,544,1044,544),(1016,556,1030,556),(1009,570,1009,570)],
          gauze,[(998,502),(1017,493),(1034,480),(1044,489),(1043,519),(1034,539),(1023,551),(1012,535),(1000,518)],.105,.23,True)
    panel([(1090,303,1102,299),(1094,347,1123,342),(1097,386,1149,380),
           (1099,428,1170,417),(1100,477,1181,463),(1099,502,1167,500),
           (1097,524,1139,514),(1096,530,1105,526),(1101,536,1109,533),
           (1109,543,1117,540),(1102,550,1109,549),(1094,558,1100,555),(1087,570,1087,570)],
          gauze,[(1102,484),(1144,483),(1160,481),(1169,489),(1154,504),(1121,517),(1101,525)],.18,.26,True)
    # A fluted, opaque rear fan. Free scallops carry a rolled pale selvedge.
    ends=[(987,466),(997,477),(1015,480),(1032,465),(1040,472),(1054,479),(1064,478),(1069,471),(1084,482),(1090,483),(1094,475),(1098,478),(1104,480)]
    v,u=lattice(59,74);edge=curve(ends,u[0])[None]
    xy=np.stack([1092+(edge[...,0]-1092)*(.085+.915*v),302+(edge[...,1]-302)*v],axis=-1)
    vis=[(1084,329),(1089,332),(1091,373),(1091,449),(1090,473),(1085,480),(1076,476),(1067,469),(1062,473),(1053,474),(1038,469),(1032,461),(1017,476),(1006,475),(995,466),(1010,440),(1035,392),(1060,357)]
    uv=pattern.chart(xy,vis)
    p=fit(xy,.27,0)
    for sign in [1,-1]:
        q=p.copy();q[...,0]*=sign
        t.grid(petal,q,flip=sign<0,uv=uv);t.wire(silk,q[-1],.013,7)
    panel([(1091,298,1100,298),(1093,326,1127,324),(1097,357,1144,348),
           (1097,386,1156,370),(1101,402,1168,390),(1111,417,1182,413),
           (1126,434,1190,435),(1138,451,1199,456),(1146,462,1204,473),
           (1163,468,1192,476),(1176,474,1183,474)],
          petal,[(1097,326),(1105,336),(1127,372),(1147,396),(1163,415),(1172,442),(1179,472),(1150,460),(1136,444),(1115,420),(1103,402),(1099,379)],.36,.04)


def waist_jewel(t, gold, silver, pearl):
    from yuexiao_jewels import articulated_chain, link, stone_cut
    # Sculpt the setting over the finished front cloth. The chased texture
    # is sampled locally from each leaf of the same drawing as its outline.
    box=np.array([484,240]);size=np.array([96,268])
    with Image.open(ART) as art:
        art.crop((*box,*(box+size))).resize((384,1072),Image.BICUBIC).convert('RGB').save(TEX/'yuexiao-filigree.jpg',quality=98,subsampling=0)
    chased=t.material('ChasedMetal','filigree.jpg')
    enamel=t.material('Celadon','filigree.jpg')
    stone=t.material('Moonstone','filigree.jpg')
    nacre=t.material('PearlInlay','filigree.jpg')
    cut_stone=t.material('PendantCrystal','jewels.jpg')
    front=np.array([0.,0.,-1.]);right_axis=np.array([1.,0.,0.]);upright=np.array([0.,1.,0.])
    def place(xy,relief):
        x,y=xy[...,0],xy[...,1]
        z=np.zeros_like(x)-1.2
        for i in range(3):
            p=front_xy(x,y,z)
            h=p[...,1]
            fitted=smooth((h-12.65)/1.10)
            # Curl the outer wing over the side of the actual waist.
            # The centre and the free pendant retain their frontal register.
            section=np.clip(h,t.torso.heights[0],t.torso.heights[-1])
            reach=abs(t.torso.surface(np.sign(p[...,0])*pi/2,section,.062)[...,0])
            reach=np.maximum(reach,.08)
            xx=abs(p[...,0]);start=.61*reach
            over=np.maximum(xx-start,0)
            inset=over-.38*reach*np.tanh(over/(.38*reach))
            mounted=p[...,0]-np.sign(p[...,0])*fitted*inset
            z=t.jewel_surface(mounted,h)-(.023-.011*fitted)-relief*(1-.65*fitted)
        p=front_xy(x,y,z)
        p[...,0]=mounted
        return p
    def leaf(left,right,depth=.06,belly=.056,mat=chased,segments=13,solid=False):
        xy=cut(left,right,27,segments)
        v,u=lattice(27,segments)
        rise=depth+belly*np.sin(pi*u)**.79*(.13+.87*np.sin(pi*v)**.65)
        p=place(xy,rise)
        t.grid(mat,p,uv=(xy-box)/size)
        # A narrow turned undercut gives the piece thickness in profile.
        for j in (0,-1):
            edge=p[:,j];wall=np.stack([edge,edge+[0,0,.033]],axis=1)
            t.grid(mat,wall,uv=np.repeat(((xy[:,j:j+1] if j==0 else xy[:,-1:])-box)/size,2,axis=1))
        if solid:
            back=place(xy,depth-.033-belly*np.sin(pi*u)*np.sin(pi*v))
            t.grid(mat,back,flip=True,uv=(xy-box)/size)
        return p
    def thread(pts,r=.010,depth=.067,mat=gold):
        xy=curve(pts,np.linspace(0,1,36))
        t.wire(mat,place(xy,depth),r,6)
    # The outside points spiral away from the stone. Each wing keeps its
    # own engraved ribs, recess colour, and curved return at the hip.
    leaf([(521,282),(513,282),(505,284),(499,290),(493,302),(488,309)],
         [(522,287),(515,292),(506,298),(500,300),(494,304),(488,309)],.067,.079)
    leaf([(539,282),(548,282),(555,284),(560,289),(564,298),(570,310)],
         [(540,287),(548,294),(554,299),(560,302),(567,305),(570,310)],.064,.079)
    for rib in [
      [(519,284),(512,285),(507,288),(502,295),(497,301)],
      [(519,286),(514,287),(509,292),(505,296),(499,299)],
      [(542,284),(548,285),(553,288),(558,294),(563,302)],
      [(543,286),(548,288),(551,292),(557,297),(562,300)],
    ]:
        a=np.asarray(rib,dtype=float)
        rib=leaf(a-[[.24,.12]],a+[[.24,.12]],.137,.020,segments=4)
        t.wire(silver,rib[:,2],.0048,5)
    spear=leaf([(532,274),(525,268),(526,260),(531,252),(532,246)],
               [(537,276),(540,266),(537,258),(534,251),(532,246)],.088,.077)
    for k in (0,3,10,13):
        t.wire(gold,spear[:,k]+.004*front,.009 if k in (0,13) else .007,6)
    t.wire(silver,spear[3:-3,6]+.007*front,.006,6)
    for i,(l,r) in enumerate([
     ([(530,280),(521,277),(516,270),(513,260)],[(532,277),(526,266),(522,263),(513,260)]),
     ([(535,278),(537,268),(542,263),(547,260)],[(538,281),(545,275),(548,267),(547,260)]),
     ([(524,286),(513,281),(510,276),(508,269)],[(526,282),(519,276),(514,270),(508,269)]),
     ([(538,281),(546,277),(552,274),(557,275)],[(541,285),(550,283),(556,279),(557,275)]),
     ([(525,282),(518,283),(514,288),(514,292),(516,294)],[(527,286),(524,291),(521,294),(518,295),(516,294)]),
     ([(538,284),(542,285),(547,288),(550,291)],[(537,288),(542,293),(547,294),(550,291)]),
     ([(530,290),(524,296),(521,304),(517,311),(515,317)],[(534,293),(530,303),(526,310),(519,316),(515,317)]),
     ([(536,292),(537,302),(541,308),(546,313)],[(539,291),(543,300),(548,309),(546,313)]),
     ([(533,297),(530,305),(526,312),(527,321),(533,333)],[(535,297),(538,306),(539,315),(538,323),(533,333)])
    ]):
        if i==8:
            # Two independently turned rails surround the small celadon
            # marquise. The fabric is visible between the inset and the rails.
            left,right=cut(l,r,34,1).transpose(1,0,2)
            for side,opposite in ((left,right),(right,left)):
                lip=leaf(side,side+.16*(opposite-side),.122,.032,chased,5)
                t.wire(gold,lip[:,0],.008,6)
            middle=(left+right)/2
            spread=(right-left)*(.19*np.sin(np.linspace(0,pi,len(left)))**.7)[:,None]
            inset=leaf(middle-spread,middle+spread,.150,.027,enamel)
            for side in (0,-1):t.wire(gold,inset[:,side],.005,5)
            continue
        petal=leaf(l,r,.11,.064,nacre if i in (2,3,4,5,6,7) else chased)
        t.wire(gold,petal[:,0],.006,6)
        if i in (0,1,6,7):
            t.wire(gold,petal[:,-1],.006,6)
            t.wire(silver,petal[3:-3,7]+.004*front,np.linspace(.008,.003,len(petal)-6),5)
    surround=leaf([(532,267),(527,272),(523,281),(526,290),(531,297),(534,300)],
         [(532,267),(538,271),(541,281),(542,288),(537,295),(534,300)],.18,.131,nacre)
    for k in (0,13):t.wire(gold,surround[:,k],.009,6)
    cab=leaf([(532,272),(529,275),(528,281),(530,286),(534,289)],
             [(532,272),(535,275),(537,281),(537,286),(534,289)],.29,.067,stone)
    for edge in (cab[:,0],cab[:,-1]):t.wire(gold,edge,.008,6)
    for x,y in [(528.6,280.5),(535.9,279.2),(532.7,287.8)]:
        p=place(np.array([x,y]),.312)
        t.stone(gold,p,(.018,.025,.016))
    articulated_chain(t,gold,place(curve([(525,315),(517,325),(518,330),(526,338),(531,343)],np.linspace(0,1,34)),.068),front,.066,.0065)
    thread([(533,330),(533,335),(534,341),(534,351)],.016)
    for side in (-1,1):
        p=place(np.array([532+side*14.,317.+(side+1)*1.1]),.08)
        t.stone(pearl,p,(.033,.059,.030))
    pearl_mount=leaf([(534,337),(529,339),(527,345),(529,350),(534,352)],
         [(534,337),(539,339),(541,345),(539,349),(534,352)],.083,.094,nacre,solid=True)
    for j in (0,-1):t.wire(silver,pearl_mount[:,j],.0065,6)
    for x,y in [(517.5,324.),(546.8,324.)]:
        p=place(np.array([x,y]),.095)
        link(t,gold,p,right_axis,upright,.022,.039,.007)
        t.stone(pearl,p-.049*upright,(.019,.032,.018))
    # Three hollow marquises, a warm gold spine and a loose jade blade.
    for index,(l,r) in enumerate([
      ([(534,352),(530,363),(522,377),(520,389),(522,401),(529,416),(535,428)],
       [(534,352),(533,365),(526,380),(524,390),(526,401),(531,416),(535,428)]),
      ([(535,352),(538,365),(543,378),(544,390),(541,405),(537,418),(535,428)],
       [(535,352),(542,365),(548,378),(548,390),(545,405),(540,418),(535,428)]),
      ([(533,356),(529,371),(527,386),(531,400),(534,405)],
       [(533,356),(534,370),(534,384),(535,397),(534,405)]),
      ([(535,356),(535,371),(536,385),(535,397),(534,403)],
       [(535,356),(538,371),(540,385),(538,395),(534,403)]),
      ([(517,373),(514,377),(513,386),(515,395),(519,403)],
       [(517,373),(518,378),(516,387),(517,396),(519,403)]),
      ([(550,375),(549,380),(550,388),(548,399)],
       [(550,375),(554,379),(555,389),(548,399)])]):
        blade=leaf(l,r,.083,.039,enamel if index in (2,3) else nacre if index>=4 else chased)
        if index<=3:
            t.wire(gold,blade[:,0],.0075,6)
        else:
            # The short jewelled returns are soldered to the back of the
            # upper fork. From the front only the free beaded edges show.
            x,y=l[0]
            thread([(534,354),((534+x)*.5,361),(x,369),(x,y)],.006,.058)
            for row in (5,11,18,23):
                t.stone(pearl,blade[row,6]+.008*front,(.016,.021,.014))
    articulated_chain(t,gold,place(curve([(535,427),(536,433),(537,439),(536,448),(537,455)],np.linspace(0,1,30)),.10),front,.079,.007)
    for x,y,r in [(536,431,.044),(536.8,435,.059),(537,443,.033),(537.1,450,.028)]:
        p=place(np.array([x,y]),.114)
        if y==435:
            stone_cut(t,cut_stone,p,right_axis,upright,front,(r,r*1.15,r*.66),'brooch',np.array([x,y]),[1.4,1.8])
        else:
            t.stone(gold if y in (431,450) else pearl,p,(r,r*1.12,r*.72))
    leaf([(537,451),(535,460),(533,473),(531,483),(532,493),(537,503)],
         [(537,451),(539,460),(542,473),(544,483),(542,495),(537,503)],.10,.095,enamel,solid=True)
