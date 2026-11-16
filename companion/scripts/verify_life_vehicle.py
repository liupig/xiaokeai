"""Render a bundled life vehicle in isolated background Blender for visual QA."""
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
if len(args) != 2:
    raise SystemExit('usage: blender -b --python verify_life_vehicle.py -- input.glb output.png')
model = Path(args[0]).resolve()
output = Path(args[1]).resolve()
if not model.is_file():
    raise SystemExit('vehicle model missing')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model))
meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
if not meshes:
    raise SystemExit('vehicle contains no mesh')
corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
low = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
high = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
center = (low + high) / 2
extent = max(high - low)
if extent <= 0:
    raise SystemExit('empty vehicle bounds')
bpy.ops.object.camera_add(location=center + Vector((extent * 1.55, -extent * 1.9, extent * 1.3)))
camera = bpy.context.object
camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = extent * 1.55
bpy.context.scene.camera = camera
bpy.ops.object.light_add(type='AREA', location=center + Vector((extent, -extent, extent * 2)))
bpy.context.object.data.energy = 500
bpy.context.object.data.shape = 'DISK'
bpy.context.object.data.size = extent * 3
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 16
if scene.world is None:
    scene.world = bpy.data.worlds.new('QA World')
scene.world.color = (0.22, 0.22, 0.22)
scene.render.resolution_x = 640
scene.render.resolution_y = 480
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = True
output.parent.mkdir(parents=True, exist_ok=True)
scene.render.filepath = str(output)
bpy.ops.render.render(write_still=True)
print(f'VEHICLE_OK meshes={len(meshes)} extent={extent:.3f} output={output}')
