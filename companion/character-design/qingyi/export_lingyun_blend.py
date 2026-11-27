"""Pack the current, sole visible Qingyi hairstyle into an editable Blender scene."""
from pathlib import Path
from math import radians
import json
import tempfile
import sys
from time import sleep
from uuid import uuid4
from collections import Counter
import bmesh
import bpy
from mathutils import Euler
from mathutils.kdtree import KDTree

root=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(root/"companion/tools"),str(root/"companion/tools/python-packages")]
import mmd_tools
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fengguan import add_blender_regalia
bpy.ops.wm.read_factory_settings(use_empty=True)
mmd_tools.register()
variant = sys.argv[sys.argv.index("--")+1] if "--" in sys.argv else "lingyun"
if variant not in ("liuting","lingyun","lanxu","yuexiao","yuexiao-photo","yuexiao-strapless"):
    raise ValueError(f"Unknown variant: {variant}")
two_view = variant in ("yuexiao", "yuexiao-strapless")
style = "liuting" if variant == "lanxu" else variant
bpy.ops.mmd_tools.import_model(
    filepath=str(Path(tempfile.gettempdir())/f"qingyi-{variant}-edit.pmx"),
    scale=.08,rename_bones=False)


def join_material_rims(ob, panel_name, donor_names):
    # PMX splits vertices at UV seams. In the editing scene the two charts
    # can share a vertex because Blender stores their UVs per face corner.
    mesh = ob.data
    slots = [m.name for m in mesh.materials]
    def boundary(name):
        index = slots.index(name)
        edges = Counter(e for face in mesh.polygons if face.material_index == index for e in face.edge_keys)
        return {edge for edge, count in edges.items() if count == 1}
    panel = boundary(panel_name)
    donor = set().union(*(boundary(name) for name in donor_names))
    ids = {i for e in donor for i in e}
    tree = KDTree(len(ids))
    for i in ids:
        tree.insert(mesh.vertices[i].co, i)
    tree.balance()
    target = {}
    for i in {i for e in panel for i in e}:
        matches = sorted(hit[1] for hit in tree.find_range(mesh.vertices[i].co, .000002))
        if not matches:
            raise ValueError(f"Unmatched rim vertex in {panel_name}")
        for source in [i, *matches[1:]]:
            if source != matches[0]:
                target[source] = matches[0]
    if not target:
        if not panel.issubset(donor):
            raise ValueError(f"Disconnected boundary in {panel_name}")
        return
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bmesh.ops.weld_verts(bm, targetmap={bm.verts[i]:bm.verts[j] for i,j in target.items()})
    bmesh.update_edit_mesh(mesh)
    bpy.ops.object.mode_set(mode="OBJECT")
    joined = boundary(panel_name)
    if len(joined) != len(panel) or not joined.issubset(set().union(*(boundary(name) for name in donor_names))):
        raise ValueError(f"Unjoined edge in {panel_name}")


for ob in bpy.context.scene.objects:
    if ob.type=="ARMATURE":
        ob.show_in_front=False
    elif style == "liuting" and ob.type == "MESH" and "Liuting_Crown" in ob.data.materials:
        join_material_rims(ob,"Liuting_Crown",["Hair_Back"])
    elif two_view and ob.type == "MESH" and "QingyiTorso" in ob.data.materials:
        join_material_rims(ob,"QingyiTorso",["Up_Skin","Down_Skin"])
        join_material_rims(ob,"QingyiScalp",["Face_","Up_Skin"])
if style == "liuting":
    armature = next(ob for ob in bpy.context.scene.objects if ob.type=="ARMATURE")
    add_blender_regalia(bpy,armature)


def apply_costume_finish(mat, tex, shader, recipe):
    tree = mat.node_tree
    def node(kind, label, x, y):
        result = tree.nodes.new(kind)
        result.label = label
        result.location = (x, y)
        return result
    wire = tree.links.new
    shader.location = (150, 220)
    tree.nodes.get("Material Output").location = (500, 220)
    inputs = shader.inputs
    if tex:
        tex.location = (-740, 350)
        colour = node("ShaderNodeMixRGB", "Silk or setting colour", -360, 360)
        colour.blend_type = "MULTIPLY"
        colour.inputs[0].default_value = 1
        colour.inputs[2].default_value = (*recipe["tint"], 1)
        wire(tex.outputs["Color"], colour.inputs[1])
        wire(colour.outputs[0], inputs["Base Color"])
        if "lacquerBase" in recipe:
            lacquer = node("ShaderNodeMixRGB", "Rose lacquer pigment", -120, 500)
            lacquer.inputs[0].default_value = .48
            lacquer.inputs[2].default_value = (*recipe["lacquerBase"],1)
            wire(colour.outputs[0], lacquer.inputs[1])
            wire(lacquer.outputs[0], inputs["Base Color"])
        wire(tex.outputs["Color"], inputs["Emission Color"])
    else:
        rgb = tuple(mat.mmd_material.diffuse_color)
        inputs["Base Color"].default_value = (*[x*y for x,y in zip(rgb,recipe["tint"])],1)
        inputs["Emission Color"].default_value = (*rgb,1)
    if "opacity" in recipe:
        inputs["Alpha"].default_value *= recipe["opacity"]
    for socket, key in (("Emission Strength","fill"), ("Roughness","roughness"),
                        ("Metallic","metalness"), ("Coat Weight","coat"), ("Coat Roughness","coatRough"),
                        ("Anisotropic","anisotropy"), ("Sheen Weight","sheen"), ("Sheen Roughness","sheenRough")):
        inputs[socket].default_value = recipe[key]
    inputs["IOR"].default_value = 1.48
    inputs["Transmission Weight"].default_value = recipe.get("transmission", 0)
    inputs["Specular IOR Level"].default_value = recipe["specular"] * .5
    inputs["Anisotropic Rotation"].default_value = .25
    if recipe["anisotropy"]:
        tangent = node("ShaderNodeTangent", "Direction of warp", -130, -600)
        tangent.direction_type = "UV_MAP"
        wire(tangent.outputs[0], inputs["Tangent"])
    def linear(channel):
        v = int(channel, 16)/255
        return v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4
    hex_colour = recipe["sheenTint"]
    inputs["Sheen Tint"].default_value = (*[linear(hex_colour[i:i+2]) for i in (1,3,5)], 1)
    if recipe["film"]:
        inputs["Thin Film Thickness"].default_value = 155
        inputs["Thin Film IOR"].default_value = 1 + .28*recipe["film"]
    if mat.name in ("Moon_Veil","Moon_Gauze"):
        coverage = node("ShaderNodeMath", "Thread coverage", -130, 500)
        coverage.operation = "MULTIPLY"
        coverage.inputs[1].default_value = inputs["Alpha"].default_value
        wire(tex.outputs["Alpha"], coverage.inputs[0])
        wire(coverage.outputs[0], inputs["Alpha"])
    if not recipe["map"]:
        return
    filename = 'yuexiao-' + recipe["map"] + '-finish.png'
    packed = node("ShaderNodeTexImage", "Height / roughness / metal", -740, -50)
    packed.image = bpy.data.images.load(str(root / 'online-demo/frontend/public/models/qingyi-jade/textures' / filename), check_existing=True)
    packed.image.colorspace_settings.name = 'Non-Color'
    channels = node("ShaderNodeSeparateColor", "Linear surface channels", -460, -50)
    wire(packed.outputs["Color"], channels.inputs[0])
    if recipe.get("studioResponse"):
        gain = node("ShaderNodeMath", "Studio diffuse compensation", -370, -360)
        gain.operation = "MULTIPLY_ADD"
        gain.inputs[1].default_value = 1.4
        gain.inputs[2].default_value = .4
        wire(channels.outputs["Blue"], gain.inputs[0])
        pigment = node("ShaderNodeMixRGB", "Calibrated pigment", -100, 340)
        pigment.blend_type = "MULTIPLY"
        pigment.inputs[0].default_value = 1
        wire(colour.outputs[0], pigment.inputs[1])
        wire(gain.outputs[0], pigment.inputs[2])
        wire(pigment.outputs[0], inputs["Base Color"])
    bump = node("ShaderNodeBump", "Thread or chased relief", -130, -360)
    bump.inputs["Distance"].default_value = recipe["bump"]
    wire(channels.outputs["Red"], bump.inputs["Height"])
    wire(bump.outputs["Normal"], inputs["Normal"])
    for socket, channel, value, y in (("Roughness","Green",recipe["roughness"],0),
                                     ("Metallic","Blue",recipe["metalness"],-160)):
        if value:
            scale = node("ShaderNodeMath", socket, -130, y)
            scale.operation = "MULTIPLY"
            scale.inputs[1].default_value = value
            wire(channels.outputs[channel], scale.inputs[0])
            wire(scale.outputs[0], inputs[socket])
    if recipe["map"] in ("fibre","mantle","parted-fringe"):
        secondary = node("ShaderNodeBsdfAnisotropic", "Cuticle reflection", 150, -110)
        secondary.inputs["Color"].default_value = (.91,.76,.82,1)
        secondary.inputs["Roughness"].default_value = .37
        secondary.inputs["Anisotropy"].default_value = .76
        secondary.inputs["Rotation"].default_value = .27
        wire(tangent.outputs[0], secondary.inputs["Tangent"])
        wire(bump.outputs["Normal"], secondary.inputs["Normal"])
        reflection = node("ShaderNodeMixShader","Fibre reflection",430,160)
        reflection.inputs[0].default_value = .09
        if mat.name == "MoonHair_Fibres":
            coverage = node("ShaderNodeMath","Reflection coverage",140,-350)
            coverage.operation = "MULTIPLY"
            coverage.inputs[1].default_value = .09
            wire(tex.outputs["Alpha"],coverage.inputs[0])
            wire(coverage.outputs[0],reflection.inputs[0])
        wire(shader.outputs[0],reflection.inputs[1])
        wire(secondary.outputs[0],reflection.inputs[2])
        output=tree.nodes.get("Material Output")
        output.location=(650,160)
        wire(reflection.outputs[0],output.inputs["Surface"])


def add_neckline_reflection(tree, mask, surface):
    mask.image.alpha_mode = 'CHANNEL_PACKED'
    original = surface.links[0].from_socket
    coverage = tree.nodes.new('ShaderNodeMath')
    coverage.operation = 'SUBTRACT'
    coverage.inputs[0].default_value = 1.
    coverage.location = (-390,-720)
    tree.links.new(mask.outputs['Alpha'],coverage.inputs[1])
    tint = tree.nodes.new('ShaderNodeVectorMath')
    tint.operation = 'SCALE'
    tint.inputs[0].default_value = (.182,.148,.136)
    tint.location = (-160,-720)
    tree.links.new(coverage.outputs[0],tint.inputs['Scale'])
    lobe = tree.nodes.new('ShaderNodeBsdfGlossy')
    lobe.label = 'Upper neckline reflection'
    lobe.location = (55,-540)
    lobe.inputs['Roughness'].default_value = .52
    tree.links.new(tint.outputs[0],lobe.inputs['Color'])
    both = tree.nodes.new('ShaderNodeAddShader')
    both.location = (390,-120)
    tree.links.new(original,both.inputs[0])
    tree.links.new(lobe.outputs[0],both.inputs[1])
    tree.links.new(both.outputs[0],surface)


def apply_skin_zones(slot, zone_map, surface_folder):
    face = slot == 'Face_'
    tree = bpy.data.materials[slot].node_tree
    surface = next(n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL').inputs['Surface']
    original = surface.links[0].from_socket
    mask = tree.nodes.new('ShaderNodeTexImage')
    mask.label = 'Facial skin zones' if face else 'Body skin zones'
    mask.image = bpy.data.images.load(str(surface_folder/'textures'/f'yuexiao-{zone_map}-finish.png'), check_existing=True)
    mask.image.colorspace_settings.name = 'Non-Color'
    mask.location = (-650, -480)
    channels = tree.nodes.new('ShaderNodeSeparateColor')
    channels.location = (-400, -480)
    tree.links.new(mask.outputs['Color'], channels.inputs[0])
    satin = tree.nodes.new('ShaderNodeBsdfPrincipled')
    satin.label = 'Soft facial skin' if face else 'Soft body skin'
    satin.location = (-140, -390)
    tree.links.new(tree.nodes['mmd_base_tex'].outputs['Color'], satin.inputs['Base Color'])
    tree.links.new(channels.outputs['Green'], satin.inputs['Roughness'])
    tree.links.new(channels.outputs['Blue'], satin.inputs['Specular IOR Level'])
    if face:
        satin.inputs['Subsurface Weight'].default_value = .18
    else:
        tree.links.new(channels.outputs['Red'], satin.inputs['Subsurface Weight'])
    satin.inputs['Subsurface Scale'].default_value = .001
    strength = tree.nodes.new('ShaderNodeMath')
    strength.operation = 'MULTIPLY'
    strength.location = (-140, -220)
    strength.inputs[1].default_value = .16 if face else .38
    tree.links.new(channels.outputs['Red' if face else 'Blue'], strength.inputs[0])
    mix = tree.nodes.new('ShaderNodeMixShader')
    mix.location = (160, 0)
    tree.links.new(strength.outputs[0], mix.inputs[0])
    tree.links.new(original, mix.inputs[1])
    tree.links.new(satin.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], surface)
    if slot in ('Up_Skin','QingyiTorso'):
        add_neckline_reflection(tree,mask,surface)

finishes = {}
if two_view:
    if variant == 'yuexiao-strapless':
        surface_folder = root / 'online-demo/frontend/public/models/qingyi-jade'
        profile = json.loads((surface_folder / 'xiaokeai-pbr.json').read_text(encoding='utf-8'))
        for slot, zone_map in profile['skinZones'].items():
            apply_skin_zones(slot, zone_map, surface_folder)
        profiles = profile['finishes']
    else:
        profiles = json.loads((root / "online-demo/frontend/src/yuexiao-finishes.json").read_text(encoding="utf-8"))
    finishes = {material: profile for profile in profiles for material in profile["materials"]}
if variant in ("lanxu","yuexiao","yuexiao-photo","yuexiao-strapless"):
    for mat in bpy.data.materials:
        if not mat.name.startswith(("Lanxu_","Moon_","MoonHair_")) and mat.name not in finishes:
            continue
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        fabric = next((node.image for node in nodes if node.type=="TEX_IMAGE"
                       and node.image and (any(prefix in node.image.filepath for prefix in ("lanxu-","yuexiao-"))
                       or (mat.name.endswith("_Nail") and node.name=="mmd_base_tex"))),None)
        rgb = tuple(mat.mmd_material.diffuse_color)
        nodes.clear()
        out = nodes.new("ShaderNodeOutputMaterial")
        shader = nodes.new("ShaderNodeBsdfPrincipled")
        mat.node_tree.links.new(shader.outputs["BSDF"],out.inputs["Surface"])
        shader.inputs["Base Color"].default_value = (*rgb,1.)
        gilt = mat.name.endswith(("_GiltCord","_Gold","_Silver","_Engraving","_SandalGold","_ChasedMetal"))
        shader.inputs["Metallic"].default_value = .72 if gilt else 0.
        shader.inputs["Roughness"].default_value = .64 if fabric else .28 if gilt else .23
        if fabric:
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = fabric
            mat.node_tree.links.new(tex.outputs["Color"],shader.inputs["Base Color"])
            nodes.active = tex
            if mat.name.endswith(("_Down","_Nail")) or mat.name in ("MoonHair_Wisps","MoonHair_FrontFall","MoonHair_Fibres"):
                mat.node_tree.links.new(tex.outputs["Alpha"],shader.inputs["Alpha"])
            if two_view and mat.name in ("Moon_Silk","Moon_Brocade","Moon_Petal","Moon_PearlHem","Moon_Veil"):
                mat.node_tree.links.new(tex.outputs["Color"],shader.inputs["Emission Color"])
                shader.inputs["Emission Strength"].default_value=.16
            shader.inputs["Sheen Weight"].default_value = .32
            shader.inputs["Sheen Roughness"].default_value = .68
        elif not gilt:
            shader.inputs["Coat Weight"].default_value = .35
        if mat.name == "Moon_Gauze":
            shader.inputs["Alpha"].default_value = .39 if variant=="yuexiao-photo" else .54
        elif mat.name == "Moon_Veil":
            shader.inputs["Alpha"].default_value = .48
        elif mat.name == "Moon_IllusionBias":
            shader.inputs["Alpha"].default_value = .51
        elif mat.name == "Moon_Carving":
            shader.inputs["Metallic"].default_value = .24
            shader.inputs["Roughness"].default_value = .42
            shader.inputs["Sheen Weight"].default_value = 0.
        elif mat.name=="MoonHair_Glass":
            shader.inputs["Coat Weight"].default_value=.32
            shader.inputs["Roughness"].default_value=.27
        elif mat.name in ("Moon_Moonstone","Moon_Celadon","Moon_SandalPearl","Moon_LilacEnamel"):
            shader.inputs["Coat Weight"].default_value=.32
            shader.inputs["Roughness"].default_value=.27
            shader.inputs["Sheen Weight"].default_value=0
        if two_view and mat.name in ("Moon_Gauze","Moon_Veil"):
            shader.inputs["Thin Film Thickness"].default_value=125
            shader.inputs["Thin Film IOR"].default_value=1.28
            shader.inputs["Sheen Weight"].default_value=.58
        elif two_view and mat.name=="Moon_Petal":
            shader.inputs["Alpha"].default_value=.90
        if mat.name in finishes:
            apply_costume_finish(mat, tex if fabric else None, shader, finishes[mat.name])
        if variant=="yuexiao-photo" and mat.name in ("Moon_Silk","Moon_Petal","Moon_Brocade","Moon_Gauze","Moon_Illusion","Moon_Down","MoonHair_Down","MoonHair_Wisps","MoonHair_FrontFall"):
            shader.inputs["Roughness"].default_value=.82
            shader.inputs["Sheen Weight"].default_value=.16
bpy.ops.object.select_all(action="DESELECT")
for area in bpy.context.screen.areas:
    if area.type=="VIEW_3D":
        space=area.spaces.active
        space.overlay.show_overlays=False
        space.shading.color_type="TEXTURE"
        if two_view:
            space.shading.type="MATERIAL"
        space.region_3d.view_rotation=Euler((radians(88),0,radians(12))).to_quaternion()
        space.region_3d.view_distance=1.33
        space.region_3d.view_location=(0,0,1.48)
        if variant in ("lanxu","yuexiao","yuexiao-photo","yuexiao-strapless"):
            space.region_3d.view_distance=3.20
            space.region_3d.view_location=(0,0,.88)
bpy.ops.file.pack_all()
missing=[im.name for im in bpy.data.images if im.source=="FILE" and not im.packed_file and im.filepath]
if missing:
    raise ValueError(f"Missing texture files: {missing}")
destination = Path(__file__).with_name(f"qingyi-{variant}.blend")
if variant == "yuexiao-strapless":
    bpy.context.scene["角色名"] = "小可爱"
    bpy.context.scene["本版作者"] = "liupig"
staging = destination.with_name(f".{destination.stem}-{uuid4().hex}.blend")
try:
    save_options = {"compress": True} if variant in ("yuexiao","yuexiao-photo","yuexiao-strapless") else {}
    bpy.ops.wm.save_as_mainfile(filepath=str(staging),copy=True,**save_options)
    for attempt in range(8):
        try:
            staging.replace(destination)
            break
        except PermissionError:
            if attempt==7:
                raise
            sleep(.2*(attempt+1))
finally:
    staging.unlink(missing_ok=True)
