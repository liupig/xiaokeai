"""Tailor Lanxu to the local Qingyi rig. Run after build_lingyun.py."""
from collections import OrderedDict
from math import pi
from pathlib import Path
import copy
import runpy
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
OUT = ROOT / "online-demo/frontend/public/models/qingyi-jade"
TEX = OUT / "textures"
PMX = runpy.run_path(str(ROOT / "companion/tools/mmd_tools/core/pmx/__init__.py"))
sin, cos = np.sin, np.cos


def atlas(name, top, hem, folds, motif=None, sides=False):
    w,h = 1024,1024
    v,u = np.mgrid[0:h,0:w]/np.array((h-1,w-1))[:,None,None]
    f = u*folds + .14*sin(2*pi*u+v*2)*v
    twist = .35*sin(2*pi*u+1.3)*v
    tone = (.035+.095*v)*cos(2*pi*f+twist) + .031*cos(4*pi*f+twist)
    weave = .008*cos(2*pi*(u*w*.42+v*h*.18)) + .006*sin(2*pi*v*h*.39)
    # Paired woven lines, celadon band, and a meandering couched vine at the hem.
    col = ((1-v[:,:,None]**1.4)*np.array(top) + v[:,:,None]**1.4*np.array(hem))*(1+tone+weave)[:,:,None]
    def thread(dist, width, rgb, mix=1):
        amount = np.clip(1.1-abs(dist)/width,0,1)[:,:,None]*mix
        col[:] = col*(1-amount)+np.array(rgb)*amount
    if name=='brocade':
        # A shadow-woven curl catches light only as the front folds turn.
        for sign in (-1,1):
            wave=.5+sign*(.13+.052*sin(3*pi*v)+.07*v)
            thread(u-wave,.006,(121,158,143),.27)
            thread(u-wave-sign*.014,.002,(170,176,145),.35)
    elif name!='sash':
        thread(v-.963,.019,(49,100,97),.56)
        for yy in (.942,.951,.979,.991):
            thread(v-yy,.0018,(232,200,142),.92)
        thread(v-.966-.006*sin(2*pi*folds*u),.0017,(224,204,156),.85)
    if sides:
        for xx in (.009,.019,.982,.992):
            thread(u-xx,.0021,(223,197,147),.94)
    dst=Image.fromarray(np.uint8(np.clip(col,0,255))).convert('RGBA')
    if name=='brocade':
        # Woven cloud-head on one facing. The returning hook, fine split stem
        # and tapering leaf veins are painted in the seam's UV coordinates.
        pattern=Image.new('RGBA',dst.size);draw=ImageDraw.Draw(pattern)
        def stitch(curves,color,thickness):
            for a,b,c,d in curves:
                k=np.linspace(0,1,65)[:,None]
                points=((1-k)**3*np.array(a)+3*k*(1-k)**2*np.array(b)
                        +3*k*k*(1-k)*np.array(c)+k**3*np.array(d))*1023
                draw.line([tuple(p) for p in points],fill=color,width=thickness)
        branch=[((.89,.82),(.84,.66),(.68,.61),(.75,.47)),
                ((.75,.47),(.83,.30),(.91,.42),(.85,.47)),
                ((.85,.47),(.814,.505),(.781,.457),(.816,.443))]
        stitch(branch,(210,190,135,140),3)
        stitch([((.845,.73),(.81,.61),(.69,.56),(.677,.42)),
                ((.677,.42),(.724,.46),(.72,.54),(.799,.62)),
                ((.844,.70),(.89,.64),(.905,.58),(.896,.55)),
                ((.896,.55),(.86,.58),(.873,.63),(.844,.70))],(168,185,153,142),4)
        dst=Image.alpha_composite(dst,pattern)
    if motif:
        art=Image.open(DESIGN/'lanxu-embroidery.png').convert('RGBA')
        alpha=art.getchannel('A')
        art=art.crop(alpha.point(lambda v:255 if v>80 else 0).getbbox())
        for x,y,ww,hh,opacity,flipped in motif:
            spr=art.transpose(Image.FLIP_LEFT_RIGHT) if flipped else art
            spr=spr.resize((ww,hh),Image.LANCZOS)
            if opacity!=1:
                spr.putalpha(spr.getchannel('A').point(lambda a:int(a*opacity)))
            dst.alpha_composite(spr,(x,y))
    dst.convert('RGB').save(TEX/('lanxu-'+name+'.jpg'),quality=94,subsampling=0)


def dyed(source, name, palette):
    im=Image.open(TEX/source).convert('RGBA')
    value=np.asarray(im.convert('L'),np.float32)
    k=np.array([0,75,142,205,255])
    pixels=np.stack([np.interp(value,k,channel) for channel in np.array(palette).T],axis=-1)
    tex=Image.fromarray(pixels.astype('uint8')).convert('RGBA')
    tex.putalpha(im.getchannel('A'))
    tex.save(TEX/('lanxu-'+name+'.png'))


def make_textiles():
    atlas('undersilk',(49,92,93),(148,197,184),20)
    atlas('embroid',(25,58,66),(56,112,111),3,
          [(432,314,326,582,.87,False)],True)
    atlas('ivory',(128,168,155),(233,227,199),3,
          [(589,582,238,310,.44,True)],True)
    atlas('back',(49,106,103),(99,162,150),5,
          [(144,360,390,539,.85,True)],True)
    atlas('sash',(41,79,83),(28,66,72),4)
    atlas('brocade',(27,65,74),(44,96,96),2)
    dyed('Up_EX.png','bodice',[(48,67,72),(107,133,128),(177,191,174),(223,222,199),(249,240,213)])
    dyed('Cloth_EX.png','sleeve',[(24,52,62),(45,90,96),(85,137,132),(158,192,172),(230,221,185)])


def cut_lining(model, triangles, levels=(10.18,10.25),
               colors=((120,157,144),(39,70,75)),target='lanxu-lining.png'):
    """Paint the fitted dance shorts on their own skin UVs, following the leg weights exactly."""
    mat=next(x for x in model.materials if x.name=='Down_Skin')
    im=Image.open(model.textures[mat.texture].path).convert('RGBA')
    w,h=im.size
    paint=np.asarray(im).copy()
    masks=[np.zeros((h,w),np.uint8) for _ in range(2)]
    for tri in triangles:
        data=np.array([(*model.vertices[i].uv,model.vertices[i].co[1]) for i in tri])
        if data[:,2].max()<min(levels): continue
        for mask,level in zip(masks,levels):
            poly=[]
            for j,q in enumerate(data):
                p=data[j-1]
                if (q[2]>=level)!=(p[2]>=level):
                    poly.append((p+(q-p)*((level-p[2])/(q[2]-p[2])))[:2])
                if q[2]>=level:poly.append(q[:2])
            if len(poly)>=3:
                poly=np.rint(np.asarray(poly)*[w-1,h-1]*16).astype('int32')
                cv2.fillConvexPoly(mask,poly,255,lineType=cv2.LINE_AA,shift=4)
    for mask,color in zip(masks,colors):
        mix=mask[:,:,None].astype('float32')/255
        paint[:,:,:3]=paint[:,:,:3]*(1-mix)+np.array(color)*mix
    Image.fromarray(paint).save(TEX/target)


# Cross-sections taken around the original hip and bust, in PMX centimetre units.
levels=np.array([8.2,9.1,10.3,11.2,12.05,12.75,13.4,13.95,14.45,15.05,15.65,16.18])
width=np.array([2.68,2.60,2.46,2.29,2.12,1.87,1.60,1.36,1.20,1.08,1.15,1.33])
front=np.array([1.17,1.14,1.10,1.05,1.02,1.0,.99,.97,.95,.98,1.12,1.28])
back=np.array([1.98,1.92,1.85,1.79,1.71,1.57,1.32,1.08,.91,.84,.91,1.02])


def shell(a,y,lift=0,fold=0):
    xrad=np.interp(y,levels,width)
    fr=np.interp(y,levels,front)
    ba=np.interp(y,levels,back)
    cy=(ba-fr)/2
    zrad=(ba+fr)/2
    # Slightly flattened front and rear, closer to a tailored hip than an ellipse.
    s,c=sin(a),cos(a)
    power=np.interp(y,[12,14,16],[.82,.93,1.0])
    x=(xrad+lift+fold)*np.sign(s)*abs(s)**power
    z=cy-(zrad+lift+fold)*np.sign(c)*abs(c)**power
    return np.stack((x,y,z),axis=-1)


def bodice_form(model):
    """Measure radial sections of the sewn bust. Interpolate across open side seams."""
    from scipy.ndimage import gaussian_filter
    vs=np.asarray([v.co for v in model.vertices])
    cursor=0; pieces=[]
    for mat in model.materials:
        n=mat.vertex_count//3
        if mat.name in ('Up_','Up_Skin','Down_Skin'):
            pieces.extend(model.faces[cursor:cursor+n])
        cursor+=n
    tri=vs[np.asarray(pieces)]
    tri=tri[(tri[:,:,1].max(axis=1)>14)&(tri[:,:,1].min(axis=1)<16.95)&
            (abs(tri[:,:,0]).min(axis=1)<1.55)]
    heights=np.linspace(14.0,16.9,59)
    angles=np.linspace(-pi,pi,180,endpoint=False)
    rays=np.column_stack([sin(angles),-cos(angles)])
    table=[]
    def cross(p,q):return p[...,0]*q[...,1]-p[...,1]*q[...,0]
    for height in heights:
        edges=[]
        for t in tri[(tri[:,:,1].min(axis=1)<=height)&(tri[:,:,1].max(axis=1)>height)]:
            points=[]
            for j,q in enumerate(t):
                p=t[j-1]
                if (q[1]>height)!=(p[1]>height):
                    v=p+(q-p)*((height-p[1])/(q[1]-p[1]))
                    points.append(v[[0,2]]-[0,.10])
            if len(points)==2:edges.append(points)
        edges=np.asarray(edges);p=edges[:,0];d=edges[:,1]-p
        den=cross(rays[:,None],d[None])
        with np.errstate(invalid='ignore',divide='ignore'):
            ray=cross(p,d)/den
            hit=cross(p[None],rays[:,None])/den
        fallback=shell(angles,np.full_like(angles,height))
        fallback=np.hypot(fallback[:,0],fallback[:,2]-.10)
        valid=(hit>=0)&(hit<=1)&(ray>.4)&(ray<fallback[:,None]+.30)
        measured=np.max(np.where(valid,ray,0),axis=1)
        # The bust has a hollow centre. Use the original surface there, but
        # provide an unbroken woven backing wherever the donor has no side wall.
        mix=np.clip((height-14.0)/.48,0,1)
        table.append(fallback*(1-mix)+np.where(measured>.4,measured,fallback)*mix)
    table=gaussian_filter(np.asarray(table),(.95,2.1),mode=('nearest','wrap'))
    def point(a,y,lift):
        a,y=np.broadcast_arrays(a,y)
        x=(a+pi)*len(angles)/(2*pi);i=np.floor(x).astype(int);f=x-i
        k=np.clip((y-heights[0])/(heights[1]-heights[0]),0,len(heights)-1.001)
        j=k.astype(int);g=k-j
        radius=(1-g)*((1-f)*table[j,i%len(angles)]+f*table[j,(i+1)%len(angles)])+g*((1-f)*table[j+1,i%len(angles)]+f*table[j+1,(i+1)%len(angles)])
        r=radius+lift
        return np.stack([r*sin(a),y,.10-r*cos(a)],axis=-1)
    return point


def bust_seam(a):
    return 15.91+.50*abs(sin(a))**1.15+.19*(1-cos(a))+.13*sin(a)


def torso_depth(model):
    """Front/back sewing forms rasterized from the donor's real torso triangles."""
    from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates
    scale=75
    xmin,ymin=-1.72,15.18
    shape=(265,259)
    mins=np.full(shape,np.inf);maxs=np.full(shape,-np.inf)
    vs=np.asarray([v.co for v in model.vertices]);cursor=0
    for mat in model.materials:
        n=mat.vertex_count//3;faces=model.faces[cursor:cursor+n];cursor+=n
        if mat.name not in ('Up_','Up_Skin') or not faces:continue
        tris=vs[np.array(faces)]
        for tri in tris[(tris[:,:,1].max(1)>ymin)&(tris[:,:,1].min(1)<18.7)&(abs(tris[:,:,0]).min(1)<1.56)]:
            p=(tri[:,:2]-[xmin,ymin])*scale
            l,b=np.maximum(0,np.floor(p.min(axis=0)).astype(int))
            r,t=np.minimum([shape[1]-1,shape[0]-1],np.ceil(p.max(axis=0)).astype(int))
            if r<l or t<b:continue
            e=p[1]-p[0];f=p[2]-p[0];det=e[0]*f[1]-e[1]*f[0]
            if abs(det)<1e-8:continue
            yy,xx=np.mgrid[b:t+1,l:r+1];xx=xx-p[0,0];yy=yy-p[0,1]
            u=(xx*f[1]-yy*f[0])/det;v=(e[0]*yy-e[1]*xx)/det
            inside=(u>=0)&(v>=0)&(u+v<=1)
            z=tri[0,2]+u*(tri[1,2]-tri[0,2])+v*(tri[2,2]-tri[0,2])
            sl=np.s_[b:t+1,l:r+1]
            np.minimum(mins[sl],np.where(inside,z,np.inf),out=mins[sl])
            np.maximum(maxs[sl],np.where(inside,z,-np.inf),out=maxs[sl])
    maps=[]
    for grid in (mins,maxs):
        ids=distance_transform_edt(~np.isfinite(grid),return_distances=False,return_indices=True)
        maps.append(gaussian_filter(grid[tuple(ids)],1.7))
    def at(x,y,rear=False,allowance=.058):
        x,y=np.broadcast_arrays(x,y)
        axis=np.stack([(y-ymin)*scale,(x-xmin)*scale])
        z=map_coordinates(maps[int(rear)],axis,order=1,mode='nearest')
        return np.stack([x,y,z+(allowance if rear else -allowance)],axis=-1)
    return at


def settle_temple(model):
    """Curve the long temple lock to end at the clavicle on the dressed Liuting only."""
    style=next((m for m in model.morphs if m.name=='QingyiLiutingHair'),None)
    offsets={o.index:o for o in style.offsets} if style else {}
    cursor=0;ids=set()
    for mat in model.materials:
        n=mat.vertex_count//3
        if mat.name in ('Hair_Bangs','Hair_Bangs+'):
            ids.update(i for tr in model.faces[cursor:cursor+n] for i in tr)
        cursor+=n
    for i in ids:
        vertex=model.vertices[i]
        p=np.asarray(vertex.co)+(offsets[i].offset if i in offsets else np.zeros(3))
        x,y,z=p
        if x<=0 or y>=18.72:continue
        d=18.72-y
        shift=np.array([.055*d,.53*d,-.071*d])
        if style:
            if i not in offsets:
                o=PMX['VertexMorphOffset']();o.index=i;o.offset=(0.,0.,0.);style.offsets.append(o);offsets[i]=o
            offsets[i].offset=shift+offsets[i].offset
        else:vertex.co=np.asarray(vertex.co)+shift

class Tailor:
    def __init__(self,model):
        self.m=model
        self.bones={b.name:i for i,b in enumerate(model.bones)}
        self.parts=OrderedDict()
        self.textures={Path(t.path).name:i for i,t in enumerate(model.textures)}

    def tex(self,name):
        if name not in self.textures:
            t=PMX['Texture'](); t.path=str(TEX/name)
            self.textures[name]=len(self.m.textures)
            self.m.textures.append(t)
        return self.textures[name]

    def cloth(self,name,image=None,rgb=(1.,1.,1.)):
        m=copy.deepcopy(self.m.materials[25])
        m.name=m.name_e='Lanxu_'+name
        m.texture=self.tex('lanxu-'+image) if image else -1
        m.diffuse=(*rgb,1);m.ambient=(.16,.17,.16)
        m.specular=(.18,.16,.13);m.shininess=34
        m.sphere_texture=m.toon_texture=-1
        m.sphere_texture_mode=0;m.is_shared_toon_texture=False
        m.enabled_toon_edge=False;m.is_double_sided=True
        self.parts[m]=[]
        return m

    def weights(self,p):
        x,y,_=p
        b=self.bones
        if y>=13.0:
            # Blend through the actual three torso joints so the waistband follows a bow.
            levels=[13,14.15,15.55,16.4,18.12,18.76]
            weights=[b['下半身'],b['上半身'],b['上半身1'],b['上半身2'],b['上半身2'],b['首']]
            i=min(len(levels)-2,max(0,np.searchsorted(levels,y)-1))
            t=float(np.clip((y-levels[i])/(levels[i+1]-levels[i]),0,1))
            ids=[weights[i],weights[i+1]];ws=[1-t,t]
        else:
            leg=float(np.clip((13-y)/3.25,0,1))
            side=float(np.clip(.5+x*.5,0,1))
            ids=[b['下半身'],b['左足'],b['右足']];ws=[1-leg,leg*side,leg*(1-side)]
        w=PMX['BoneWeight']();w.type=w.BDEF4
        w.bones=(ids+[b['下半身']]*4)[:4];w.weights=(ws+[0.]*4)[:4]
        return w

    def grid(self,mat,points,flip=False,uv=None):
        p=np.asarray(points)
        nr,nc=p.shape[:2]
        ids=np.arange(nr*nc).reshape(nr,nc)+len(self.m.vertices)
        a=ids[:-1,:-1].ravel();c=ids[1:,:-1].ravel()
        fs=np.vstack((np.c_[a,a+1,c],np.c_[a+1,c+1,c]))
        norm=np.cross(np.gradient(p,axis=1),np.gradient(p,axis=0))
        norm/=np.maximum(np.linalg.norm(norm,axis=2,keepdims=True),1e-10)
        if flip:norm*=-1;fs=fs[:,::-1]
        # PMX stores clockwise faces.
        self.parts[mat].extend(fs[:,::-1].tolist())
        if uv is None:
            v,u=np.mgrid[0:nr,0:nc]/np.array([nr-1,nc-1])[:,None,None]
            uv=np.stack([u,v],axis=-1)
        for pos,n,texcoord in zip(p.reshape(-1,3),norm.reshape(-1,3),uv.reshape(-1,2)):
            v=PMX['Vertex']();v.co=pos;v.normal=n;v.uv=texcoord
            v.weight=self.weights(pos);v.edge_scale=0
            self.m.vertices.append(v)

    def wire(self,mat,line,rad,sides=8):
        line=np.asarray(line)
        tg=np.gradient(line,axis=0);tg/=np.linalg.norm(tg,axis=1,keepdims=True).clip(1e-9)
        ref=np.eye(3)[np.argmin(abs(tg[0]))];basis=[]
        for tangent in tg:
            ref=ref-tangent*np.dot(tangent,ref);ref/=np.linalg.norm(ref).clip(1e-9)
            basis.append(ref)
        b=np.array(basis)
        a=np.linspace(0,2*pi,sides+1)[None,:,None]
        r=np.broadcast_to(rad,(len(line),))[:,None,None]
        self.grid(mat,line[:,None]+r*(np.cos(a)*b[:,None]+np.sin(a)*np.cross(tg,b)[:,None]))

    def stone(self,mat,center,scale):
        lat=np.linspace(.002,pi-.002,16)[:,None];a=np.linspace(0,2*pi,25)[None]
        xyz=np.stack(np.broadcast_arrays(sin(lat)*cos(a),cos(lat),sin(lat)*sin(a)),axis=-1)
        self.grid(mat,np.array(center)+xyz*np.array(scale))

    def finish(self):
        for mat,faces in self.parts.items():
            mat.vertex_count=3*len(faces);self.m.materials.append(mat);self.m.faces.extend(faces)


def tailor(model):
    t=Tailor(model)
    fitted=bodice_form(model)
    at=torso_depth(model)
    settle_temple(model)
    cursor=0;kept=[]
    for mat in model.materials:
        count=mat.vertex_count//3
        faces=model.faces[cursor:cursor+count];cursor+=count
        if mat.name in ('Magnolia pleated silk','Down_Bow','Up_Metal'):
            faces=[]
        if mat.name in ('Up_','Up_in'):
            # Remove the old long front tabard at a seam hidden by the new underbust wrap.
            faces=[tr for tr in faces if max(model.vertices[i].co[1] for i in tr)>15.32]
            mat.texture=t.tex('lanxu-bodice.png')
        if mat.name in ('Cloth_Sleeve','Cloth_Sleevein'):
            mat.texture=t.tex('lanxu-sleeve.png')
        if mat.name=='Down_Skin':
            if not (TEX/'lanxu-lining.png').exists():cut_lining(model,faces)
            mat.texture=t.tex('lanxu-lining.png')
        mat.vertex_count=len(faces)*3;kept.extend(faces)
    model.faces=kept
    lining=t.cloth('PleatedSilk','undersilk.jpg')
    jacquard=t.cloth('MagnoliaWrap','embroid.jpg')
    pearl=t.cloth('IvoryReverse','ivory.jpg')
    backcloth=t.cloth('RearWrap','back.jpg')
    belt=t.cloth('SilkGirdle','sash.jpg')
    topcloth=t.cloth('Brocade','brocade.jpg')
    gold=t.cloth('GiltCord',rgb=(.83,.59,.30))
    jade=t.cloth('Jade',rgb=(.25,.63,.55))
    iv=t.cloth('SeedPearls',rgb=(.94,.86,.68))
    V,U=np.mgrid[0:33,0:161]/np.array((32,160))[:,None,None]
    a=(U-.5)*2*pi
    hem=9.58+.35*sin(a-.22)+.28*cos(2*a+.4)-.23*(1-cos(a))+.09*cos(15*a)
    y=14.37+(hem-14.37)*V
    ridge=(.020+.061*V**1.55)*cos(17*a+.54*V)+.017*V*cos(34*a+V)
    t.grid(lining,shell(a,y,.025,ridge))
    # Independent bias-cut silk gores spiral from the high waist. Each hem is
    # traced in that panel's UV space, including the curved fall at the corners.
    def wrap(mat,left,right,bias,top,bottom,lo,pleats):
        v,u=np.mgrid[0:33,0:61]/np.array((32,60))[:,None,None]
        ang=left+(right-left)*u+bias*v+(.18*sin(pi*u)-.058*sin(2*pi*u))*sin(pi*v)
        y=top+(bottom(u)-top)*v
        open_pleat=.34+.66*np.minimum(1.,v*4.5)
        ridge=(.009+.022*v)*cos(2*pi*(pleats*u+.11*v))
        lift=.056+(lo-.056)*open_pleat+.043*v
        t.grid(mat,shell(ang,y,lift,ridge))
    wrap(pearl,.25,3.12,.14,14.18,lambda u:10.73-1.41*sin(pi*u)**.85+.25*u,.145,3)
    wrap(backcloth,1.80,4.63,.22,14.21,lambda u:10.65-1.96*sin(pi*u)**.87+.25*u,.217,4)
    wrap(jacquard,-1.95,.86,-.29,14.28,lambda u:10.66-1.95*sin(pi*u)**.88+.76*u,.283,3)
    # Two cut ends of a flat silk knot follow the rear hip. Each turns once
    # about its length, so the pale reverse only appears along the folded edge.
    for direction,finish in [(-1,lining),(1,topcloth)]:
        vv,uu=np.mgrid[0:38,0:12]/np.array((37,11))[:,None,None]
        along=2.70+direction*(.04+.34*vv+.10*sin(pi*vv))
        spread=(.055+.135*sin(pi*vv)**.70)*(2*uu-1)
        aa=along+spread
        yy=14.0-(3.75+.28*direction)*vv-.25*vv**4*(1-abs(2*uu-1))
        lift=.17+.34*np.minimum(1.,vv*3)+.19*sin(pi*vv)**1.7+.055*(uu-.5)*sin(2*pi*vv)
        ribbon=shell(aa,yy,lift)
        t.grid(finish,ribbon)
        t.wire(gold,ribbon[:,0],.011)
    # Continuous underbust jacket and oblique belt, made as separate cloth layers.
    a=(U-.5)*2*pi
    upper=bust_seam(a)
    y=upper+(13.92-upper)*V
    t.grid(topcloth,fitted(a,y,.074+.009*cos(6*a+.9*V)))
    ang=np.linspace(-pi,pi,145)
    for arc in (ang[ang< -1.23],ang[ang>1.23]):
        t.wire(gold,fitted(arc,bust_seam(arc),.080),.012)
    # Overlapping diagonal binding wraps from the outer cup into the obi.
    v,u=np.mgrid[0:45,0:7]/np.array((44,6))[:,None,None]
    aa=-1.22+1.90*v+(u-.5)*(.16+.09*sin(pi*v))
    yy=bust_seam(aa)*(1-v)+(14.28+.18*sin(aa))*v
    t.grid(topcloth,fitted(aa,yy,.106))
    t.wire(gold,fitted(aa[:,0],yy[:,0],.11),.011)
    # Raised collar and two curved front facings. The almond-shaped opening
    # frames the existing sternum painting. The shoulders stay entirely open.
    v,u=np.mgrid[0:71,0:29]/np.array((70,28))[:,None,None]
    y=18.36-2.64*v
    xx=np.array([15.72,16.05,16.38,16.7,17.0,17.35,17.70,18.0,18.36])
    ww=np.array([.93,1.20,1.27,1.17,1.01,.82,.66,.49,.33])
    broad=np.interp(y,xx,ww)
    opening=np.clip((y-16.88)/.99,0,1)
    gap=.52*np.maximum(0.,sin(pi*opening))**1.30
    for sign in (-1,1):
        x=sign*(gap+(broad-gap)*u)
        f=at(x,y,allowance=.093)
        t.grid(topcloth,f,flip=sign<0,uv=np.stack([.50+sign*(.06+.42*u),v],axis=-1))
        t.wire(gold,f[:, -1],.014)
        sel=(y[:,0]>16.88)&(y[:,0]<17.87)
        t.wire(gold,f[sel,0],.010)
        # A separate narrow back strap sinks into the top of the corset.
        ry=18.51-2.30*v
        rx=sign*(.30+.65*v+.12*sin(pi*v)+(u-.5)*(.14+.073*v))
        rf=at(rx,ry,True,.046)
        t.grid(topcloth,rf,flip=sign>0)
        t.wire(gold,rf[:,-1],.011)
    aa=(U-.5)*2*pi
    yy=18.58-.28*V-.075*cos(aa)
    collar=np.stack([(.399+.03*V)*sin(aa),yy,.673-(.427+.035*V)*cos(aa)],axis=-1)
    t.grid(topcloth,collar)
    t.wire(gold,collar[0],.014)
    # Pair of cord loops forms a small pankou at the throat.
    tau=np.linspace(0,2*pi,41)
    for sign in (-1,1):
        px=.048+sign*(.094-.082*cos(tau));py=18.23+.035*sin(tau)
        t.wire(gold,at(px,py,allowance=.095),.019)
    pin=at(np.array([.048]),np.array([18.21]),allowance=.112)[0]
    t.stone(jade,pin,(.058,.060,.052))
    top=14.64+.22*sin(a-.20)
    lower=13.79+.24*sin(a-.55)-.16*cos(a)
    y=top+(lower-top)*V
    t.grid(belt,shell(a,y,.17+.052*sin(pi*V),.012*cos(8*a+V)))
    ang=np.linspace(-pi,pi,145)
    for yy,rad in [(14.64+.22*sin(ang-.20),.023),(13.79+.24*sin(ang-.55)-.16*cos(ang),.029)]:
        t.wire(gold,shell(ang,yy,.193),rad)
    # Twin bias folds cross the waist, converging at a pierced jade bi on the hip.
    for off in (0,.087):
        k=np.linspace(0,1,60)
        aa=-2.65+3.43*k
        yy=(14.43+.18*off)*(1-k)+14.05*k-.20*sin(pi*k)+off*sin(pi*k)
        t.wire(gold,shell(aa,yy,.237+.096*k**6),.015)
    ca=.78;cy=14.05
    center=shell(np.asarray(ca),np.asarray(cy),.32)
    tangent=np.array([cos(ca),0,sin(ca)])
    normal=np.array([sin(ca),0,-cos(ca)])
    up=np.array([0,1.,0])
    def loop(mat,ctr,rx,ry,r):
        s=np.linspace(0,2*pi,57)[:,None]
        t.wire(mat,ctr+rx*cos(s)*tangent+ry*sin(s)*up,r)
    loop(gold,center,.215,.265,.030)
    loop(jade,center+normal*.028,.158,.189,.066)
    t.stone(iv,center+normal*.08+up*.19,(.048,.056,.043))
    # Silk ties settle along the skirt curvature, ending in unequal carved drops.
    for dd,fall in [(-.09,1.06),(.10,1.43)]:
        k=np.linspace(0,1,41)
        aa=ca+dd+.07*sin(pi*k)-.10*k
        yy=cy-.17-fall*k
        line=shell(aa,yy,.39+.04*sin(pi*k))
        t.wire(gold,line,.022)
        p=line[-1];t.stone(iv,p,(.060,.067,.060))
        t.stone(jade,p-up*.167,(.075,.136,.071))
    t.finish()
    model.name='清漪 · 兰汀短裳'
    assert len(model.faces)*3==sum(m.vertex_count for m in model.materials)
    return model


if __name__=='__main__':
    make_textiles()
    tmp=Path(tempfile.gettempdir())
    # Both use the same tailoring. The artist's scene already has Liuting's
    # scalp geometry baked in; the live PMX retains the full hair wardrobe.
    for source,destination in [(OUT/'lingyun.pmx',OUT/'lanxu.pmx'),
                               (tmp/'qingyi-liuting-edit.pmx',tmp/'qingyi-lanxu-edit.pmx')]:
        model=tailor(PMX['load'](str(source)))
        PMX['save'](str(destination),model,add_uv_count=3)
        print(destination,len(model.vertices),len(model.faces))
