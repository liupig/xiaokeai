"""Hand-lofted magnolia, wax-carved leaves and fork, traced from the original jewel artwork."""
from math import pi

import numpy as np


ATLAS = np.array([2098.,749.])
# Each pair of splines runs from calyx to tip. The individual blades have
# their own closed cross sections, material coordinates, twist and curvature.
LEAVES = {
    "left": (
        [(366,497),(288,455),(159,435),(63,475),(13,573)],
        [(368,506),(280,513),(176,549),(77,539),(13,579)]),
    "upper": (
        [(1028,434),(1091,283),(1211,209),(1363,184),(1489,217)],
        [(1032,440),(1161,382),(1291,352),(1399,246),(1494,218)]),
    "lower": (
        [(952,506),(1074,477),(1207,483),(1326,574),(1374,738)],
        [(954,514),(1064,575),(1175,651),(1294,671),(1377,741)]),
    "far": (
        [(1476,370),(1540,403),(1608,472),(1626,554),(1626,619)],
        [(1475,373),(1521,442),(1548,510),(1597,562),(1623,620)]),
}
WHITE_UV = (
    [(481,480),(452,405),(439,333),(469,259),(526,197),(600,149)],
    [(516,473),(543,404),(613,328),(625,262),(622,201),(611,148)])


class Setting:
    def __init__(self,piece,spline,frame,scale=1.):
        self.piece,self.spline,self.frame,self.scale = piece,spline,frame,scale

    def xyz(self,x,y,d):
        return self.frame(*np.broadcast_arrays(x,y,d))

    def branch(self,points,radii,finish="Gold"):
        points = np.asarray(points,float)
        p = self.spline(points,5*len(points)+1)
        r = np.interp(np.linspace(0,1,len(p)),np.linspace(0,1,len(radii)),radii)
        self.piece.wire(self.xyz(*p.T),self.scale*r,finish,9)

    def pearl(self,x,y,d,size,elongation=1.):
        centre = self.xyz(x,y,d)
        a = np.arange(14)*2*pi/14
        b = np.linspace(.035,pi-.035,12)[:,None]
        globe = np.stack(np.broadcast_arrays(np.sin(b)*np.cos(a),
                         elongation*np.cos(b),np.sin(b)*np.sin(a)),axis=-1)
        self.piece.shell("Pearl",centre+self.scale*size*globe)

    def blade(self,edges,*,base=.04,tip=.05,twist=.015,cup=.035,thick=.015,
              material="Carving",donor=None,bezel=False):
        count = 33
        l,r = [self.spline(p,count) for p in edges]
        # The very ends have finite width to support a smooth bevel and cap.
        t = np.linspace(0,1,count)[:,None]
        a = np.arange(18)*2*pi/18
        w = np.cos(a)[None,:]
        xy = (l+r)[:,None]/2+(r-l)[:,None]*w[:,:,None]/2
        swell = np.sin(pi*t)**.68
        bend = base+(tip-base)*t**1.5+twist*swell*(.55+.70*t)*w
        relief = bend+cup*swell*(1-w*w)+thick*(.13+.87*swell)*np.sin(a)
        world = self.xyz(xy[:,:,0],xy[:,:,1],relief)
        u,v = [self.spline(p,count) for p in (donor or edges)]
        # Pull the sample away from the antialiased exterior of the artwork.
        # Texture detail travels around the back of the carved stone too.
        uv = ((u+v)[:,None]/2+(v-u)[:,None]*(.89*w[:,:,None])/2)/ATLAS
        self.piece.shell(material,world,np.clip(uv,.001,.999))
        if bezel:
            for side,k in [(1,0),(-1,9)]:
                line = self.xyz(xy[:,k,0],xy[:,k,1],bend[:,k])
                self.piece.wire(line,self.scale*(.002+.0055*swell.ravel()),"Wire",6)

    def bud(self,edges,base,tip,twist):
        self.blade(edges,base=base,tip=tip,twist=twist,cup=.014,
                   thick=.043,donor=WHITE_UV)
        # Fold a separate sepal over the stone, with an engraved gold edge.
        l,r = [np.asarray(p,float) for p in edges]
        mid = (l+r)*.5
        self.blade((l[:3],mid[:3]),base=base+.026,tip=base+.05,twist=.006,
                   cup=.014,thick=.008,material="Gold")

    def left_sprig(self):
        self.branch([(303,664,.008),(377,609,.016),(388,549,.023),(372,473,.035),
                     (318,424,.038),(235,399,.049),(174,354,.063),(129,296,.067)],
                    [.028,.029,.024,.023,.020,.017,.013,.005])
        self.branch([(389,534,.01),(377,510,.027),(350,498,.036)],[.015,.014,.007])
        self.blade(LEAVES["left"],base=.037,tip=.092,twist=-.027,cup=.028,bezel=True)
        self.bud(([(168,359),(109,329),(70,285),(39,217)],
                  [(170,355),(154,299),(111,254),(45,213)]),.058,.134,-.018)


def magnolia(s):
    # Four layers open towards the viewer; distant petals curl into the hair
    # and the forward lip rolls out over the calyx.
    petals = [
        (([(473,547),(395,404),(373,280),(415,163),(494,82),(563,13)],
          [(485,545),(537,422),(622,310),(630,196),(603,89),(575,11)]),
         -.005,-.118,-.058,.055),
        (([(502,548),(539,407),(586,256),(676,119),(766,64),(824,35)],
          [(520,551),(684,444),(788,349),(860,242),(859,126),(834,31)]),
         -.004,-.065,.051,.066),
        (([(505,552),(597,433),(733,320),(870,263),(954,262),(1022,294)],
          [(517,563),(697,475),(830,444),(929,390),(985,320),(1033,301)]),
         .021,.063,.036,.051),
        (([(470,550),(411,424),(396,335),(444,244),(539,164),(620,119)],
          [(483,548),(565,431),(639,348),(670,267),(649,179),(630,119)]),
         .028,.135,-.038,.073),
        (([(484,558),(528,464),(621,388),(759,344),(848,355),(948,326)],
          [(496,573),(641,532),(743,475),(836,456),(904,412),(953,326)]),
         .058,.24,.040,.082),
    ]
    for i,(outline,base,tip,twist,cup) in enumerate(petals):
        s.blade(outline,base=base,tip=tip,twist=twist,cup=cup,thick=.033,
                donor=WHITE_UV if i<3 else outline)
    # Set the stamens into the open cup at separate depths.
    for x,y,d in [(738,223,.135),(794,272,.165),(717,268,.179)]:
        s.branch([(553,482,.092),(640,397,d-.024),(x-28,y+69,d),(x,y,d)],
                 [.008,.007,.006,.003],"Wire")
        s.pearl(x,y,d,.019,1.36)
    for edge in [
        ([(477,574),(445,536),(432,491),(441,453)],[(484,567),(479,523),(467,479),(443,453)]),
        ([(477,570),(501,530),(569,509),(671,483)],[(489,578),(550,559),(615,532),(674,483)]),
    ]:
        s.blade(edge,base=.091,tip=.136,twist=.015,cup=.025,thick=.013,material="Gold")


def sculpt(piece_type,spline,circlet):
    crown = piece_type("汀兰月冠 · 玉兰半冠")
    fork = piece_type("汀兰月冠 · 含苞双股钗")

    def wrap(x,y,d):
        u = x/ATLAS[0]
        a = (x-1010)*.00147
        h = (606-167*u+54*np.sin(2*pi*u)-y)*.00129
        # Weak tilt out of the scalp opens the flower in silhouette. The bud
        # settles against the opposite temple at the end of the same branch.
        base = circlet(a)
        radial = .043+d+.20*h
        return base+np.stack([radial*np.sin(a),h+.034,radial*np.cos(a)],axis=-1)

    s = Setting(crown,spline,wrap)
    s.branch([(299,666,.009),(397,621,.013),(500,578,.018),(568,580,.016),
              (655,608,.012),(752,577,.022),(836,525,.026),(1008,478,.024),
              (1149,414,.014),(1328,369,.018),(1456,336,.012),(1614,351,.017),
              (1727,398,.025),(1848,475,.041),(1931,476,.050)],
             [.035,.040,.036,.029,.030,.029,.023,.021,.019,.020,.018,.016,.014,.011,.008])
    s.left_sprig()
    for name,depth,tip,twist in [("upper",.025,.080,.095),("lower",.031,.123,-.105),
                                 ("far",.035,.088,-.058)]:
        s.blade(LEAVES[name],base=depth,tip=tip,twist=twist,bezel=True)
    # Seat the calyx in the branch but let the cup open in its own oblique
    # plane. Wrapping broad petals around the scalp pinches the outer lip.
    calyx = wrap(np.asarray(486.),np.asarray(559.),np.asarray(.017))
    def flower_plane(x,y,d):
        lateral = (x-486)*.00144
        h = (559-y)*.00140
        return calyx+np.stack([.932*lateral-.362*d, h+.035*lateral,
                              .362*lateral+.932*d+.12*h],axis=-1)
    magnolia(Setting(crown,spline,flower_plane))
    s.bud(([(1891,471),(1926,429),(1985,412),(2047,423),(2087,450)],
           [(1892,481),(1952,504),(2015,508),(2058,481),(2090,452)]),.046,.087,.017)

    # The rear mounting is a changing-width, carved celadon crescent. It
    # lifts from the hair beside the knot and narrows to two concealed feet.
    a = np.linspace(1.30,5.38,97)
    base = circlet(a)
    t = np.linspace(0,1,len(a))
    env = np.sin(pi*t)**.8
    width = (.006+.039*env+.056*np.exp(-((t-.67)/.18)**2)*env)
    height = .70*width-.016
    outward = np.column_stack([np.sin(a),np.zeros(len(a)),np.cos(a)])
    up = np.array([0.,1.,0.])
    ridge = base+height[:,None]*up+(.007+.012*env)[:,None]*outward
    b = np.arange(14)*2*pi/14
    rings = ridge[:,None]+width[:,None,None]*np.cos(b)[None,:,None]*up
    rings += (.012+.018*env)[:,None,None]*np.sin(b)[None,:,None]*outward[:,None]
    # The back is cut from the same veined jade as the leaves. Map the
    # grain along the changing width of the crescent.
    u = 1110+190*t[:,None]+14*np.cos(b)
    v = 311-65*t[:,None]+20*np.cos(b)
    crown.shell("Carving",rings,np.stack(np.broadcast_arrays(u/ATLAS[0],v/ATLAS[1]),axis=-1))
    crown.wire(ridge+width[:,None]*up,.006+.007*env,"Wire",7)
    crown.wire(ridge-width[:,None]*up,.008+.008*env,"Gold",7)
    # A shallow crescent cradles the foreground branch and tapers into the
    # right bud. Its open window follows the hair part in three-quarter view.
    s.blade(([(435,585),(570,568),(757,538),(933,518),(1165,473),(1371,389)],
             [(437,590),(571,587),(763,566),(943,538),(1168,481),(1375,391)]),
            base=.065,tip=.050,twist=.012,cup=.015,thick=.010,material="Gold")
    s.branch([(898,522,.061),(955,527,.068),(1016,512,.068),(1064,487,.060)],
             [.004,.007,.005,.002],"Wire")
    s.pearl(951,536,.067,.019)
    # Three small, spaced dew settings at the clasp, not a repeated border.
    for i,r in [(45,.020),(49,.033),(53,.017)]:
        p = ridge[i]+.037*outward[i]
        angles = np.arange(12)*pi/6
        heights = np.linspace(.04,pi-.04,9)[:,None]
        bead = np.stack(np.broadcast_arrays(np.sin(heights)*np.cos(angles),np.cos(heights),
                        np.sin(heights)*np.sin(angles)),axis=-1)
        crown.shell("Pearl",p+r*bead)

    # Lay the fork across the low chignon, tangential to the rolled hair.
    def at_knot(x,y,d):
        u = (393-x)*.00149
        v = (619-y)*.00141
        return np.stack([-1.39-.105*np.sin(np.clip(u,0,.70)*pi/.7)-.61*d,
                         19.79+v+.09*u,-1.73-.70*u+.035*v+.16*d],axis=-1)
    pin = Setting(fork,spline,at_knot,.76)
    pin.left_sprig()
    # A folded white petal and its leaf cup make a closed bud in profile.
    pin.blade(([(171,359),(136,314),(105,260),(80,231)],
               [(174,351),(166,295),(126,254),(83,229)]),
              base=.077,tip=.187,twist=.022,cup=.026,thick=.020,donor=WHITE_UV)
    pin.branch([(317,425,.045),(323,454,.047),(327,479,.050)],
               [.008,.005,.004],"Wire")
    pin.pearl(327,489,.055,.032,1.28)
    pin.branch([(231,507,.055),(216,530,.095),(213,554,.133)],
               [.007,.005,.004],"Wire")
    pin.pearl(213,578,.137,.043,1.32)
    root = at_knot(*np.asarray([303.,664.,.008]))
    for side in (-1,1):
        shank = spline([root,root+[.075,-.030,side*.018],
                        root+[.30,-.15,.09+side*.063],root+[.57,-.36,.16+side*.095]],19)
        fork.wire(shank,np.linspace(.017,.0025,len(shank)),"Gold")
    for x,y,d,r in [(310,418,.055,.028),(269,412,.062,.017)]:
        pin.pearl(x,y,d,r)
    return crown,fork
