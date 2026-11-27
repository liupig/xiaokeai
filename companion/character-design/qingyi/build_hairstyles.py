"""Sculpt Qingyi's interchangeable hairpieces in head-bone space (PMX units)."""
import bpy
from pathlib import Path
from math import sin, cos, pi, exp
from mathutils import Vector

root=Path.cwd()
design=root/"companion/character-design/qingyi"
out=root/"online-demo/frontend/public/models/qingyi-jade"
bpy.ops.wm.read_factory_settings(use_empty=True)

def pigment(name, color, roughness):
    m=bpy.data.materials.new(name)
    m.diffuse_color=(*color,1)
    m.use_nodes=True
    bs=m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value=(*color,1)
    bs.inputs["Roughness"].default_value=roughness
    return m

hair=pigment("Aubergine silk",(.085,.063,.095),.48)
light=pigment("Plum ribbons",(.105,.079,.114),.45)
jade=pigment("Celadon",(.27,.49,.41),.29)
gold=pigment("Aged gold",(.45,.30,.14),.36)

def point(p):
    x,y,z=p
    return (x,z-.4551863,y-19.189396)

def surface(name,f,rows,cols,mat):
    vertices=[point(f(i/rows,j/cols)) for i in range(rows+1) for j in range(cols+1)]
    faces=[]
    for i in range(rows):
        for j in range(cols):
            k=i*(cols+1)+j
            faces.append((k,k+1,k+cols+2,k+cols+1))
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(vertices,[],faces)
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent=group
    mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth=True
    return obj

def lock(name,coords,width,depth,material=hair):
    points=[Vector(p) for p in coords]
    def path(t):
        pos=min(t*(len(points)-1),len(points)-1-.000001)
        k=int(pos)
        f=pos-k
        a,b,c,d=[points[max(0,min(len(points)-1,k+h))] for h in (-1,0,1,2)]
        return .5*(2*b+(-a+c)*f+(2*a-5*b+4*c-d)*f*f+(-a+3*b-3*c+d)*f**3)
    def strand(t,u):
        center=path(t)
        direction=(path(min(1,t+.001))-path(max(0,t-.001))).normalized()
        axis=direction.cross(Vector((0,0,1)))
        if axis.length<.02:
            axis=direction.cross(Vector((0,1,0)))
        axis.normalize()
        normal=direction.cross(axis).normalized()
        a=u*2*pi
        taper=max(.008,sin(pi*t)**.52)
        return center+taper*(width*cos(a)*axis+depth*sin(a)*normal)
    surface(name,strand,36,14,material)

def bun(name,center,radii,twist):
    def coil(t,u):
        a=u*2*pi
        b=.001+(pi-.002)*t
        ripple=1+.085*cos(7*a+twist*b)+.012*cos(38*a+twist*b)
        return (center[0]+radii[0]*sin(b)*cos(a)*ripple,
                center[1]+radii[1]*cos(b),center[2]+radii[2]*sin(b)*sin(a)*ripple)
    surface(name,coil,48,144,hair)

for style in ("low","high","braid"):
    group=bpy.data.objects.new(style,None)
    bpy.context.collection.objects.link(group)
    def cap(t,u):
        a=2*pi*u-pi
        front=cos(a)
        edge=1.89-.87*front+.12*sin(2*a)
        b=.001+t*edge
        sweep=a+.59*(1-t)*sin(a-.38)
        fluting=(.021*cos(23*a+.8*sin(b*2))+.006*cos(61*a))*sin(b)
        return (.20*(1-t)**2+(.99+fluting)*sin(b)*sin(sweep),
                19.85+1.40*cos(b)+.07*sin(b)*sin(a),
                .39-(1.03+fluting)*sin(b)*cos(sweep))
    surface("Combed crown",cap,46,192,hair)
    for side in (-1,1):
        # Loft the entire sweep from the curved part to the temple.
        # The leading edge crosses the brow, with progressively shorter locks behind it.
        def fringe(t,u):
            a=side*1.67*t+.19*(1-t)
            edge=1.03+.79*t+.23*sin(pi*t)**2*(1 if side<0 else .55)
            b=.11+u*(edge-.11)
            angle=a+.16*side*(1-u)*sin(t*pi)
            grooves=.016*cos(46*u+2*t)+.009*cos(88*u+t)
            rad=1.08+grooves+.075*sin(pi*u)
            return (rad*sin(b)*sin(angle)+.14*(1-t)*(1-u),
                    19.86+(1.42+grooves)*cos(b)+.08*sin(pi*t),
                    .34-(1.17+grooves)*sin(b)*cos(angle))
        surface("Side-part sweep",fringe,64,92,light)
        length=.52 if side==1 else .96
        lock("Temple wisp",[(side*.8,20.26,-.27),(side*.88,19.88,-.24),
             (side*.84,19.47,-.22),(side*.80,19.36-length*.50,-.20),
             (side*.66,19.34-length,-.08)],.043,.034)
    if style=="low":
        bun("Nape chignon",(0,19.13,1.28),(.96,.53,.61),3.2)
        lock("Jade pin",[(-1.13,18.97,1.35),(-.46,19.14,1.36),
              (.5,19.34,1.38),(1.23,19.50,1.4)],.075,.068,jade)
    elif style=="high":
        bun("High knot",(0,21.26,.90),(.67,.65,.64),4.6)
        lock("Gold hairpin",[(-.89,21.0,.89),(-.35,21.22,.91),(.27,21.41,.91),
             (.91,21.64,.91)],.068,.065,gold)
    else:
        for i in range(3):
            coords=[]
            for j in range(37):
                t=j/36
                a=2*pi*(2*t+i/3)
                coords.append((.5+1.13*sin(t*pi*.62)+.27*(1-.6*t)*cos(a),
                               19.54-4.12*t,1.13-1.55*t+.23*(1-.55*t)*sin(a)))
            lock("Side braid",coords,.255,.215,light if i==1 else hair)
        bun("Braid tip",(1.55,15.37,-.44),(.16,.24,.14),2)
    for obj in group.children:
        obj.select_set(True)
    group.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(out/(style+"-hair.glb")),use_selection=True)
    bpy.ops.object.select_all(action='DESELECT')
bpy.ops.wm.save_as_mainfile(filepath=str(design/"qingyi-hair-wardrobe.blend"))
