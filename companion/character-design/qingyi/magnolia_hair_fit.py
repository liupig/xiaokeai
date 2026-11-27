"""Refit the Magnolia inner fall and give the shoulder-length rows a stable drape."""
import numpy as np

from build_lanxu import PMX


def smooth(value):
    t = np.clip(value, 0, 1)
    return t*t*(3-2*t)


def replace_nape(model, faces, coords, neck_height):
    # Identify the closed underlay authored by waves(), in both the editor
    # model and the compact stage export. Other Silk islands include the cap.
    rows, cols = 36, 65
    ids = np.unique(faces)
    root = ids[(abs(coords[ids, 0]) < 1e-5) & (abs(coords[ids, 2]-1.46) < 1e-5)]
    root = root[abs(coords[root, 1] - (neck_height+2.066)) < .012]
    if len(root) != 2 or root[1]-root[0] != cols-1:
        raise ValueError("Magnolia nape grid does not match the authored seam")
    grid = np.arange(root[0], root[0]+rows*cols).reshape(rows, cols)
    inside = (faces >= grid.min()) & (faces <= grid.max())
    selected = inside.all(axis=1)
    if inside.any(axis=1).sum() != selected.sum() or selected.sum() != 2*(rows-1)*(cols-1):
        raise ValueError("Magnolia nape has unexpected shared faces")
    rebuilt = [faces[~selected]]
    depths = [1.49, 1.72, 1.57, 1.83, 1.46, 1.67, 1.39]
    v = np.linspace(0, 1, rows)[:, None]
    widths = [9, 10, 9, 10, 9, 9, 9]
    boundaries = np.linspace(-1.36, 1.36, len(widths)+1)
    col = 0
    for j, (count, length) in enumerate(zip(widths, depths)):
        idx = grid[:, col:col+count]
        col += count
        u = np.linspace(-1, 1, count)[None, :]
        mid = (boundaries[j]+boundaries[j+1])*.5
        taper = 1-.987*smooth((v-.24)/.76)
        turn = mid + .24*u*taper + .11*np.sin(3.8*v+.71*j)*v
        # Feather the underside around the occiput. Start inside the cranial
        # shell, then lay the ends into the rear lengths above the shoulders.
        x = (.84+.14*v)*np.sin(turn) + .078*np.sin(4*v+.6*j)*v
        y = neck_height+1.77+.13*np.cos(turn) - length*v - .035*(1-u*u)*v
        z = .55+(.87+.23*v)*np.cos(turn) + (.33+.23*abs(mid))*v
        z += .041*(1-u*u)*taper + .024*np.sin(3.4*v+j)*v
        points = np.stack(np.broadcast_arrays(x,y,z),axis=-1)
        normals = np.cross(np.gradient(points,axis=0), np.gradient(points,axis=1))
        normals /= np.maximum(np.linalg.norm(normals,axis=2,keepdims=True),1e-10)
        uv = np.stack(np.broadcast_arrays((1.08+.68*(u+1)/2+.08*np.sin(v*3+j))/4,.15+.79*v),-1)
        for i,p,n,t in zip(idx.ravel(),points.reshape(-1,3),normals.reshape(-1,3),uv.reshape(-1,2)):
            vertex = model.vertices[i]
            vertex.co, vertex.normal, vertex.uv = p,n,t
        coords[idx] = points
        a,b,c,d = idx[:-1,:-1],idx[:-1,1:],idx[1:,:-1],idx[1:,1:]
        rebuilt.extend((np.stack((a,b,c),-1).reshape(-1,3), np.stack((b,d,c),-1).reshape(-1,3)))
    return np.concatenate(rebuilt), grid.ravel()


def support(weight, torso, gain):
    if weight.type == weight.BDEF1:
        values = [1.]
    elif weight.type == weight.BDEF2:
        values = [weight.weights[0], 1-weight.weights[0]]
    elif weight.type == weight.BDEF4:
        values = weight.weights
    else:
        raise ValueError("Unexpected skinning on Magnolia hair")
    merged = {torso: gain}
    for bone,w in zip(weight.bones,values):
        if bone >= 0 and w > 0:
            merged[bone] = merged.get(bone,0.)+(1-gain)*w
    pairs = sorted(merged.items(),key=lambda p:-p[1])[:4]
    total = sum(w for _,w in pairs)
    result = PMX['BoneWeight']()
    result.type = result.BDEF4
    result.bones = [int(b) for b,_ in pairs]+[0]*(4-len(pairs))
    result.weights = [float(w/total) for _,w in pairs]+[0.]*(4-len(pairs))
    return result


def refit_magnolia_hair(model):
    bones = {b.name:i for i,b in enumerate(model.bones)}
    rigids = {r.name:r for r in model.rigids}
    if 'MX_ShoulderGuard_L' in rigids:
        raise ValueError("Shoulder drape has already been applied")
    coords = np.array([v.co for v in model.vertices])
    neck_y = model.bones[bones['首']].location[1]
    torso = bones['上半身2']
    names = {'MoonHair_'+s for s in ('Silk','Tress','Filament','Fibres','Mantle')}
    hair = []
    cursor = 0
    for mat in model.materials:
        end = cursor+mat.vertex_count//3
        if mat.name in names:
            faces = np.asarray(model.faces[cursor:end],dtype=np.int32)
            if mat.name == 'MoonHair_Silk':
                revised, underlay = replace_nape(model,faces,coords,neck_y)
                model.faces[cursor:end] = revised.tolist()
                mat.vertex_count = 3*len(revised)
                end = cursor+len(revised)
                faces = revised
            hair.append(np.unique(faces))
        cursor = end
    ids = np.unique(np.concatenate(hair))
    # The inner leaves have been recut. Rebind roots from their new height
    # rather than retaining the old tube's simulated waist-end weights.
    for i in underlay:
        w = PMX['BoneWeight']()
        w.bones = [bones['頭']]
        model.vertices[i].weight = w
    xyz = coords[ids]
    def inner_shoulder(points):
        x,y,z = points.T
        # These S-curves turn behind the ear to clear the Magnolia neckline.
        # Reserve extra space at the acromion on the inside of the hair only.
        return (smooth((abs(x)-.38)/.65)*smooth((z-.30)/.62)
                *(1-smooth((z-1.25)/1.24))*np.exp(-((y-neck_y+.08)/1.22)**2))
    def sweep(points):
        x,y,z = points.T
        band = smooth((neck_y+1.7-y)/2.05)*smooth((y-neck_y+3.35)/2.10)
        rear = smooth((z-.16)/.62)
        return band*rear*(.14+.19*smooth((abs(x)-.38)/.70)) + .39*inner_shoulder(points)
    offset = sweep(xyz)
    # Inverse-transpose the normal of z'=z+sweep(x,y,z), including fine cards.
    gradients = np.stack([(sweep(xyz+.002*axis)-sweep(xyz-.002*axis))/.004
                          for axis in np.eye(3)],axis=1)
    y = xyz[:,1]
    grip = smooth((neck_y+2.18-y)/3.35)*(.43+.29*smooth((y-neck_y+4.6)/2.9))
    grip += (1-grip)*.35*inner_shoulder(xyz)
    for k in np.flatnonzero((grip>1e-6)|(offset>1e-6)):
        vertex = model.vertices[ids[k]]
        if offset[k]>0:
            normal = np.array(vertex.normal)
            normal -= gradients[k]*normal[2]/(1+gradients[k,2])
            vertex.normal = normal/max(np.linalg.norm(normal),1e-10)
            vertex.co = xyz[k]+[0,0,offset[k]]
        if grip[k]>0:
            vertex.weight = support(vertex.weight,torso,grip[k])
    # The original first arm guards begin below and lateral to the acromion.
    # Bridge the gap with capsules following each clavicle and a deltoid
    # sphere following each upper arm. Enable contact for the rear roots too.
    source = rigids['MX_Nape']
    for side,tag,sign in [('左','L',1),('右','R',-1)]:
        shoulder = bones[side+'肩']
        arm = bones[side+'腕']
        a = np.array(model.bones[shoulder].location)+[0,.05,.10]
        b = np.array(model.bones[arm].location)+[sign*.05,-.04,.12]
        for name,bone,pos,radius in [('ClavicleGuard',shoulder,(a+b)/2,.29),
                                     ('ShoulderGuard',arm,b,.40)]:
            rigid = PMX['Rigid']()
            rigid.name = rigid.name_e = 'MX_'+name+'_'+tag
            rigid.bone,rigid.location = bone,pos
            rigid.mode,rigid.mass,rigid.friction = 0,0.,.32
            rigid.velocity_attenuation,rigid.rotation_attenuation,rigid.bounce = .78,.86,0.
            rigid.collision_group_number = source.collision_group_number
            rigid.collision_group_mask = source.collision_group_mask
            rigid.type,rigid.size,rigid.rotation = 0,(radius,0.,0.),(0.,0.,0.)
            if name=='ClavicleGuard':
                d = (b-a)/np.linalg.norm(b-a)
                rigid.type,rigid.size = 2,(radius,np.linalg.norm(b-a),0.)
                rigid.rotation = (np.arctan2(d[2],d[1]),0.,-np.arcsin(d[0]))
            model.rigids.append(rigid)
    for tag in ('L','C','R'):
        rigids['MX_Hair_'+tag+'_1'].collision_group_mask = 1<<source.collision_group_number
