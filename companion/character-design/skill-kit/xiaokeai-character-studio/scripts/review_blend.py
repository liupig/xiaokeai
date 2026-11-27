"""Render four matched clay views using Blender's evaluated scene at the current frame."""
import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--collection", help="Character collection, including nested collections")
    parser.add_argument("--front", choices=["-y", "y", "-x", "x"], default="-y")
    parser.add_argument("--height", type=float, help="Fixed orthographic view height in scene units")
    parser.add_argument("--center", nargs=3, type=float, metavar=("X", "Y", "Z"))
    parser.add_argument("--size", type=int, default=640)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    if args.size < 16 or (args.height is not None and args.height <= 0):
        parser.error("Supply a positive height and an image size of at least 16.")
    scene = bpy.context.scene
    collection = bpy.data.collections.get(args.collection) if args.collection else scene.collection
    if not collection:
        parser.error(f"Collection not found: {args.collection}")
    meshes = {ob for ob in collection.all_objects if ob.type == "MESH" and ob.visible_get() and not ob.hide_render}
    if not meshes:
        parser.error("No visible renderable meshes in the chosen collection.")
    for ob in scene.objects:
        if ob.type in {"MESH", "CURVE", "FONT", "SURFACE", "META", "VOLUME", "POINTCLOUD", "GREASEPENCIL"} and ob not in meshes:
            ob.hide_render = True
    graph = bpy.context.evaluated_depsgraph_get()
    corners = []
    for ob in meshes:
        evaluated = ob.evaluated_get(graph)
        corners.extend(evaluated.matrix_world @ Vector(point) for point in evaluated.bound_box)
    low = Vector([min(p[i] for p in corners) for i in range(3)])
    high = Vector([max(p[i] for p in corners) for i in range(3)])
    center = Vector(args.center) if args.center else (low + high) / 2
    camera = bpy.data.cameras.new("Review camera")
    obj = bpy.data.objects.new("Review camera", camera)
    scene.collection.objects.link(obj)
    scene.camera = obj
    radius = max(.001, max((p-center).length for p in corners))
    camera.type = "ORTHO"
    camera.clip_start, camera.clip_end = radius*.001, radius*8
    span = max(2*max(abs(p.z-center.z), math.hypot(p.x-center.x, p.y-center.y)) for p in corners)
    camera.ortho_scale = args.height or max(.001,span*1.09)
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light, shading.color_type = "STUDIO", "SINGLE"
    shading.single_color = (.68,.64,.62)
    shading.background_type, shading.background_color = "VIEWPORT", (.08,.08,.095)
    shading.show_shadows, shading.show_cavity = True, False
    scene.render.film_transparent = False
    scene.render.use_sequencer = False
    scene.render.use_compositing = False
    scene.render.use_border = False
    scene.render.resolution_x = scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_file_extension = True
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    yaw = {"-y":0, "x":90, "y":180, "-x":270}[args.front]
    for label, angle in [("front",0), ("three-quarter",45), ("side",90), ("back",180)]:
        a = math.radians(yaw+angle)
        direction = Vector((math.sin(a),-math.cos(a),0))
        obj.location = center + direction*radius*3
        obj.rotation_euler = (-direction).to_track_quat("-Z","Y").to_euler()
        scene.render.filepath = str(args.out/(label+".png"))
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
