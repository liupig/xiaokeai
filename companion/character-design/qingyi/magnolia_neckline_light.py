"""Bake local complexion and skin-response changes in the dressed PMX's coordinates."""
import cv2
import numpy as np
from PIL import Image


def neckline_values(xyz, finish):
    x, y, z = xyz.T
    x = np.abs(x)
    front = np.clip((.03-z)/.58, 0., 1.)
    front *= front*(3.-2.*front)
    # Follow the upper arc of each fitted cup. Its inner end descends towards
    # the sternum and its outer end turns away towards the arm.
    span = (x-.76)/.76
    top = 18.79-.46*span**2
    below_arc = top-y
    taper = np.exp(-1.2*span**4)
    crown = taper*np.exp(-((below_arc-.205)/.225)**2)
    crest = np.exp(-((x-.88)/.42)**2-((below_arc-.15)/.135)**2)
    # Half-tone just above the turn gives the dome a readable top contour
    # even when the renderer fills the front of the figure with ambient light.
    turn = taper*np.exp(-((below_arc+.09)/.145)**2)
    shoulderward = np.exp(-((x-1.32)/.28)**2-((y-18.31)/.42)**2)
    inner = np.exp(-(x/(.16+.17*np.clip(y-17.88,0.,1.)))**2-((y-18.13)/.44)**2)
    upper = np.exp(-((x-.67)/.51)**2-((y-18.83)/.20)**2)
    if finish:
        # R is warm scatter, G is roughness, B is the view-dependent specular lobe.
        # A is inverse coverage of the broad reflected lobe. An ordinary RGB
        # mask samples as A=1, so pre-existing skins use their original finish.
        channels=(.055*crown+.10*shoulderward+.10*inner,
                  -.105*crown-.040*crest+.055*inner+.055*turn,
                  .40*crown+.14*crest-.105*inner-.085*turn,
                  -.74*(.56*crown+.44*crest))
        return np.column_stack(channels)*front[:,None]*255.
    # Broad value and hue transitions support the rounded form in flat toon light.
    # The localized specular reflection itself is supplied by the finish map.
    return front[:,None]*(
        crown[:,None]*[25.,28.,28.]+crest[:,None]*[13.,15.,15.]
        -turn[:,None]*[12.,16.,15.]
        -inner[:,None]*[16.,20.,19.]
        -shoulderward[:,None]*[7.,12.,11.]
        -upper[:,None]*[3.,5.,5.])


def apply_neckline_light(image, positions, uv, faces, *, finish=False):
    pixels = np.asarray(image.convert('RGBA') if finish else image).copy()
    h,w = pixels.shape[:2]
    p = positions[faces]
    # Include triangles that cross the working volume, including chart seams.
    selected = ((p[:,:,0].min(1)<1.88)&(p[:,:,0].max(1)>-1.88)
                &(p[:,:,1].min(1)<19.20)&(p[:,:,1].max(1)>17.38)
                &(p[:,:,2].min(1)<.03))
    ids, local = np.unique(faces[selected],return_inverse=True)
    t = uv[ids]*[w,h]-.5
    corners = local.reshape(-1,3)
    values = neckline_values(positions[ids],finish)
    lo = np.maximum(np.floor(t.min(0)).astype(int)-5,0)
    hi = np.minimum(np.ceil(t.max(0)).astype(int)+5,[w-1,h-1])
    size = tuple((hi-lo+1)[::-1])
    field = np.zeros((*size,values.shape[1]),np.float32)
    covered = np.zeros(size,np.uint8)
    t -= lo
    for face in corners:
        tri=t[face]
        a,b=tri[1:]-tri[0]
        det=a[0]*b[1]-a[1]*b[0]
        if abs(det)<1.e-7: continue
        left,top=np.maximum(np.floor(tri.min(0)).astype(int),0)
        right,bottom=np.minimum(np.ceil(tri.max(0)).astype(int),np.array(size[::-1])-1)
        yy,xx=np.mgrid[top:bottom+1,left:right+1]
        dx,dy=xx-tri[0,0],yy-tri[0,1]
        u=(dx*b[1]-dy*b[0])/det
        v=(a[0]*dy-a[1]*dx)/det
        use=(u>=0)&(v>=0)&(u+v<=1)
        if not use.any(): continue
        field[yy[use],xx[use]]=np.column_stack((1-u[use]-v[use],u[use],v[use]))@values[face]
        covered[yy[use],xx[use]]=1
    # Extend signed values into the gutter without taking a channel-wise max.
    for _ in range(4):
        count=cv2.boxFilter(covered,cv2.CV_32F,(3,3),normalize=False)
        edge=(covered==0)&(count>0)
        total=cv2.boxFilter(field,-1,(3,3),normalize=False)
        field[edge]=total[edge]/count[edge,None]
        covered[edge]=1
    area=pixels[lo[1]:hi[1]+1,lo[0]:hi[0]+1,:values.shape[1]]
    area[:]=np.clip(np.rint(area+field),0,255).astype(np.uint8)
    return Image.fromarray(pixels)
