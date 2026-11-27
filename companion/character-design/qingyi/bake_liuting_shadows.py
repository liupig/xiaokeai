"""Bake short-range contact shadows on the fitted hair using Blender's BVH."""
import json
import sys
from pathlib import Path
from math import cos, pi, sin, sqrt

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import delaunay_2d_cdt


def triangulate_sockets(filename):
    path = Path(filename)
    result = []
    for panel in json.loads(path.read_text()):
        n = panel["rim"]
        points = [Vector(p) for p in panel["points"]]
        _, _, faces, origins, _, _ = delaunay_2d_cdt(
            points, [], [list(range(n))], 2, 1e-7)
        result.append([[origins[i][0] for i in face] for face in faces])
    path.write_text(json.dumps(result))


def bake(mesh_path, output_path):
    with np.load(mesh_path) as mesh:
        positions, normals, triangles = (mesh[k] for k in ("positions","normals","triangles"))
    tree = BVHTree.FromPolygons(positions.tolist(),triangles.tolist(),all_triangles=True)
    rays = []
    for i in range(40):
        radius = sqrt((i+.5)/40)
        angle = i*pi*(3-sqrt(5))
        rays.append((radius*cos(angle),radius*sin(angle),sqrt(1-radius*radius)))
    contact = np.zeros(len(positions),dtype=np.float32)
    up, right = Vector((0,1,0)), Vector((1,0,0))
    for i,(point,normal) in enumerate(zip(positions,normals)):
        n = Vector(normal).normalized()
        side = n.cross(up if abs(n.y)<.85 else right).normalized()
        along = n.cross(side)
        origin = Vector(point)+.012*n
        total = 0.
        for x,y,z in rays:
            hit = tree.ray_cast(origin,x*side+y*along+z*n,.58)[3]
            if hit is not None:
                total += (1-hit/.58)**1.5
        contact[i] = total/len(rays)
    np.save(output_path,contact)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--")+1:]
    if args[0] == "sockets":
        triangulate_sockets(args[1])
    else:
        bake(*args)
