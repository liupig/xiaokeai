"""Fit the occiput between the original facial outline and the back of the neck."""
from collections import Counter, defaultdict
import copy
from math import pi

import numpy as np
from PIL import Image
from scipy.interpolate import CubicSpline

from build_lanxu import PMX, TEX


def fit_scalp(atelier):
    model = atelier.m
    head = atelier.bones['頭']
    head_y = model.bones[head].location[1]
    ranges = {}
    start = 0
    for material in model.materials:
        end = start + material.vertex_count // 3
        if material.name in ('Face_', 'Up_Skin'):
            ranges[material.name] = (material, start, end)
        start = end

    face, first, last = ranges['Face_']
    triangles = model.faces[first:last]
    # The donor closes the face with two flat fans on mirrored UV islands.
    # Removing just these faces keeps all original facial morph indices stable.
    hubs = {i for i in np.unique(triangles)
            if abs(model.vertices[i].uv[1] - .2053) < .0001
            and abs(abs(model.vertices[i].uv[0] - .5) - .47835) < .0001}
    kept = [tri for tri in triangles if hubs.isdisjoint(tri)]
    if len(hubs) != 2 or len(triangles) - len(kept) != 46:
        raise ValueError('Unexpected donor facial closure')
    skin, n0, n1 = ranges['Up_Skin']
    edges, donors = Counter(), {}
    for mat, faces in [(face, kept), (skin, model.faces[n0:n1])]:
        for tri in faces:
            if min(model.vertices[i].co[1] for i in tri) < head_y - .75:
                continue
            keys = [tuple(np.round(model.vertices[i].co, 4)) for i in tri]
            for k, i in zip(keys, tri):
                donors[k] = (i, mat)
            for a, b in zip(keys, keys[1:] + keys[:1]):
                edges[tuple(sorted((a, b)))] += 1
    neighbours = defaultdict(list)
    for (a, b), count in edges.items():
        if count == 1:
            neighbours[a].append(b)
            neighbours[b].append(a)
    crown = max(neighbours, key=lambda p: p[1])
    loop = [crown]
    prev, current = crown, neighbours[crown][0]
    while current != crown:
        if current in loop or len(neighbours[current]) != 2:
            raise ValueError('Facial and neck outlines do not form a single ring')
        loop.append(current)
        other = next(k for k in neighbours[current] if k != prev)
        prev, current = current, other
    if not any(p[2] > 1. for p in loop) or not 28 <= len(loop) <= 70:
        raise ValueError('Occipital outline does not reach the nape')
    if loop[1][0] > 0:
        loop = [loop[0], *reversed(loop[1:])]
    ids = [donors[k][0] for k in loop]
    rim = np.asarray([model.vertices[i].co for i in ids])
    count = len(ids)
    distance = np.linalg.norm(np.roll(rim, -1, axis=0) - rim, axis=1)
    u = np.r_[0., np.cumsum(distance)] / distance.sum()
    # The donor has wide triangles above the forehead. Keep their actual
    # edges at the join, then triple the angular resolution across the vault.
    columns = count * 3
    longitude = np.interp(np.arange(columns)/3, np.arange(count + 1), u)
    guides = CubicSpline(u, np.vstack((rim, rim[0])), axis=0, bc_type='periodic')(longitude)

    # Sweep each actual rim point around a common cranial ellipsoid. The
    # forehead continues over the vertex while the nuchal line turns upward.
    centre = np.array([0., head_y + .68, .455])
    radii = np.array([.917, 1.285, 1.023])
    ray = (guides - centre) / radii
    radius = np.linalg.norm(ray, axis=1)
    xy = np.linalg.norm(ray[:, :2], axis=1)
    angle = np.arctan2(xy, ray[:, 2])
    meridian = ray[:, :2] / xy[:, None]
    rows = 34
    t = np.arange(rows)[:, None] / rows
    theta = (1 - t) * angle
    factor = radius + (1 - radius) * (1 - (1 - t)**4)
    radial = factor * np.sin(theta)
    shell = centre + radii * np.dstack((radial * meridian[:, 0],
                                       radial * meridian[:, 1], factor * np.cos(theta)))
    shell[0, ::3] = rim
    pole = centre + [0, 0, radii[2]]
    tangent = np.roll(shell, -1, axis=1) - np.roll(shell, 1, axis=1)
    normal = np.cross(tangent, np.gradient(shell, axis=0))
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    direction = 1 if np.sum(normal[-1, :, 2]) > 0 else -1
    normal *= direction

    # A disk chart keeps the meridian welded. Carry the donor colours along
    # its circumference into the first rings, with one skin tone at the pole.
    maps = {mat.name: np.asarray(Image.open(model.textures[mat.texture].path).convert('RGB'))
            for mat in (face, skin)}
    shades = []
    for key in loop:
        i, mat = donors[key]
        image = maps[mat.name]
        uv = np.clip(model.vertices[i].uv, 0, 1)
        x, y = np.rint(uv * (np.array(image.shape[1::-1]) - 1)).astype(int)
        shades.append(image[y, x])
    shades = np.array([*shades, shades[0]])
    gy, gx = np.mgrid[:256, :256]
    dx, dy = (gx + .5 - 128) / 124, (gy + .5 - 128) / 124
    us = (np.arctan2(dy, dx) / (2*pi)) % 1
    band = np.stack([np.interp(us, u, channel) for channel in shades.T], axis=-1)
    blend = np.exp(-(np.maximum(0, 1 - np.hypot(dx, dy)) / .22)**2)[..., None]
    rgb = blend * band + (1 - blend) * np.median(shades, axis=0)
    Image.fromarray(rgb.round().astype('uint8')).save(TEX / 'yuexiao-scalp.png')

    scalp = copy.deepcopy(skin)
    scalp.name = scalp.name_e = 'QingyiScalp'
    scalp.texture = atelier.tex('yuexiao-scalp.png')
    rigid = PMX['BoneWeight']()
    rigid.bones = [head]
    faces = []
    rings = []
    morph_links = defaultdict(list)
    neck = atelier.bones['首']
    from yuexiao_torso import skin_weights
    neck_weight = np.array([dict(skin_weights(model.vertices[i])).get(neck, 0) for i in ids])
    for j in range(rows):
        ring = []
        for k in range(0, columns, 3 if j == 0 else 1):
            left, mix = k // 3, (k % 3) / 3
            right = (left + 1) % count
            old = model.vertices[ids[left]]
            vertex = PMX['Vertex']()
            vertex.co = shell[j, k]
            vertex.normal = old.normal if j == 0 else normal[j, k]
            angle_uv = 2*pi*longitude[k]
            vertex.uv = .5 + (124/256) * (1 - j/rows) * np.array([np.cos(angle_uv), np.sin(angle_uv)])
            vertex.weight = rigid
            if j == 0:
                vertex.weight = old.weight
            elif j < 6:
                w = ((1-mix)*neck_weight[left] + mix*neck_weight[right]) * (1 - j/6)**2
                if w > 0:
                    vertex.weight = PMX['BoneWeight']()
                    vertex.weight.type = rigid.BDEF2
                    vertex.weight.bones, vertex.weight.weights = [neck, head], [w]
            vertex.edge_scale = 0
            index = len(model.vertices)
            ring.append(index)
            model.vertices.append(vertex)
            if j < 6:
                for donor, weight in ((ids[left], 1-mix), (ids[right], mix)):
                    if weight:
                        morph_links[donor].append((index, weight*(1-j/6)**2))
        rings.append(ring)
    for outer, inner in zip(rings, rings[1:]):
        stride = len(inner) // len(outer)
        for k, a in enumerate(outer):
            b = outer[(k+1) % len(outer)]
            strip = [inner[(k*stride+i) % len(inner)] for i in range(stride+1)]
            faces.append([a,b,strip[-1]])
            faces.extend([a,q,p] for p,q in zip(strip,strip[1:]))
    tip = PMX['Vertex']()
    tip.co, tip.normal, tip.uv, tip.weight, tip.edge_scale = pole, (0., 0., 1.), (.5, .5), rigid, 0
    end = len(model.vertices)
    model.vertices.append(tip)
    faces.extend([a,b,end] for a,b in zip(rings[-1],rings[-1][1:]+rings[-1][:1]))
    if direction > 0:  # PMX stores clockwise triangles.
        faces = [f[::-1] for f in faces]
    # Propagate expression offsets through the first few rings.
    for morph in model.morphs:
        if morph.type_index() != 1:
            continue
        deltas = defaultdict(lambda: np.zeros(3))
        for old in morph.offsets:
            for index, weight in morph_links.get(old.index, ()):
                deltas[index] += np.asarray(old.offset) * weight
        for index, delta in deltas.items():
            offset = PMX['VertexMorphOffset']()
            offset.index, offset.offset = index, delta
            morph.offsets.append(offset)
    model.faces[first:last] = kept
    face.vertex_count = 3 * len(kept)
    scalp.vertex_count = 3 * len(faces)
    model.faces.extend(faces)
    model.materials.append(scalp)
