"""Reconstruct the two ear sockets on the native crown, sharing their posed rims."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import cv2
import numpy as np
from PIL import Image
from scipy.interpolate import RBFInterpolator
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def boundary_loops(faces, coords):
    # UV seams split PMX vertices. Trace geometric half-edges, retaining the
    # original face corners so their individual UVs can be sampled later.
    ids = np.unique(faces)
    _, weld = np.unique(np.round(coords[ids], 5), axis=0, return_inverse=True)
    corners = np.vstack([faces, faces[:, [1, 2, 0]], faces[:, [2, 0, 1]]])
    edges = weld[np.searchsorted(ids, corners[:, :2])]
    _, first, counts = np.unique(np.sort(edges, axis=1), axis=0,
                                 return_index=True, return_counts=True)
    starts = first[counts == 1]
    # Only two completely enclosed rims lie on the upper lateral scalp.
    upper = (coords[corners[starts, :2], 1].min(axis=1) > 20.35)
    starts = starts[upper]
    next_edge = {edges[i, 0]: i for i in starts}
    while next_edge:
        start = next(iter(next_edge))
        at, ordered = start, []
        while at in next_edge:
            i = next_edge.pop(at)
            ordered.append(corners[i])
            at = edges[i, 1]
        if at == start and len(ordered) >= 12:
            loop = np.array(ordered)
            p = coords[loop[:, 0]]
            if np.ptp(p[:, 2]) > .9 and np.min(abs(p[:, 0])) > .24:
                yield loop


def meridian(coords, side):
    x, y, z = coords.T
    q = np.arctan2(side*x, (y-19.86)/1.35)
    return np.column_stack([z, q])


def strand_lane(z, q, side):
    # The two native crown sections are combed in different directions.
    # Each lane opens out from the front part and bends toward the gather.
    fan = .69 + .40*np.tanh((z-.20)/.53)
    sweep = (.48 if side < 0 else .27)*z - .09*z*z
    return (q-sweep)/fan


def fit_crown(model, original, comb):
    hair = next(m for m in model.materials if m.name == "Hair_Back")
    start = sum(m.vertex_count for m in model.materials[:model.materials.index(hair)])//3
    faces = np.asarray(model.faces[start:start+hair.vertex_count//3])
    coords = np.array([v.co for v in model.vertices])
    for i, delta in original.items():
        coords[i] += delta
    ids = np.unique(faces)
    _, weld = np.unique(np.round(coords[ids], 5), axis=0, return_inverse=True)
    welded = weld[np.searchsorted(ids, faces)]
    graph_edges = np.vstack([welded[:, :2], welded[:, 1:], welded[:, [2, 0]]])
    _, island = connected_components(coo_matrix((np.ones(len(graph_edges)), graph_edges.T),
                                                 shape=(weld.max()+1, weld.max()+1)), directed=False)
    uv = np.array([v.uv for v in model.vertices])
    panels = []
    for edges in boundary_loops(faces, coords):
        rim = coords[edges[:, 0]]
        side = np.sign(rim[:, 0].mean())
        chart = meridian(rim, side)
        contour = chart.astype(np.float32)
        lo, hi = chart.min(axis=0)-.025, chart.max(axis=0)+.025
        step = .035
        interior = []
        depths = []
        for row, q in enumerate(np.arange(lo[1], hi[1], step*.87)):
            for z in np.arange(lo[0]+(row % 2)*step*.5, hi[0], step):
                d = cv2.pointPolygonTest(contour, (z, q), True)
                if d > .47*step:
                    interior.append((z, q))
                    depths.append(d)
        points = np.vstack([chart, interior])
        z, q = points.T
        # Fit the residual from an ellipsoid. This restores convexity at the
        # old socket without flattening the side where the knot draws it down.
        def ellipse(depth):
            return np.sqrt(np.maximum(.18, 1-((depth-.53)/1.4)**2))
        radial = np.hypot(rim[:, 0], (rim[:, 1]-19.86)/1.35)
        field = RBFInterpolator(chart, radial/ellipse(chart[:, 0]))
        r = field(points)*ellipse(z)
        depth = np.r_[np.zeros(len(rim)), depths]
        lane = strand_lane(z, q, side)
        r += .015*(1-np.exp(-depth/.075))*(.45+np.cos(17*lane+.6*np.sin(6*lane)))
        xyz = np.column_stack([side*r*np.sin(q), 19.86+1.35*r*np.cos(q), z])
        xyz[:len(rim)] = rim
        posed = np.array([comb(p, "Hair_Back") for p in xyz])
        normals = np.array([model.vertices[i].normal for i in edges[:, 0]])
        edge_uv = np.array([[model.vertices[i].uv for i in tri] for tri in edges])
        shell = island[welded[:, 0]] == island[weld[np.searchsorted(ids, edges[0, 0])]]
        upper = shell & (side*coords[faces, 0].mean(axis=1) > .1) & (coords[faces, 1].max(axis=1) > 20.05)
        shell_xyz = coords[faces[upper]]
        panels.append(dict(side=side, points=points, rim=len(rim), lo=lo, hi=hi,
                           coords=posed, rim_normals=normals, edge_uv=edge_uv,
                           shell_chart=meridian(shell_xyz.reshape(-1, 3), side).reshape(-1, 3, 2),
                           shell_uv=uv[faces[upper]],
                           edge_ids=edges[:, 0], depth=depth))
    panels.sort(key=lambda panel: panel["side"])
    if len(panels) != 2:
        raise ValueError(f"Expected two crown sockets, found {len(panels)}")
    here = Path(__file__).resolve().parent
    bundled = sorted((here.parents[1]/"tools/blender").glob("*/blender.exe"))
    blender = str(bundled[-1]) if bundled else shutil.which("blender")
    with TemporaryDirectory() as work:
        path = Path(work)/"sockets.json"
        path.write_text(json.dumps([dict(points=p["points"].tolist(), rim=p["rim"]) for p in panels]))
        subprocess.run([blender, "-b", "--python-exit-code", "1", "-P",
                        str(here/"bake_liuting_shadows.py"), "--", "sockets", str(path)], check=True)
        meshes = json.loads(path.read_text())
    for panel, triangles in zip(panels, meshes):
        tris = np.asarray(triangles)
        n = panel["rim"]
        directed = np.vstack([tris[:, :2], tris[:, 1:], tris[:, [2, 0]]])
        if ((directed == [0, 1]).all(axis=1)).any():
            tris = tris[:, ::-1]
        edges, counts = np.unique(np.sort(directed, axis=1), axis=0, return_counts=True)
        expected = {tuple(sorted((i, (i+1) % n))) for i in range(n)}
        if set(map(tuple, edges[counts == 1])) != expected:
            raise ValueError("Crown triangulation lost a rim edge")
        verts = panel["coords"]
        normals = np.zeros_like(verts)
        areas = np.cross(verts[tris[:, 1]]-verts[tris[:, 0]], verts[tris[:, 2]]-verts[tris[:, 0]])
        for corner in tris.T:
            np.add.at(normals, corner, areas)
        if (normals[:n]*panel["rim_normals"]).sum() < 0:
            normals *= -1
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
        # Use the original corner normals at the boundary, with a narrow
        # transition to the normals of the actual fitted surface.
        chart = panel["points"]
        distance = np.linalg.norm(chart[:, None]-chart[:n], axis=2)
        influence = 1/np.maximum(distance, 1e-5)**3
        neighbour = (influence @ panel["rim_normals"])/influence.sum(axis=1)[:, None]
        mix = np.exp(-panel["depth"]/.052)[:, None]
        normals = normals*(1-mix)+neighbour*mix
        panel["normals"] = normals/np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
        panel["triangles"] = tris
    return panels


def attach_crown(model, pmx, panels, path):
    tex = pmx["Texture"]()
    tex.path = str(path)
    mat = copy.deepcopy(next(m for m in model.materials if m.name == "Hair_Back"))
    mat.name = mat.name_e = "Liuting_Crown"
    mat.texture = len(model.textures)
    mat.diffuse = (1., 1., 1., 1.)
    mat.ambient = (.11, .10, .13)
    mat.enabled_toon_edge = False
    mat.vertex_count = 0
    model.textures.append(tex)
    for side_index, p in enumerate(panels):
        first = len(model.vertices)
        uv = (p["points"]-p["lo"])/(p["hi"]-p["lo"])
        uv[:, 0] = (side_index+uv[:, 0])*.5
        head = copy.deepcopy(model.vertices[p["edge_ids"][0]].weight)
        for pos, normal, texcoord in zip(p["coords"], p["normals"], uv):
            v = pmx["Vertex"]()
            v.co, v.normal, v.uv, v.weight = pos, normal, texcoord, head
            model.vertices.append(v)
        model.faces.extend((p["triangles"]+first).tolist())
        mat.vertex_count += p["triangles"].size
    model.materials.append(mat)


def raster_map(triangle, values, shape):
    low = np.maximum(np.floor(triangle.min(axis=0)).astype(int), 0)
    high = np.minimum(np.ceil(triangle.max(axis=0)).astype(int)+1, shape)
    if np.any(high <= low):
        return
    local = np.float32(triangle-low)
    if abs(cv2.contourArea(local)) < .01:
        return
    mask = np.zeros(tuple((high-low)[::-1]), np.uint8)
    cv2.fillConvexPoly(mask, np.int32(np.rint(local*32)), 1, shift=5)
    y, x = np.where(mask)
    transform = cv2.getAffineTransform(local, np.float32(values))
    sample = np.column_stack([x, y])@transform[:, :2].T+transform[:, 2]
    return y+low[1], x+low[0], sample


def soften_ear_shadow(panel, tex):
    # The native ear cast a dark, triangular painted shadow on a peninsula
    # of intact hair. Recomb it from a nearby undamaged part of the same
    # painted lock. Work in scalp coordinates across both PMX UV charts.
    shape = np.array(tex.shape[1::-1])
    chart, uv = panel["shell_chart"], panel["shell_uv"]*shape-.5
    donor_size = np.array([180, 512])
    lower = np.array([1.32, .27])
    span = np.array([.30, .92])
    donor = np.zeros((*donor_size[::-1], 3), np.uint8)
    seen = np.zeros(donor_size[::-1], np.uint8)
    for tri, tex_tri in zip(chart, uv):
        sample = raster_map((tri-lower)/span*donor_size, tex_tri, donor_size)
        if sample is not None:
            y, x, coords = sample
            u, v = np.int32(np.rint(coords)).clip(0, shape-1).T
            donor[y, x] = tex[v, u]
            seen[y, x] = 1
    _, nearest = cv2.distanceTransformWithLabels(1-seen, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    lut = np.zeros((nearest.max()+1, 3), np.uint8)
    lut[nearest[seen > 0]] = donor[seen > 0]
    donor = lut[nearest]

    def stroke(z, q):
        donor_z = 1.45+.064*np.sin(2.8*z-.54*q)
        donor_q = .75*q+.159+(.23+.105*(1-q))*(donor_z-z)-.058*(donor_z-z)**2
        u = np.clip((donor_z-lower[0])/span[0]*donor_size[0], 0, donor_size[0]-1.001)
        v = np.clip((donor_q-lower[1])/span[1]*donor_size[1], 0, donor_size[1]-1.001)
        x, y = u.astype(int), v.astype(int)
        fx, fy = (u-x)[..., None], (v-y)[..., None]
        target = ((1-fy)*((1-fx)*donor[y, x]+fx*donor[y, x+1])+
                  fy*((1-fx)*donor[y+1, x]+fx*donor[y+1, x+1]))
        # A soft brush stops just above the underlapping nape lock.
        def ramp(t):
            t = np.clip(t, 0, 1)
            return t*t*(3-2*t)
        weight = (ramp((z-.04)/.18)*ramp((1.46-z)/.38)*
                  ramp((q-.52)/.25)*ramp((1.23-q)/.115))
        return target, weight[..., None]

    # Paint each chart texel once, even along shared triangle edges.
    original = tex.copy()
    for tri, tex_tri in zip(chart, uv):
        if (tri[:, 0].max() < .04 or tri[:, 0].min() > 1.46 or
                tri[:, 1].max() < .52 or tri[:, 1].min() > 1.23):
            continue
        result = raster_map(tex_tri, tri, shape)
        if result is not None:
            y, x, coords = result
            target, weight = stroke(*coords.T)
            tex[y, x] = original[y, x]*(1-weight)+target*weight
    return stroke


def paint_crown(panels, source, dest):
    # Transport the native painted colours along the sweep of the hair.
    # Every sample on the PMX seam comes from the corresponding native UV
    # edge, including the short section across a UV split.
    original = Image.open(source).convert("RGBA")
    tex = np.asarray(original.convert("RGB"), dtype=np.float32)
    stroke = soften_ear_shadow(panels[1], tex)
    Image.fromarray(np.dstack([tex.astype(np.uint8), np.asarray(original.getchannel("A"))])).save(source)
    outputs = []
    size = 640
    yy, xx = (np.indices((size, size), dtype=np.float32)+.5)/size
    for p in panels:
        z = p["lo"][0]+xx*(p["hi"][0]-p["lo"][0])
        q = p["lo"][1]+yy*(p["hi"][1]-p["lo"][1])
        lane = strand_lane(z, q, p["side"])
        chart = p["points"][:p["rim"]]
        dist = np.full((2, size, size), np.inf, np.float32)
        paint = np.zeros((2, size, size, 3), np.float32)
        for i, (a, b) in enumerate(zip(chart, np.roll(chart, -1, axis=0))):
            ua, ub, uc = p["edge_uv"][i]
            # Short segments follow the curved lane even along a long edge.
            for t0, t1 in zip(np.arange(0, 1, .25), np.arange(.25, 1.01, .25)):
                c = (1-t0)*a+t0*b
                d = (1-t1)*a+t1*b
                v0, v1 = strand_lane(*c, p["side"]), strand_lane(*d, p["side"])
                if abs(v1-v0) < 1e-8:
                    continue
                iy, ix = np.where((lane >= min(v0, v1)) & (lane <= max(v0, v1)))
                f = (lane[iy, ix]-v0)/(v1-v0)
                t = t0+(t1-t0)*f
                travel = z[iy, ix]-(a[0]+(b[0]-a[0])*t)
                direction = (travel < 0).astype(int)
                uv = ua+(ub-ua)*t[:, None]
                uv += .012*(uc-uv)
                coord = np.clip(uv*np.array(tex.shape[1::-1])-.5, 0, np.array(tex.shape[1::-1])-1.001)
                px, py = coord.astype(int).T
                fx, fy = (coord-np.floor(coord)).T[:, :, None]
                rgb = ((1-fy)*((1-fx)*tex[py, px]+fx*tex[py, px+1])+
                       fy*((1-fx)*tex[py+1, px]+fx*tex[py+1, px+1]))
                keep = abs(travel) < dist[direction, iy, ix]
                which = direction[keep], iy[keep], ix[keep]
                dist[which] = abs(travel[keep])
                paint[which] = rgb[keep]
        valid = np.isfinite(dist).all(axis=0)
        # Padding also covers sub-pixel precision differences along the rim.
        a, b = np.minimum(dist, 1e4)
        t = a/(a+b+1e-9)
        rgb = paint[0]*(1-t[:, :, None])+paint[1]*t[:, :, None]
        weight = np.minimum(1., np.minimum(a, b)/.15)
        phase = lane*29 + .27*np.sin(lane*10+z*1.2)
        grain = (2.7*np.cos(phase)+1.4*np.cos(phase*2.23+.6*z)+
                 .9*np.cos(phase*11.4+.8*np.sin(z*2+lane)))
        rgb += (weight*grain)[:, :, None]
        if p["side"] > 0:
            target, blend = stroke(z, q)
            # Match the repainted peninsula through the centre of the panel.
            rgb += (target-rgb)*blend*np.minimum(1., np.minimum(a, b)/.06)[:, :, None]
        _, nearest = cv2.distanceTransformWithLabels(np.uint8(~valid), cv2.DIST_L2, 5,
                                                       labelType=cv2.DIST_LABEL_PIXEL)
        lut = np.zeros((nearest.max()+1, 3), np.uint8)
        lut[nearest[valid]] = np.uint8(np.clip(rgb[valid], 0, 255))
        outputs.append(lut[nearest])
    Image.fromarray(np.hstack(outputs)).save(dest)
