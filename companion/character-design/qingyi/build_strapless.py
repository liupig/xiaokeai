"""Fit a separate magnolia bodice to the released, rigged Xiaokeai model."""
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

import numpy as np
import cv2
from PIL import Image
from scipy.interpolate import PchipInterpolator
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from build_lanxu import DESIGN, OUT, PMX, TEX, Tailor
from build_yuexiao import filter_faces, lattice
from magnolia_satin import DressAtlas, neck_edge, pearl_setting
from magnolia_fit import DressForm, attach_skin
from magnolia_nape_lining import finish_nape_and_lining
from magnolia_neckline_light import apply_neckline_light
from magnolia_physics import bind_magnolia_physics
from magnolia_skirt_fit import fit_skirt
from yuexiao_pattern import measured_front_layers
from yuexiao_decals import bind_expression_art
from yuexiao_portrait import prepare_face_overlays
from yuexiao_torso import Torso, centre, smooth


SLUG = 'yuexiao-strapless'
SKIN = ('Up_Skin', 'Down_Skin', 'QingyiTorso')


def clear_neckline(model, groups, coords, rise):
    # Sweep just the two complete foreground locks behind the shoulders.
    # Component selection keeps the fine fibres paired with their parent lock.
    faces=np.concatenate([f for k,f in groups.items() if k.startswith('MoonHair_') and len(f)])
    ids,ix=np.unique(faces,return_inverse=True)
    ix=ix.reshape(-1,3)
    graph=coo_matrix((np.ones(3*len(ix),np.uint8),
                      (ix.ravel(),np.roll(ix,-1,axis=1).ravel())),shape=(len(ids),len(ids)))
    _,cc=connected_components(graph,directed=False)
    x,y,z=coords[ids].T
    pick=(abs(x)>.55)&(abs(x)<1.73)&(y<17.52)&(z<-.75)
    ids=ids[np.isin(cc,np.unique(cc[pick]))&(y<19.63)]
    x,y,z=coords[ids].T
    levels=[15.8,16.4,17.,17.5,18.,18.5,18.95,19.30,19.64]
    sweep=PchipInterpolator(levels,[2.95,3.03,2.97,2.60,1.87,1.09,.57,.23,0])
    spread=PchipInterpolator(levels,[.09,.14,.27,.15,.09,.105,.10,.055,0])
    heights=np.clip(y,levels[0],levels[-1])
    dx=np.sign(x)*spread(heights)
    for i,pos in zip(ids,np.stack([x+dx,y+rise,z+sweep(heights)],axis=1)):
        model.vertices[i].co=pos
    normals=np.array([model.vertices[i].normal for i in ids])
    normals[:,1]-=normals[:,0]*np.sign(x)*spread.derivative()(heights)+normals[:,2]*sweep.derivative()(heights)
    normals/=np.linalg.norm(normals,axis=1,keepdims=True).clip(1e-8)
    for i,n in zip(ids,normals):
        model.vertices[i].normal=n


def neckline_complexion(tailor, mat, faces, coords, art):
    """Repaint the exposed skin which used to sit beneath the halter collar."""
    rgba = np.array(Image.open(tailor.m.textures[mat.texture].path).convert('RGBA'))
    h,w = rgba.shape[:2]
    tint = np.zeros((h,w,3),np.uint8)
    mask = np.zeros((h,w),np.uint8)
    x,y,z = coords.T
    mix = (smooth((1.53-abs(x))/.31)*smooth((y-16.05)/.36)*
           smooth((18.02-y)/.35)*smooth((.24-z)/.48))
    faces = faces[np.max(mix[faces],axis=1)>.002]
    ids = np.unique(faces)
    uv = np.array([tailor.m.vertices[i].uv for i in ids])*[w-1,h-1]
    x,y,z = coords[ids].T
    # Project only the exposed skin between the two fabric edges and the
    # collarbones. Keep its graduated shadow registered with the new sternum.
    px = np.clip(524.6 + x*45.8,458,589)
    py = 224.7 - (y-16.54)*40.
    source = cv2.GaussianBlur(art[164:229,452:597],(0,0),.65)
    for face in np.searchsorted(ids,faces):
        tri=uv[face]
        lo=np.maximum(0,np.floor(tri.min(0)).astype(int))
        hi=np.minimum([w-1,h-1],np.ceil(tri.max(0)).astype(int))
        if (hi<lo).any():
            continue
        b,c=tri[1:]-tri[0];det=b[0]*c[1]-b[1]*c[0]
        if abs(det)<1e-7:
            continue
        yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
        xx=xx-tri[0,0];yy=yy-tri[0,1]
        u=(xx*c[1]-yy*c[0])/det;v=(b[0]*yy-b[1]*xx)/det
        bary=np.stack([1-u-v,u,v],axis=-1)
        region=np.s_[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
        alpha=np.uint8(255*np.clip(bary@mix[ids[face]],0,1))
        take=(bary.min(-1)>=-.002)&(alpha>mask[region])
        sx = bary@px[face]
        sy = np.clip(bary@py[face],167,neck_edge(sx)-1.9)
        sample = cv2.remap(source,(sx-452).astype('f'),(sy-164).astype('f'),cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REPLICATE).astype(float)
        colour = [245.,220.,218.] + (sample-[231.,199.,197.])*[1.05,1.02,1.00]
        tint[region][take]=colour[take].clip(0,255)
        mask[region][take]=alpha[take]
    # Continue the painted edge a few texels into chart gutters for mipmaps.
    empty=mask==0;kernel=np.ones((5,5),np.uint8)
    tint[empty]=cv2.dilate(tint,kernel)[empty]
    mask[empty]=cv2.dilate(mask,kernel)[empty]
    alpha=mask[...,None]/255.
    rgba[:,:,:3]=np.rint(rgba[:,:,:3]*(1-alpha)+tint*alpha)
    return Image.fromarray(rgba)


def bodice(tailor, body, materials, art):
    atlas = DressAtlas(art)
    satin = materials['Moon_Brocade']
    satin.texture = tailor.tex('yuexiao-strapless-satin.jpg')
    gold = materials['Moon_Gold']
    tailor.parts[satin] = []
    tailor.parts[gold] = []
    stations = [0,.20,.46,.73,.97,1.19,1.43,1.70,2.10,2.65,np.pi]
    # Scoop the side wing below the swept upper arm in a forward reach.
    # Carry that curve through the lower seam so the wing keeps its width.
    top = PchipInterpolator(stations,[16.61,16.96,17.22,17.18,16.84,16.08,15.66,15.57,15.61,15.68,15.73])
    under = PchipInterpolator(stations,[15.54,15.66,15.79,15.86,15.84,15.67,15.41,15.32,15.30,15.34,15.38])
    bottom = PchipInterpolator([0,.30,.80,1.35,1.75,2.23,np.pi],
                               [14.76,14.80,14.89,14.92,14.88,14.84,14.86])
    for sign in (-1,1):
        for cup in (False,True):
            v,u = lattice(47 if cup else 22,124)
            phi = np.pi*u
            fraction = v if cup else np.zeros_like(v)
            seam = .115*(1-fraction) + .110*np.sin(np.pi*fraction)
            if not cup:
                seam *= v
            overlap=.018 if sign<0 else -.062*smooth((1-fraction)/.30)
            angle = sign*phi + (seam + overlap)*(1-u)**2
            lo,hi = (under(phi),top(phi)) if cup else (bottom(phi),under(phi))
            h = lo + (hi-lo)*v
            edge_fade = smooth(v/.12)*smooth((1-v)/.12)
            ease = .029 + .004*np.exp(-((phi-.64)/.58)**2)
            ease += .009*np.exp(-((h-15.82)/.19)**2-((phi-.49)/.31)**2)
            ease += .038*np.exp(-((h-16.23)/.34)**2-((phi-.58)/.55)**2)
            front = 1-smooth((phi-.82)/.57)
            if cup:
                # Bias pleats fan from the waist flower into a taut outer edge.
                # Each tuck has its own curved path and tapers before the neckline.
                for level, height, fold_width in [(.30,.022,.083),(.60,.018,.089),(.91,.011,.091)]:
                    track = .055 + level*(1-np.exp(-1.81*phi)) + .13*np.sin(1.7*phi)
                    across=(v-track)/fold_width
                    ease += height*(np.exp(-across**2)-.45*np.exp(-((across+.98)/1.3)**2))*front*smooth(phi/.15)*edge_fade
                # The cloth spans the hollow between the two supported forms.
                ease += .050*np.exp(-(angle/.29)**2)*np.maximum(np.sin(np.pi*v),0.)**.85
                side_fold=np.exp(-((phi-1.24)/.38)**2)
                for t0,amplitude in ((.34,.017),(.58,.011)):
                    bias=(v-(t0+.21*(phi-1.05)))/.076
                    ease+=amplitude*side_fold*edge_fade*(np.exp(-bias*bias)-.38*np.exp(-((bias+1.24)/1.31)**2))
            if sign<0:
                ease += .012*(1-u)**2
            p = body.cloth_surface(angle,h,ease)
            uv=atlas.chart(sign,cup,u,v,p)
            tailor.grid(satin,p,flip=sign>0,uv=uv)
            if cup:
                # Fold the satin around its edge before applying the fine
                # metallic cord. The turned lip is also visible in profile.
                radial=np.stack([np.sin(angle[-1]),np.zeros_like(u[-1]),-np.cos(angle[-1])],axis=1)
                up=np.array([0.,1.,0.])
                rim=np.stack([p[-1],p[-1]+.004*radial+.005*up,
                              p[-1]-.004*radial+.009*up,p[-1]-.009*radial+.002*up])
                tailor.grid(satin,rim,flip=sign>0,uv=np.stack([uv[-1],uv[-1],uv[-2],uv[-2]]))
                tailor.wire(gold,rim[1],.0057,7)
                visible = phi[0]<1.58
                tailor.wire(gold,p[0,visible],.0055,7)
                if sign<0:
                    tailor.wire(gold,p[:,0],.0063,7)
    atlas.save()


def basque_chains(model,groups,coords,original,body,rise):
    # In dressed(), each pair of pearl cords is sewn immediately before a
    # 16-by-64 side sash. Keep every pearl and bring its terminal pin onto
    # the lower silk wing of this cut.
    silk=np.unique(groups['Moon_Silk'])
    runs=np.split(silk,np.flatnonzero(np.diff(silk)>1)+1)
    bands=[r for r in runs if len(r)==17*65 and abs(coords[r[0],1]-14.68)<.02]
    if len(bands)!=2:
        raise ValueError('Unable to locate the two sash bands')
    count=54*7+51*8+9*9*15
    ids=np.concatenate([np.arange(r[0]-count,r[0]) for r in bands])
    if not np.isin(ids,np.union1d(groups['Moon_Gold'],groups['Moon_Pearl'])).all():
        raise ValueError('Sash cords no longer match the donor pattern')
    x,y,z=coords[ids].T
    a=np.arctan2(x,centre(y)-z)
    h=y-.72*smooth((abs(a)-.28)/1.18)
    radial=np.stack([np.sin(a),np.zeros_like(a),-np.cos(a)],axis=1)
    relief=((coords[ids]-original.surface(a,y))*radial).sum(1)-.088
    gap=.036+.012*(a<0)*(1-abs(a)/np.pi)**2+.020*np.isin(ids,groups['Moon_Pearl'])
    coords[ids]=body.cloth_surface(a,h,gap)+relief[:,None]*radial
    for i in ids:model.vertices[i].co=coords[i]+[0,rise,0]
    return ids


def seat_flower(model, groups, coords, old, fitted, rise):
    # The original carved leaves are a separate batch immediately before
    # the arm jewellery. Transfer their relief to the new torso section.
    ids = np.arange(groups['Moon_ChasedMetal'].min(),groups['Moon_CuffSetting'].min())
    x,y,z = coords[ids].T
    ids = ids[(abs(x)<1.34)&(y>14.15)&(y<16.56)&(z<-.36)]
    x,y,z = coords[ids].T
    def hem_height(y):
        return y+.025*smooth((y-14.15)/.89)-.13*smooth((y-15.35)/.70)
    def shift(x,y):
        return (fitted(x,hem_height(y))-old(x,y))*smooth((y-14.15)/.89)
    relief = shift(x,y)
    coords[ids] = np.stack([x,hem_height(y),z+relief],axis=1)
    eps=.005
    dzdx=(shift(x+eps,y)-shift(x-eps,y))/(2*eps)
    dzdy=(shift(x,y+eps)-shift(x,y-eps))/(2*eps)
    dhdy=(hem_height(y+eps)-hem_height(y-eps))/(2*eps)
    norm=np.asarray([model.vertices[i].normal for i in ids])
    norm[:,0]-=norm[:,2]*dzdx
    norm[:,1]=(norm[:,1]-norm[:,2]*dzdy)/dhdy
    norm/=np.linalg.norm(norm,axis=1,keepdims=True).clip(1e-9)
    for i,n in zip(ids,norm):
        model.vertices[i].co=coords[i]+[0,rise,0]
        model.vertices[i].normal=n
    return ids


def save_model(path,model):
    staging=path.with_name('.'+path.stem+'-'+uuid4().hex+'.pmx')
    try:
        PMX['save'](str(staging),model,add_uv_count=3)
        staging.replace(path)
    finally:
        staging.unlink(missing_ok=True)


def build():
    model = PMX['load'](str(OUT/'yuexiao.pmx'))
    prepare_face_overlays(model)
    bind_expression_art(model,TEX)
    groups, cursor = {}, 0
    materials = {m.name:m for m in model.materials}
    for mat in model.materials:
        end = cursor+mat.vertex_count//3
        groups[mat.name] = np.asarray(model.faces[cursor:end],dtype=np.int32).reshape(-1,3)
        cursor = end
    # The fitted halter and its bindings were cut as a single batch between
    # the reconstructed skin and the first skirt panel in dressed().
    first = int(groups['Moon_Brocade'].min())
    end = int(groups['Moon_PearlHem'].min())
    assert first < groups['Moon_Brocade'].max() < end
    coords = np.array([v.co for v in model.vertices])
    rise = coords[first,1]-14.76
    assert .5 < rise < 2.
    coords[:,1] -= rise
    original = Torso.__new__(Torso)
    original.measure(coords[np.concatenate([groups[k] for k in SKIN])])
    layers = ('Moon_Petal','Moon_Brocade','Moon_PearlHem','Moon_Veil')
    original_front = measured_front_layers(coords[np.vstack([groups[k] for k in layers])],original)
    paint_faces = {k:groups[k] for k in SKIN}
    clear_neckline(model,groups,coords,rise)
    coords = attach_skin(model,groups,rise)
    body = DressForm(model,coords,np.concatenate([groups[k] for k in SKIN]))
    art = np.asarray(Image.open(DESIGN/'xiaokeai-magnolia-strapless-concept.png').convert('RGB'))
    tailor = Tailor(model)
    pearl_setting(tailor,materials,art)
    for name,filename in [('Up_Skin','yuexiao-strapless-skin.png'),
                          ('QingyiTorso','yuexiao-strapless-torso.png')]:
        image = neckline_complexion(tailor,materials[name],paint_faces[name],coords,art)
        ids, local = np.unique(groups[name],return_inverse=True)
        uv = np.asarray([model.vertices[i].uv for i in ids])
        positions = coords[ids]+[0,rise,0]
        apply_neckline_light(image,positions,uv,local.reshape(-1,3)).save(TEX/filename)
        materials[name].texture = tailor.tex(filename)
    start = len(model.vertices)
    bodice(tailor,body,materials,art)
    work = np.vstack((coords,[v.co for v in model.vertices[start:]]))
    cloth = np.vstack([tailor.parts[materials[k]] if k=='Moon_Brocade' else groups[k] for k in layers])
    fitted_front = measured_front_layers(work[cloth],body)
    ornament = seat_flower(model,groups,work,original_front,fitted_front,rise)
    chains=basque_chains(model,groups,work,original,body,rise)
    body.bind_at(model,chains,work)
    body.bind_at(model,ornament[work[ornament,1]>14.30],work)
    body.bind_at(model,np.arange(start,len(model.vertices)),work)
    for vertex in model.vertices[start:]:
        vertex.co = vertex.co + [0,rise,0]
    def replace_top(mat, faces):
        if mat.name in SKIN:
            return groups[mat.name].tolist()
        old = groups[mat.name]
        keep = (old.max(axis=1)<first)|(old.min(axis=1)>=end)
        assert np.all(keep|((old.min(axis=1)>=first)&(old.max(axis=1)<end)))
        return old[keep].tolist()+tailor.parts.get(mat,[])
    filter_faces(model,replace_top)
    materials['Moon_Brocade'].name = materials['Moon_Brocade'].name_e = 'Moon_MagnoliaSatin'
    model.name = '小可爱'
    model.name_e = 'Xiaokeai'
    model.comment = '本版作者：liupig\r\n服装：玉兰抹胸\r\n\r\n'+model.comment
    model.comment_e = 'Edition author: liupig\r\nOutfit: Magnolia\r\n\r\n'+model.comment_e
    finish_nape_and_lining(model,TEX)
    bind_magnolia_physics(model)
    fit_skirt(model)
    save_model(OUT/(SLUG+'.pmx'),model)
    filter_faces(model,lambda m,f: [] if m.name.startswith(('Hair_','Lingyun_','Liuting_','Fengguan_'))
                 or m.name in ('Cloth_Hairpin','QingyiHairLining') else f)
    save_model(Path(gettempdir())/f'qingyi-{SLUG}-edit.pmx',model)


if __name__ == '__main__':
    build()
