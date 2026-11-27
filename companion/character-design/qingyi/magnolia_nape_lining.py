"""Finish the nape and inner seam of the fitted magnolia costume."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.interpolate import LinearNDInterpolator
from scipy.ndimage import distance_transform_edt


def ramp(a, b, value):
    t = np.clip((value-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def tuck_nape(vertices, faces, skin, fibre, dest):
    ids, inverse = np.unique(faces, return_inverse=True)
    triangles = inverse.reshape(-1, 3)
    p = np.array([vertices[i].co for i in ids])
    uv = np.array([vertices[i].uv for i in ids])
    normals = np.array([vertices[i].normal for i in ids])
    ring = 1 - np.linalg.norm(uv-.5, axis=1)/(.5*124/128)
    # Retain the joined facial/neck rim and the top of the vault. Draw the
    # mastoid in and lift the underside under the existing long curtains.
    x, y, z = p.T.copy()
    side = ramp(.20,.62,abs(x)) * ramp(.24,.71,z)
    tuck = side*ramp(.0,.20,ring)*(1-ramp(20.64,21.36,y))
    p[:,0] -= np.sign(x)*.12*tuck
    p[:,1] += .13*tuck
    a,b,c = p[triangles].transpose(1,0,2)
    area = np.cross(b-a,c-a)
    if np.median((area*normals[triangles[:,0]]).sum(1)) < 0:
        area *= -1
    updated = np.zeros_like(p)
    for corner in triangles.T:
        np.add.at(updated,corner,area)
    updated /= np.maximum(1e-12,np.linalg.norm(updated,axis=1,keepdims=True))
    influence = ramp(.001,.15,tuck)[:,None]
    updated = normals*(1-influence) + updated*influence
    updated /= np.maximum(1e-12,np.linalg.norm(updated,axis=1,keepdims=True))
    for j in np.flatnonzero(tuck>1e-8):
        vertices[ids[j]].co = p[j]
        vertices[ids[j]].normal = updated[j]

    # The fitted cap has a welded disk UV. Sample the existing hair pigment
    # along the head in 3D so the strands turn continuously around the nape.
    size = 1024
    v,u = (np.mgrid[:size,:size]+.5)/size
    dx,dy = u-.5,v-.5
    radius = np.hypot(dx,dy)
    clip = np.minimum(1,.477/np.maximum(radius,1e-9))
    xyz = LinearNDInterpolator(uv,p)(.5+dx*clip,.5+dy*clip)
    assert np.isfinite(xyz).all()
    x,y,z = xyz.transpose(2,0,1)
    az = np.arctan2(x,z-.40)/(2*np.pi)
    sweep = az + .033*np.sin((y-20.36)*2.1+az*4) + .028*(y-20.65)
    field = (sweep*2.5 + .035*np.sin(sweep*21) + .5) % 1
    source = np.asarray(Image.open(fibre).convert('RGB'))
    h,w = source.shape[:2]
    pigment = cv2.remap(source,((.012+.975*field)*w/4).astype('f'),
                       ((.24+.51*np.clip((22.3-y)/2.15,0,1))*h).astype('f'),
                       cv2.INTER_LINEAR).astype('f')
    # Short terminal hairs break up the hairline. Its skin margin is wider
    # towards the forehead and narrower behind the jaw and above the neck.
    angle = np.arctan2(dy,dx)
    distance = 1-radius/(124/256)
    wisps = .011*np.sin(51*angle+.52*np.sin(17*angle))+.005*np.sin(133*angle)
    hairline = .034 + .085*ramp(21.18,21.80,y) + .018*ramp(.7,1.05,z) + wisps
    cover = ramp(hairline-.019,hairline+.032,distance)[...,None]
    base = cv2.resize(np.asarray(Image.open(skin).convert('RGB')), (size,size), interpolation=cv2.INTER_CUBIC)
    Image.fromarray(np.rint(base*(1-cover)+pigment*cover).astype('uint8')).save(dest)


def shorts_hem(x,z):
    # A shallow tulip hem outside, lower across the seated gluteal fold.
    return 11.94+.24*ramp(.45,1.65,abs(x))-.14*ramp(.38,1.15,z)


def clear_thigh_charm(image):
    """Remove the painted donor charm from the front thigh's UV island."""
    h,w=image.shape[:2]
    # Centre line on the 2048 px donor atlas, from the old hem to the red tip.
    y0,y1=round(726*h/2048),round(833*h/2048)
    x0,x1=round(1026*w/2048),round(1087*w/2048)
    yy,xx=np.mgrid[y0:y1,x0:x1]
    y=(yy[:,0]+.5)*2048/h
    centre=np.interp(y,[726,738,754,770,784,798,812,824,833],
                         [1066,1067,1068,1067,1063,1058,1051,1045,1045])
    offset=(xx+.5)*2048/w-centre[:,None]
    # Reconstruct the local gradient across the stroke on each scanline. The
    # lining is composited afterwards, so its curved piping stays intact.
    sides=[]
    for distance in (-15,15):
        samples=np.rint((centre[:,None]+distance+np.arange(-1,2))*w/2048-.5).astype(int)
        sides.append(image[yy[:,:1],samples,:3].mean(axis=1))
    t=np.clip((offset+15)/30,0,1)[...,None]
    clean=sides[0][:,None]*(1-t)+sides[1][:,None]*t
    amount=(1-ramp(9,14,np.abs(offset)))*ramp(726,731,y)[:,None]*(1-ramp(827,833,y))[:,None]
    region=image[y0:y1,x0:x1,:3]
    region[:]=np.rint(region*(1-amount[...,None])+clean*amount[...,None]).astype(np.uint8)


def finish_lining(vertices, faces, source, dest):
    ids, local = np.unique(faces, return_inverse=True)
    tri = local.reshape(-1,3)
    pts = np.asarray([vertices[i].co for i in ids])
    uv = np.asarray([vertices[i].uv for i in ids])
    image = np.array(Image.open(source).convert('RGBA'))
    clear_thigh_charm(image)
    h,w = image.shape[:2]
    # Work in the final leg proportions. The leg openings curve down on the
    # inside so the existing fabric continues across the lowest saddle.
    near = (abs(pts[:,0])<.01)&(pts[:,1]>12)&(pts[:,1]<13)&(abs(pts[:,2]-.23)<.29)
    saddle = pts[near,1].min()
    assert 12.48 < saddle < 12.57
    sample = pts[tri]
    take = (sample[:,:,1].max(1)>11.75)&(sample[:,:,1].min(1)<14.97)
    mask = np.zeros((h,w),np.float32)
    pigment = np.zeros((h,w,3),np.float32)
    for f in tri[take]:
        pix = uv[f]*[w,h]-.5
        lo=np.maximum(0,np.floor(pix.min(0)).astype(int))
        hi=np.minimum([w-1,h-1],np.ceil(pix.max(0)).astype(int))
        a,b,c=pix
        det=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if abs(det)<1e-8 or (hi<lo).any(): continue
        sy,sx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
        v=((sx-a[0])*(c[1]-a[1])-(sy-a[1])*(c[0]-a[0]))/det
        t=((b[0]-a[0])*(sy-a[1])-(b[1]-a[1])*(sx-a[0]))/det
        inside=(v>=-1e-5)&(t>=-1e-5)&(t+v<=1.00001)
        x,y,z=(pts[f[0]]+v[...,None]*(pts[f[1]]-pts[f[0]])
                +t[...,None]*(pts[f[2]]-pts[f[0]])).transpose(2,0,1)
        height=y-shorts_hem(x,z)
        blend=inside*ramp(-.012,.012,height)*(1-ramp(14.90,14.96,y))
        binding=1-ramp(.045,.078,height)
        seam=np.exp(-((height-.103)/.016)**2)
        dye=np.array([203.,190.,207.])+binding[...,None]*[20.,17.,13.]
        shade=4*np.cos(3.6*x+.65*y)+1.3*np.sin(64*y+12*z)+1.2*np.cos(48*x-15*z)
        dye+=shade[...,None]+seam[...,None]*[19.,15.,9.]
        sl=np.s_[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
        written=(blend>0)&(blend>=mask[sl])
        pigment[sl][written]=dye[written]
        np.maximum(mask[sl],blend,out=mask[sl])
    # Fill gutters as well as triangles so a bilinear sample on the UV split
    # cannot pick up the old dark texels. Only extend strongly covered texels.
    distance,nearest=distance_transform_edt(mask<=.98,return_indices=True)
    amount=(1-ramp(2,7,distance))*mask[tuple(nearest)]
    use=amount>mask
    mask[use]=amount[use]
    pigment[use]=pigment[nearest[0][use],nearest[1][use]]
    image[:,:,:3]=np.uint8(np.clip(np.rint(image[:,:,:3]*(1-mask[...,None])+pigment*mask[...,None]),0,255))
    Image.fromarray(image).save(dest)


def finish_nape_and_lining(model, texture_dir):
    target = Path(texture_dir)
    start=0
    for mat in model.materials:
        end=start+mat.vertex_count//3
        if mat.name in ('Down_Skin','QingyiScalp'):
            slot=model.textures[mat.texture]
            source=Path(slot.path)
            part='lining' if mat.name=='Down_Skin' else 'nape'
            dest=target/f'yuexiao-strapless-{part}.png'
            faces=np.asarray(model.faces[start:end],dtype=np.int32)
            if part=='lining':
                finish_lining(model.vertices,faces,source,dest)
            else:
                tuck_nape(model.vertices,faces,source,source.with_name('yuexiao-fibre-base.jpg'),dest)
            slot.path=str(dest.resolve())
        start=end
