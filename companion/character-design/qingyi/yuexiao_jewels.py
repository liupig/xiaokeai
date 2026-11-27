"""Model the jewellery from the local front and three-quarter costume sheet."""
from math import pi

import numpy as np
from PIL import Image

from build_lanxu import TEX
from build_yuexiao import ART, curve, lattice
from yuexiao_finish import surface


# Keep each fitting in its own padded UV chart. Coordinates below are pixels
# on the original sheet, including the different comb on the far temple.
CHARTS = {
    'temple': (991, 23, 1077, 127),
    'spray': (538, 6, 605, 121),
    'vamp': (456, 850, 517, 985),
    'heel': (976, 824, 1039, 983),
    'wrist': (345, 374, 415, 447),
    'brooch': (483, 239, 581, 507),
}
TILE = 320


def bake_jewels():
    atlas = Image.new('RGB', (TILE*3, TILE*2))
    packed = Image.new('RGB', atlas.size)
    rng=np.random.default_rng(671)
    with Image.open(ART) as source:
        for i, box in enumerate(CHARTS.values()):
            rgb = np.asarray(source.crop(box).convert('RGB').resize((TILE-8,TILE-8), Image.BICUBIC))
            rgb = np.pad(rgb, ((4,4),(4,4),(0,0)), mode='edge')
            pos = (i%3*TILE, i//3*TILE)
            atlas.paste(Image.fromarray(rgb), pos)
            channels=surface(rgb.astype('float32')/255, False)
            if i in (0,1):
                # Fine mineral specks break the reflection within the enamel,
                # even between the few source pixels on a single petal.
                grain=rng.normal(0,5,rgb.shape[:2])
                fleck=rng.random(rgb.shape[:2])>.955
                channels[:,:,0]=np.clip(channels[:,:,0]+grain*.44+5*fleck,0,255)
                channels[:,:,1]=np.clip(channels[:,:,1]+grain-42*fleck,20,245)
            packed.paste(Image.fromarray(channels), pos)
    atlas.save(TEX/'yuexiao-jewels.jpg', quality=98, subsampling=0)
    packed.save(TEX/'yuexiao-jewels-finish.png', optimize=True)


def chart(name, xy):
    x, y, right, bottom = CHARTS[name]
    i = list(CHARTS).index(name)
    local = np.clip((np.asarray(xy)-[x,y])/[right-x,bottom-y], 0, 1)
    return (np.array([i%3*TILE+4.5,i//3*TILE+4.5])+local*(TILE-9))/[TILE*3,TILE*2]


def stone_cut(t, mat, c, right, up, front, size, tile, pixel, sample, pear=False):
    """Closed pointed back, girdle and a low crown with staggered cutting facets."""
    right, up, front = map(np.asarray, (right, up, front))
    w, h, depth = size
    count = 10 if pear else 12
    a = np.linspace(0,2*pi,count+1)
    rings, images = [], []
    for r, z, twist in [(0.008,-.63,0),(.82,-.23,.45),(1.,0,0),(.94,.18,0),(.64,.73,.42),(.30,.97,.10),(.009,1.,0)]:
        xx, yy = r*np.cos(a+twist*pi/count), r*np.sin(a+twist*pi/count)
        if pear:
            xx = xx*(.79-.38*yy)
        rings.append(c+w*xx[:,None]*right+h*yy[:,None]*up+depth*z*front)
        images.append(chart(tile, pixel+np.stack([xx*sample[0],-yy*sample[1]],axis=-1)))
    # Give each facet its own plane normal rather than smoothing the dome into a bead.
    for row in range(len(rings)-1):
        for j in range(count):
            t.grid(mat, np.stack([rings[row][j:j+2],rings[row+1][j:j+2]]),
                   uv=np.stack([images[row][j:j+2],images[row+1][j:j+2]]))


def link(t, mat, c, right, up, width, height, gauge):
    a = np.linspace(0,2*pi,17)
    t.wire(mat, c+width*np.cos(a)[:,None]*right+height*np.sin(a)[:,None]*up, gauge, 6)


def articulated_chain(t, wire, pts, face, pitch=.063, gauge=.007):
    """Alternately turned oval links between two actual attachment points."""
    pts = np.asarray(pts)
    lengths = np.r_[0,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))]
    count = max(2,round(lengths[-1]/pitch))
    q = np.linspace(0,lengths[-1],count+1)
    knots = np.stack([np.interp(q,lengths,col) for col in pts.T],axis=-1)
    for j,(a,b) in enumerate(zip(knots,knots[1:])):
        segment = b-a
        up = segment/max(np.linalg.norm(segment),1.e-7)
        right = np.cross(up,face)
        right /= max(np.linalg.norm(right),1.e-7)
        if j%2:
            right = .45*right + .89*np.cross(up,right)
        link(t,wire,(a+b)/2,right,up,pitch*.22,np.linalg.norm(segment)*.61,gauge)


SIDE_LEAVES = [
    ([(1035,66),(1025,57),(1024,44),(1021,30)],[(1037,65),(1034,52),(1031,41),(1021,30)]),
    ([(1035,67),(1028,60),(1030,46),(1037,38)],[(1037,66),(1041,55),(1040,45),(1037,38)]),
    ([(1036,65),(1040,56),(1050,54),(1062,49)],[(1038,67),(1050,65),(1057,58),(1062,49)]),
    ([(1037,66),(1048,63),(1057,69),(1063,74)],[(1037,68),(1046,76),(1056,77),(1063,74)]),
    ([(1035,67),(1036,77),(1042,85),(1045,96)],[(1038,67),(1047,76),(1047,86),(1045,96)]),
    ([(1034,68),(1027,73),(1026,85),(1024,90)],[(1036,68),(1037,76),(1032,84),(1024,90)]),
    ([(1034,65),(1023,63),(1010,68),(997,78)],[(1033,68),(1023,75),(1010,78),(997,78)]),
    ([(1035,64),(1027,59),(1016,55),(1008,56)],[(1034,67),(1024,66),(1014,62),(1008,56)]),
]


def mount_combs(t, wire, pearl):
    glass = t.material('Glass','jewels.jpg',hair=True)
    cut_glass = t.material('Crystal','jewels.jpg',hair=True)
    gold = t.material('Gilt','jewels.jpg',hair=True)
    vertical = np.array([0.,1.,0.])
    for s in (-1,1):
        dominant = s<0
        if dominant:
            tile, pivot, leaves, scale = 'temple', np.array([1036.,66.]), SIDE_LEAVES, .0215
            c = np.array([-.999,20.305,-.125])
            yaw, pitch, bank = np.radians([50,13,5])
        else:
            tile, pivot, scale = 'spray', np.array([570.,55.]), .021
            c = np.array([.953,20.51,.055])
            yaw, pitch, bank = np.radians([52,21,-7])
            leaves = [
                ([(570,55),(573,48),(579,43),(586,40)],[(571,56),(579,52),(583,47),(586,40)]),
                ([(571,56),(579,51),(590,55),(601,60)],[(571,57),(581,64),(592,64),(601,60)]),
                ([(571,56),(579,59),(585,69),(587,76)],[(569,57),(574,66),(581,72),(587,76)]),
                ([(570,57),(568,66),(571,73),(570,80)],[(572,56),(575,67),(574,74),(570,80)]),
                ([(569,55),(564,49),(563,41),(559,34)],[(572,55),(572,45),(568,39),(559,34)]),
            ]
        # Both mounts sit at the measured outer surface of the fine-weave
        # temple, with the comb teeth pointing inward. The upper ornament
        # banks towards the part while the main flower opens over the ear.
        facing = np.array([s*np.sin(yaw),0.,-np.cos(yaw)])
        across = np.array([np.cos(yaw),0.,s*np.sin(yaw)])
        front = facing*np.cos(pitch)+vertical*np.sin(pitch)
        uphill = vertical*np.cos(pitch)-facing*np.sin(pitch)
        right = across*np.cos(bank)+uphill*np.sin(bank)
        up = uphill*np.cos(bank)-across*np.sin(bank)
        def place(xy, lift=0., hanging=False):
            xy = np.asarray(xy)
            dx=(xy[...,0:1]-pivot[0])*scale
            dy=(pivot[1]-xy[...,1:2])*scale
            # A shallow dome gives the outer leaves and the two tall sprays
            # a common mounting surface, even in a view from above the part.
            height=dy
            if hanging:
                # Once a chain clears the setting it falls with gravity.
                height=np.maximum(dy,-.27)
            depth=np.asarray(lift)[...,None]-.24*dx**2-.27*height**2
            p=c+dx*right+height*up+(dy-height)*vertical+depth*front
            if dominant and not hanging:
                # Turn the forward petals around the swept fringe. A planar
                # flower loses these three tips inside the convex hairline.
                turn=np.maximum(dx,0)
                p[...,0:1]-=.38*turn
                p[...,2:3]-=.37*turn
            if hanging:
                release=np.clip((-.17-dy[...,0])/.50,0,1)
                release=release*release*(3-2*release)
                p[...,0]+=s*release*np.maximum(0,1.095-s*p[...,0])
            return p
        # The shoe of the comb actually enters the hair behind the leaves.
        for displacement in (-.08,.09):
            p=curve([c+.06*front,c+displacement*up-.14*front,c+(displacement-.08)*up-.31*front],np.linspace(0,1,12))
            t.wire(wire,p,.019,7)
        for j,(left,edge) in enumerate(leaves):
            v,u=lattice(25,10)
            l,r=(curve(line,v[:,0])[:,None] for line in (left,edge))
            xy=l+(r-l)*u[...,None]
            mid=1-abs(2*u-1)**1.35
            z=.027+.082*np.sin(pi*v)**.8*mid+.035*np.sin(2*pi*v+.8*j)*v+.038*v
            p=place(xy,z)
            t.grid(glass,p,uv=chart(tile,xy))
            for k in (0,-1):
                t.wire(wire,p[:,k],.0058,5)
                wall=np.stack([p[:,k],p[:,k]-.013*front],axis=1)
                t.grid(glass,wall,uv=chart(tile,np.repeat(xy[:,k][:,None,:],2,axis=1)))
            midline=p[2:-4:2,5]+.003*front
            t.wire(wire,midline,np.linspace(.007,.002,len(midline)),5)
        def gem(x,y,dimensions,sample,depth=.10,pear=False):
            # The free teardrops keep a vertical axis below their tilted comb.
            axes=(across,vertical,facing) if pear else (right,up,front)
            stone_cut(t,cut_glass,place([x,y],depth,hanging=pear),*axes,dimensions,tile,np.array([x,y]),sample,pear)
        if dominant:
            stems=[([(1026,70),(1015,80),(1009,88),(1004.4,99.8)],(1004.4,99.8),2.0),
                   ([(1004.4,101),(1004.3,107),(1003.5,112),(1002.9,118.2)],(1002.9,118.2),1.8),
                   ([(1025,72),(1018,82),(1017,96),(1019.2,105)],(1019.2,107.8),3.25),
                   ([(1042,78),(1044,89),(1044,99),(1042.6,105.6)],(1042.6,105.6),1.2),
                   ([(1042.6,106),(1041.1,112),(1039.3,117),(1038.5,121.4)],(1038.5,121.4),1.4)]
        else:
            stems=[([(577,61),(582,68),(586,75),(591,87)],(591,88),2.1),
                   ([(591,90),(594,96),(596,102),(597,107)],(597,108),2.3),
                   ([(573,65),(579,76),(580,86),(579,99)],(579,100),3.)]
            for route,sz in [([(569,55),(563,43),(557,34),(549,20),(546,13)],2.5),
                             ([(571,53),(573,42),(574,31),(576,23)],3.0)]:
                u=np.linspace(0,1,27)
                p=place(curve(route,u),.035)
                # The stem rests along the crown and the terminal pearl
                # lifts just above it, silhouetted in the front view.
                p+=u[:,None]**1.7*(.065*front+.10*vertical)
                t.wire(wire,p,.010,6)
                t.stone(pearl,p[-1],(sz*.019,sz*.022,sz*.018))
            for x,y,r in [(561,38,1.5),(565,38,2.0),(564,44,2.4),(570,45,1.8),(567,50,2.6),(572,51,1.9),(570,57,2.5)]:
                gem(x,y,(r*.024,r*.026,r*.019),(r,r))
        for pts,(x,y),rad in stems:
            line=place(curve(pts,np.linspace(0,1,22)),.018,hanging=True)
            articulated_chain(t,wire,line,front,.067,.006)
            gem(x,y,(rad*.026,rad*.036,rad*.023),(rad,rad*1.3),.023,True)
        for j in range(6):
            a=j*pi/3+.15
            pt=c+.111*front+.054*(np.cos(a)*right+np.sin(a)*up)
            stone_cut(t,gold,pt,right,up,front,(.026,.032,.024),'brooch',np.array([531.,269.]),[1.1,1.3])
        gem(*pivot,(.042,.051,.035),(1.5,1.7),.144)
    return cut_glass
