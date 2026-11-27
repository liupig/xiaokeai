"""Register the magnolia bodice's satin, embroidery and roughness in one UV space."""
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import distance_transform_edt

from build_lanxu import TEX


RESPONSE = Path(__file__).with_name('magnolia-studio-response.npz')


def linear_rgb(srgb):
    return np.where(srgb<=.04045,srgb/12.92,((srgb+.055)/1.055)**2.4)


def balanced_pigment(image):
    """Separate the sheet's colour from the preview studio's diffuse and
    specular response. The same intrinsic pigment can then be lit from any
    angle in the viewer or in Blender."""
    target=linear_rgb(np.asarray(image).astype('f')/255)
    result=target.copy()
    size=image.width//2
    with np.load(RESPONSE) as plates:
        for row in range(2):
            for col in range(2):
                tile=np.s_[row*size:(row+1)*size,col*size:(col+1)*size]
                gain=cv2.resize(plates['gain'][row,col].astype('f'),(size,size),interpolation=cv2.INTER_CUBIC)
                glint=cv2.resize(plates['glint'][row,col].astype('f'),(size,size),interpolation=cv2.INTER_CUBIC)
                dye=(target[tile]-.90*glint)/np.maximum(gain,.28)
                dye=np.clip(dye,target[tile]*.46,np.minimum(.99,target[tile]*1.65))
                result[tile]=target[tile]+.86*(dye-target[tile])
    srgb=np.where(result<=.0031308,12.92*result,1.055*np.maximum(0,result)**(1/2.4)-.055)
    return Image.fromarray(np.uint8(np.clip(np.rint(255*srgb),0,255)))


def neck_edge(x):
    # Traced top edge of the satin in the approved frontal drawing.
    return np.interp(x,[455,460,465,472,479,486,494,504,514,524,528,536,546,558,568,576,583,589,592],
                       [224,212,206,202.8,201.4,202,204.5,209,216,225,226,217,208,203.5,203.5,205.8,210.5,220,231])


class DressAtlas:
    size = 768

    def __init__(self, art):
        self.art = art
        self.colour = Image.new('RGB',(2*self.size,2*self.size))
        self.surface = Image.new('RGB',self.colour.size)

    def swatch(self, polygon, x, y):
        points=np.asarray(polygon,np.int32)
        origin=points.min(axis=0)-3
        end=points.max(axis=0)+4
        art=self.art[origin[1]:end[1],origin[0]:end[0]]
        valid=cv2.fillPoly(np.zeros(art.shape[:2],np.uint8),[points-origin],1)
        _,nearest=distance_transform_edt(valid==0,return_indices=True)
        return cv2.remap(art[tuple(nearest)],(x-origin[0]).astype('f'),(y-origin[1]).astype('f'),
                         cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE).astype(float)

    def chart(self, sign, cup, u, v, panel):
        n = self.size
        row, col = int(not cup), int(sign>0)
        yy,xx = np.mgrid[:n,:n]
        s = np.clip((xx-3)/(n-7),0,1)
        t = np.clip((yy-3)/(n-7),0,1)
        # Transfer distances on the visible garment, rather than angular
        # distances around the bust. A bias fold thus keeps its drawn slope
        # across the projecting cup and rolls around the side seam.
        projection = sign*panel[...,0]/(20.+panel[...,2])
        outer = np.argmax(projection[:,:panel.shape[1]//2+1],axis=1)
        spread = projection[np.arange(len(outer)),outer]-projection[:,0]
        registered = (projection-projection[:,:1])/spread[:,None]
        registered[np.arange(projection.shape[1])[None,:]>=outer[:,None]]=1.
        front = np.clip(cv2.remap(registered.astype('f'),(s*(u.shape[1]-1)).astype('f'),
                                  (t*(u.shape[0]-1)).astype('f'),cv2.INTER_CUBIC),0,1)
        seam = 526.2 + 8.2*(1-t) + 8.0*np.sin(np.pi*t)
        edge = 456.8 if sign<0 else 589.3
        x = seam+(edge-seam)*front
        bound_x = 527.4 + (edge-527.4)*front
        crest = neck_edge(bound_x)
        foot = np.interp(front,[0,.28,.64,.86,1],[269,267,261,256,244])
        # Register texture height in projected space as well. The lower roll
        # and the top slope have markedly different depths in the side view.
        py=(panel[...,1]-17.1)/(20.+panel[...,2])
        progress=(py-py[:1])/(py[-1:]-py[:1])
        rowpos=np.clip(cv2.remap(progress.astype('f'),(s*(u.shape[1]-1)).astype('f'),
                                 (t*(u.shape[0]-1)).astype('f'),cv2.INTER_CUBIC),0,1)
        y = foot*(1-rowpos)+crest*rowpos

        ivory = [(458,217),(463,209),(471,204),(479,203),(488,204),(500,209),
                 (514,218),(526,229),(535,244),(538,255),(536,259),(522,262),
                 (517,259),(512,262),(488,255),(471,248),(460,238)]
        lilac = [(531,227),(539,217),(551,208),(563,205),(575,207),(581,210),
                 (586,218),(586,230),(581,241),(572,249),(553,257),(544,259),(541,247)]
        origin = np.array([452,195])
        rgb=self.swatch(ivory if sign<0 else lilac,x,y)
        base = np.array([216.,200.,200.] if sign<0 else [206.,184.,206.])
        face=np.clip((.47-s)/.20,0,1)
        face*=face*(3-2*face)
        # Draft the wrapping half from the second view. Its pale bias lines
        # turn around the side of the cup and disappear beneath the arm.
        around=np.clip((s-.30)/.30,0,1)
        side_top_x=1164-22*around
        side_top_y=207+26*around
        side_foot_x=1162-15*around
        side_foot_y=255-9*around
        profile_x=side_top_x*t+side_foot_x*(1-t)+14*np.sin(np.pi*t)*(1-.88*around)
        profile_y=side_top_y*t+side_foot_y*(1-t)
        side=self.swatch([(1142,234),(1150,225),(1162,211),(1165,207),(1173,215),
                          (1178,225),(1177,235),(1171,246),(1160,253),(1154,253),(1148,243)],
                         profile_x,profile_y)
        side+=np.array([0,-3,4] if sign>0 else [4,2,-1])
        rgb=face[...,None]*rgb+(1-face[...,None])*side
        back=np.clip((s-.50)/.21,0,1)
        back*=back*(3-2*back)
        back_sample=self.swatch([(1054,257),(1069,254),(1085,249),(1097,247),(1090,269),
                                 (1081,282),(1074,285),(1062,278)],1067+17*t+5*np.sin(4*s),
                                280-27*t+2*np.sin(6.1*s))
        rgb=rgb*(1-back[...,None])+back_sample*back[...,None]
        if not cup:
            base = np.array([210.,189.,204.])
            rgb=.56*back_sample+.44*base+(3*np.cos(2*np.pi*(1.5*s+.12*t)))[...,None]
            rgb -= (8.5*face*np.exp(-((1-t)/.115)**2))[...,None]*[.81,1.02,.79]
        elif sign>0:
            # The leading ivory petal casts a small contact shadow on the
            # lavender bias. It narrows continuously into the sweetheart notch.
            edge_u=(.018+.062*np.clip((1-t)/.30,0,1))/np.pi
            rgb-=(11*np.exp(-((s-edge_u)/.017)**2)*(.2+.8*np.sin(np.pi*t)**.6))[...,None]*[.86,1,.84]

        if cup:
            # Two fine couched branches follow the reference's left and
            # right petals. Supersampling keeps single threads fine up close.
            lines = ([[(477,211),(479,219),(482,224),(489,231),(502,238),(518,251)],
                      [(482,224),(481,229),(483,234)],[(489,231),(495,232),(501,235)]]
                     if sign<0 else
                     [[(536,238),(543,231),(552,225),(563,221),(570,215)],
                      [(545,230),(547,220),(554,212)],[(557,224),(563,231),(568,232)]])
            ink = np.zeros((82*8,144*8),np.uint8)
            for path in lines:
                nodes=np.asarray(path)
                curve=PchipInterpolator(np.arange(len(nodes)),nodes)(np.linspace(0,len(nodes)-1,90))
                pts=np.int32(np.round((curve-origin)*8))
                cv2.polylines(ink,[pts],False,255,2,cv2.LINE_AA)
            thread=cv2.remap(ink,((x-452)*8).astype('f'),((y-195)*8).astype('f'),cv2.INTER_LINEAR)/255.*face
        else:
            # Muted jacquard sprouts on the basque, visible in the side view.
            stem = .27+.24*t+.043*np.sin(4.2*t)
            thread = .41*np.exp(-((s-stem)/.0024)**2)
            for h in (.19,.40,.66):
                for hand in (-1,1):
                    k = (t-h)/.19
                    leaf = stem+hand*.039*np.sin(np.pi*k)
                    thread += .29*np.exp(-((s-leaf)/.0021)**2)*((k>0)&(k<1))
        warp=np.sin(2*np.pi*(xx*.21+.037*yy+.115*yy*s+1.42*np.sin(yy*.005+2*s)))
        weft=np.sin(2*np.pi*(yy*.32-.054*xx))
        rib=.68*warp+.32*weft
        rgb += (1.7*rib)[...,None]
        rgb += thread[...,None]*(np.array([230,211,185])-rgb)*.54
        lum=(rgb-base)@np.array([.21,.72,.07])
        surf=np.stack([126+17*rib+63*thread,214-.45*lum-44*thread+5*weft, 2+224*thread],axis=-1)
        for dest, data in ((self.colour,rgb),(self.surface,surf)):
            dest.paste(Image.fromarray(np.uint8(np.clip(data,0,255))),(col*n,row*n))
        return np.stack([(col*n+3.5+(n-7)*u)/(2*n),(row*n+3.5+(n-7)*v)/(2*n)],axis=-1)

    def save(self):
        pigment=balanced_pigment(self.colour) if RESPONSE.exists() else self.colour
        pigment.save(TEX/'yuexiao-strapless-satin.jpg',quality=97,subsampling=0)
        self.surface.save(TEX/'yuexiao-magnolia-finish.png')


def pearl_setting(tailor, materials, art):
    # Retain the carved leaf UVs. The upper rosette on the strapless sheet
    # has a small pearl clutch, a shorter central leaf and a warmer setting.
    filename = 'yuexiao-strapless-filigree.jpg'
    old = np.array(Image.open(TEX/'yuexiao-filigree.jpg').convert('RGB'))
    py,px = np.mgrid[:old.shape[0],:old.shape[1]]
    y=240+(py+.5)/4
    x=484+(px+.5)/4
    sy=np.interp(y,[240,246,260,272,280,289,302,317,340],[251,257,267,279,285,293,304,318,340])
    sx=529.7+(x-532)*1.015
    registered=cv2.remap(art,sx.astype('f'),sy.astype('f'),cv2.INTER_CUBIC)
    mix=np.clip((325-y)/10,0,1)[...,None]
    rgb=registered*mix+old*(1-mix)
    Image.fromarray(np.uint8(rgb)).save(TEX/filename,quality=97,subsampling=0)
    for name in ('Moon_ChasedMetal','Moon_Celadon','Moon_Moonstone','Moon_PearlInlay'):
        materials[name].texture=tailor.tex(filename)
