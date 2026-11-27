"""Articulate the Magnolia hair, petal skirt and four cuff streamers in PMX space."""
import numpy as np
from scipy.spatial import cKDTree

from build_lanxu import PMX
from magnolia_hair_fit import refit_magnolia_hair


def ease(t):
    t = np.clip(t, 0, 1)
    return t*t*(3-2*t)


def bind_magnolia_physics(model):
    bone_ids = {b.name: i for i, b in enumerate(model.bones)}
    used = {r.collision_group_number for r in model.rigids}
    if any(n.startswith('MX_') for n in bone_ids):
        raise ValueError('Magnolia physics is already bound')
    dynamic, collider = sorted(set(range(16))-used, reverse=True)[:2]
    coords = np.asarray([v.co for v in model.vertices])
    groups, cursor = {}, 0
    for mat in model.materials:
        end = cursor + mat.vertex_count//3
        groups[mat.name] = np.unique(model.faces[cursor:end]).astype(np.int32)
        cursor = end
    zero = (0., 0., 0.)
    def body(name, bone, position, radius, mass, collision=False):
        r = PMX['Rigid']()
        r.name = r.name_e = 'MX_'+name
        r.bone, r.location, r.rotation = bone, position, zero
        r.size = (radius, 0, 0)
        r.mode = int(mass > 0)
        r.mass, r.velocity_attenuation, r.rotation_attenuation = mass, .78, .86
        r.bounce, r.friction = 0, .32
        r.collision_group_number = dynamic if mass else collider
        r.collision_group_mask = (1 << collider) if mass else ((1 << dynamic) if collision else 0)
        model.rigids.append(r)
        return len(model.rigids)-1

    def chain(name, parent, path, radius, limit, stiffness):
        path = np.asarray(path)
        bones = []
        parent = bone_ids[parent]
        previous = body(name+'_Pin', parent, path[0], .08, 0)
        for i, (start, end) in enumerate(zip(path, path[1:])):
            b = PMX['Bone']()
            b.name = b.name_e = f'MX_{name}_{i+1}'
            b.parent, b.location, b.displayConnection = parent, start, tuple(end-start)
            b.isMovable = False
            parent = len(model.bones)
            model.bones.append(b)
            bones.append(parent)
            link = body(f'{name}_{i+1}', parent, (start+end)*.5, radius, .20/(1+.35*i))
            rigid = model.rigids[link]
            # A little sphere has almost no rotational inertia around a long strip.
            # Match each link's mass distribution to the strip.
            length = np.linalg.norm(end-start)
            direction = (end-start)/length
            if direction[1] < 0:
                direction = -direction
            width = min(.32*length,max(.165,radius))
            height = .56*length
            rigid.type, rigid.size = 2, (width,height,0.)
            rigid.rotation = (np.arctan2(direction[2],direction[1]),0.,
                              -np.arcsin(np.clip(direction[0],-1,1)))
            rigid.velocity_attenuation, rigid.rotation_attenuation = .91,.96
            if i == 0 or length < .95:
                # Roots and the small cuff petals sit against their own pin's collider.
                rigid.collision_group_mask = 0
            j = PMX['Joint']()
            j.name = j.name_e = b.name
            j.src_rigid, j.dest_rigid = previous, link
            j.location, j.rotation = start, zero
            j.minimum_location = j.maximum_location = j.spring_constant = zero
            j.maximum_rotation = (limit, limit*.65, limit)
            j.minimum_rotation = tuple(-v for v in j.maximum_rotation)
            j.spring_rotation_constant = (stiffness*rigid.mass*(height*height+5*width*width)*.85,)*3
            model.joints.append(j)
            previous = link
        return np.asarray(bones)

    def paint(ids, new_bones, new_weights):
        # Fold the authored skinning and the simulated influences into PMX's four slots.
        for idx, bones, weights in zip(ids, new_bones, new_weights):
            total = sum(weights)
            if total < .0001:
                continue
            w = model.vertices[idx].weight
            if w.type == 0:
                old = [1.]
            elif w.type in (1, 3):
                first = w.weights[0] if w.type == 1 else w.weights.weight
                old = [first, 1-first]
            else:
                old = w.weights
            merged = {}
            for b, v in zip(w.bones, old):
                if v > 0 and b >= 0:
                    merged[b] = merged.get(b, 0.) + v*(1-total)
            for b, v in zip(bones, weights):
                if v > 0:
                    merged[b] = merged.get(b, 0.) + v
            pairs = sorted(merged.items(), key=lambda item: -item[1])[:4]
            normalizer = sum(v for _, v in pairs)
            result = PMX['BoneWeight']()
            result.type = 2
            result.bones = [int(b) for b, _ in pairs] + [0]*(4-len(pairs))
            result.weights = [v/normalizer for _, v in pairs] + [0.]*(4-len(pairs))
            model.vertices[idx].weight = result

    def influences(chains, section, position, gain):
        # Interpolate both along each strip and around/across neighbouring strips.
        chains = np.asarray(chains)
        position = np.clip(position, 0, chains.shape[1]-1)
        k = position.astype(int)
        h = np.minimum(k+1, chains.shape[1]-1)
        a = np.floor(section).astype(int) % len(chains)
        b = (a+1) % len(chains)
        v, u = position-k, section-np.floor(section)
        return (np.stack([chains[a,k],chains[a,h],chains[b,k],chains[b,h]], axis=1),
                np.stack([(1-u)*(1-v),(1-u)*v,u*(1-v),u*v], axis=1)*gain[:,None])

    hair = [chain('Hair_'+name, '頭', path, .17, .28, 7) for name, path in [
        ('R', [(-.85,20.65,1.18),(-1.14,18.85,1.7),(-1.35,16.85,2.18),(-1.22,15.2,2.58),(-1.08,13.7,2.7)]),
        ('C', [(0,20.65,1.5),(0,18.85,2.12),(0,16.85,2.5),(0,15.2,2.77),(0,13.7,2.82)]),
        ('L', [(.85,20.65,1.18),(1.14,18.85,1.7),(1.35,16.85,2.18),(1.22,15.2,2.58),(1.08,13.7,2.7)])]]
    front = [chain('Temple_'+name,'頭',[(s*.76,21.3,.10),(s*1.11,20.15,-.12),
             (s*1.02,18.75,-.36),(s*.94,17.5,-.25)],.10,.16,9) for s,name in [(-1,'R'),(1,'L')]]
    ids = np.unique(np.concatenate([groups['MoonHair_'+k] for k in
                    ('Silk','Tress','Fibres','Filament','Fringe','Mantle')]))
    x,y,z = coords[ids].T
    rear = ease((z-.12)/.94)
    hb,hw = influences(hair,np.clip(x/1.3+1,0,2),(20.65-y)/1.82,
                       .88*ease((20.75-y)/1.35)*rear)
    fb,fw = influences(front,(x>0).astype(float),(21.3-y)/1.23,
                       .73*ease((21.25-y)/1.55)*(1-rear))
    paint(ids,np.hstack([hb,fb]),np.hstack([hw,fw]))

    skirt = []
    for i in range(8):
        angle = i*np.pi/4
        path = [(w*np.sin(angle),y,.28-d*np.cos(angle)) for y,w,d in
                [(15.45,1.2,.83),(13.60,1.86,1.33),(11.85,2.40,1.58),(9.72,2.57,1.88)]]
        skirt.append(chain('Hem_'+str(i),'下半身',path,.19,.21,9))
    ids = np.unique(np.concatenate([groups[n] for n in ('Moon_Petal','Moon_Veil','Moon_PearlHem','Moon_Silk','Moon_Silver')]))
    ids = ids[(abs(coords[ids,0])<3.85)&(coords[ids,1]<15.45)]
    x,y,z = coords[ids].T
    section = np.arctan2(x/1.55,-(z-.28)/1.15)*4/np.pi
    sb,sw = influences(skirt,section,(15.45-y)/1.82,.65*ease((15.45-y)/2.7))
    paint(ids,sb,sw)

    strips = groups['Moon_Gauze'].reshape(4,72,20)
    ribbon_ids, ribbon_bones, ribbon_weights = [], [], []
    for i, grid in enumerate(strips):
        centers = coords[grid].mean(axis=1)
        long = np.linalg.norm(centers[-1]-centers[0])>3
        side = '左' if centers[0,0]>0 else '右'
        stops = [0,18,36,54,71] if long else [0,36,71]
        links = chain('Ribbon_'+str(i),side+'腕',centers[stops],.10 if long else .06,
                      .21 if long else .14,7 if long else 5)
        row = np.repeat(np.arange(72),20)
        section = np.zeros(len(row))
        rb,rw = influences([links],section,np.interp(row,stops,np.arange(len(stops))),
                           (.83 if long else .67)*ease(row/25.))
        ribbon_ids.extend(grid.ravel())
        ribbon_bones.extend(rb)
        ribbon_weights.extend(rw)
    ribbon_ids = np.asarray(ribbon_ids)
    ribbon_bones, ribbon_weights = np.asarray(ribbon_bones), np.asarray(ribbon_weights)
    paint(ribbon_ids,ribbon_bones,ribbon_weights)
    trim = np.unique(np.concatenate([groups[n] for n in ('Moon_Silk','Moon_Silver','Moon_Gold','Moon_Pearl')]))
    trim = trim[abs(coords[trim,0])>2.65]
    dist,near = cKDTree(coords[ribbon_ids]).query(coords[trim])
    # Include the suspended tip jewels beyond the meshed ends, but leave bracelets on the wrist.
    ends = np.isin(ribbon_ids[near],strips[:, -1].ravel())
    keep = (dist<.095) | (ends & (dist<.57) & (abs(coords[trim,0])>7))
    paint(trim[keep],ribbon_bones[near[keep]],ribbon_weights[near[keep]])

    for name,parent,offset,r in [('Nape','首',(0,-.4,.22),.44),
            ('Back','上半身2',(0,.5,.46),.85),('Pelvis','下半身',(0,-.65,.14),.88)]:
        bone = bone_ids[parent]
        body(name,bone,np.asarray(model.bones[bone].location)+offset,r,0,True)
    for side,tag in [('左','L'),('右','R')]:
        for part,start,end,r in [('Arm','腕','ひじ',.30),('Wrist','ひじ','手首',.22),('Thigh','足','ひざ',.53)]:
            bone = bone_ids[side+start]
            a,b = (np.asarray(model.bones[k].location) for k in (bone,bone_ids[side+end]))
            for i,frac in enumerate((.24,.57,.86)):
                body(f'{part}_{tag}_{i}',bone,a+(b-a)*frac,r,0,True)
    refit_magnolia_hair(model)
