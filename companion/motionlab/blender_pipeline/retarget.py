from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

from .config import BONE_MAP, REST_CHILDREN, mixamo_name


def natural_hand(source_name: str) -> bool:
    return source_name.endswith("Hand") or "Hand" in source_name


@dataclass(frozen=True)
class RestBone:
    matrix: Matrix
    position: Vector
    rotation: Quaternion


def world_rest(obj, bone) -> RestBone:
    matrix = obj.matrix_world @ bone.matrix_local
    return RestBone(matrix, matrix.translation.copy(), matrix.to_quaternion())


def ordered_bones(armature):
    result = []
    def visit(bone):
        result.append(bone)
        for child in bone.children:
            visit(child)
    for bone in armature.data.bones:
        if bone.parent is None:
            visit(bone)
    return result


def reference_frame(direction: Vector, hint: Vector) -> Matrix:
    y = direction.normalized()
    x = hint - y * hint.dot(y)
    if x.length < 1e-6:
        fallback = Vector((1, 0, 0)) if abs(y.x) < 0.9 else Vector((0, 1, 0))
        x = fallback - y * fallback.dot(y)
    x.normalize()
    z = x.cross(y).normalized()
    return Matrix((x, y, z)).transposed()


def generic_hint(direction: Vector) -> Vector:
    forward = Vector((0, 1, 0))
    return forward if abs(direction.normalized().dot(forward)) < 0.95 else Vector((1, 0, 0))


class MixamoToMmd:
    def __init__(self, source, target):
        self.source = source
        self.target = target
        bpy.context.view_layer.update()
        self.source_rest = {mixamo_name(b.name): world_rest(source, b) for b in source.data.bones}
        self.source_rest.pop("", None)
        self.target_rest = {b.name: world_rest(target, b) for b in target.data.bones}
        self.source_by_name = {mixamo_name(b.name): b for b in source.data.bones}
        self.source_by_name.pop("", None)
        self.pairs = self._build_pairs()
        if "Hips" not in self.pairs:
            raise ValueError("目标模型缺少 センター，无法转换髋部")
        if len(self.pairs) < 10:
            raise ValueError(f"只映射到 {len(self.pairs)} 根骨骼，目标模型不是兼容的 MMD 人形骨架")
        self.alignments = self._build_alignments()
        self.leg_scale = self._leg_scale()

    def _build_pairs(self):
        pairs = dict(BONE_MAP)
        target_bones = self.target.data.bones
        if "上半身2" in target_bones:
            pairs["Spine1"] = "上半身"
            pairs["Spine2"] = "上半身2"
        else:
            pairs["Spine"] = "上半身"
        return {
            source: target for source, target in pairs.items()
            if source in self.source_rest and target in self.target_rest
        }

    def _build_alignments(self):
        alignments = {}
        for source, target in self.pairs.items():
            if source not in REST_CHILDREN:
                continue
            source_child, target_child = REST_CHILDREN[source]
            if source_child not in self.source_rest or target_child not in self.target_rest:
                continue
            source_direction = self.source_rest[source_child].position - self.source_rest[source].position
            target_direction = self.target_rest[target_child].position - self.target_rest[target].position
            if source_direction.length < 1e-6 or target_direction.length < 1e-6:
                continue
            source_hint = generic_hint(source_direction)
            target_hint = generic_hint(target_direction)
            source_frame = reference_frame(source_direction, source_hint)
            target_frame = reference_frame(target_direction, target_hint)
            alignments[source] = source_frame @ target_frame.inverted()
        return alignments

    def _leg_scale(self):
        source_names = ("LeftUpLeg", "LeftFoot")
        target_names = ("左足", "左足首")
        if all(name in self.source_rest for name in source_names) and all(name in self.target_rest for name in target_names):
            source_length = (self.source_rest[source_names[1]].position - self.source_rest[source_names[0]].position).length
            target_length = (self.target_rest[target_names[1]].position - self.target_rest[target_names[0]].position).length
            if source_length > 1e-6 and target_length > 1e-6:
                return target_length / source_length
        return 1.0

    def convert(self, in_place=True, progress=None):
        action = self.source.animation_data.action if self.source.animation_data else None
        if action is None:
            raise ValueError("FBX 中没有动画 Action")
        start, end = (int(round(value)) for value in action.frame_range)
        if end < start:
            raise ValueError(f"动画帧范围无效：{start}–{end}")

        scene = bpy.context.scene
        scene.render.fps = 30
        scene.frame_start = start
        scene.frame_end = end
        self.target.animation_data_create()
        self.target.animation_data.action = bpy.data.actions.new(f"{Path(action.name).stem}_MMD")
        self.target.animation_data.action.use_fake_user = True
        for pose_bone in self.target.pose.bones:
            pose_bone.rotation_mode = "QUATERNION"

        target_bones = ordered_bones(self.target)
        target_by_mixamo = {target: source for source, target in self.pairs.items()}
        hips_target = self.pairs["Hips"]
        source_hips_rest = self.source_rest["Hips"]
        target_hips_rest = self.target_rest[hips_target]
        target_world = self.target.matrix_world.copy()
        source_world = self.source.matrix_world.copy()

        for frame in range(start, end + 1):
            scene.frame_set(frame)
            source_pose = {
                name: source_world @ self.source.pose.bones[self.source_by_name[name].name].matrix
                for name in self.source_by_name
            }
            desired = {}
            for bone in target_bones:
                rest = self.target_rest[bone.name]
                parent_rest = self.target_rest[bone.parent.name].matrix if bone.parent else target_world
                parent_desired = desired[bone.parent.name] if bone.parent else parent_rest
                rest_local = parent_rest.inverted() @ rest.matrix
                position = (parent_desired @ rest_local).translation.copy()

                source_name = target_by_mixamo.get(bone.name)
                if source_name and not natural_hand(source_name):
                    pose = source_pose[source_name]
                    source_rest = self.source_rest[source_name]
                    source_delta = pose.to_quaternion() @ source_rest.rotation.inverted()
                    alignment = self.alignments.get(source_name, Matrix.Identity(3)).to_quaternion()
                    rotation = source_delta @ alignment @ rest.rotation
                    if source_name == "Hips":
                        displacement = pose.translation - source_hips_rest.position
                        displacement *= self.leg_scale
                        if in_place:
                            displacement.x = 0
                            displacement.y = 0
                        position = target_hips_rest.position + displacement
                    matrix = rotation.to_matrix().to_4x4()
                    matrix.translation = position
                    desired_pose = matrix
                else:
                    desired_pose = parent_desired @ rest_local

                local_pose = parent_desired.inverted() @ desired_pose
                basis = rest_local.inverted() @ local_pose
                pose_bone = self.target.pose.bones[bone.name]
                pose_bone.matrix_basis = basis
                pose_bone.keyframe_insert("rotation_quaternion", frame=frame, group=bone.name)
                if bone.name == hips_target:
                    pose_bone.keyframe_insert("location", frame=frame, group=bone.name)
                desired[bone.name] = desired_pose
            if progress and (frame == start or frame == end or (frame - start) % 30 == 0):
                progress(frame - start + 1, end - start + 1)

        bpy.context.view_layer.objects.active = self.target
        self.target.select_set(True)
        return {
            "frame_start": start,
            "frame_end": end,
            "frames": end - start + 1,
            "mapped_bones": len(self.pairs),
            "leg_scale": self.leg_scale,
        }


def import_pmx(path: Path):
    bpy.ops.mmd_tools.import_model(
        filepath=str(path), types={"ARMATURE"}, scale=0.08, rename_bones=False,
    )
    return next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")


def import_fbx(path: Path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=True)
    armatures = [obj for obj in set(bpy.context.scene.objects) - before if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise ValueError(f"{path.name} 应包含一个 Mixamo Armature，实际为 {len(armatures)}")
    return armatures[0]


def convert_file(source_path: Path, model_path: Path, output_path: Path, in_place=True, progress=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    target = import_pmx(model_path)
    source = import_fbx(source_path)
    info = MixamoToMmd(source, target).convert(in_place=in_place, progress=progress)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.mmd_tools.export_vmd(
        filepath=str(output_path), scale=12.5,
        use_pose_mode=False, use_frame_range=True, preserve_curves=False,
    )
    if not output_path.is_file() or not output_path.read_bytes().startswith(b"Vocaloid Motion Data"):
        raise RuntimeError(f"VMD 导出失败：{output_path}")
    return info
