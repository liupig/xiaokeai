"""Build the pearl-silk 小可爱 look against Qingyi's existing PMX skeleton."""
from pathlib import Path
from math import pi
import tempfile
import numpy as np
from PIL import Image
from scipy.interpolate import PchipInterpolator

from build_lanxu import PMX, OUT, TEX, DESIGN, Tailor, cut_lining

sin,cos=np.sin,np.cos
YUE="yuexiao"
ART=DESIGN/"qingyi-yueluo-concept.png"


def lattice(n,m):
    return np.mgrid[:n+1,:m+1]/np.array([n,m])[:,None,None]


def curve(points,t):
    p=np.array(points,dtype=float)
    return PchipInterpolator(np.linspace(0,1,len(p)),p,axis=0)(t)


def textures():
    # A radial silk sheen, fine warp and shallow shadow-weave are all on the
    # cloth UVs, so the folds and their embroidery stay registered in motion.
    n=768;v,u=lattice(n-1,n-1)
    for name,top,foot in [('silk',(245,237,232),(227,212,219)),('petal',(232,221,241),(217,196,232)),
                            ('gauze',(236,229,249),(211,191,231))]:
        du=u-.52
        gloss=.042*cos(2*pi*(3.1*u+.18*v))+.018*cos(2*pi*(7*u-.16*v))
        shade=-.07*abs(du)**1.4-.03*v + gloss+.004*sin(2*pi*345*(u+v*.13))
        rgb=((1-v[...,None])*np.array(top)+v[...,None]*np.array(foot))*(1+shade[...,None])
        for k in range(3):
            stem=.19+.25*k+.10*sin(4.3*v+k*.63)
            mark=np.exp(-((u-stem)/.0024)**2)
            for l in range(4):
                h=.19+l*.16+.025*k
                leaf=((u-stem-.044*sin(13*(v-h)))/.024)**2+((v-h)/.041)**2
                mark+=np.exp(-((leaf-1)/.23)**2)*.63
            rgb+=mark[...,None]*[10,10,7]
        border=np.exp(-((v-.978)/.0027)**2)
        rgb=rgb*(1-.57*border[...,None])+np.array([242,221,183])*.57*border[...,None]
        Image.fromarray(np.uint8(np.clip(rgb,0,255))).save(TEX/(YUE+'-'+name+'.jpg'),quality=94)
    # Follow real painted strands in the approved rear view. Use a strip
    # entirely inside the hair's silhouette, then extend its cross-strand detail.
    art=np.asarray(Image.open(ART).convert('RGB'),dtype=float)
    h,w=1024,384
    v,u=np.mgrid[:h,:w]/np.array([h-1,w-1])[:,None,None]
    y=84+v*238
    mid=np.interp(y,[84,115,145,175,205,245,282,322],[1058,1042,1031,1022,1014,1006,1001,1007])
    spread=np.interp(y,[84,150,220,280,322],[11,12,15,14,12])
    from scipy.ndimage import map_coordinates,gaussian_filter
    coords=[y,mid+(u-.5)*2*spread]
    tex=np.stack([map_coordinates(art[:,:,i],coords,order=1) for i in range(3)],axis=-1)
    tone=gaussian_filter(tex.mean(axis=(1,2)),50)
    drift=.023*sin(v*6.4+.3)+.012*sin(v*11)
    g=u+drift
    rng=np.random.default_rng(114)
    yarn=gaussian_filter(rng.normal(0,1,900),1.0)*4.5
    grain=np.interp(g%1,np.linspace(0,1,len(yarn)),yarn)
    value=6*cos(2*pi*(4.3*g+.10*sin(pi*v)))+3*cos(2*pi*(9.5*g+.09*v))+grain
    value+=5.1*cos(2*pi*(1.18*u+.04*v))+.11*(tone[:,None]-tone.mean())
    top=np.array([192,167,180]);end=np.array([232,188,201])
    rgb=top+(end-top)*v[...,None]+value[...,None]+17*sin(pi*v)[...,None]
    Image.fromarray(np.uint8(np.clip(rgb,0,255))).save(TEX/(YUE+'-locks.jpg'),quality=95)
    # Unwrap the lit crest of one continuous S-wave. The dark turn around
    # its axis is baked into the cross-section, independent of the camera.
    guide=[(1039,145),(1037,173),(1033,194),(1029,212),(1019,232),(1003,248),(995,264)]
    line=curve(guide,v[:,0])
    sy,sx=np.broadcast_arrays(line[:,1,None],line[:,0,None]+(u-.5)*23)
    stripe=np.stack([map_coordinates(art[:,:,i],[sy,sx],order=1) for i in range(3)],axis=-1)
    delta=stripe-stripe.mean(axis=(0,1))
    brush=rgb+delta*.58+3.5*np.sin(pi*v[...,None])
    Image.fromarray(np.uint8(np.clip(brush,0,255))).save(TEX/(YUE+'-tress.jpg'),quality=95)
    # Cloth-only samples inside the embroidery. The original fold gradation
    # and the woven thread colours survive even on a close camera.
    def swatch(file,rails,tint):
        v,u=lattice(511,383)
        edges=curve(rails,v[:,0]);x=edges[:,0,None]*(1-u)+edges[:,1,None]*u
        y=np.broadcast_to(edges[:,2,None],x.shape)
        rgb=np.stack([map_coordinates(art[:,:,i],[y,x],order=1) for i in range(3)],axis=-1)
        rgb=(rgb-rgb.mean(axis=(0,1)))*.79+np.asarray(tint)
        Image.fromarray(np.uint8(np.clip(rgb,0,255))).save(TEX/(YUE+'-'+file+'.jpg'),quality=95)
    swatch('brocade',[(491,502,174),(481,503,190),(471,505,210),(472,504,229),(475,503,248),(481,501,256)],
           (232,218,229))
    swatch('embroidery',[(510,520,317),(501,521,326),(493,523,337),(488,524,349),
        (481,517,362),(475,506,373),(471,492,384),(464,475,393)],(225,205,228))
    # Extract only the two swept hairline panels. The studio reference is
    # never applied to the face and is not shipped in full with the live model.
    fringe=np.asarray(Image.open(ART).crop((440,10,600,110)).resize((960,600),Image.BICUBIC).convert('RGB'),float)
    fringe=.97*fringe+np.array([12,9,11])
    Image.fromarray(np.uint8(np.clip(fringe,0,255))).save(TEX/(YUE+'-fringe.jpg'),quality=96)
    Image.open(ART).crop((480,240,586,446)).resize((424,824),Image.BICUBIC).convert('RGB').save(TEX/(YUE+'-carving.jpg'),quality=95)
    v,u=lattice(255,255)
    x,y=(u-.5)*2,(v-.5)*2
    rr=np.minimum(1,np.hypot(x,y))
    flash=np.exp(-((x+.27+.31*y)/.37)**2-((y+.22)/.75)**2)
    edge=rr**2.3
    core=(1-edge[...,None])*[125,154,158]+edge[...,None]*[211,191,166]
    core+=flash[...,None]*[24,36,46]+np.exp(-((x+.31)/.15)**2-((y+.47)/.11)**2)[...,None]*35
    Image.fromarray(np.uint8(np.clip(core,0,255))).save(TEX/(YUE+'-moonstone.jpg'),quality=97)
    im=Image.open(TEX/'Up_EX.png').convert('RGBA')
    lum=np.array(im.convert('L'),float)/255
    c=(1-lum[...,None])*np.array([161,145,166])+lum[...,None]*np.array([251,243,235])
    out=Image.fromarray(np.uint8(c)).convert('RGBA');out.putalpha(im.getchannel('A'))
    out.save(TEX/(YUE+'-underbust.png'))


class Atelier(Tailor):
    mode='body'
    def material(self,name,image=None,color=(1.,1.,1.),alpha=1,hair=False):
        mat=self.cloth(name,rgb=color);mat.name=mat.name_e=('MoonHair_' if hair else 'Moon_')+name
        if image:mat.texture=self.tex(YUE+'-'+image)
        mat.diffuse=(*color,alpha)
        return mat

    def weights(self,p):
        x,y,z=p
        if self.mode=='body':return super().weights(p)
        if self.mode=='hair':
            # Release only the lower lengths from head rotation.
            t=np.clip((19.12-y)/3.1,0,1);t=float(t*t*(3-2*t))
            names=['頭','上半身2'];ws=[1-t,t]
        elif self.mode=='head':names=['頭'];ws=[1.]
        else:
            side='左' if self.mode=='arm+' else '右'
            a=np.array([abs(x),y,z])
            shoulder=np.array([1.28,17.64,.85]);elbow=np.array([3.70,15.89,.79])
            along=np.dot(a-shoulder,elbow-shoulder)/np.dot(elbow-shoulder,elbow-shoulder)
            t=float(np.clip((along-.80)/.40,0,1));t=t*t*(3-2*t)
            names=[side+'腕',side+'ひじ'];ws=[1-t,t]
        w=PMX['BoneWeight']()
        if len(names)==1:w.bones=[self.bones[names[0]]]
        else:w.type=w.BDEF2;w.bones=[self.bones[n] for n in names];w.weights=[ws[0]]
        return w


def jewel_leaf(t,mat,wire,root,tip,spread,width,bulge,openwork=False):
    root,tip,spread=map(np.asarray,(root,tip,spread))
    v,u=lattice(16,8);d=u*2-1
    w=sin(pi*v)**.78
    facing=np.cross(tip-root,spread);facing/=max(np.linalg.norm(facing),1e-8)
    if facing[2]>0:facing=-facing
    p=root+(tip-root)*v[...,None]+spread*(width*w*d)[...,None]+facing*(bulge*w*(1-.84*d*d))[...,None]
    if not openwork:t.grid(mat,p)
    t.wire(wire,p[:,0],.012,6);t.wire(wire,p[:,-1],.012,6)
    t.wire(wire,p[:,4],.010 if openwork else .007,6)


def lock(t,mat,path,width,thick,normal,phase=0,root=.55,n=43):
    v=np.linspace(0,1,n);line=curve(path,v)
    tangent=np.gradient(line,axis=0);tangent/=np.maximum(np.linalg.norm(tangent,axis=1,keepdims=True),1e-9)
    face=np.broadcast_to(np.asarray(normal,dtype=float),line.shape).copy()
    face-=tangent*np.sum(face*tangent,axis=1,keepdims=True)
    face/=np.maximum(np.linalg.norm(face,axis=1,keepdims=True),1e-9)
    across=np.cross(tangent,face)
    q=np.linspace(0,2*pi,19)[None,:]
    span=np.interp(v,[0,.09,.28,.58,.79,.93,1],[root,.80,1.,.98,.85,.44,.012])
    angle=.26*sin(2*pi*v+phase)+.10*sin(pi*v)
    axis=cos(angle)[:,None]*across+sin(angle)[:,None]*face
    norm=cos(angle)[:,None]*face-sin(angle)[:,None]*across
    # Slight asymmetric fluting carries a highlight off the centre of each lock.
    x=cos(q)*span[:,None]*width
    z=sin(q)*span[:,None]*thick*(1+.09*cos(4*q+.38*v[:,None]))
    points=line[:,None]+x[...,None]*axis[:,None]+z[...,None]*norm[:,None]
    uv=np.stack(np.broadcast_arrays(.49+.47*cos(q+.07*sin(v[:,None]*4+phase)),v[:,None]),axis=-1)
    t.grid(mat,points,uv=uv)


def hairfall(t,hair,crest,frame_face=True):
    t.mode='hair'
    # Underlayer of the fall closes sightlines at the nape. Its tapered end
    # terminates inside the separate waist-length tresses.
    v,u=lattice(45,76);a=2*pi*u
    y=20.05-(6.62+.24*cos(3*a))*v
    w=(.68+.50*sin(pi*v*.85))*(1-.93*v**3)
    deep=(.32+.10*sin(pi*v))*(1-.82*v**2)
    cx=.10*sin(2*pi*v+.3)*v;cz=1.06+.64*sin(pi*v*.80)+.25*v
    p=np.stack([cx+w*sin(a),y,cz+deep*cos(a)],axis=-1)
    t.grid(hair,p,uv=np.stack([u*3,v],axis=-1))
    # A fan of layered sections, with shared root direction and staggered
    # endings. Long S-curves soften the outside profile from both sides.
    for j in range(13):
        q=(j-6)/6;ab=abs(q)
        end=12.40+1.18*ab**1.15+.39*sin(j*2.13)
        path=[(.30*q,21.29-.11*ab,.48+.18*(1-ab)),(.69*q,21.08-.13*ab,1.15-.18*ab)]
        for k,(y,width,depth) in enumerate([(20.44,1.02,1.64),(19.58,1.19,1.76),(18.68,1.31,1.85),
                                            (17.48,1.46,2.16),(16.24,1.41,2.38),(15.13,1.33,2.48),
                                            (14.00,1.52,2.34),(end,1.19,2.23)]):
            wave=(.27+.11*ab)*sin(k*1.18+q*2.3+.18)*min(1,k/2.7)
            x=width*q+wave+.12*sin(j*.72+k*.65)*k/7
            z=depth-.55*ab**2+.13*cos(q*7+k*.83)
            path.append((x,y,z))
        lock(t,hair,path,.267+.050*cos(j*1.1),.134+.028*(1-ab),(.46*q,0,.96-.36*ab),phase=j*.92,root=.055,n=56)
    # Overlapping crests, each at a different depth. A curl sweeps across its
    # neighbour at the shoulder and opens up into a fork near the waist.
    for j,q in enumerate([-.80,-.34,.15,.62]):
        path=[(.42*q,21.15,.97),(.88*q,20.53,1.68-.17*q*q),
              (1.14*q+.10,19.63,1.98-.24*q*q),(1.29*q+.22,18.79,2.11-.28*q*q),
              (1.28*q+.08,17.94,2.32-.30*q*q),(1.31*q-.38,16.99,2.49-.26*q*q),
              (1.33*q-.18,16.09,2.64-.25*q*q),(1.43*q+.36,15.11,2.73-.18*q*q),
              (1.39*q+.42,14.40,2.71-.21*q*q),(1.13*q+.09,13.66,2.65-.22*q*q),
              (.92*q-.18,12.65+.29*j,2.50-.20*q*q)]
        lock(t,crest,path,.20+.025*sin(j),.115,(q*.33,0,1),phase=1.4+j*.32,root=.012,n=70)
    for side in (-1,1):
        s=side
        # Outer sections run behind the shoulder. Two fine blades divide from
        # the thicker sweep near its free end.
        for j in range(3):
            d=j*.12
            path=[(.71*s,20.78,.67+d),(.99*s,20.04,.68+d),(1.03*s,19.30,.60+d),
                  ((1.10+d)*s,18.57,.62+d),((1.31+d)*s,17.63,1.18+d),
                  ((1.60+d)*s,16.75,1.64+d),((1.46+d)*s,15.95,1.75+d),
                  ((1.26+d)*s,15.09,1.94+d),((1.44+d)*s,14.31,2.02+d),
                  ((1.20+d)*s,13.66+j*.17,2.08+d)]
            lock(t,hair,path,.32-.055*j,.110-.018*j,(.90*s,0,.41),phase=.69*j+s)
        if not frame_face:
            continue
        # Face-framing locks travel outside the cheek and in front of the clavicle.
        path=[(.77*s,20.50,-.07),(1.02*s,19.91,-.14),(.94*s,19.29,-.24),
              (.90*s,18.72,-.33),(1.04*s,18.06,-.40),((1.32+.10*s)*s,17.46,-.75),
              ((1.39+.08*s)*s,16.95,-1.19),(1.22*s,16.65,-1.46),
              (1.22*s,16.29-.13*s,-1.47)]
        lock(t,crest,path,.238,.106,(.34*s,0,-1),phase=s*.7)
        for j in range(2):
            p=np.asarray(path).copy()
            g=np.linspace(0,1,len(p));p[:,0]+=s*(.15+.08*j)*sin(pi*g)+s*.14*j*g
            p[:,2]-=.045+.027*j;p[:,1]+=.16*j*g
            lock(t,hair,p,.053-.016*j,.031,(.26*s,0,-1),phase=1.9+j,root=.14,n=36)


def hairstyle(t):
    from yuexiao_pattern import waves
    from yuexiao_jewels import mount_combs, stone_cut
    from yuexiao_hair import Groom, parted_crown
    hair=t.material('Silk','fibre-base.jpg',hair=True)
    crest=t.material('Tress','fibre-base.jpg',hair=True)
    fibres=t.material('Fibres','fibre-cards.png',hair=True)
    filament=t.material('Filament','fibre-base.jpg',hair=True)
    groom=Groom(t,crest,fibres,filament)
    fringe=t.material('Fringe','parted-fringe.jpg',hair=True)
    wire=t.material('Silver',color=(.85,.73,.69),hair=True)
    pearl=t.material('Pearl',color=(.96,.87,.84),hair=True)
    parted_crown(t,hair,fringe,groom)
    waves(t,hair,groom)
    crystal=mount_combs(t,wire,pearl)
    # Fine forehead drop at the centre part, fastened into the front hairline.
    f=curve([(0,21.40,.22),(-.014,21.27,-.09),(-.016,21.04,-.33),
             (.008,20.78,-.49),(.017,20.50,-.533),(.018,20.18,-.552)],np.linspace(0,1,38))
    anchor=np.clip((f[:,1]-20.54)/.38,0,1)
    f[:,1]-=.085*anchor
    f[:,2]+=.126*anchor
    t.wire(wire,f,.014,7)
    stone_cut(t, crystal, f[-1],
              [1.,0,0],[0,1.,0],[0,0,-1.],(.056,.095,.041),'temple',np.array([1019.2,107.8]),[2.7,3.2],True)
    t.mode='body'


def filter_faces(model,keep):
    cursor=0;out=[]
    for mat in model.materials:
        n=mat.vertex_count//3;faces=model.faces[cursor:cursor+n];cursor+=n
        selected=keep(mat,faces)
        mat.vertex_count=len(selected)*3;out.extend(selected)
    model.faces=out


def build():
    from yuexiao_pattern import SheetForm, dressed
    from yuexiao_hair import bake_fibres
    from yuexiao_torso import Torso
    from yuexiao_sandals import sandals, remove_painted_straps
    from yuexiao_jewels import bake_jewels
    textures();bake_fibres();bake_jewels()
    model=PMX['load'](str(OUT/'lingyun.pmx'));t=SheetForm(model)
    from yuexiao_portrait import bind_eye_art, fit_portrait
    fit_portrait(model)
    bind_eye_art(t)
    m=[t.material('Silk','silk.jpg'),t.material('Petal','pattern.jpg',alpha=.90),t.material('Gauze','organza.png',alpha=.54),
       t.material('Gold',color=(.67,.50,.32)),t.material('Silver',color=(.86,.75,.68)),
       t.material('Pearl',color=(.95,.87,.81))]
    cursor=0
    for mat in model.materials:
        count=mat.vertex_count//3
        if mat.name=='Down_Skin':
            cut_lining(model,model.faces[cursor:cursor+count],levels=(11.38,11.46),
                       colors=((222,210,214),(218,201,210)),target='yuexiao-lining.png')
            remove_painted_straps()
            break
        cursor+=count
    t.torso=Torso(t)
    dressed(t,m);sandals(t);hairstyle(t)
    save_look(t,YUE,'小可爱 · 双视图定稿',replace_bodice=True)


def save_look(t,slug,title,lining='yuexiao-lining.png',replace_bodice=False):
    model=t.m
    def remove_old(mat,faces):
        if slug==YUE and mat.name=='Face_':
            from yuexiao_portrait import without_undereye_mark
            return without_undereye_mark(model,faces)
        if mat.name in ('Magnolia pleated silk','Down_Bow','Down_Sleeve','Cloth_Sleeve','Cloth_Sleevein','Up_Metal','Cloth_Glove'):return []
        if slug==YUE and mat.name in ('Down_Metal','Down_Jewel'):return []
        if mat.name in ('Up_','Up_in'):
            if replace_bodice:return []
            mat.texture=t.tex(YUE+'-underbust.png')
            return [tr for tr in faces if max(model.vertices[i].co[1] for i in tr)>15.32]
        if mat.name=='Down_Skin':mat.texture=t.tex(lining)
        return faces
    filter_faces(model,remove_old);t.finish()
    if slug == YUE:
        from yuexiao_portrait import prepare_face_overlays
        from yuexiao_proportions import lengthen_legs
        from yuexiao_scalp import fit_scalp
        prepare_face_overlays(model)
        lengthen_legs(model)
        fit_scalp(t)
    model.name=title
    model.name_e='Xiaokeai'
    assert len(model.faces)*3==sum(m.vertex_count for m in model.materials)
    PMX['save'](str(OUT/(slug+'.pmx')),model,add_uv_count=3)
    def editable(mat,faces):
        alt=('Hair_','Lingyun_','Liuting_','Fengguan_')
        return [] if mat.name.startswith(alt) or mat.name in ('Cloth_Hairpin','QingyiHairLining') else faces
    filter_faces(model,editable)
    PMX['save'](str(Path(tempfile.gettempdir())/f'qingyi-{slug}-edit.pmx'),model,add_uv_count=3)
    print('Moon edition:',len(model.vertices),'vertices,',len(model.faces),'active triangles')


if __name__=='__main__':
    build()
