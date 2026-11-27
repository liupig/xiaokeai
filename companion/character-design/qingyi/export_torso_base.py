"""Build the editable skin cage and its turntable from the same two shapes."""
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

import bmesh
import bpy
import numpy as np
from mathutils import Vector


DESIGN=Path(__file__).resolve().parent
PUBLIC=DESIGN.parents[2]/'online-demo/frontend/public/models/qingyi-jade'
KEY='自然胸廓'
bpy.ops.wm.read_factory_settings(use_empty=True)
data=np.load(Path(gettempdir())/'xiaokeai-torso-base.npz',allow_pickle=False)


def world(arr):
    return np.ascontiguousarray(arr[:,[0,2,1]]*.08,dtype=np.float32)


def make_cage():
    orig=data['coords']
    _,first,merge=np.unique(orig.round(5),axis=0,return_index=True,return_inverse=True)
    # PMX positions are split at texture boundaries; Blender corner UVs let
    # these loops deform together. Carry the original index on every corner.
    corners=data['faces']
    faces=merge[corners]
    valid=np.all(np.diff(np.sort(faces,axis=1),axis=1)!=0,axis=1)
    faces,corners=faces[valid],corners[valid]
    before=world(data['previous'][first])
    after=world(data['sculpt'][first])
    tris=before[faces]
    mid=tris.mean(axis=1)
    anterior=(abs(mid[:,0])<.085)&(mid[:,1]<-.035)&(mid[:,2]>1.33)&(mid[:,2]<1.45)
    if np.median(np.cross(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0])[anterior,1])>0:
        faces,corners=faces[:,::-1],corners[:,::-1]
    # Three nearly collinear seam triangles in the inherited waist patch
    # point against their neighbours. Orient by shared edges, not by radius.
    from collections import defaultdict, deque
    adjacency=defaultdict(list)
    for fi,tri in enumerate(faces):
        for i,j in zip(tri,np.roll(tri,-1)):
            adjacency[(min(i,j),max(i,j))].append((fi,i<j))
    graph=defaultdict(list)
    for entries in adjacency.values():
        if len(entries)==2:
            (i,di),(j,dj)=entries
            graph[i].append((j,di==dj));graph[j].append((i,di==dj))
    flip={}
    for start in range(len(faces)):
        if start in flip:continue
        flip[start]=False;q=deque([start])
        while q:
            i=q.popleft()
            for j,reverse in graph[i]:
                expected=flip[i]^reverse
                if j not in flip:flip[j]=expected;q.append(j)
                elif flip[j]!=expected:raise ValueError('Non-orientable skin')
    flipped=[i for i,k in flip.items() if k]
    faces[flipped]=faces[flipped,::-1];corners[flipped]=corners[flipped,::-1]
    mesh=bpy.data.meshes.new('原角色身体 · 缝合UV边')
    mesh.from_pydata(before.tolist(),[],faces.tolist())
    mesh.update()
    ob=bpy.data.objects.new('小可爱 · 上身底模',mesh)
    bpy.context.collection.objects.link(ob)
    clay=bpy.data.materials.new('素模 · 暖灰')
    clay.diffuse_color=(.52,.49,.47,1)
    clay.use_nodes=True
    bsdf=clay.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value=clay.diffuse_color
    bsdf.inputs['Roughness'].default_value=.54
    bsdf.inputs['Specular IOR Level'].default_value=.32
    mesh.materials.append(clay)
    mesh.polygons.foreach_set('use_smooth',np.ones(len(faces),dtype=bool))
    uv=data['uv'][corners.ravel()].copy();uv[:,1]=1-uv[:,1]
    mesh.uv_layers.new(name='原角色 UV').data.foreach_set('uv',np.ascontiguousarray(uv.ravel(),dtype=np.float32))
    ids=mesh.attributes.new('pmx_vertex','INT','CORNER')
    ids.data.foreach_set('value',np.ascontiguousarray(data['ids'][corners.ravel()],dtype=np.int32))
    slots=mesh.attributes.new('skin_panel','INT','FACE')
    slots.data.foreach_set('value',np.ascontiguousarray(data['surface'][valid],dtype=np.int32))
    # Use the exact armature datablock from the fitted character.
    with bpy.data.libraries.load(str(DESIGN/'qingyi-yuexiao-strapless.blend')) as (src,dst):
        dst.armatures=[next(n for n in src.armatures if 'strapless' in n)]
    rig=bpy.data.objects.new('小可爱 · 原骨架',dst.armatures[0])
    bpy.context.collection.objects.link(rig)
    skin=ob.modifiers.new('原骨架变形','ARMATURE');skin.object=rig
    ob.parent=rig
    rig.hide_set(True)
    return ob,corners,(before,after),first


def bind_skin(ob,first,previous):
    prefix='previous_' if previous else ''
    weights=data[prefix+'weights'];bones=data[prefix+'bones'];names=data['names']
    rig=ob.parent
    assert np.allclose(weights.sum(axis=1),1,atol=1e-5)
    ob.vertex_groups.clear()
    groups={}
    for i,src_index in enumerate(first):
        for idx,w in zip(bones[src_index],weights[src_index]):
            if w<=0:continue
            name=str(names[idx])
            if name not in rig.data.bones:raise ValueError('Missing bind bone '+name)
            if name not in groups:groups[name]=ob.vertex_groups.new(name=name)
            groups[name].add([i],float(w),'ADD')


def finish_posed_normals(ob,first):
    # Custom loop normals are relative to their original triangles. After
    # skinning, use the deformed surface tangents in the underarm transition.
    mask=ob.data.attributes.new('axilla_fair','FLOAT','POINT')
    mask.data.foreach_set('value',np.ascontiguousarray(data['axilla_fade'][first],np.float32))
    group=bpy.data.node_groups.new('腋下 · 姿势表面法线','GeometryNodeTree')
    group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    def node(kind,x,y):
        n=group.nodes.new(kind);n.location=(x,y);return n
    link=group.links.new
    src=node('NodeGroupInput',0,250)
    normal=node('GeometryNodeInputNormal',0,0)
    mask_node=node('GeometryNodeInputNamedAttribute',220,-240)
    mask_node.data_type='FLOAT';mask_node.inputs['Name'].default_value=mask.name
    blur=node('GeometryNodeBlurAttribute',200,30);blur.data_type='FLOAT_VECTOR'
    blur.inputs['Iterations'].default_value=12
    link(normal.outputs['True Normal'],blur.inputs['Value'])
    point=node('GeometryNodeFieldOnDomain',400,40);point.data_type='FLOAT_VECTOR';point.domain='POINT'
    link(blur.outputs['Value'],point.inputs['Value'])
    mix=node('ShaderNodeMix',610,25);mix.data_type='VECTOR'
    link(mask_node.outputs['Attribute'],mix.inputs[0])
    link(normal.outputs['Normal'],mix.inputs[4]);link(point.outputs['Value'],mix.inputs[5])
    normalize=node('ShaderNodeVectorMath',800,20);normalize.operation='NORMALIZE'
    link(mix.outputs[1],normalize.inputs[0])
    setter=node('GeometryNodeSetMeshNormal',1000,240);setter.mode='FREE';setter.domain='CORNER'
    link(src.outputs[0],setter.inputs['Mesh']);link(normalize.outputs[0],setter.inputs['Custom Normal'])
    end=node('NodeGroupOutput',1210,240);link(setter.outputs[0],end.inputs[0])
    modifier=ob.modifiers.new('腋下 · 随姿势平滑法线','NODES')
    modifier.node_group=group


def set_shape(ob,corners,positions,value):
    ob.data.vertices.foreach_set('co',positions[value].ravel())
    ob.data.update()
    source=data['sculpt_normals' if value else 'previous_normals']
    normals=source[corners.ravel()][:,[0,2,1]]
    ob.data.normals_split_custom_set(normals.tolist())
    ob.data.update()


def review_section(ob,corners,positions,value):
    set_shape(ob,corners,positions,value)
    bpy.context.view_layer.update()
    evaluated=ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh=evaluated.to_mesh()
    # Bisect changes loop indices. Carry evaluated shading normals in
    # object space so a new edge at the section cannot rotate them.
    indices=np.empty(len(mesh.loops),np.int32);mesh.loops.foreach_get('vertex_index',indices)
    cn=np.empty((len(indices),3),np.float32);mesh.corner_normals.foreach_get('vector',cn.ravel())
    vn=np.zeros((len(mesh.vertices),3),np.float32)
    np.add.at(vn,indices,cn)
    vn/=np.maximum(np.linalg.norm(vn,axis=1,keepdims=True),1e-8)
    mesh.attributes.new('section_normal','FLOAT_VECTOR','POINT').data.foreach_set('vector',vn.ravel())
    bm=bmesh.new();bm.from_mesh(mesh);evaluated.to_mesh_clear()
    # All four cut planes lie outside the sculpt. Both versions have the
    # same section, including planar caps, regardless of the blend value.
    planes=[((0,0,1.16),(0,0,-1)),((0,0,1.586),(0,0,1)),
            ((.257,0,1.41),(.97,0,-.24)),((-.257,0,1.41),(-.97,0,-.24))]
    for point,normal in planes:
        cut=bmesh.ops.bisect_plane(bm,geom=[*bm.verts,*bm.edges,*bm.faces],dist=1e-6,
                                   plane_co=point,plane_no=normal,clear_outer=True)
        rim=[e for e in cut['geom_cut'] if isinstance(e,bmesh.types.BMEdge) and e.is_valid and e.is_boundary]
        if rim:
            for f in bmesh.ops.holes_fill(bm,edges=rim,sides=0)['faces']:f.smooth=False
    bm.normal_update()
    out=bpy.data.meshes.new('素模审形截面')
    bm.to_mesh(out);bm.free();out.update()
    arr=np.empty((len(out.vertices),3),np.float32)
    out.attributes['section_normal'].data.foreach_get('vector',arr.ravel())
    arr/=np.linalg.norm(arr,axis=1,keepdims=True).clip(1e-8)
    vi=np.empty(len(out.loops),np.int32);out.loops.foreach_get('vertex_index',vi)
    ln=arr[vi].copy()
    for face in out.polygons:
        if not face.use_smooth:ln[face.loop_start:face.loop_start+face.loop_total]=face.normal[:]
    out.normals_split_custom_set(ln.tolist())
    out.attributes.remove(out.attributes['section_normal'])
    out.update()
    return out


def make_preview(ob,corners,positions,first):
    views=[]
    bpy.ops.object.select_all(action='DESELECT')
    # The reference is standing with relaxed arms. Use the actual shoulder
    # skinning in both proofs, then restore the editable body to its bind pose.
    rig=ob.modifiers[0].object
    pose_bones=[rig.pose.bones[n] for n in ('右腕','左腕')]
    for sign,bone in zip((-1,1),pose_bones):
        basis=bone.bone.matrix_local.to_quaternion()
        rest=(bone.bone.tail_local-bone.bone.head_local).normalized()
        target=Vector((.37*sign,-.04,-.928)).normalized()
        bone.rotation_quaternion=basis.inverted() @ rest.rotation_difference(target) @ basis
    for value,name in enumerate(('Previous','Sculpt')):
        bind_skin(ob,first,previous=value==0)
        if value==1:finish_posed_normals(ob,first)
        mesh=review_section(ob,corners,positions,value)
        mesh.materials.clear();mesh.materials.append(ob.data.materials[0])
        view=bpy.data.objects.new(name,mesh)
        bpy.context.collection.objects.link(view)
        view.select_set(True);bpy.context.view_layer.objects.active=view
        views.append(view)
    for bone in pose_bones:
        bone.rotation_quaternion=(1,0,0,0)
    bpy.context.view_layer.update()
    dest=PUBLIC/'xiaokeai-torso-base.glb'
    tmp=dest.with_name(f'.torso-{uuid4().hex}.glb')
    try:
        bpy.ops.export_scene.gltf(filepath=str(tmp),export_format='GLB',use_selection=True,
                                  export_morph=False,export_animations=False,
                                  export_skins=False,export_texcoords=False,export_attributes=False)
        tmp.replace(dest)
    finally:tmp.unlink(missing_ok=True)
    for view in views:
        mesh=view.data;bpy.data.objects.remove(view,do_unlink=True);bpy.data.meshes.remove(mesh)


def save_source(ob):
    reference=bpy.data.images.load(str(DESIGN/'xiaokeai-magnolia-strapless-concept.png'))
    reference.name='小可爱 · 抹胸正面与侧后参考'
    reference.pack()
    ob['参考原图']=reference
    bpy.context.view_layer.objects.active=ob
    ob.select_set(True)
    direction=Vector((-.28,.94,-.10))
    for area in bpy.context.screen.areas:
        if area.type=='VIEW_3D':
            space=area.spaces.active
            space.overlay.show_overlays=False
            space.shading.type='SOLID';space.shading.light='STUDIO'
            space.shading.color_type='MATERIAL'
            space.region_3d.view_rotation=direction.to_track_quat('-Z','Y')
            space.region_3d.view_distance=.78
            space.region_3d.view_location=(0,-.012,1.39)
            space.region_3d.view_perspective='ORTHO'
    bpy.data.orphans_purge(do_recursive=True)
    dest=DESIGN/'xiaokeai-torso-base.blend'
    tmp=dest.with_name(f'.torso-{uuid4().hex}.blend')
    try:
        bpy.ops.wm.save_as_mainfile(filepath=str(tmp),compress=True,copy=True)
        tmp.replace(dest)
    finally:tmp.unlink(missing_ok=True)


body,corners,positions,first=make_cage()
make_preview(body,corners,positions,first)
body.shape_key_add(name=KEY)
body.shape_key_add(name='上一版轮廓',from_mix=False).data.foreach_set('co',positions[0].ravel())
save_source(body)
