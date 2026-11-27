"""Fit the photographed wig and costume to Qingyi's neutral pose.

Pass --reference <original 1200x2670 photograph> to rebake the swatches.
Subsequent builds can reuse the exported material atlases.
"""
from argparse import ArgumentParser
from math import pi
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, gaussian_filter1d, map_coordinates

from build_lanxu import OUT, TEX, PMX, bodice_form, bust_seam, cut_lining, shell, torso_depth
from build_yuexiao import Atelier, curve, hairfall, jewel_leaf, lattice, lock, save_look

SLUG='yuexiao-photo'
sin,cos=np.sin,np.cos
# Coordinates on the straightened wig and on the unrotated bodice.
# Each pair follows its own two visible borders, from root to free edge.
BANGS=[
    ([(285,85),(269,83),(250,87),(225,104),(205,133),(195,163),(193,195),(189,218),(172,230)],
     [(288,176),(277,171),(264,182),(255,202),(247,219),(233,235),(216,241),(194,240),(172,230)]),
    ([(288,85),(308,82),(331,89),(356,107),(377,137),(386,167),(395,195),(407,222)],
     [(289,177),(302,171),(316,178),(328,193),(338,213),(355,232),(380,237),(407,222)])]
PLATE=[]


def plate(left,right,rise,rounding):
    PLATE.append((left,right,rise,rounding))


# Individual webs, holes between wings, raised gem setting and the two
# articulated pieces of the drop. No opaque plane spans a cut-out.
plate([(337,380),(328,371),(328,361),(339,350)],[(341,376),(339,369),(337,362),(339,350)],.09,.04)
plate([(345,371),(344,360),(349,347),(364,339)],[(349,372),(353,361),(360,354),(364,339)],.12,.07)
plate([(354,378),(365,373),(370,366),(373,349)],[(360,383),(373,380),(380,372),(373,349)],.11,.05)
plate([(329,376),(309,375),(290,385),(267,400),(239,409)],[(331,383),(312,391),(297,404),(266,412),(239,409)],.10,.085)
plate([(356,402),(364,417),(360,435),(369,456),(400,490)],[(363,395),(377,410),(379,433),(384,463),(400,490)],.11,.08)
plate([(315,399),(294,410),(275,415),(260,429)],[(321,401),(309,414),(285,424),(260,429)],.10,.06)
plate([(350,366),(337,377),(331,390),(334,401),(341,409)],[(350,366),(359,377),(362,387),(355,399),(341,409)],.195,.14)
plate([(313,445),(306,457),(308,469),(325,487)],[(318,445),(327,454),(331,464),(325,487)],.17,.09)
plate([(290,491),(278,501),(278,513),(281,520)],[(291,490),(300,499),(297,510),(281,520)],.145,.06)
plate([(267,546),(252,563),(242,585),(233,610),(229,636),(234,655)],
      [(270,546),(271,576),(264,602),(255,622),(242,645),(234,655)],.23,.15)
plate([(248,552),(223,562),(203,577),(182,600),(165,611)],
      [(248,552),(235,569),(216,585),(192,602),(165,611)],.125,.073)
plate([(272,549),(280,565),(277,586),(279,613),(265,638)],
      [(272,549),(291,567),(300,589),(299,612),(265,638)],.14,.080)
plate([(211,585),(203,611),(203,642),(200,672),(198,687)],
      [(216,581),(217,611),(213,641),(207,667),(198,687)],.115,.046)


def grid_between(pair,rows,cols):
    v,u=lattice(rows,cols)
    l,r=[curve(edge,v[:,0]) for edge in pair]
    return l[:,None]*(1-u[...,None])+r[:,None]*u[...,None]


def atlas(img,pieces,cols,rows,name,tile=(256,256),tint=None):
    tw,th=tile
    canvas=Image.new('RGB',(cols*tw,rows*th))
    source=np.asarray(img.convert('RGB'),dtype=float)
    for k,pair in enumerate(pieces):
        xy=grid_between(pair,th-1,tw-1)
        pixels=np.stack([map_coordinates(source[:,:,c],[xy[...,1],xy[...,0]],order=1) for c in range(3)],axis=-1)
        if tint is not None:
            pixels=(pixels-pixels.mean(axis=(0,1)))*.91+np.asarray(tint)
        canvas.paste(Image.fromarray(np.uint8(np.clip(pixels,0,255))),((k%cols)*tw,(k//cols)*th))
    canvas.save(TEX/(SLUG+'-'+name+'.jpg'),quality=96,subsampling=0)


def bake(photo):
    original=Image.open(photo).convert('RGB')
    if original.size!=(1200,2670):
        raise ValueError('Expected the original 1200 x 2670 image')
    wig=original.rotate(-11,resample=Image.BICUBIC,center=(735,733)).crop((442,459,1002,1139))
    cloth=original.crop((350,820,1040,1570))
    # The real chain is reconstructed in relief. Fill just its seven-pixel
    # track with the immediately adjacent hair before unwrapping the bangs.
    wig_base=np.array(wig)
    for row in range(89,179):
        mid=round(np.interp(row,[89,112,146,178],[282,286,286,289]))
        for j in range(-4,5):
            f=(j+5)/10
            wig_base[row,mid+j]=wig_base[row,mid-6]*(1-f)+wig_base[row,mid+6]*f
    atlas(Image.fromarray(wig_base),BANGS,2,1,'fringe',(420,360),tint=(208,186,188))
    atlas(cloth,[(p[0],p[1]) for p in PLATE],4,4,'metal',(192,180))
    atlas(cloth,[
        ([(322,112),(312,146),(306,182),(310,228),(303,269),(293,309),(277,344)],
          [(359,114),(357,148),(355,184),(349,231),(341,273),(321,309),(282,344)]),
        ([(386,135),(391,166),(395,199),(397,243),(399,295),(400,342),(402,375)],
          [(429,137),(443,171),(449,204),(441,248),(465,290),(473,342),(464,375)])],
          2,1,'pearl-weave',(320,560),tint=(236,230,237))
    atlas(cloth,[([(65,479),(81,475),(107,463),(132,454),(158,446)],
                  [(105,514),(125,505),(146,496),(170,476),(188,465)])],
          1,1,'flounce',(416,416),tint=(228,222,234))
    v,u=lattice(767,319)
    rng=np.random.default_rng(1723)
    drift=.018*sin(2*pi*v+.2)+.008*sin(v*10)
    x=(u+drift)%1
    grain=np.interp(x,np.linspace(0,1,1200),gaussian_filter(rng.normal(size=1200),1.3)*9)
    tone=grain+6.8*cos(2*pi*x*3.05)+3.4*cos(2*pi*x*10.4)
    color=(1-v[...,None])*np.array([200,180,184])+v[...,None]*np.array([231,183,189])
    color+=13*sin(pi*v)[...,None]+tone[...,None]
    Image.fromarray(np.uint8(np.clip(color,0,255))).save(TEX/(SLUG+'-hair.jpg'),quality=95)
    lane=curve([(208,262),(200,298),(184,334),(162,364),(140,392),(120,420),(97,451),(77,474)],v[:,0])
    rgb=np.asarray(wig,dtype=float)
    extent=np.interp(v,[0,.30,.65,1],[10,16,21,15])
    xx=lane[:,0,None]+(u-.5)*2*extent; yy=np.broadcast_to(lane[:,1,None],u.shape)
    twist=np.stack([map_coordinates(rgb[:,:,c],[yy,xx],order=1) for c in range(3)],axis=-1)
    twist-=gaussian_filter(twist.mean(axis=1,keepdims=True),(40,0,0))
    strands=color+.83*twist+5*cos(2*pi*(u+.11*sin(4*v)))[...,None]
    Image.fromarray(np.uint8(np.clip(strands,0,255))).save(TEX/(SLUG+'-tress.jpg'),quality=95)
    # Fine asymmetric fibre fringes are cut from alpha. The dense central
    # band joins the solid lock underneath, so side views retain hair volume.
    pattern=.5+.5*sin(2*pi*(x*84+.16*sin(2*pi*(4*x+v))))
    edge=.20+.13*v+.07*sin(8*v)
    d=np.minimum(u,1-u)
    alpha=np.clip((d-.014)/edge,0,1)**.75
    alpha*=np.clip((pattern*.68+.47+.65*(d/edge-.15)),0,1)
    alpha*=np.clip((1-v+.012+.034*sin(u*242))/.13,0,1)
    def rgba(name,col,alpha):
        out=np.concatenate([col,np.clip(alpha,0,1)[...,None]*255],axis=-1)
        Image.fromarray(np.uint8(np.clip(out,0,255)),'RGBA').save(TEX/(SLUG+'-'+name+'.png'))
    rgba('wisps',color+8,alpha)
    # A continuous visible front section, sampled from the real hair only.
    # Its irregular opacity margin softens into the volumetric locks beneath.
    edges=([(197,250),(184,280),(165,316),(142,353),(117,390),(92,421),(68,449),(59,468),(65,483)],
           [(220,251),(217,283),(207,322),(191,357),(165,393),(137,422),(105,447),(82,465),(65,483)])
    points=grid_between(edges,767,319)
    section=np.stack([map_coordinates(rgb[:,:,c],[points[...,1],points[...,0]],order=1) for c in range(3)],axis=-1)
    section=(section-section.mean(axis=(0,1)))*1.13+np.array([212,184,190])
    section+=.73*grain[...,None]+5.4*sin(2*pi*(u+.08*v))[...,None]
    rgba('front-fall',section,alpha)
    # Soft fur wisps, separately mapped on overlapping shells and small tufts.
    length=.54+.26*np.interp(u,np.linspace(0,1,650),gaussian_filter(rng.random(650),.65))
    length+=.18*(.5+.5*sin(u*137+1.1))
    density=np.clip((length-v)/.18,0,1)*(.51+.49*pattern)
    fuzz=np.stack([237+4*grain/8+10*v,232+6*grain/8+10*v,240+6*grain/8+9*v],axis=-1)
    rgba('down',fuzz,density)


class Studio(Atelier):
    def fabric(self,name,file=None,**kw):
        m=self.material(name,**kw)
        if file:m.texture=self.tex(SLUG+'-'+file)
        return m

    def weights(self,p):
        if self.mode.startswith(('ankle','wrist')):
            side='左' if self.mode.endswith('+') else '右'
            joint='足首' if self.mode.startswith('ankle') else '手首'
            w=PMX['BoneWeight']();w.bones=[self.bones[side+joint]]
            return w
        return super().weights(p)

    def stone(self,mat,center,scale):
        # Use only as many facets as the projected jewellery can resolve.
        n=8 if max(scale)<.08 else 12
        lat=np.linspace(.002,pi-.002,n+1)[:,None];a=np.linspace(0,2*pi,2*n+1)[None]
        xyz=np.stack(np.broadcast_arrays(sin(lat)*cos(a),cos(lat),sin(lat)*sin(a)),axis=-1)
        self.grid(mat,np.asarray(center)+np.asarray(scale)*xyz)


def tile_uv(v,u,k,nx,ny):
    return np.stack([((k%nx)+.006+.988*u)/nx,((k//nx)+.006+.988*v)/ny],axis=-1)


def feather_puff(t,mat,c,rad,seed):
    # Soft overlapping shells at different radii fade into isolated tips.
    rng=np.random.default_rng(seed)
    c,rad=np.asarray(c),np.asarray(rad)
    for i in range(5):
        v,u=lattice(14,44)
        a=2*pi*u+.19*i+.14*sin(v*3+.72*i)
        phi=.008+(pi-.016)*v
        r=.74+i*.062+.035*sin(11*a+2*v+.7*i)
        xyz=np.stack([sin(phi)*cos(a),cos(phi),sin(phi)*sin(a)],axis=-1)
        uv=np.stack([u*4+.13*i,np.clip(.12+i*.115+.21*v,.01,.94)],axis=-1)
        t.grid(mat,c+rad*r[...,None]*xyz,uv=uv)
    for j in range(34):
        z=rng.uniform(-.94,.94);a=j*2.39996+seed
        d=np.array([np.sqrt(1-z*z)*cos(a),z,np.sqrt(1-z*z)*sin(a)])
        side=np.cross(d,[0,1,0]);side/=np.linalg.norm(side)
        v,u=lattice(6,6)
        center=c+rad*d*(.69+.48*v[...,None])
        size=(.21+.07*rng.random())*(1-.67*v)*(u*2-1)
        p=center+size[...,None]*rad*side
        t.grid(mat,p)


def drape_card(t,mat,path,width,facing,phase):
    v,u=lattice(43,12)
    sm=v[:,0];center=curve(path,sm)
    tangent=np.gradient(center,axis=0)
    lateral=np.cross(tangent,np.asarray(facing))
    lateral/=np.maximum(np.linalg.norm(lateral,axis=1,keepdims=True),1.e-8)
    w=np.interp(sm,[0,.12,.32,.80,.95,1],[.17,.74,1,.82,.42,.04])*width
    d=(u*2-1)
    curl=(.06+.025*sin(2*pi*v+phase))*(1-d*d)
    p=center[:,None]+(d*w[:,None])[...,None]*lateral[:,None]+curl[...,None]*np.asarray(facing)
    t.grid(mat,p)


def coiffure(t,down):
    hair=t.fabric('Silk','hair.jpg',hair=True)
    crest=t.fabric('Tress','tress.jpg',hair=True)
    wisps=t.fabric('Wisps','wisps.png',hair=True)
    photographed=t.fabric('FrontFall','front-fall.png',hair=True)
    fringe=t.fabric('Fringe','fringe.jpg',hair=True)
    pearl=t.fabric('Pearl',color=(.92,.86,.83),hair=True)
    wire=t.fabric('Silver',color=(.79,.67,.54),hair=True)
    blue=t.fabric('Glass',color=(.36,.58,.63),hair=True)
    opal=t.fabric('IrisGlass',color=(.67,.72,.86),hair=True)
    t.mode='head'
    v,u=lattice(36,90);a=2*pi*(u-.5)
    b=v*(1.10+.97*(1-cos(a))*.5+.33*sin(a)**2)+.001
    r=.017*cos(27*a+.6*b)*sin(b)**.8
    scalp=np.stack([(1.08+r)*sin(b)*sin(a),19.98+(1.49+r)*cos(b),.48-(1.08+r)*sin(b)*cos(a)],axis=-1)
    t.grid(hair,scalp,uv=np.stack([u*5,v*.58],axis=-1))
    for k,pair in enumerate(BANGS):
        v,u=lattice(60,31)
        xy=grid_between(pair,60,31)
        x=(xy[...,0]-300)*.0107
        y=21.51-(xy[...,1]-52)*.00875
        ell=np.clip(1-(x/1.26)**2-((y-19.99)/1.60)**2,.052,1.)
        side=np.minimum(1,abs(x)/1.26)
        z=.48-1.15*np.sqrt(ell)-.095*sin(pi*u)-.36*side**3
        # Sink the root margin tangentially into the crown. In profile a
        # real part has no vertical ledge at the top of the swept section.
        scalp_z=.48-1.08*np.sqrt(np.maximum(.032,1-(x/1.08)**2-((y-19.98)/1.49)**2))
        fade=np.clip(u/.43,0,1);fade=fade**2*(3-2*fade)
        fade=1-(1-fade)*(1-np.minimum(side,.99)**3)
        z=(scalp_z+.026)*(1-fade)+z*fade
        z-=.035*sin(pi*v)*cos(5*pi*u+.55*v)
        p=np.stack([x,y,z],axis=-1)
        t.grid(fringe,p,flip=k==0,uv=tile_uv(v,u,k,2,1))
        pts=p[21:,30,:].copy();e=np.linspace(0,1,len(pts))
        pts[:,1]-=.038*sin(pi*e);pts[:,2]-=.017
        pts[:,0]+=(-1 if k==0 else 1)*.071*e**2
        drape_card(t,wisps,pts,.026,(0,0,-1),k)
        # Two fine fringe ends lie separately against the outer brow.
        s=-1 if k==0 else 1
        for j in range(2):
            pts=[((.29+.06*j)*s,20.52,-.59),((.39+.05*j)*s,20.30,-.64),
                 ((.46+.10*j)*s,20.13,-.64),((.56+.12*j)*s,19.99-.035*j,-.58)]
            drape_card(t,wisps,pts,.024-.004*j,(.12*s,0,-1),j)
    hairfall(t,hair,crest,frame_face=False)
    # A broad fan of blush hair sweeps over each shoulder, with offsets in
    # depth as well as length so that the locks also separate in profile.
    t.mode='hair'
    for s in (-1,1):
        for j in range(5):
            f=j/4;wiggle=.18*sin(2.3*j)
            path=[((.73+.20*f)*s,20.65,.12+.48*f),((.93+.21*f)*s,19.90,-.13+.50*f),
                ((.87+.28*f)*s,19.17,-.30+.48*f),((.98+.32*f)*s,18.58,-.31+.43*f),
                ((1.06+.42*f)*s,18.02,-.62+.47*f),((1.30+.38*f)*s,17.49,-.91+.45*f),
                ((1.40+.22*f+wiggle)*s,17.02,-1.26+.53*f),((1.26+.27*f)*s,16.66,-1.51+.46*f),
                ((1.07+.45*f+wiggle)*s,16.24,-1.57+.46*f),((1.13+.40*f)*s,15.91+.24*sin(j*1.74),-1.41+.33*f)]
            lock(t,crest,path,.18-.065*f,.095-.030*f,(.32*s,0,-1),phase=j*.87+s,root=.25)
            pp=np.asarray(path);pp[:,2]-=.072
            drape_card(t,wisps,pp,.24-.067*f,(.30*s,0,-.96),j)
        # A separated tendril loops in towards the sternum below the broad wave.
        path=[(.91*s,19.43,-.32),(.87*s,18.70,-.45),(.96*s,18.14,-.69),
            (1.18*s,17.68,-1.02),(1.27*s,17.17,-1.46),(1.03*s,16.83,-1.59),
            (.90*s,16.49,-1.58),(1.02*s,16.12,-1.49)]
        drape_card(t,wisps,path,.13,(.14*s,0,-1),s*.7)
        # A single wide, convex sweep groups the five locks at the cheek.
        # It rolls forward at the shoulder and forks at a different height
        # on each side, just as the photographed hair does.
        v,u=lattice(54,29);d=2*u-1
        profile=[(.99,19.96,-.22,.16),(.96,19.54,-.34,.24),(.97,19.04,-.42,.27),
            (1.01,18.56,-.46,.28),(1.16,17.99,-.81,.32),(1.38,17.49,-1.06,.37),
            (1.50,17.07,-1.43,.39),(1.35,16.78,-1.65,.31),(1.12,16.48,-1.69,.23),
            (1.06+.16*s,16.25-.09*s,-1.65,.10),(1.19+.09*s,16.06-.16*s,-1.53,.01)]
        x,y,z,w=curve(profile,v[:,0]).T
        bias=(.08+.075*s)*sin(pi*v)*sin(1.55*pi*v)
        xx=s*(x[:,None]+w[:,None]*d+bias)
        zz=z[:,None]+.22*d+.19*d*d-.045*cos(3*pi*u+.74*v)
        yy=y[:,None]+.18*d*sin(pi*v*1.1)
        t.grid(photographed,np.stack([xx,yy,zz],axis=-1),flip=s>0)
    for j in range(8):
        q=(j-3.5)/4
        path=[(.69*q,21.08,1.20),(.98*q,20.39,1.75-.31*q*q),
            (1.26*q+.11,19.23,2.04-.42*q*q),(1.36*q+.21,18.30,2.27-.47*q*q),
            (1.38*q-.25,17.07,2.54-.32*q*q),(1.41*q-.07,15.94,2.74-.31*q*q),
            (1.40*q+.40,14.96,2.80-.26*q*q),(1.18*q+.23,13.88,2.74-.33*q*q),
            (.99*q-.25,12.28+.61*abs(q)+.18*cos(j*4),2.51-.25*q*q)]
        drape_card(t,wisps,path,.22,(.25*q,0,1),j*.83)
    t.mode='head'
    for s in (-1,1):
        c=np.array([s*1.08,20.19,-.02])
        feather_puff(t,down,c+np.array([.125*s,-.20,.41]),(.39,.57,.30),10+(s+1))
        horizontal=np.array([s*.88,0,.47]);up=np.array([0.,1.,0.]);front=np.array([.47*s,0,-.88])
        for j,(dx,dy,width) in enumerate([(.35,.27,.118),(.47,-.04,.141),(.31,-.28,.116),
                                       (-.18,-.22,.105),(-.18,.19,.105),(.06,.40,.084)]):
            axis=horizontal*dx+up*dy
            normal=(-dy*horizontal+dx*up)/np.linalg.norm(axis)
            tip=c+axis+front*.11
            jewel_leaf(t,opal if j in (0,3) else blue,wire,c,tip,normal,width*.79,.049)
            for f in (.39,.64):
                start=c+axis*f+front*(.053+.075*f)
                end=start+axis*.13+normal*(width*(.6 if j%2 else -.6))
                t.wire(wire,np.linspace(start,end,6),.005,5)
        t.stone(opal,c+.14*front,(.064,.077,.059))
        # Small pearls branch towards the crown like a comb of gypsophila.
        for j in range(6):
            a=np.linspace(0,1,20);dx=-.13+.105*j
            stem=c+a[:,None]*(dx*horizontal+(.42+.17*cos(j*.92))*up)+.045*sin(pi*a)[:,None]*front
            t.wire(wire,stem,.009,5)
            for row,tilt in [(9,-1),(14,1),(19,0)]:
                start=stem[row];tip=start+.083*tilt*horizontal+(.048+.027*(j%2))*up
                if tilt:t.wire(wire,np.linspace(start,tip,5),.006,5)
                t.stone(pearl,tip,(.030,.037,.029))
        for j in range(2):
            line=curve([c,c+(.15*j+.08)*horizontal-.19*up+.07*front,
                c+(.16*j+.04)*horizontal-(.46+.12*j)*up+.05*front],np.linspace(0,1,19))
            t.wire(wire,line,.009,5);t.stone(opal,line[-1],(.044,.063,.036))
    # Fine linked forehead ornament with an open marquise and a crystal drop.
    center=curve([(0,21.46,.32),(-.015,21.40,.03),(-.028,21.28,-.24),
             (-.033,21.04,-.49),(-.016,20.83,-.59),(.007,20.59,-.71),(.012,20.35,-.72)],np.linspace(0,1,56))
    center[:,0]-=.130
    center[:,2]-=.016
    t.wire(wire,center,.010,6)
    for i in range(5,51,5):t.stone(wire,center[i]+[0,0,-.014],(.025,.030,.023))
    root=center[-1];tip=root+[0,-.16,-.025]
    jewel_leaf(t,opal,wire,root,tip,[1,0,0],.060,.022,openwork=True)
    t.stone(opal,tip+[0,-.043,0],(.040,.071,.035))
    t.mode='body'


def metalwork(t,gold,pearl,opal):
    enamel=t.fabric('Carving','metal.jpg')
    recess=t.fabric('Engraving',color=(.29,.19,.14))
    blue=t.fabric('Moonstone',color=(.36,.55,.62))
    def place(x,y,depth):
        # Undo the shift of the pendant across the sitter's lifted thigh.
        # The waist and both swivel joints now share a standing centreline.
        origin=np.interp(y,[295,385,446,500,554,605,692],[367,348,316,294,266,247,213])
        x=(x-origin)*.0143
        h=14.83-(y-385)*.0148
        z=shell(np.zeros_like(h),h,.267)[...,2]+.095*x*x-depth
        return np.stack(np.broadcast_arrays(x,h,z),axis=-1)
    for j,(left,right,depth,bow) in enumerate(PLATE):
        v,u=lattice(24,10);xy=grid_between((left,right),24,10)
        p=place(xy[...,0],xy[...,1],depth+bow*sin(pi*u)*(.28+.72*sin(pi*v)))
        t.grid(enamel,p,uv=tile_uv(v,u,j,4,4))
        t.wire(gold,p[:,0],.013,6);t.wire(gold,p[:,-1],.013,6)
        if j in (3,4,8,9,10):
            # Recessed ribs alternate with a narrow polished ridge. These
            # give both wings their engraved feather structure at 3/4 view.
            for col in (3,6):
                line=p[4:-3,col,:].copy();line[:,2]-=.012
                t.wire(recess,line,.013 if j in (3,4) else .010,6)
    for coords,radius in [
       ([(342,409),(340,423),(324,430),(315,445)],.016),
       ([(326,486),(311,486),(300,489),(292,496)],.014),
       ([(282,518),(280,529),(268,541),(264,555)],.015),
       ([(370,351),(364,335),(362,316),(361,290)],.014),
       ([(242,555),(228,561),(218,560),(203,569)],.012),
       ([(283,565),(299,577),(307,591),(303,610),(295,630)],.021)]:
        pp=curve(coords,np.linspace(0,1,32))
        t.wire(gold,place(pp[:,0],pp[:,1],.16),radius,7)
    for px,py,r in [(318,449,.079),(312,472,.063),(281,519,.055),(306,598,.051),(303,611,.035)]:
        center=place(np.array(px),np.array(py),.19)
        t.stone(pearl,center,(r,.99*r,.70*r))
    # Raised, faceted marquises echo the cool reflections inside the two
    # silver settings. The supporting gallery can be seen from the side.
    for px,py,rx,ry,dz in [(348,385,.093,.177,.339),(249,600,.087,.252,.384)]:
        c=place(np.array(float(px)),np.array(float(py)),dz)
        v,u=lattice(6,8);a=u*2*pi
        rr=np.interp(v,[0,.20,.46,.68,1],[.004,.76,1,.79,.004])
        h=np.interp(v,[0,.20,.46,.68,1],[.065,.018,-.034,-.077,-.112])
        shape=np.stack([rx*rr*np.sign(cos(a))*abs(cos(a))**1.22,
                        ry*rr*np.sign(sin(a))*abs(sin(a))**.86,h],axis=-1)
        t.grid(blue,shape+c);t.wire(gold,shape[3]+c,.014,6)


def costume(t,down):
    silk=t.fabric('Silk','flounce.jpg');pearlcloth=t.fabric('Brocade','pearl-weave.jpg')
    petal=t.fabric('Petal','flounce.jpg')
    chiffon=t.fabric('Gauze','flounce.jpg',alpha=.39)
    silver=t.fabric('Silver',color=(.83,.76,.68))
    gold=t.fabric('Gold',color=(.78,.60,.38))
    opal=t.fabric('Opal',color=(.64,.79,.80));pearl=t.fabric('Pearl',color=(.94,.87,.80))
    skinmesh=t.fabric('Illusion',color=(.76,.59,.56))
    fitted=bodice_form(t.m);at=torso_depth(t.m)
    # Blush illusion mesh at the cut sides of the waist, closed under the
    # halter and skirt. The photograph shows this warm tone between them.
    v,u=lattice(26,120);a=(u-.5)*2*pi
    top=bust_seam(a)+.18;h=top+(13.90-top)*v
    t.grid(skinmesh,fitted(a,h,.071+.011*cos(4*a+v)))
    for s in (-1,1):
        v,u=lattice(63,41)
        # Crescent bust hem opening upwards towards the side waist. Neck
        # gathers release over each cup and return to a small waist point.
        a0=-.10+.10*v
        breadth=np.interp(v,[0,.12,.28,.43,.60,.81,1],[.34,.54,.94,1.20,1.30,1.25,1.17])
        x=s*(a0+u*(breadth-a0))
        hem=14.82+1.09*u**.97+.12*sin(pi*u)
        y=18.35+(hem-18.35)*v
        a=np.arcsin(np.clip(x/np.interp(y,[14.7,15.7,16.6],[1.18,1.28,1.38]),-.965,.965))
        r=.024*(sin(pi*v)**1.3+.60*v**3)*cos(2*pi*(4.5*u+.32*v))+.016*sin(2*pi*(7*u-.17*v))*v*v
        p=at(x,y,allowance=.110+.028*(s>0)+r)
        mix=np.clip((15.82-y)/.60,0,1);mix=mix*mix*(3-2*mix)
        under=fitted(a,y,.15+.022*(s>0))[...,2]
        p[...,2]=p[...,2]*(1-mix)+(under-r)*mix
        p[...,2]=np.minimum(p[...,2],gaussian_filter1d(p[...,2],3.5,axis=1)-.013)
        t.grid(pearlcloth,p,flip=s<0,uv=tile_uv(v,u,int(s>0),2,1))
        t.wire(silk,p[-1],.026,7);t.wire(silver,p[:,-1],.010,6)
        if s>0:t.wire(silk,p[:,0],.016,6)
        # A small rouleau follows the original under-bust edge.
        x=np.linspace(.05,1.15,46)*s;y=14.83+1.04*(abs(x)/1.15)**.92
        pp=at(x,y,allowance=.149)
        ang=np.arcsin(np.clip(x/1.30,-.95,.95));mix=np.clip((15.80-y)/.58,0,1)
        pp[...,2]=pp[...,2]*(1-mix)+fitted(ang,y,.174)[...,2]*mix
        t.wire(gold,pp,.011,6)
        # Back panels taper off the shoulder blades to reveal the centre back.
        v,u=lattice(24,14);ry=18.34-2.22*v
        rx=s*(.24+.63*v+(.19+.18*sin(pi*v))*(u-.5))
        t.grid(silk,at(rx,ry,True,.068),flip=s>0)
    v,u=lattice(13,70);a=(u-.5)*2*pi
    y=18.54-.29*v-.057*cos(a)+.029*cos(2*a+v)
    p=np.stack([(.40+.052*v)*sin(a),y,.67-(.439+.071*v)*cos(a)],axis=-1)
    t.grid(silk,p);t.wire(silk,p[0],.018,7)
    # A closed opaque scalloped underskirt supports the raised thigh side.
    v,u=lattice(42,152);a=(u-.5)*2*pi
    rise=1.02*np.exp(-((a+.79)/.62)**2)
    bias=.15*sin(a+.3)-.22*(1-cos(a))*.5+rise
    hem=10.26+bias+.27*cos(6*a+.31)+.095*cos(12*a-.1)
    h=14.47+(hem-14.47)*v
    fold=.035*cos(7*a+.22*v)+v**1.8*(.115*cos(10*a-.47)+.053*cos(16*a+.61*v))
    p=shell(a,h,.083+.19*v**2,fold);t.grid(silk,p)
    t.wire(silver,p[-1],.015,7);lip=p[-2].copy();lip[:,1]+=.035;t.wire(silk,lip,.019,6)
    # Cut each overskirt layer on the bias. Its ruffle gathers tightly at
    # the hip; the lower edge falls as an irregular translucent scallop.
    def flounce(a0,sweep,span,top,hem,lift,mat,phase):
        v,u=lattice(33,48);d=2*u-1
        a=a0+sweep*v+span*d*(.57+.44*sin(pi*v*.70))+.075*sin(pi*v)*(1-d*d)
        by=hem+.59*d*d+.16*cos(3*pi*u+phase)+.092*cos(7*pi*u)+.96*np.exp(-((a+.79)/.66)**2)
        y=top+(by-top)*v+.082*sin(2*pi*u)*sin(pi*v)
        ribs=.11*cos(2*pi*(2.6*u+.26*v)+phase)*v**1.3
        ribs+=.059*cos(2*pi*(6.1*u-.18*v))*v**2
        p=shell(a,y,.10+lift*np.minimum(v*3,1)+(.18+.17*sin(pi*u))*v*v,ribs)
        t.grid(mat,p);t.wire(silk,p[-1],.012,6)
        return p
    for side in (-1,1):
        s=side; bias=.21*s
        flounce(.42*s,.46*s,.78,14.51,10.47+bias,.14,petal,.9*s)
        flounce(.76*s,.48*s,.76,14.34,10.89+bias,.245,chiffon,.55*s)
        flounce(1.40*s,.61*s,.68,14.24,9.53+bias,.27,chiffon,1.17*s)
        flounce(2.01*s,.47*s,.73,14.36,9.91,.16,petal,.39*s)
        flounce(2.62*s,-.12*s,.68,14.38,9.66,.24,chiffon,.67*s)
        # Three short, crumpled organza loops at the hip, set behind the pin.
        for j in range(3):
            v,u=lattice(23,16);d=u*2-1
            a=s*(.88+.17*j+.55*v+.21*d*sin(pi*v))
            y=14.22+.05*j-1.09*v+.20*sin(pi*v)+.25*d*sin(pi*v)
            p=shell(a,y,.12+.23*sin(pi*v)**.80+.09*d*sin(pi*v))
            t.grid(chiffon,p);t.wire(silk,p[:,-1],.011,6)
        a=np.linspace(s*.19,s*2.80,107)
        h=14.77+.82*abs(sin(a))**1.50+.13*(1-cos(a))
        coords=shell(a,h,.19);t.wire(gold,coords,.018,6)
        # Pearl side chains visually bridge the blush mesh opening.
        aa=np.linspace(.69,1.49,32)*s
        yy=14.83+.72*np.linspace(0,1,32)-.57*sin(np.linspace(0,pi,32))
        pp=shell(aa,yy,.21)
        t.wire(gold,pp,.012,6)
        for idx in (4,9,14,19,24,29):
            r=.041+.014*sin(pi*idx/32);t.stone(pearl,pp[idx],(r,r*1.11,r))
    metalwork(t,gold,pearl,opal)
    accessories(t,chiffon,down,silver,gold,opal,pearl)


def accessories(t,chiffon,down,silver,gold,opal,pearl):
    for s in (-1,1):
        sign='+' if s==1 else '-'
        t.mode='arm'+sign
        axis=np.array([s*.811,-.585,0]);normal=np.array([s*.585,.811,0]);zaxis=np.array([0.,0.,1.])
        seat=np.array([s*2.47,16.77,.83])
        a=np.linspace(0,2*pi,57)
        # Offset rings wind diagonally around the arm. Their openings gather
        # below the glass petal and carry the little gold chain.
        for k in range(2):
            ring=seat+(.431*cos(a))[:,None]*normal+(.45*sin(a))[:,None]*zaxis
            ring+=(.31*k+.24*cos(a+.32*k))[:,None]*axis
            t.wire(silver if k==0 else gold,ring,.026-.007*k,7)
        # Curved glass cuff wraps the outside of the arm. One tip rises
        # towards the shoulder while the other slips back under the chain.
        v,u=lattice(27,14);theta=-1.58+2.28*v;d=2*u-1
        rim=cos(theta)[...,None]*normal+sin(theta)[...,None]*zaxis
        spread=.034+.16*sin(pi*v)**.82
        p=seat+(.47+.046*sin(pi*v)*(1-d*d))[...,None]*rim
        p+=(.18-.49*v+.28*sin(pi*v)+spread*d)[...,None]*axis
        t.grid(opal,p);t.wire(silver,p[:,0],.012,6);t.wire(silver,p[:,-1],.013,6)
        c=seat+axis*.37-.40*zaxis
        v=np.linspace(0,1,28)
        rail=c+v[:,None]*(axis*.50-normal*.25)-(.13*sin(pi*v))[:,None]*zaxis
        t.wire(gold,rail,.015,6)
        for j in (7,15,22):t.stone(gold,rail[j],(.040,.047,.030))
        c=rail[-1]+np.array([.04*s,-.15,0])
        feather_puff(t,down,c,(.235,.246,.202),20+s)
        for k in range(2):
            v,u=lattice(28,18);d=u*2-1
            length=.34+(4.01-.48*k)*v
            wave=.17+.27*sin(2*pi*v+.63*k)+.11*v
            depth=.12+.35*sin(pi*v*1.44+.43*k)
            center=seat+length[...,None]*axis+wave[...,None]*normal+depth[...,None]*zaxis
            breadth=(.06+.32*sin(pi*v)**.8+.08*v)*d
            p=center+breadth[...,None]*(normal*sin(pi*v+.5*k)[...,None]+zaxis*cos(pi*v+.5*k)[...,None])
            t.grid(chiffon,p);t.wire(silver,p[:,0],.008,5)
        t.mode='wrist'+sign
        wr=np.asarray(t.m.bones[t.bones[('左' if s>0 else '右')+'手首']].location)
        p=wr+.05*axis+.254*cos(a)[:,None]*normal+.232*sin(a)[:,None]*zaxis
        t.wire(silver,p,.019,7)
        t.mode='ankle'+sign
        ank=np.asarray(t.m.bones[t.bones[('左' if s>0 else '右')+'足首']].location)
        # The photo shows a short white down cuff above each open shoe.
        cen=ank+[0,.35,-.018];v,u=lattice(13,68);theta=2*pi*u
        for j in range(4):
            f=.78+.075*j+.13*sin(pi*v)
            p=cen+np.stack([(.32*f)*sin(theta),.23-.46*v+.045*sin(9*theta+.9*j),
                            (.35*f)*cos(theta)],axis=-1)
            t.grid(down,p,uv=np.stack([u*5+.2*j,.08+.86*v],axis=-1))
    t.mode='body'


def build(reference):
    if reference:bake(reference)
    t=Studio(PMX['load'](str(OUT/'lingyun.pmx')))
    down=t.fabric('Down','down.png')
    hairdown=t.fabric('Down','down.png',hair=True)
    costume(t,down);coiffure(t,hairdown)
    lining=SLUG+'-lining.png'
    cursor=0
    for mat in t.m.materials:
        count=mat.vertex_count//3
        if mat.name=='Down_Skin':
            cut_lining(t.m,t.m.faces[cursor:cursor+count],levels=(11.73,11.80),
                       colors=((218,207,210),(222,209,215)),target=lining)
            break
        cursor+=count
    save_look(t,SLUG,'小可爱 · 真人照片版',lining=lining)


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--reference')
    build(parser.parse_args().reference)
